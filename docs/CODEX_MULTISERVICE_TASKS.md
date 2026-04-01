# Codex task pack: TrustTunnel + telemt unified control plane

## Objective

Evolve `trusttunel_bot` from a TrustTunnel-only bot into a unified control plane for:

- TrustTunnel user lifecycle
- telemt user lifecycle
- end-user self-service bundle delivery
- migration/sync of already existing TrustTunnel users into telemt

The end result should preserve the current meaning of the bot:

- admin sends a Telegram username to the bot
- bot provisions VPN access
- user later asks the bot for everything needed to connect

But now the bundle must include both:

- TrustTunnel access
- telemt access

## Current baseline in repo

Current code already has a usable TrustTunnel pipeline:

- `src/trusttunel_bot/config.py`
- `src/trusttunel_bot/credentials.py`
- `src/trusttunel_bot/user_management.py`
- `src/trusttunel_bot/service.py`
- `src/trusttunel_bot/endpoint.py`
- `src/trusttunel_bot/cli_config.py`
- `src/trusttunel_bot/rules.py`
- `src/trusttunel_bot/bot.py`

Current limitations:

- bot config only models TrustTunnel settings
- TrustTunnel binaries are called by name instead of explicit configured paths
- no telemt control layer exists
- no user bundle abstraction exists
- user provisioning is TT-only
- self-service output is TT-only

## Operational assumptions

This plan is written for the current server layout already discussed and already working:

- TrustTunnel config: `/opt/trusttunnel/vpn-ha.toml`
- TrustTunnel hosts: `/opt/trusttunnel/hosts.toml`
- TrustTunnel credentials: `/opt/trusttunnel/credentials.toml`
- TrustTunnel service name: `trusttunnel`
- TrustTunnel binary path should be configurable and expected to point to `/opt/trusttunnel-current/trusttunnel_endpoint`
- telemt config: `/opt/telemt/telemt.toml`
- telemt service name: `telemt`
- telemt API base URL should be configurable and expected to default to `http://127.0.0.1:9091`

## Design rules

1. TrustTunnel remains the source of truth for "VPN user exists".
2. telemt is a second managed backend, not a replacement.
3. Do not hardcode binary names from PATH when explicit configured paths are available.
4. Do not handcraft telemt `tg://` links when telemt API can return canonical links.
5. Existing TT users must be syncable into telemt without manual recreation.
6. The old TT user-facing flow must keep working after refactor.

---

## Task 1 — adapt the bot to the current TrustTunnel runtime

### Goal
Make current TT logic explicitly compatible with the current runtime layout and current binary paths.

### Required changes

#### `src/trusttunel_bot/config.py`
Expand `BotConfig` with at least:

- `trusttunnel_service_name: str = "trusttunnel"`
- `trusttunnel_endpoint_binary: Path | None = None`
- `trusttunnel_client_binary: Path | None = None`

Also keep existing fields:

- `credentials_file`
- `vpn_config`
- `hosts_config`
- `endpoint_public_address`
- `dns_upstreams`
- `rules_file`
- `reload_endpoint`
- `endpoint_command_timeout_s`

#### `src/trusttunel_bot/endpoint.py`
Replace hardcoded `trusttunnel_endpoint` invocation with configured binary path.

Expected behavior:

- if `trusttunnel_endpoint_binary` is set, use it
- otherwise keep current fallback behavior for compatibility

#### `src/trusttunel_bot/cli_config.py`
Replace hardcoded `trusttunnel_client` invocation with configured binary path.

Expected behavior:

- if `trusttunnel_client_binary` is set, use it
- otherwise keep current fallback behavior for compatibility

#### `src/trusttunel_bot/service.py`
Replace hardcoded `systemctl restart trusttunnel` with configurable service name.

### Acceptance criteria

- TT endpoint export still works
- TT CLI config generation still works
- service reload/restart still works
- bot can be configured against `/opt/trusttunnel/vpn-ha.toml`

---

## Task 2 — add telemt API client layer

### Goal
Create a dedicated telemt integration layer instead of mixing telemt logic into `bot.py`.

### New file

Create `src/trusttunel_bot/telemt_api.py`

### Required capabilities

Implement a small typed client around telemt HTTP API with support for:

- `GET /v1/users`
- `GET /v1/users/{username}`
- `POST /v1/users`
- `DELETE /v1/users/{username}`

Optional:

- `PATCH /v1/users/{username}`

### Required data models

At minimum:

```python
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
```

### Required functions

At minimum:

```python
def list_telemt_users(config: BotConfig) -> list[TelemtUser]: ...
def get_telemt_user(config: BotConfig, username: str) -> TelemtUser | None: ...
def create_telemt_user(config: BotConfig, username: str, secret: str | None = None) -> TelemtUser: ...
def delete_telemt_user(config: BotConfig, username: str) -> None: ...
def ensure_telemt_user(config: BotConfig, username: str) -> TelemtUser: ...
```

### Config additions

Extend `BotConfig` with at least:

- `telemt_enabled: bool = False`
- `telemt_api_base_url: str | None = None`
- `telemt_api_auth_header: str | None = None`
- `telemt_service_name: str = "telemt"`
- `telemt_public_host: str | None = None`
- `telemt_public_port: int = 443`
- `telemt_tls_domain: str | None = None`
- `telemt_lazy_create: bool = True`
- `telemt_sync_on_add: bool = True`

### Important behavior

- Prefer telemt API as the write path
- Prefer telemt API as the source for user links
- Generate a 32-hex secret when secret is not supplied
- Treat `404` on user lookup as "user not found"

### Acceptance criteria

- bot can list telemt users
- bot can create telemt user
- bot can delete telemt user
- bot can fetch canonical telemt links for a user

---

## Task 3 — add unified access orchestration layer

### Goal
Move from TT-only user management to a unified "access bundle" model.

### New file

Create `src/trusttunel_bot/access_management.py`

### Required behavior

This module should orchestrate TT + telemt together.

### Required functions

At minimum:

```python
@dataclass(frozen=True)
class ProvisionResult:
    username: str
    trusttunnel_password: str | None
    telemt_secret: str | None
    trusttunnel_updated: bool
    telemt_updated: bool


def add_access(config: BotConfig, username: str, password: str | None = None) -> ProvisionResult: ...
def delete_access(config: BotConfig, username: str) -> None: ...
def ensure_full_access(config: BotConfig, username: str) -> ProvisionResult | None: ...
def sync_tt_users_to_telemt(config: BotConfig) -> list[str]: ...
```

### Rules

- `add_access()` must create TT user first
- if telemt is enabled and sync-on-add is enabled, also create telemt user
- `delete_access()` must delete TT user and attempt telemt deletion
- `ensure_full_access()` must preserve TT user and lazily create missing telemt user when enabled
- `sync_tt_users_to_telemt()` must load all TT users from `credentials.toml` and create missing telemt users

### Acceptance criteria

- one call can provision a new user for both systems
- one call can remove a user from both systems
- existing TT users can be synced into telemt without touching TT credentials

---

## Task 4 — add bundle builder for end-user delivery

### Goal
Create a dedicated layer that prepares everything the user should receive.

### New file

Create `src/trusttunel_bot/bundle.py`

### Required models

At minimum:

```python
@dataclass(frozen=True)
class UserBundle:
    username: str
    tt_cli_config_path: Path | None
    tt_mobile_profile_text: str | None
    telemt_tls_links: list[str]
    telemt_classic_links: list[str]
    telemt_secure_links: list[str]
```

### Required function

```python
def build_user_bundle(config: BotConfig, username: str) -> UserBundle: ...
```

### Required behavior

- generate TT endpoint config using existing TT export pipeline
- generate TT CLI config using existing TT client config pipeline
- generate TT mobile profile text using existing profile formatter
- if telemt is enabled, ensure telemt user exists and fetch telemt links

### Acceptance criteria

- one function returns the full end-user package
- bundle creation works for newly created users and already existing TT users

---

## Task 5 — refactor Telegram bot UI to use unified orchestration

### Goal
Keep current bot UX style, but make it control both backends.

### Files to modify

- `src/trusttunel_bot/bot.py`

### Required behavior changes

Replace direct TT-only calls with orchestration-layer calls:

- replace direct `add_user(...)` calls with `add_access(...)`
- replace direct `delete_user(...)` calls with `delete_access(...)`
- replace TT-only `_send_configs(...)` with bundle-driven delivery

### Recommended admin actions

Keep current style, but extend menu with:

- add user
- delete user
- issue access bundle
- sync TT -> telemt
- show rules

### Required user action

Keep a self-service action similar to current `Мой конфиг`, but make it deliver both TT and telemt data.

### Required output behavior

When user or admin requests access bundle:

1. send TT CLI config as document
2. send TT mobile profile as text
3. send telemt links as text

### Acceptance criteria

- current TT-only user flow still works
- admin can provision user into both systems
- user can self-request both TT and telemt access bundle

---

## Task 6 — migration and sync of already existing TT users

### Goal
Make current TT user base usable in telemt without manual rebuild.

### Required behavior

Implement two ways to populate telemt for old TT users:

1. explicit admin sync action
2. lazy creation on user bundle request

### Rules

- TT users are loaded from `credentials.toml`
- missing telemt users are created with new 32-hex secrets
- already existing telemt users are preserved
- sync must be idempotent

### Acceptance criteria

- running sync twice does not duplicate or break users
- an old TT-only user can request `Мой доступ` and receive telemt links after lazy creation

---

## Task 7 — docs and examples

### Goal
Leave the repo in a state where future Codex runs and manual maintenance are easy.

### Required additions

- update `README.md` to describe TT + telemt unified mode
- document required `bot.toml` fields
- document sync behavior for existing TT users
- add a multi-service example config file

### Acceptance criteria

- repo contains a working config example for the current `/opt/...` layout
- README no longer describes the project as TT-only

---

## Suggested file plan

### Existing files to modify

- `README.md`
- `src/trusttunel_bot/config.py`
- `src/trusttunel_bot/service.py`
- `src/trusttunel_bot/endpoint.py`
- `src/trusttunel_bot/cli_config.py`
- `src/trusttunel_bot/bot.py`

### New files to add

- `src/trusttunel_bot/telemt_api.py`
- `src/trusttunel_bot/access_management.py`
- `src/trusttunel_bot/bundle.py`
- `examples/bot.multiservice.example.toml`

---

## Implementation notes

### TrustTunnel compatibility

The TT side must target the current runtime layout:

- `vpn_config = "/opt/trusttunnel/vpn-ha.toml"`
- `hosts_config = "/opt/trusttunnel/hosts.toml"`
- `credentials_file = "/opt/trusttunnel/credentials.toml"`

### telemt links

Do not manually build `tg://proxy` links if telemt API already returns canonical links. Use API-provided links whenever possible.

### Secret generation

telemt secret generation should produce 16 random bytes encoded as 32 lowercase hex chars.

### Error handling

- TT creation failure must fail the whole provisioning call
- telemt creation failure should surface clearly to admin
- lazy telemt creation failure must not silently claim success

### Backward compatibility

- keep old TT code paths usable where practical
- preserve current menu style and current replace-in-place message approach

---

## Suggested execution order for Codex

1. Task 1
2. Task 2
3. Task 3
4. Task 4
5. Task 5
6. Task 6
7. Task 7

That order minimizes breakage and keeps UI work for last.
