from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import tomllib


@dataclass(frozen=True)
class ClientConfigResult:
    output_path: Path
    content: str
    used_setup_wizard: bool
    skip_verification: bool


def generate_client_config(
    endpoint_config_path: Path,
    output_path: Path | None = None,
    prefer_setup_wizard: bool = True,
) -> ClientConfigResult:
    output_path = output_path or endpoint_config_path.parent / "trusttunnel_client.toml"
    if prefer_setup_wizard:
        wizard_result = _try_setup_wizard(endpoint_config_path, output_path)
        if wizard_result:
            return wizard_result
    content, skip_verification = _build_client_config_from_endpoint(endpoint_config_path)
    output_path.write_text(content, encoding="utf-8")
    return ClientConfigResult(
        output_path=output_path,
        content=content,
        used_setup_wizard=False,
        skip_verification=skip_verification,
    )


def _try_setup_wizard(
    endpoint_config_path: Path,
    output_path: Path,
) -> ClientConfigResult | None:
    completed = subprocess.run(
        [
            "trusttunnel_client",
            "setup_wizard",
            "--mode",
            "non-interactive",
            "--endpoint_config",
            str(endpoint_config_path),
            "--settings",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not output_path.exists():
        return None
    content = output_path.read_text(encoding="utf-8")
    return ClientConfigResult(
        output_path=output_path,
        content=content,
        used_setup_wizard=True,
        skip_verification=False,
    )


def _build_client_config_from_endpoint(
    endpoint_config_path: Path,
) -> tuple[str, bool]:
    data = tomllib.loads(endpoint_config_path.read_text(encoding="utf-8"))
    hostname = _get_value(data, "hostname")
    addresses = _get_value(data, "addresses")
    username = _get_value(data, "username")
    password = _get_value(data, "password")
    protocol = _get_value(data, "protocol")
    certificate = _get_value(data, "certificate", required=False)
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
    skip_verification = False
    lines: list[str] = []
    lines.append(f"hostname = \"{_escape(str(hostname))}\"")
    lines.append(f"addresses = {_format_list(addresses)}")
    lines.append(f"username = \"{_escape(str(username))}\"")
    lines.append(f"password = \"{_escape(str(password))}\"")
    lines.append(f"protocol = \"{_escape(str(protocol))}\"")
    if certificate:
        lines.append(f"certificate = {_format_multiline_string(str(certificate))}")
    else:
        skip_verification = True
        lines.append("skip_verification = true")
    content = "\n".join(lines).rstrip() + "\n"
    return content, skip_verification


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


def _format_list(values) -> str:
    if not isinstance(values, list):
        values = [values]
    escaped = [f"\"{_escape(str(value))}\"" for value in values]
    return f"[{', '.join(escaped)}]"


def _format_multiline_string(value: str) -> str:
    cleaned = value.strip("\n")
    return f'"""\n{cleaned}\n"""'


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\"", "\\\"")
