from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - py<3.11 fallback
    import tomli as tomllib

from trusttunel_bot.config import BotConfig


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
    dns_upstreams: list[str] | None = None,
) -> ClientConfigResult:
    output_path = output_path or endpoint_config_path.parent / "trusttunnel_client.toml"
    if prefer_setup_wizard:
        wizard_result = _try_setup_wizard(endpoint_config_path, output_path)
        if wizard_result:
            if dns_upstreams:
                content = _merge_dns_upstreams(
                    wizard_result.content,
                    dns_upstreams,
                )
                output_path.write_text(content, encoding="utf-8")
                return ClientConfigResult(
                    output_path=output_path,
                    content=content,
                    used_setup_wizard=wizard_result.used_setup_wizard,
                    skip_verification=wizard_result.skip_verification,
                )
            return wizard_result
    content, skip_verification = _build_client_config_from_endpoint(
        endpoint_config_path,
        dns_upstreams=dns_upstreams,
    )
    output_path.write_text(content, encoding="utf-8")
    return ClientConfigResult(
        output_path=output_path,
        content=content,
        used_setup_wizard=False,
        skip_verification=skip_verification,
    )


def generate_client_config_from_bot_config(
    config: BotConfig,
    endpoint_config_path: Path,
    output_path: Path | None = None,
    prefer_setup_wizard: bool = True,
) -> ClientConfigResult:
    return generate_client_config(
        endpoint_config_path=endpoint_config_path,
        output_path=output_path,
        prefer_setup_wizard=prefer_setup_wizard,
        dns_upstreams=config.dns_upstreams,
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
    dns_upstreams: list[str] | None = None,
) -> tuple[str, bool]:
    data = tomllib.loads(endpoint_config_path.read_text(encoding="utf-8"))
    hostname = _get_value(data, ["hostname"])
    addresses = _get_value(data, ["addresses"])
    username = _get_value(data, ["username"])
    password = _get_value(data, ["password"])
    protocol = _get_value(data, ["upstream_protocol", "protocol"])
    fallback_protocol = _get_value(data, ["upstream_fallback_protocol"], required=False)
    has_ipv6 = _get_value(data, ["has_ipv6"], required=False)
    anti_dpi = _get_value(data, ["anti_dpi"], required=False)
    certificate = _get_value(data, ["certificate"], required=False)
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
    
    lines: list[str] = ["vpn_mode = \"general\""]
    lines.append(f"killswitch_enabled = true")

    if dns_upstreams:
        lines.append(f"dns_upstreams = {_format_list(dns_upstreams)}")
    lines.append(f"[endpoint]")
    lines.append(f"hostname = \"{_escape(str(hostname))}\"")
    lines.append(f"addresses = {_format_list(addresses)}")
    if has_ipv6 is not None:
        lines.append(f"has_ipv6 = {str(bool(has_ipv6)).lower()}")
    lines.append(f"username = \"{_escape(str(username))}\"")
    lines.append(f"password = \"{_escape(str(password))}\"")
    lines.append(f"upstream_protocol = \"{_escape(str(protocol))}\"")
    if fallback_protocol not in (None, "", []):
        lines.append(f"upstream_fallback_protocol = \"{_escape(str(fallback_protocol))}\"")
    if anti_dpi is not None:
        lines.append(f"anti_dpi = {str(bool(anti_dpi)).lower()}")
    if certificate:
        lines.append(f"certificate = {_format_multiline_string(str(certificate))}")
    else:
        skip_verification = True
        lines.append("skip_verification = true")
    lines.append("[listener]")
    lines.append("[listener.tun]")
    lines.append("bound_if = \"\"")
    lines.append("included_routes = [\"0.0.0.0/0\", \"2000::/3\", \"10.3.2.1/32\"]")
    lines.append("excluded_routes = [\"0.0.0.0/8\", \"169.254.0.0/16\", \"172.16.0.0/12\", \"192.168.0.0/16\", \"224.0.0.0/3\"]")
    lines.append("mtu_size = 1500")
    lines.append("change_system_dns = true")
    content = "\n".join(lines).rstrip() + "\n"
    return content, skip_verification


def _merge_dns_upstreams(content: str, dns_upstreams: list[str]) -> str:
    lines = content.splitlines()
    rendered = f"dns_upstreams = {_format_list(dns_upstreams)}"
    for index, line in enumerate(lines):
        if line.strip().startswith("dns_upstreams"):
            lines[index] = rendered
            return "\n".join(lines).rstrip() + "\n"
    lines.append(rendered)
    return "\n".join(lines).rstrip() + "\n"


def _get_value(data: dict, keys: list[str], required: bool = True):
    for key in keys:
        if key in data:
            return data[key]
    for section_key in ("endpoint", "client", "connection"):
        section = data.get(section_key)
        if isinstance(section, dict):
            for key in keys:
                if key in section:
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
