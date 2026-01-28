from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import tempfile
import tomllib

from trusttunel_bot.config import BotConfig


@dataclass(frozen=True)
class EndpointConfigResult:
    output_path: Path
    content: str


@dataclass(frozen=True)
class ConnectionProfile:
    server_name: str
    address: str
    hostname: str
    username: str
    password: str
    protocol: str
    dns: str
    self_signed: bool


def generate_endpoint_config(
    config: BotConfig,
    username: str,
    output_path: Path | None = None,
) -> EndpointConfigResult:
    vpn_config, hosts_config, endpoint_address = _ensure_endpoint_settings(config)
    result = _run_command_safely(
        [
            "trusttunnel_endpoint",
            str(vpn_config),
            str(hosts_config),
            "-c",
            username,
            "-a",
            endpoint_address,
        ],
        timeout_s=config.endpoint_command_timeout_s,
    )
    endpoint_path = output_path or Path(tempfile.gettempdir()) / f"{username}.endpoint.toml"
    endpoint_path.write_text(result.stdout, encoding="utf-8")
    return EndpointConfigResult(output_path=endpoint_path, content=result.stdout)


def build_connection_profile(
    endpoint_config_path: Path,
    server_name: str | None = None,
) -> ConnectionProfile:
    data = tomllib.loads(endpoint_config_path.read_text(encoding="utf-8"))
    hostname = _get_value(data, "hostname")
    addresses = _get_value(data, "addresses")
    username = _get_value(data, "username")
    password = _get_value(data, "password")
    protocol = _get_value(data, "protocol")
    dns = _get_value(data, "dns", required=False)
    missing = [
        name
        for name, value in {
            "hostname": hostname,
            "addresses": addresses,
            "username": username,
            "password": password,
            "protocol": protocol,
        }.items()
        if value in (None, "", [])
    ]
    if missing:
        raise ValueError(
            "Endpoint config is missing required fields: " + ", ".join(sorted(missing))
        )
    address = _pick_address(addresses)
    resolved_server_name = server_name or f"{hostname}-server"
    resolved_protocol = str(protocol).lower()
    resolved_dns = _format_dns(dns)
    self_signed = _is_self_signed(data)
    return ConnectionProfile(
        server_name=str(resolved_server_name),
        address=address,
        hostname=str(hostname),
        username=str(username),
        password=str(password),
        protocol=resolved_protocol,
        dns=resolved_dns,
        self_signed=self_signed,
    )


def format_connection_profile(profile: ConnectionProfile) -> str:
    lines = [
        "Профиль подключения:",
        f"Server name: {profile.server_name}",
        f"Address: {profile.address}",
        f"Hostname: {profile.hostname}",
        f"Username/Password: {profile.username}/{profile.password}",
        f"Protocol: {profile.protocol}",
        f"DNS: {profile.dns}",
    ]
    if profile.self_signed:
        lines.append("⚠️ Сертификат self-signed — Flutter-клиент не подключится.")
    return "\n".join(lines)


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    stderr: str
    exit_code: int


def _run_command_safely(args: list[str], timeout_s: int) -> CommandResult:
    completed = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Command failed with exit code "
            f"{completed.returncode}: {completed.stderr.strip()}"
        )
    return CommandResult(
        stdout=completed.stdout,
        stderr=completed.stderr,
        exit_code=completed.returncode,
    )


def _ensure_endpoint_settings(config: BotConfig) -> tuple[Path, Path, str]:
    if not config.vpn_config or not config.hosts_config or not config.endpoint_public_address:
        raise ValueError("vpn_config, hosts_config, and endpoint_public_address must be set")
    return config.vpn_config, config.hosts_config, config.endpoint_public_address


def _get_value(data: dict, key: str, required: bool = True):
    if key in data:
        return data[key]
    for section_key in ("endpoint", "client", "connection"):
        section = data.get(section_key)
        if isinstance(section, dict) and key in section:
            return section[key]
    if required:
        return None
    return None


def _pick_address(addresses) -> str:
    if isinstance(addresses, list):
        return str(addresses[0]) if addresses else ""
    return str(addresses)


def _format_dns(dns) -> str:
    if dns in (None, "", []):
        return "default (system)"
    if isinstance(dns, list):
        return ", ".join(str(value) for value in dns)
    return str(dns)


def _is_self_signed(data: dict) -> bool:
    for key in ("self_signed", "selfSigned", "certificate_is_self_signed"):
        if key in data:
            return bool(data[key])
    for section_key in ("endpoint", "client", "connection"):
        section = data.get(section_key)
        if isinstance(section, dict):
            for key in ("self_signed", "selfSigned", "certificate_is_self_signed"):
                if key in section:
                    return bool(section[key])
    return False
