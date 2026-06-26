from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Literal

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - py<3.11 fallback
    import tomli as tomllib

from trusttunel_bot.access_management import ensure_full_access
from trusttunel_bot.cli_config import generate_client_config_from_bot_config
from trusttunel_bot.config import BotConfig
from trusttunel_bot.endpoint import (
    build_connection_profile,
    format_connection_profile,
    generate_endpoint_config,
    generate_endpoint_deeplink,
)
from trusttunel_bot.hev_socks5 import format_hev_socks5_access, ensure_hev_socks5_user
from trusttunel_bot.telemt_api import ensure_telemt_user


AccessKind = Literal["trusttunnel", "telemt", "socks5", "all"]


@dataclass(frozen=True)
class UserBundle:
    username: str
    tt_cli_config_path: Path | None
    tt_mobile_profile_text: str | None
    telemt_tls_links: list[str]
    telemt_classic_links: list[str]
    telemt_secure_links: list[str]
    socks5_access_text: str | None = None


def build_user_bundle(config: BotConfig, username: str, kind: AccessKind = "all") -> UserBundle:
    build_tt = kind in {"trusttunnel", "all"}
    build_telemt = kind in {"telemt", "all"}
    build_socks5 = kind in {"socks5", "all"}

    ensure_result = ensure_full_access(
        config,
        username,
        ensure_telemt=build_telemt,
        ensure_socks5=build_socks5,
    )
    if ensure_result is None:
        raise ValueError(f"User '{username}' not found in TrustTunnel credentials")

    endpoint = generate_endpoint_config(config, username=username) if build_tt else None
    try:
        deeplink = generate_endpoint_deeplink(config, username=username) if build_tt else None
    except RuntimeError:
        deeplink = None
    tt_cli_config_path: Path | None = None
    if build_tt and endpoint is not None:
        try:
            client_config = generate_client_config_from_bot_config(
                config,
                endpoint_config_path=endpoint.output_path,
            )
            tt_cli_config_path = client_config.output_path
        except (RuntimeError, ValueError):
            tt_cli_config_path = _build_tt_uri_fallback_file(
                endpoint.output_path,
                username=username,
                deeplink=deeplink,
            )

    mobile_profile = (
        _build_combined_mobile_text(config, endpoint.output_path, deeplink=deeplink)
        if build_tt and endpoint is not None
        else None
    )

    tls_links: list[str] = []
    classic_links: list[str] = []
    secure_links: list[str] = []
    if build_telemt and config.telemt_enabled:
        telemt_user = ensure_telemt_user(config, username)
        tls_links = telemt_user.links.tls
        classic_links = telemt_user.links.classic
        secure_links = telemt_user.links.secure

    socks5_access_text = None
    if build_socks5 and config.hev_socks5_enabled:
        socks5_access_text = format_hev_socks5_access(config, ensure_hev_socks5_user(config, username))

    return UserBundle(
        username=username,
        tt_cli_config_path=tt_cli_config_path,
        tt_mobile_profile_text=mobile_profile,
        telemt_tls_links=tls_links,
        telemt_classic_links=classic_links,
        telemt_secure_links=secure_links,
        socks5_access_text=socks5_access_text,
    )


def _build_tt_uri_fallback_text(endpoint_config_path: Path) -> str:
    tt_uri, qr_url = _read_tt_uri_fields(endpoint_config_path)
    if not tt_uri:
        raise ValueError("Could not build TT fallback profile: missing tt_uri")
    lines = [
        "TrustTunnel использует новый URI-формат подключения.",
        "Скопируйте ссылку ниже в клиент:",
        tt_uri,
    ]
    if qr_url:
        lines.append(f"QR page: {qr_url}")
    return "\n".join(lines)


def _build_combined_mobile_text(
    config: BotConfig,
    endpoint_config_path: Path,
    deeplink: str | None = None,
) -> str:
    old_format_text: str | None = None
    try:
        profile = build_connection_profile(endpoint_config_path)
        dns_override = ", ".join(config.dns_upstreams) if config.dns_upstreams else None
        old_format_text = format_connection_profile(profile, dns_override=dns_override)
    except (RuntimeError, ValueError):
        old_format_text = (
            "Профиль старого формата (hostname/address/username/password) "
            "недоступен для этого пользователя."
        )

    tt_uri, qr_url = _read_tt_uri_fields(endpoint_config_path)
    tt_uri = tt_uri or deeplink
    if not tt_uri:
        return old_format_text

    lines = [
        "Новый формат (deeplink):",
        tt_uri,
    ]
    if qr_url:
        lines.append(f"QR page: {qr_url}")
    new_format_text = "\n".join(lines)
    return f"{old_format_text}\n\n{new_format_text}"


def _build_tt_uri_fallback_file(
    endpoint_config_path: Path,
    username: str,
    deeplink: str | None = None,
) -> Path | None:
    tt_uri, qr_url = _read_tt_uri_fields(endpoint_config_path)
    tt_uri = tt_uri or deeplink
    if not tt_uri:
        return None
    out_path = Path(tempfile.gettempdir()) / f"{username}.trusttunnel-uri.txt"
    lines = [tt_uri]
    if qr_url:
        lines.append(qr_url)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def _read_tt_uri_fields(endpoint_config_path: Path) -> tuple[str | None, str | None]:
    data = tomllib.loads(endpoint_config_path.read_text(encoding="utf-8"))
    tt_uri = data.get("tt_uri")
    qr_url = data.get("qr_url")
    return (str(tt_uri) if tt_uri else None, str(qr_url) if qr_url else None)
