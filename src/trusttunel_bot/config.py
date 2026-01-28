from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class BotConfig:
    credentials_file: Path
    reload_endpoint: str | None = None
    vpn_config: Path | None = None
    hosts_config: Path | None = None
    endpoint_public_address: str | None = None
    endpoint_command_timeout_s: int = 10


def load_config(path: Path) -> BotConfig:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    credentials_file = data.get("credentials_file")
    if not credentials_file:
        raise ValueError("credentials_file is required in bot config")
    reload_endpoint = data.get("reload_endpoint")
    vpn_config = data.get("vpn_config")
    hosts_config = data.get("hosts_config")
    endpoint_public_address = data.get("endpoint_public_address")
    endpoint_command_timeout_s = data.get("endpoint_command_timeout_s", 10)
    return BotConfig(
        credentials_file=Path(credentials_file),
        reload_endpoint=reload_endpoint,
        vpn_config=Path(vpn_config) if vpn_config else None,
        hosts_config=Path(hosts_config) if hosts_config else None,
        endpoint_public_address=endpoint_public_address,
        endpoint_command_timeout_s=int(endpoint_command_timeout_s),
    )
