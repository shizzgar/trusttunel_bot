# TrustTunnel Telegram Bot (trusttunel_bot)

Телеграм-бот unified control plane для **TrustTunnel + telemt + hev-socks5-server**.

Базовый сценарий:
- администратор добавляет Telegram username;
- бот создаёт доступ в TrustTunnel;
- опционально синхронно создаёт доступы в telemt и SOCKS5 / hev-socks5-server;
- пользователь или администратор выбирает, какой доступ выдать: TrustTunnel, telemt, SOCKS5 или всё сразу;
- существующие TT-пользователи могут быть синхронизированы в telemt и lazy-created в дополнительных provider'ах при выдаче доступа.

## Возможности

- Управление жизненным циклом пользователей TrustTunnel (create/delete).
- Управление пользователями telemt через API (`/v1/users`).
- Управление пользователями `hev-socks5-server` через whitespace-separated auth-файл `USERNAME PASSWORD MARK`.
- Единый orchestration слой (`add_access`, `delete_access`, `ensure_full_access`, `sync_tt_users_to_telemt`).
- Выборочная выдача пользовательского bundle:
  - TT CLI config (документ);
  - TT mobile profile (текст);
  - telemt canonical links (TLS / Classic / Secure);
  - SOCKS5 параметры и URI (`socks5h://...`).

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
  - `hev-socks5-server` (если SOCKS5 включён)

## Конфигурация (`bot.toml`)

```toml
telegram_token = "123456:ABCDEF"
admin_ids = [123456789]
known_chats_file = "/opt/trusttunnel/trusttunel_bot/known_chats.txt"

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
trusttunnel_setup_wizard_binary = "/opt/trusttunnel_client/setup_wizard"

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

# hev-socks5-server
hev_socks5_enabled = true
hev_socks5_auth_file = "/opt/hev-socks5-server/conf/auth.txt"
hev_socks5_service_name = "hev-socks5-server"
hev_socks5_public_host = "proxy.example.com"
hev_socks5_public_port = 1080
hev_socks5_scheme = "socks5h"
hev_socks5_sync_on_add = true
hev_socks5_lazy_create = true
hev_socks5_mark_start = 16
```

Готовый пример: `examples/bot.multiservice.example.toml`.

## hev-socks5-server

Для включения SOCKS5 provider'а задайте `hev_socks5_enabled = true`, путь к auth-файлу, публичный host/port и, при необходимости, имя systemd/process service.

Для твоей текущей схемы, где TrustTunnel, telemt и их конфиги живут в `/opt`, держи `hev-socks5-server` там же:

```txt
/opt/hev-socks5-server/
  bin/hev-socks5-server
  conf/main.yml
  conf/auth.txt
```

Если репозиторий уже склонирован и собран в `/opt/hev-socks5-server`, достаточно создать `conf/auth.txt`, прописать его в `conf/main.yml`, а в `bot.toml` указать `hev_socks5_auth_file = "/opt/hev-socks5-server/conf/auth.txt"`.

Пример systemd unit для `/opt`-layout:

```ini
[Unit]
Description=hev-socks5-server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/hev-socks5-server
ExecStart=/opt/hev-socks5-server/bin/hev-socks5-server /opt/hev-socks5-server/conf/main.yml
Restart=on-failure
RestartSec=3
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
```

`main.yml` у `hev-socks5-server` должен ссылаться на тот же auth-файл, которым управляет бот:

```yaml
auth:
  file: /opt/hev-socks5-server/conf/auth.txt
```

Бот меняет **только auth-файл**, а не основной `main.yml`. Auth-файл сохраняется простым форматом, который ожидает `hev-socks5-server`:

```txt
USERNAME PASSWORD MARK
```

После изменения auth-файла бот пытается сделать live reload командой `killall -SIGUSR1 hev-socks5-server`. Если live reload не удался, используется fallback `systemctl restart <hev_socks5_service_name>`.

Пароли SOCKS5 не ротируются при повторной выдаче доступа: существующая строка пользователя в auth-файле переиспользуется.

## Поведение sync для существующих TT пользователей

Есть два способа заполнить telemt пользователями из TrustTunnel:

1. Явный админ action в UI: **`Sync TT -> telemt`**.
2. Lazy-режим при запросе bundle (если `telemt_lazy_create = true`).

SOCKS5 provider поддерживает похожую lazy-схему: если `hev_socks5_lazy_create = true`, то при выдаче SOCKS5 или полного bundle пользователь создаётся в auth-файле, если его там ещё нет.

Правила:
- читаются пользователи из `credentials.toml`;
- если пользователь уже существует в telemt/SOCKS5 — не перезаписывается;
- если отсутствует — создаётся с новым секретом/паролем;
- sync/lazy-create идемпотентны.

## Telegram UI

Админ:
- ➕ Добавить пользователя
- ➖ Удалить пользователя
- 🧾 Выдать доступ
- 🔄 Sync TT -> telemt
- 📣 Отправить сообщение пользователям
- 📜 Показать rules

Пользователь:
- 🔑 Мой доступ

При выдаче доступа бот сначала показывает выбор:

- 🔐 TrustTunnel
- 📨 telemt
- 🧦 SOCKS5
- 📦 Всё сразу

После выбора отправляется только соответствующий тип доступа. Для админа flow такой: выбрать пользователя → выбрать тип доступа → получить нужный конфиг.

## Разработка и тесты

Runtime dependencies остаются минимальными (`aiogram`, `tomli` fallback для Python < 3.11). Для локального запуска тестов установите `pytest` отдельно или через dev-зависимости проекта, если они добавлены в окружение.

```bash
python -m pytest
```

## Запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m trusttunel_bot.bot
```
