from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import tempfile

from trusttunel_bot.config import BotConfig


@dataclass(frozen=True)
class EndpointConfigResult:
    output_path: Path
    content: str


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
