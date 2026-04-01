from __future__ import annotations

from dataclasses import dataclass
import secrets

from trusttunel_bot.config import BotConfig
from trusttunel_bot.credentials import load_credentials
from trusttunel_bot.telemt_api import (
    TelemtAPIError,
    create_telemt_user,
    delete_telemt_user,
    ensure_telemt_user,
    get_telemt_user,
)
from trusttunel_bot.user_management import add_user, delete_user


@dataclass(frozen=True)
class ProvisionResult:
    username: str
    trusttunnel_password: str | None
    telemt_secret: str | None
    trusttunnel_updated: bool
    telemt_updated: bool


def add_access(config: BotConfig, username: str, password: str | None = None) -> ProvisionResult:
    resolved_password = password or _generate_tt_password()
    add_user(config, username=username, password=resolved_password)

    telemt_secret: str | None = None
    telemt_updated = False
    if config.telemt_enabled and config.telemt_sync_on_add:
        telemt_user = ensure_telemt_user(config, username)
        telemt_secret = telemt_user.secret
        telemt_updated = True

    return ProvisionResult(
        username=username,
        trusttunnel_password=resolved_password,
        telemt_secret=telemt_secret,
        trusttunnel_updated=True,
        telemt_updated=telemt_updated,
    )


def _generate_tt_password() -> str:
    return secrets.token_urlsafe(12)


def delete_access(config: BotConfig, username: str) -> None:
    delete_user(config, username=username)
    if config.telemt_enabled:
        try:
            delete_telemt_user(config, username)
        except TelemtAPIError:
            # TT удалён, telemt ошибка должна быть видна вызывающему коду.
            raise


def ensure_full_access(config: BotConfig, username: str) -> ProvisionResult | None:
    credentials = load_credentials(config.credentials_file)
    tt_user = next((item for item in credentials if item.username == username), None)
    if not tt_user:
        return None

    telemt_secret: str | None = None
    telemt_updated = False
    if config.telemt_enabled and config.telemt_lazy_create:
        telemt_user = get_telemt_user(config, username)
        if telemt_user is None:
            telemt_user = create_telemt_user(config, username)
            telemt_updated = True
        telemt_secret = telemt_user.secret

    return ProvisionResult(
        username=username,
        trusttunnel_password=tt_user.password,
        telemt_secret=telemt_secret,
        trusttunnel_updated=False,
        telemt_updated=telemt_updated,
    )


def sync_tt_users_to_telemt(config: BotConfig) -> list[str]:
    if not config.telemt_enabled:
        return []
    created: list[str] = []
    credentials = load_credentials(config.credentials_file)
    for item in credentials:
        if get_telemt_user(config, item.username) is None:
            create_telemt_user(config, item.username)
            created.append(item.username)
    return created
