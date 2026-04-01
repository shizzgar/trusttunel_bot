from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from trusttunel_bot.access_management import ensure_full_access
from trusttunel_bot.cli_config import generate_client_config_from_bot_config
from trusttunel_bot.config import BotConfig
from trusttunel_bot.endpoint import (
    build_connection_profile,
    format_connection_profile,
    generate_endpoint_config,
)
from trusttunel_bot.telemt_api import ensure_telemt_user


@dataclass(frozen=True)
class UserBundle:
    username: str
    tt_cli_config_path: Path | None
    tt_mobile_profile_text: str | None
    telemt_tls_links: list[str]
    telemt_classic_links: list[str]
    telemt_secure_links: list[str]


def build_user_bundle(config: BotConfig, username: str) -> UserBundle:
    ensure_result = ensure_full_access(config, username)
    if ensure_result is None:
        raise ValueError(f"User '{username}' not found in TrustTunnel credentials")

    endpoint = generate_endpoint_config(config, username=username)
    client_config = generate_client_config_from_bot_config(
        config,
        endpoint_config_path=endpoint.output_path,
    )
    profile = build_connection_profile(endpoint.output_path)
    dns_override = ", ".join(config.dns_upstreams) if config.dns_upstreams else None
    mobile_profile = format_connection_profile(profile, dns_override=dns_override)

    tls_links: list[str] = []
    classic_links: list[str] = []
    secure_links: list[str] = []
    if config.telemt_enabled:
        telemt_user = ensure_telemt_user(config, username)
        tls_links = telemt_user.links.tls
        classic_links = telemt_user.links.classic
        secure_links = telemt_user.links.secure

    return UserBundle(
        username=username,
        tt_cli_config_path=client_config.output_path,
        tt_mobile_profile_text=mobile_profile,
        telemt_tls_links=tls_links,
        telemt_classic_links=classic_links,
        telemt_secure_links=secure_links,
    )
