from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import secrets
from urllib import error, request

from trusttunel_bot.config import BotConfig

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class TelemtLinks:
    tls: list[str]
    classic: list[str]
    secure: list[str]


@dataclass(frozen=True)
class TelemtUser:
    username: str
    secret: str | None
    links: TelemtLinks


class TelemtAPIError(RuntimeError):
    pass


def list_telemt_users(config: BotConfig) -> list[TelemtUser]:
    payload = _request_json(config, "GET", "/v1/users")
    if not isinstance(payload, list):
        raise TelemtAPIError("Unexpected /v1/users response format")
    return [_parse_user(item) for item in payload]


def get_telemt_user(config: BotConfig, username: str) -> TelemtUser | None:
    try:
        payload = _request_json(config, "GET", f"/v1/users/{username}")
    except TelemtAPIError as exc:
        if "HTTP 404" in str(exc):
            return None
        raise
    return _parse_user(payload)


def create_telemt_user(
    config: BotConfig,
    username: str,
    secret: str | None = None,
) -> TelemtUser:
    resolved_secret = secret or _generate_secret()
    payload = _request_json(
        config,
        "POST",
        "/v1/users",
        body={"username": username, "secret": resolved_secret},
    )
    return _parse_user(payload)


def delete_telemt_user(config: BotConfig, username: str) -> None:
    try:
        _request_json(config, "DELETE", f"/v1/users/{username}")
    except TelemtAPIError as exc:
        if "HTTP 404" in str(exc):
            return
        raise


def ensure_telemt_user(config: BotConfig, username: str) -> TelemtUser:
    user = get_telemt_user(config, username)
    if user:
        return user
    return create_telemt_user(config, username)


def _request_json(
    config: BotConfig,
    method: str,
    path: str,
    body: dict | None = None,
):
    base = (config.telemt_api_base_url or "").rstrip("/")
    if not base:
        raise TelemtAPIError("telemt_api_base_url is not configured")
    url = f"{base}{path}"
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if config.telemt_api_auth_header:
        headers["Authorization"] = config.telemt_api_auth_header

    req = request.Request(url, method=method, headers=headers, data=data)
    try:
        with request.urlopen(req, timeout=10) as response:
            text = response.read().decode("utf-8")
            if not text.strip():
                return None
            return json.loads(text)
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        LOGGER.error(
            "telemt API HTTP error: method=%s url=%s status=%s body=%s",
            method,
            url,
            exc.code,
            details,
        )
        raise TelemtAPIError(f"telemt API request failed: HTTP {exc.code}, body={details}") from exc
    except error.URLError as exc:
        LOGGER.error("telemt API network error: method=%s url=%s error=%s", method, url, exc)
        raise TelemtAPIError(f"telemt API request failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        LOGGER.error("telemt API invalid JSON: method=%s url=%s", method, url)
        raise TelemtAPIError("telemt API returned invalid JSON") from exc


def _parse_user(payload: dict) -> TelemtUser:
    payload = _unwrap_payload(payload)
    if not isinstance(payload, dict):
        raise TelemtAPIError(f"Unexpected telemt user payload type: {type(payload).__name__}")
    username = payload.get("username")
    if not username:
        preview = _safe_preview(payload)
        LOGGER.error("telemt user payload missing username: payload=%s", preview)
        raise TelemtAPIError(f"telemt user payload missing username; payload={preview}")
    secret = payload.get("secret")
    links_data = payload.get("links") or {}
    links = TelemtLinks(
        tls=[str(value) for value in links_data.get("tls", [])],
        classic=[str(value) for value in links_data.get("classic", [])],
        secure=[str(value) for value in links_data.get("secure", [])],
    )
    return TelemtUser(username=str(username), secret=str(secret) if secret else None, links=links)


def _generate_secret() -> str:
    return secrets.token_hex(16)


def _unwrap_payload(payload):
    if isinstance(payload, dict):
        for key in ("user", "data", "result"):
            value = payload.get(key)
            if isinstance(value, dict) and value.get("username"):
                return value
    return payload


def _safe_preview(payload) -> str:
    try:
        rendered = json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(payload)
    if len(rendered) > 400:
        return rendered[:397] + "..."
    return rendered
