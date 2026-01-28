from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class ClientCredential:
    username: str
    password: str


def load_credentials(path: Path) -> list[ClientCredential]:
    if not path.exists():
        return []
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    clients = data.get("client", [])
    credentials: list[ClientCredential] = []
    for client in clients:
        username = client.get("username")
        password = client.get("password")
        if not username or not password:
            raise ValueError("Each client must have username and password")
        credentials.append(ClientCredential(username=username, password=password))
    return credentials


def save_credentials(path: Path, clients: list[ClientCredential]) -> None:
    lines: list[str] = []
    for client in clients:
        lines.append("[[client]]")
        lines.append(f"username = \"{_escape(client.username)}\"")
        lines.append(f"password = \"{_escape(client.password)}\"")
        lines.append("")
    content = "\n".join(lines).rstrip() + "\n" if lines else ""
    path.write_text(content, encoding="utf-8")


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\"", "\\\"")
