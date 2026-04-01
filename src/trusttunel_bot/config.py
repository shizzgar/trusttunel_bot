from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - py<3.11 fallback
    import tomli as tomllib


@dataclass(frozen=True)
class BotConfig:
    credentials_file: Path
    telegram_token: str | None = None
    admin_ids: list[int] | None = None
    known_chats_file: Path = Path("known_chats.txt")
    reload_endpoint: str | None = None
    vpn_config: Path | None = None
    hosts_config: Path | None = None
    endpoint_public_address: str | None = None
    dns_upstreams: list[str] | None = None
    rules_file: Path | None = None
    endpoint_command_timeout_s: int = 10
    trusttunnel_service_name: str = "trusttunnel"
    trusttunnel_endpoint_binary: Path = Path("/opt/trusttunnel-current/trusttunnel_endpoint")
    trusttunnel_client_binary: Path = Path("/opt/trusttunnel_client/trusttunnel_client")
    trusttunnel_setup_wizard_binary: Path = Path("/opt/trusttunnel_client/setup_wizard")
    telemt_enabled: bool = False
    telemt_api_base_url: str | None = None
    telemt_api_auth_header: str | None = None
    telemt_service_name: str = "telemt"
    telemt_public_host: str | None = None
    telemt_public_port: int = 443
    telemt_tls_domain: str | None = None
    telemt_lazy_create: bool = True
    telemt_sync_on_add: bool = True


def load_config(path: Path) -> BotConfig:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    credentials_file = data.get("credentials_file")
    if not credentials_file:
        raise ValueError("credentials_file is required in bot config")
    telegram_token = data.get("telegram_token")
    admin_ids = _ensure_int_list(data.get("admin_ids"))
    known_chats_file = data.get("known_chats_file")
    reload_endpoint = data.get("reload_endpoint")
    vpn_config = data.get("vpn_config")
    hosts_config = data.get("hosts_config")
    endpoint_public_address = data.get("endpoint_public_address")
    dns_upstreams = _ensure_list(data.get("dns_upstreams"))
    rules_file = data.get("rules_file")
    endpoint_command_timeout_s = data.get("endpoint_command_timeout_s", 10)

    trusttunnel_service_name = str(data.get("trusttunnel_service_name") or "trusttunnel")
    trusttunnel_endpoint_binary = data.get("trusttunnel_endpoint_binary")
    trusttunnel_client_binary = data.get("trusttunnel_client_binary")
    trusttunnel_setup_wizard_binary = data.get("trusttunnel_setup_wizard_binary")

    telemt_enabled = bool(data.get("telemt_enabled", False))
    telemt_api_base_url = data.get("telemt_api_base_url")
    telemt_api_auth_header = data.get("telemt_api_auth_header")
    telemt_service_name = str(data.get("telemt_service_name") or "telemt")
    telemt_public_host = data.get("telemt_public_host")
    telemt_public_port = int(data.get("telemt_public_port", 443))
    telemt_tls_domain = data.get("telemt_tls_domain")
    telemt_lazy_create = bool(data.get("telemt_lazy_create", True))
    telemt_sync_on_add = bool(data.get("telemt_sync_on_add", True))

    return BotConfig(
        credentials_file=Path(credentials_file),
        telegram_token=str(telegram_token) if telegram_token else None,
        admin_ids=admin_ids,
        known_chats_file=Path(known_chats_file) if known_chats_file else Path("known_chats.txt"),
        reload_endpoint=reload_endpoint,
        vpn_config=Path(vpn_config) if vpn_config else None,
        hosts_config=Path(hosts_config) if hosts_config else None,
        endpoint_public_address=endpoint_public_address,
        dns_upstreams=dns_upstreams,
        rules_file=Path(rules_file) if rules_file else None,
        endpoint_command_timeout_s=int(endpoint_command_timeout_s),
        trusttunnel_service_name=trusttunnel_service_name,
        trusttunnel_endpoint_binary=Path(trusttunnel_endpoint_binary)
        if trusttunnel_endpoint_binary
        else Path("/opt/trusttunnel-current/trusttunnel_endpoint"),
        trusttunnel_client_binary=Path(trusttunnel_client_binary)
        if trusttunnel_client_binary
        else Path("/opt/trusttunnel_client/trusttunnel_client"),
        trusttunnel_setup_wizard_binary=Path(trusttunnel_setup_wizard_binary)
        if trusttunnel_setup_wizard_binary
        else Path("/opt/trusttunnel_client/setup_wizard"),
        telemt_enabled=telemt_enabled,
        telemt_api_base_url=str(telemt_api_base_url) if telemt_api_base_url else None,
        telemt_api_auth_header=str(telemt_api_auth_header) if telemt_api_auth_header else None,
        telemt_service_name=telemt_service_name,
        telemt_public_host=str(telemt_public_host) if telemt_public_host else None,
        telemt_public_port=telemt_public_port,
        telemt_tls_domain=str(telemt_tls_domain) if telemt_tls_domain else None,
        telemt_lazy_create=telemt_lazy_create,
        telemt_sync_on_add=telemt_sync_on_add,
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
