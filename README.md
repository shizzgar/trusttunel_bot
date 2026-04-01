# TrustTunnel Telegram Bot (trusttunel_bot)

Телеграм-бот unified control plane для **TrustTunnel + telemt**.

Базовый сценарий:
- администратор добавляет Telegram username;
- бот создаёт доступ в TrustTunnel;
- при выдаче пакета доступа бот отдаёт данные для TrustTunnel и telemt;
- существующие TT-пользователи могут быть синхронизированы в telemt.

## Возможности

- Управление жизненным циклом пользователей TrustTunnel (create/delete).
- Управление пользователями telemt через API (`/v1/users`).
- Единый orchestration слой (`add_access`, `delete_access`, `sync_tt_users_to_telemt`).
- Единая выдача пользовательского bundle:
  - TT CLI config (документ);
  - TT mobile profile (текст);
  - telemt canonical links (TLS / Classic / Secure).

## Требования

- Python 3.11+
- aiogram 3
- Установленные TrustTunnel бинарники:
  - `trusttunnel_endpoint`
  - `trusttunnel_client`
- Доступ к файлам:
  - `/opt/trusttunnel/vpn-ha.toml`
  - `/opt/trusttunnel/hosts.toml`
  - `/opt/trusttunnel/credentials.toml`
- systemd сервисы:
  - `trusttunnel`
  - `telemt` (если telemt включён)

## Конфигурация (`bot.toml`)

```toml
telegram_token = "123456:ABCDEF"
admin_ids = [123456789]

# TrustTunnel
credentials_file = "/opt/trusttunnel/credentials.toml"
vpn_config = "/opt/trusttunnel/vpn-ha.toml"
hosts_config = "/opt/trusttunnel/hosts.toml"
endpoint_public_address = "xx-xx-xx-xx.sslip.io:443"
dns_upstreams = ["10.3.2.1:53"]
rules_file = "/opt/trusttunnel/rules.toml"
reload_endpoint = ""
endpoint_command_timeout_s = 10
trusttunnel_service_name = "trusttunnel"
trusttunnel_endpoint_binary = "/opt/trusttunnel-current/trusttunnel_endpoint"
trusttunnel_client_binary = "/opt/trusttunnel_client/trusttunnel_client"

# telemt
telemt_enabled = true
telemt_api_base_url = "http://127.0.0.1:9091"
telemt_api_auth_header = ""
telemt_service_name = "telemt"
telemt_public_host = "tm.xx-xx-xx-xx.sslip.io"
telemt_public_port = 443
telemt_tls_domain = "tm.xx-xx-xx-xx.sslip.io"
telemt_lazy_create = true
telemt_sync_on_add = true
```

Готовый пример: `examples/bot.multiservice.example.toml`.

## Поведение sync для существующих TT пользователей

Есть два способа заполнить telemt пользователями из TrustTunnel:

1. Явный админ action в UI: **`Sync TT -> telemt`**.
2. Lazy-режим при запросе bundle (если `telemt_lazy_create = true`).

Правила:
- читаются пользователи из `credentials.toml`;
- если пользователь уже существует в telemt — не перезаписывается;
- если отсутствует — создаётся с новым секретом (32 hex);
- sync идемпотентен.

## Telegram UI

Админ:
- ➕ Добавить пользователя
- ➖ Удалить пользователя
- 🧾 Выдать доступ
- 🔄 Sync TT -> telemt
- 📜 Показать rules

Пользователь:
- 🔑 Мой доступ

Выдача доступа отправляет:
1. TT CLI config (document)
2. TT mobile profile (text)
3. telemt links (text)

## Запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m trusttunel_bot.bot
```
