# TrustTunnel Telegram Bot (trusttunel_bot)

Телеграм‑бот для администрирования пользователей TrustTunnel и выдачи клиентских
конфигураций. Проект ориентирован на сценарий, когда администратор сервера
создаёт/удаляет пользователей VPN и по запросу выдаёт им конфиги для CLI и
мобильного клиента.

## Возможности

- Создание/удаление пользователей TrustTunnel через файл `credentials.toml`.
- Генерация endpoint‑конфига для конкретного пользователя через
  `trusttunnel_endpoint -c`.
- Генерация CLI‑конфига (TrustTunnel Client) из endpoint‑конфига.
- Формирование краткого профиля подключения для мобильного клиента
  (hostname, address, protocol, DNS, учётные данные).

> ⚠️ Flutter‑клиент **не поддерживает self‑signed сертификаты**. Для мобильного
> клиента требуется публично доверенный сертификат.

## Требования

- Python 3.11+ (используется `tomllib`).
- Доступ к установленным утилитам:
  - `trusttunnel_endpoint` (сервер TrustTunnel)
  - `trusttunnel_client` и/или `setup_wizard` (CLI‑клиент TrustTunnel)
- Доступ к файлам конфигурации TrustTunnel (`vpn.toml`, `hosts.toml`,
  `credentials.toml`).

## Установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Конфигурация бота

Пример `bot.toml`:

```toml
# Обязательный путь до credentials.toml TrustTunnel
credentials_file = "/opt/trusttunnel/credentials.toml"

# URL для hot-reload (POST). Если не задан/недоступен — будет restart systemd.
reload_endpoint = "http://127.0.0.1:8080/reload"

# Telegram bot token и список администраторов
telegram_token = "123456:ABCDEF"
admin_ids = [123456789]

# Пути к конфигам endpoint (нужны для export клиента)
vpn_config = "/opt/trusttunnel/vpn.toml"
hosts_config = "/opt/trusttunnel/hosts.toml"

# Публичный адрес/порт для клиентов
endpoint_public_address = "vpn.example.com:443"

# DNS для CLI-клиента (админский выбор)
dns_upstreams = ["10.3.2.1:53"]

# Файл правил TrustTunnel (rules.toml)
rules_file = "/opt/trusttunnel/rules.toml"

# Таймаут для запуска trusttunnel_endpoint
endpoint_command_timeout_s = 10
```

## Использование (программные функции)

### Создание пользователя

```python
from pathlib import Path
from trusttunel_bot.config import load_config
from trusttunel_bot.user_management import add_user

config = load_config(Path("bot.toml"))
result = add_user(config, username="alice", password="secret")
print(result.updated_path, result.used_hot_reload)
```

### Удаление пользователя

```python
from pathlib import Path
from trusttunel_bot.config import load_config
from trusttunel_bot.user_management import delete_user

config = load_config(Path("bot.toml"))
result = delete_user(config, username="alice")
print(result.updated_path, result.used_hot_reload)
```

### Экспорт endpoint‑конфига

```python
from pathlib import Path
from trusttunel_bot.config import load_config
from trusttunel_bot.endpoint import generate_endpoint_config

config = load_config(Path("bot.toml"))
endpoint = generate_endpoint_config(config, username="alice")
print(endpoint.output_path)
```

### Генерация CLI‑конфига

```python
from pathlib import Path
from trusttunel_bot.cli_config import generate_client_config

result = generate_client_config(Path("/tmp/alice.endpoint.toml"), dns_upstreams=["10.3.2.1:53"])
print(result.output_path, result.used_setup_wizard)
```

### Профиль для мобильного клиента

```python
from pathlib import Path
from trusttunel_bot.endpoint import build_connection_profile, format_connection_profile

profile = build_connection_profile(Path("/tmp/alice.endpoint.toml"))
print(format_connection_profile(profile))
```

## Запуск Telegram-бота

1. Заполните `bot.toml` (см. пример выше).
2. Запустите:

```bash
python -m trusttunel_bot.bot
```

### Команды и UI

- `/start` или `/menu` открывают меню.
- Все действия выполняются через единый “панельный” месседж с заменой текста
  (replace-in-place). Дополнительные файлы (конфиги) отправляются отдельными сообщениями.

### Чтение и запись rules.toml

```python
from pathlib import Path
from trusttunel_bot.rules import Rule, load_rules, save_rules, format_rules_summary

rules = load_rules(Path("/opt/trusttunnel/rules.toml"))
print(format_rules_summary(rules))

rules.append(Rule(cidr="10.3.2.1/32", client_random_prefix=None, action="allow"))
save_rules(Path("/opt/trusttunnel/rules.toml"), rules)
```

## Замечания по безопасности

- Файл `credentials.toml` хранит пароли в открытом виде. Ограничьте доступ на
  уровне ОС.
- Рекомендуется выполнять перезапуск сервиса TrustTunnel от отдельного пользователя
  с минимальными правами.

## Структура проекта

- `src/trusttunel_bot/config.py` — загрузка конфигурации бота.
- `src/trusttunel_bot/credentials.py` — чтение/запись `credentials.toml`.
- `src/trusttunel_bot/user_management.py` — добавление/удаление пользователей.
- `src/trusttunel_bot/endpoint.py` — экспорт endpoint‑конфига и профиль подключения.
- `src/trusttunel_bot/cli_config.py` — генерация CLI‑конфига.
- `src/trusttunel_bot/service.py` — перезапуск endpoint (hot‑reload/ systemctl).
- `src/trusttunel_bot/rules.py` — чтение/запись `rules.toml` и краткий вывод.
- `src/trusttunel_bot/bot.py` — Telegram-бот на aiogram (stateful UI).

## Roadmap

- Webhook-режим для продакшн-деплоя.
- Хранение состояния и аудит действий администратора.
- Настраиваемые шаблоны сообщений и локализации.

## Лицензия

MIT (если не будет выбрана другая лицензия).
