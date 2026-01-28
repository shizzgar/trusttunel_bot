from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class BotConfig:
    credentials_file: Path
    reload_endpoint: str | None = None


def load_config(path: Path) -> BotConfig:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    credentials_file = data.get("credentials_file")
    if not credentials_file:
        raise ValueError("credentials_file is required in bot config")
    reload_endpoint = data.get("reload_endpoint")
    return BotConfig(credentials_file=Path(credentials_file), reload_endpoint=reload_endpoint)
