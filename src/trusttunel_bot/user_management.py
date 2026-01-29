from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from trusttunel_bot.config import BotConfig
from trusttunel_bot.credentials import ClientCredential, load_credentials, save_credentials
from trusttunel_bot.service import reload_credentials


@dataclass(frozen=True)
class UserChangeResult:
    updated_path: Path
    used_hot_reload: bool


def list_users(config: BotConfig) -> list[str]:
    credentials = load_credentials(config.credentials_file)
    return [client.username for client in credentials]


def add_user(config: BotConfig, username: str, password: str) -> UserChangeResult:
    credentials = load_credentials(config.credentials_file)
    if any(client.username == username for client in credentials):
        raise ValueError(f"User '{username}' already exists")
    credentials.append(ClientCredential(username=username, password=password))
    save_credentials(config.credentials_file, credentials)
    result = reload_credentials(config.reload_endpoint)
    return UserChangeResult(updated_path=config.credentials_file, used_hot_reload=result.used_hot_reload)


def delete_user(config: BotConfig, username: str) -> UserChangeResult:
    credentials = load_credentials(config.credentials_file)
    remaining = [client for client in credentials if client.username != username]
    if len(remaining) == len(credentials):
        raise ValueError(f"User '{username}' not found")
    save_credentials(config.credentials_file, remaining)
    result = reload_credentials(config.reload_endpoint)
    return UserChangeResult(updated_path=config.credentials_file, used_hot_reload=result.used_hot_reload)
