from __future__ import annotations

from dataclasses import dataclass
from urllib import request, error
import subprocess


@dataclass(frozen=True)
class ReloadResult:
    used_hot_reload: bool


def reload_credentials(reload_endpoint: str | None) -> ReloadResult:
    if reload_endpoint:
        try:
            req = request.Request(reload_endpoint, method="POST")
            with request.urlopen(req, timeout=5):
                return ReloadResult(used_hot_reload=True)
        except (error.URLError, error.HTTPError):
            pass
    subprocess.run(["systemctl", "restart", "trusttunnel"], check=False)
    return ReloadResult(used_hot_reload=False)
