from __future__ import annotations

from dataclasses import dataclass
import logging
import secrets

from trusttunel_bot.config import BotConfig
from trusttunel_bot.credentials import load_credentials
from trusttunel_bot.hev_socks5 import (
    create_hev_socks5_user,
    delete_hev_socks5_user,
    ensure_hev_socks5_user,
    get_hev_socks5_user,
    reload_hev_socks5,
)
from trusttunel_bot.telemt_api import (
    TelemtAPIError,
    create_telemt_user,
    delete_telemt_user,
    ensure_telemt_user,
    get_telemt_user,
)
from trusttunel_bot.user_management import add_user, delete_user

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProvisionResult:
    username: str
    trusttunnel_password: str | None
    telemt_secret: str | None
    socks5_password: str | None
    socks5_mark: str | None
    trusttunnel_updated: bool
    telemt_updated: bool
    socks5_updated: bool


def add_access(config: BotConfig, username: str, password: str | None = None) -> ProvisionResult:
    resolved_password = password or _generate_tt_password()
    add_user(config, username=username, password=resolved_password)

    telemt_secret: str | None = None
    telemt_updated = False
    if config.telemt_enabled and config.telemt_sync_on_add:
        telemt_user = ensure_telemt_user(config, username)
        telemt_secret = telemt_user.secret
        telemt_updated = True

    socks5_password: str | None = None
    socks5_mark: str | None = None
    socks5_updated = False
    if config.hev_socks5_enabled and config.hev_socks5_sync_on_add:
        before = get_hev_socks5_user(config, username)
        socks5_user = create_hev_socks5_user(config, username) if before is None else before
        socks5_password = socks5_user.password
        socks5_mark = socks5_user.mark
        socks5_updated = before is None

    return ProvisionResult(
        username=username,
        trusttunnel_password=resolved_password,
        telemt_secret=telemt_secret,
        socks5_password=socks5_password,
        socks5_mark=socks5_mark,
        trusttunnel_updated=True,
        telemt_updated=telemt_updated,
        socks5_updated=socks5_updated,
    )


def _generate_tt_password() -> str:
    return secrets.token_urlsafe(12)


def delete_access(config: BotConfig, username: str) -> None:
    errors: list[str] = []
    try:
        delete_user(config, username=username)
    except (ValueError, RuntimeError) as exc:
        errors.append(f"TrustTunnel: {exc}")

    if config.telemt_enabled:
        try:
            delete_telemt_user(config, username)
        except TelemtAPIError as exc:
            errors.append(f"telemt: {exc}")

    if config.hev_socks5_enabled:
        try:
            changed = delete_hev_socks5_user(config, username)
            if changed:
                result = reload_hev_socks5(config)
                if not result.ok:
                    errors.append(f"SOCKS5 reload: {result.message or 'unknown error'}")
        except (ValueError, RuntimeError) as exc:
            errors.append(f"SOCKS5: {exc}")

    if errors:
        raise RuntimeError("; ".join(errors))


def ensure_full_access(
    config: BotConfig,
    username: str,
    *,
    ensure_telemt: bool = True,
    ensure_socks5: bool = True,
) -> ProvisionResult | None:
    credentials = load_credentials(config.credentials_file)
    tt_user = next((item for item in credentials if item.username == username), None)
    if not tt_user:
        return None

    telemt_secret: str | None = None
    telemt_updated = False
    if ensure_telemt and config.telemt_enabled and config.telemt_lazy_create:
        telemt_user = get_telemt_user(config, username)
        if telemt_user is None:
            telemt_user = create_telemt_user(config, username)
            telemt_updated = True
        telemt_secret = telemt_user.secret

    socks5_password: str | None = None
    socks5_mark: str | None = None
    socks5_updated = False
    if ensure_socks5 and config.hev_socks5_enabled and config.hev_socks5_lazy_create:
        before = get_hev_socks5_user(config, username)
        socks5_user = ensure_hev_socks5_user(config, username)
        socks5_password = socks5_user.password
        socks5_mark = socks5_user.mark
        socks5_updated = before is None

    return ProvisionResult(
        username=username,
        trusttunnel_password=tt_user.password,
        telemt_secret=telemt_secret,
        socks5_password=socks5_password,
        socks5_mark=socks5_mark,
        trusttunnel_updated=False,
        telemt_updated=telemt_updated,
        socks5_updated=socks5_updated,
    )


def sync_tt_users_to_telemt(config: BotConfig) -> list[str]:
    if not config.telemt_enabled:
        return []
    created: list[str] = []
    credentials = load_credentials(config.credentials_file)
    for item in credentials:
        try:
            if get_telemt_user(config, item.username) is None:
                create_telemt_user(config, item.username)
                created.append(item.username)
        except Exception:
            LOGGER.exception("Failed syncing username=%s to telemt", item.username)
            raise
    return created
