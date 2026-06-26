from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import secrets
import subprocess
from urllib.parse import quote

from trusttunel_bot.config import BotConfig
from trusttunel_bot.service import ServiceActionResult, restart_service


@dataclass(frozen=True)
class HevSocks5User:
    username: str
    password: str
    mark: str


def load_hev_auth_file(path: Path) -> list[HevSocks5User]:
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    users: list[HevSocks5User] = []
    seen: set[str] = set()
    for line_no, line in enumerate(raw.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) != 3:
            raise ValueError(f"Invalid hev-socks5 auth line {line_no}: expected USERNAME PASSWORD MARK")
        user = HevSocks5User(username=parts[0], password=parts[1], mark=parts[2])
        if user.username in seen:
            raise ValueError(f"Duplicate hev-socks5 username: {user.username}")
        seen.add(user.username)
        users.append(user)
    return users


def save_hev_auth_file(path: Path, users: list[HevSocks5User]) -> None:
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(f"{user.username} {user.password} {user.mark}\n" for user in users)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    try:
        temp_path.write_text(content, encoding="utf-8")
        temp_path.chmod(0o600)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def get_hev_socks5_user(config: BotConfig, username: str) -> HevSocks5User | None:
    path = _require_auth_file(config)
    return next((user for user in load_hev_auth_file(path) if user.username == username), None)


def create_hev_socks5_user(
    config: BotConfig,
    username: str,
    password: str | None = None,
) -> HevSocks5User:
    path = _require_auth_file(config)
    users = load_hev_auth_file(path)
    existing = next((user for user in users if user.username == username), None)
    if existing:
        return existing
    user = HevSocks5User(
        username=username,
        password=password or secrets.token_urlsafe(16),
        mark=_next_mark(users, config.hev_socks5_mark_start),
    )
    save_hev_auth_file(path, [*users, user])
    result = reload_hev_socks5(config)
    if not result.ok:
        raise RuntimeError(f"Failed to reload hev-socks5-server: {result.message or 'unknown error'}")
    return user


def ensure_hev_socks5_user(config: BotConfig, username: str) -> HevSocks5User:
    existing = get_hev_socks5_user(config, username)
    if existing:
        return existing
    return create_hev_socks5_user(config, username)


def delete_hev_socks5_user(config: BotConfig, username: str) -> bool:
    path = _require_auth_file(config)
    users = load_hev_auth_file(path)
    remaining = [user for user in users if user.username != username]
    if len(remaining) == len(users):
        return False
    save_hev_auth_file(path, remaining)
    return True


def format_hev_socks5_access(config: BotConfig, user: HevSocks5User) -> str:
    if not config.hev_socks5_public_host or not config.hev_socks5_public_port:
        raise ValueError("hev-socks5 public host/port must be configured")
    scheme = config.hev_socks5_scheme or "socks5h"
    username = quote(user.username, safe="")
    password = quote(user.password, safe="")
    uri = f"{scheme}://{username}:{password}@{config.hev_socks5_public_host}:{config.hev_socks5_public_port}"
    return (
        "SOCKS5 доступ\n\n"
        f"Host: {config.hev_socks5_public_host}\n"
        f"Port: {config.hev_socks5_public_port}\n"
        f"Username: {user.username}\n"
        f"Password: {user.password}\n\n"
        "URI:\n"
        f"{uri}"
    )


def reload_hev_socks5(config: BotConfig) -> ServiceActionResult:
    completed = subprocess.run(
        ["killall", "-SIGUSR1", config.hev_socks5_service_name],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        return ServiceActionResult(ok=True, used_hot_reload=True)
    restart_result = restart_service(config.hev_socks5_service_name)
    if restart_result.ok:
        details = completed.stderr.strip() or completed.stdout.strip() or "SIGUSR1 failed"
        return ServiceActionResult(ok=True, used_hot_reload=False, message=f"{details}; restarted service")
    details = completed.stderr.strip() or completed.stdout.strip() or "SIGUSR1 failed"
    return ServiceActionResult(
        ok=False,
        used_hot_reload=False,
        message=f"{details}; restart failed: {restart_result.message}",
    )


def _next_mark(users: list[HevSocks5User], start: int) -> str:
    used: set[int] = set()
    for user in users:
        try:
            used.add(int(user.mark, 16))
        except ValueError:
            continue
    mark = start
    while mark in used:
        mark += 1
    return f"{mark:x}"


def _require_auth_file(config: BotConfig) -> Path:
    if config.hev_socks5_auth_file is None:
        raise ValueError("hev_socks5_auth_file is required")
    return config.hev_socks5_auth_file
