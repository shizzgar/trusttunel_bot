from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class BotConfig:
    credentials_file: Path
    telegram_token: str | None = None
    admin_ids: list[int] | None = None
    reload_endpoint: str | None = None
    vpn_config: Path | None = None
    hosts_config: Path | None = None
    endpoint_public_address: str | None = None
    dns_upstreams: list[str] | None = None
    rules_file: Path | None = None
    endpoint_command_timeout_s: int = 10


def load_config(path: Path) -> BotConfig:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    credentials_file = data.get("credentials_file")
    if not credentials_file:
        raise ValueError("credentials_file is required in bot config")
    telegram_token = data.get("telegram_token")
    admin_ids = _ensure_int_list(data.get("admin_ids"))
    reload_endpoint = data.get("reload_endpoint")
    vpn_config = data.get("vpn_config")
    hosts_config = data.get("hosts_config")
    endpoint_public_address = data.get("endpoint_public_address")
    dns_upstreams = _ensure_list(data.get("dns_upstreams"))
    rules_file = data.get("rules_file")
    endpoint_command_timeout_s = data.get("endpoint_command_timeout_s", 10)
    return BotConfig(
        credentials_file=Path(credentials_file),
        telegram_token=str(telegram_token) if telegram_token else None,
        admin_ids=admin_ids,
        reload_endpoint=reload_endpoint,
        vpn_config=Path(vpn_config) if vpn_config else None,
        hosts_config=Path(hosts_config) if hosts_config else None,
        endpoint_public_address=endpoint_public_address,
        dns_upstreams=dns_upstreams,
        rules_file=Path(rules_file) if rules_file else None,
        endpoint_command_timeout_s=int(endpoint_command_timeout_s),
    )


def _ensure_list(values) -> list[str] | None:
    if values in (None, ""):
        return None
    if isinstance(values, list):
        return [str(value) for value in values]
    return [str(values)]


def _ensure_int_list(values) -> list[int] | None:
    if values in (None, ""):
        return None
    if isinstance(values, list):
        return [int(value) for value in values]
    return [int(values)]
