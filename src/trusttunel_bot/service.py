from __future__ import annotations

from dataclasses import dataclass
from urllib import error, request
import subprocess

from trusttunel_bot.config import BotConfig


@dataclass(frozen=True)
class ReloadResult:
    used_hot_reload: bool


@dataclass(frozen=True)
class ServiceActionResult:
    ok: bool
    used_hot_reload: bool = False
    message: str | None = None


def restart_service(service_name: str) -> ServiceActionResult:
    completed = subprocess.run(
        ["systemctl", "restart", service_name],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        return ServiceActionResult(ok=False, message=details)
    return ServiceActionResult(ok=True)


def reload_trusttunnel(config: BotConfig) -> ServiceActionResult:
    if config.reload_endpoint:
        try:
            req = request.Request(config.reload_endpoint, method="POST")
            with request.urlopen(req, timeout=5):
                return ServiceActionResult(ok=True, used_hot_reload=True)
        except (error.URLError, error.HTTPError) as exc:
            restart_result = restart_service(config.trusttunnel_service_name)
            if restart_result.ok:
                return ServiceActionResult(
                    ok=True,
                    used_hot_reload=False,
                    message=f"Hot reload failed, restarted service: {exc}",
                )
            return ServiceActionResult(
                ok=False,
                used_hot_reload=False,
                message=(
                    f"Hot reload failed ({exc}); restart failed: {restart_result.message}"
                ),
            )
    return restart_service(config.trusttunnel_service_name)


def reload_credentials(
    reload_endpoint: str | None,
    service_name: str = "trusttunnel",
) -> ReloadResult:
    if reload_endpoint:
        try:
            req = request.Request(reload_endpoint, method="POST")
            with request.urlopen(req, timeout=5):
                return ReloadResult(used_hot_reload=True)
        except (error.URLError, error.HTTPError):
            pass
    subprocess.run(["systemctl", "restart", service_name], check=False)
    return ReloadResult(used_hot_reload=False)
