from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
import secrets
import tempfile
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from trusttunel_bot.cli_config import generate_client_config_from_bot_config
from trusttunel_bot.config import BotConfig, load_config
from trusttunel_bot.endpoint import (
    build_connection_profile,
    format_connection_profile,
    generate_endpoint_config,
)
from trusttunel_bot.rules import format_rules_summary, load_rules
from trusttunel_bot.user_management import add_user, delete_user, list_users


@dataclass
class ChatState:
    mode: str | None = None
    pending_username: str | None = None


class StateStore:
    def __init__(self) -> None:
        self._states: dict[int, ChatState] = {}
        self._messages: dict[int, int] = {}

    def get_state(self, chat_id: int) -> ChatState:
        return self._states.setdefault(chat_id, ChatState())

    def clear_state(self, chat_id: int) -> None:
        self._states.pop(chat_id, None)

    def set_message_id(self, chat_id: int, message_id: int) -> None:
        self._messages[chat_id] = message_id

    def get_message_id(self, chat_id: int) -> int | None:
        return self._messages.get(chat_id)


state_store = StateStore()
USER_LIST_PAGE_SIZE = 10


def _is_admin(config: BotConfig, user_id: int) -> bool:
    if not config.admin_ids:
        return False
    return user_id in config.admin_ids


def _menu_keyboard(is_admin: bool) -> InlineKeyboardMarkup:
    buttons = []
    if is_admin:
        buttons.extend(
            [
                [InlineKeyboardButton(text="➕ Добавить пользователя", callback_data="add_user")],
                [InlineKeyboardButton(text="➖ Удалить пользователя", callback_data="delete_user")],
                [InlineKeyboardButton(text="🧾 Получить конфиг", callback_data="admin_config")],
                [InlineKeyboardButton(text="📜 Показать rules", callback_data="show_rules")],
            ]
        )
    buttons.append([InlineKeyboardButton(text="🔑 Мой конфиг", callback_data="my_config")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _render_menu(is_admin: bool) -> str:
    header = "Панель управления TrustTunnel"
    role = "Администратор" if is_admin else "Пользователь"
    return f"{header}\nРоль: {role}\n\nВыберите действие:"


async def _upsert_message(
    bot: Bot,
    chat_id: int,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> None:
    message_id = state_store.get_message_id(chat_id)
    if message_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=keyboard,
            )
            return
        except TelegramBadRequest:
            pass
    message = await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
    state_store.set_message_id(chat_id, message.message_id)


async def show_menu(bot: Bot, chat_id: int, is_admin: bool) -> None:
    await _upsert_message(
        bot,
        chat_id,
        _render_menu(is_admin),
        _menu_keyboard(is_admin),
    )


async def handle_start(message: Message, config: BotConfig) -> None:
    state_store.clear_state(message.chat.id)
    await show_menu(message.bot, message.chat.id, _is_admin(config, message.from_user.id))


async def handle_callback(
    callback: CallbackQuery,
    config: BotConfig,
) -> None:
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    is_admin = _is_admin(config, user_id)
    state = state_store.get_state(chat_id)

    action = callback.data
    if action in {"add_user", "delete_user", "admin_config", "show_rules"} and not is_admin:
        await callback.answer("Недостаточно прав.")
        await show_menu(callback.bot, chat_id, is_admin)
        return
    if action and action.startswith("delete_user:") and not is_admin:
        await callback.answer("Недостаточно прав.")
        await show_menu(callback.bot, chat_id, is_admin)
        return

    if action == "add_user":
        state.mode = "add_user"
        state.pending_username = None
        await _upsert_message(
            callback.bot,
            chat_id,
            "Отправьте @username пользователя или пересланное сообщение от него.",
            _menu_keyboard(is_admin),
        )
    elif action == "delete_user":
        state.mode = None
        await _show_delete_user_menu(callback.bot, chat_id, config, is_admin, page=1)
    elif action == "admin_config":
        state.mode = None
        await _show_admin_config_menu(callback.bot, chat_id, config, is_admin, page=1)
    elif action == "show_rules":
        summary = _load_rules_summary(config)
        await _upsert_message(
            callback.bot,
            chat_id,
            summary,
            _menu_keyboard(is_admin),
        )
        state_store.clear_state(chat_id)
    elif action == "my_config":
        state.mode = "my_config"
        await _upsert_message(
            callback.bot,
            chat_id,
            "Подготовка конфигурации...",
            _menu_keyboard(is_admin),
        )
        await _send_configs(callback.bot, chat_id, config, callback.from_user.username)
        await show_menu(callback.bot, chat_id, is_admin)
        state_store.clear_state(chat_id)
    elif action and action.startswith("delete_user:"):
        username = action.split(":", 1)[1]
        if not username:
            await callback.answer("Некорректный пользователь.")
            await show_menu(callback.bot, chat_id, is_admin)
            state_store.clear_state(chat_id)
            return
        try:
            delete_user(config, username=username)
        except ValueError as exc:
            await callback.answer(str(exc))
            await show_menu(callback.bot, chat_id, is_admin)
            state_store.clear_state(chat_id)
            return
        await callback.answer(f"Пользователь {username} удалён.")
        await show_menu(callback.bot, chat_id, is_admin)
        state_store.clear_state(chat_id)
        return
    elif action == "back_to_menu":
        await show_menu(callback.bot, chat_id, is_admin)
        state_store.clear_state(chat_id)
        return
    elif action and action.startswith("delete_user_page:"):
        page = _parse_page(action)
        await _show_delete_user_menu(callback.bot, chat_id, config, is_admin, page=page)
        return
    elif action and action.startswith("admin_config_page:"):
        page = _parse_page(action)
        await _show_admin_config_menu(callback.bot, chat_id, config, is_admin, page=page)
        return
    elif action and action.startswith("admin_config_select:"):
        username = action.split(":", 1)[1]
        if not username:
            await callback.answer("Некорректный пользователь.")
            await show_menu(callback.bot, chat_id, is_admin)
            state_store.clear_state(chat_id)
            return
        await _upsert_message(
            callback.bot,
            chat_id,
            f"Готовлю конфиг для {username}...",
            _menu_keyboard(is_admin),
        )
        await _send_configs(callback.bot, chat_id, config, username)
        await show_menu(callback.bot, chat_id, is_admin)
        state_store.clear_state(chat_id)
        return
    await callback.answer()


def _load_rules_summary(config: BotConfig) -> str:
    if not config.rules_file:
        return "Rules: файл rules.toml не задан в конфигурации бота."
    rules = load_rules(config.rules_file)
    return format_rules_summary(rules)


async def handle_text(message: Message, config: BotConfig) -> None:
    chat_id = message.chat.id
    state = state_store.get_state(chat_id)
    if not state.mode:
        await show_menu(message.bot, chat_id, _is_admin(config, message.from_user.id))
        return

    if state.mode == "add_user":
        await _handle_add_user(message, config)
    elif state.mode == "admin_config":
        await _handle_admin_config(message, config)
    else:
        await show_menu(message.bot, chat_id, _is_admin(config, message.from_user.id))


async def _handle_add_user(message: Message, config: BotConfig) -> None:
    username = _extract_username(message)
    if not username:
        await message.answer("Не удалось определить username. Попробуйте ещё раз.")
        return
    password = _generate_password()
    try:
        add_user(config, username=username, password=password)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await message.answer(
        f"Пользователь создан. username={username} пароль={password}"
    )
    await show_menu(message.bot, message.chat.id, True)
    state_store.clear_state(message.chat.id)


async def _handle_admin_config(message: Message, config: BotConfig) -> None:
    username = _normalize_username(message.text or "")
    if not username:
        await message.answer("Введите username (без @).")
        return
    await _send_configs(message.bot, message.chat.id, config, username)
    await show_menu(message.bot, message.chat.id, True)
    state_store.clear_state(message.chat.id)


async def _send_configs(
    bot: Bot,
    chat_id: int,
    config: BotConfig,
    username: str | None,
) -> None:
    if not username:
        await bot.send_message(chat_id=chat_id, text="У пользователя нет username.")
        return
    try:
        endpoint = generate_endpoint_config(config, username=username)
        client_config = generate_client_config_from_bot_config(
            config,
            endpoint_config_path=endpoint.output_path,
        )
        profile = build_connection_profile(endpoint.output_path)
    except (RuntimeError, ValueError) as exc:
        await _send_error(bot, chat_id, f"Ошибка генерации: {exc}")
        return
    await bot.send_document(
        chat_id=chat_id,
        document=FSInputFile(client_config.output_path),
        caption="Скачать CLI Клиент можно здесь: \n https://github.com/TrustTunnel/TrustTunnelClient/releases/latest",
    )
    dns_override = ", ".join(config.dns_upstreams) if config.dns_upstreams else None
    await bot.send_message(
        chat_id=chat_id,
        text="Скачать Android Клиент можно зедсь: \n https://github.com/TrustTunnel/TrustTunnelFlutterClient/releases/latest \n" + format_connection_profile(profile, dns_override=dns_override),
    )


def _extract_username(message: Message) -> str | None:
    if message.forward_from and message.forward_from.username:
        return message.forward_from.username
    if message.forward_from and not message.forward_from.username:
        return f"user_{message.forward_from.id}"
    return _normalize_username(message.text or "")


def _normalize_username(text: str) -> str | None:
    cleaned = text.strip()
    if cleaned.startswith("@"):
        cleaned = cleaned[1:]
    if not cleaned:
        return None
    if " " in cleaned:
        return None
    return cleaned


def _generate_password() -> str:
    return secrets.token_urlsafe(12)


def _build_paginated_user_keyboard(
    usernames: list[str],
    *,
    action_prefix: str,
    page_prefix: str,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=username, callback_data=f"{action_prefix}:{username}")]
        for username in usernames
    ]
    navigation: list[InlineKeyboardButton] = []
    if total_pages > 1:
        if page > 1:
            navigation.append(
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=f"{page_prefix}:{page - 1}",
                )
            )
        if page < total_pages:
            navigation.append(
                InlineKeyboardButton(
                    text="➡️ Вперёд",
                    callback_data=f"{page_prefix}:{page + 1}",
                )
            )
    if navigation:
        buttons.append(navigation)
    buttons.append([InlineKeyboardButton(text="↩️ В меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _paginate_usernames(config: BotConfig, page: int) -> tuple[list[str], int, int]:
    usernames = list_users(config)
    total = len(usernames)
    if total == 0:
        return [], 0, 0
    total_pages = (total + USER_LIST_PAGE_SIZE - 1) // USER_LIST_PAGE_SIZE
    page = max(1, min(page, total_pages))
    start = (page - 1) * USER_LIST_PAGE_SIZE
    end = start + USER_LIST_PAGE_SIZE
    return usernames[start:end], page, total_pages


async def _show_delete_user_menu(
    bot: Bot,
    chat_id: int,
    config: BotConfig,
    is_admin: bool,
    *,
    page: int,
) -> None:
    usernames, current_page, total_pages = _paginate_usernames(config, page)
    if not usernames:
        await _upsert_message(
            bot,
            chat_id,
            "Нет пользователей для удаления.",
            _menu_keyboard(is_admin),
        )
        return
    keyboard = _build_paginated_user_keyboard(
        usernames,
        action_prefix="delete_user",
        page_prefix="delete_user_page",
        page=current_page,
        total_pages=total_pages,
    )
    await _upsert_message(
        bot,
        chat_id,
        "Выберите пользователя для удаления.",
        keyboard,
    )


async def _show_admin_config_menu(
    bot: Bot,
    chat_id: int,
    config: BotConfig,
    is_admin: bool,
    *,
    page: int,
) -> None:
    usernames, current_page, total_pages = _paginate_usernames(config, page)
    if not usernames:
        await _upsert_message(
            bot,
            chat_id,
            "Нет пользователей для выдачи конфига.",
            _menu_keyboard(is_admin),
        )
        return
    keyboard = _build_paginated_user_keyboard(
        usernames,
        action_prefix="admin_config_select",
        page_prefix="admin_config_page",
        page=current_page,
        total_pages=total_pages,
    )
    await _upsert_message(
        bot,
        chat_id,
        "Выберите пользователя для выдачи конфига.",
        keyboard,
    )


def _parse_page(action: str) -> int:
    page_str = action.split(":", 1)[1] if ":" in action else ""
    try:
        return int(page_str)
    except ValueError:
        return 1


async def _send_error(bot: Bot, chat_id: int, text: str) -> None:
    max_len = 3900
    cleaned = text.replace("\r", "")
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 1] + "…"
    await bot.send_message(chat_id=chat_id, text=cleaned)
    if len(text) > max_len:
        error_path = Path(tempfile.gettempdir()) / "trusttunnel_error.txt"
        error_path.write_text(text, encoding="utf-8")
        await bot.send_document(chat_id=chat_id, document=FSInputFile(error_path))


def build_dispatcher(config: BotConfig) -> Dispatcher:
    dispatcher = Dispatcher()
    async def _start(message: Message) -> None:
        await handle_start(message, config)

    async def _menu(message: Message) -> None:
        await handle_start(message, config)

    async def _callback(callback: CallbackQuery) -> None:
        await handle_callback(callback, config)

    async def _text(message: Message) -> None:
        await handle_text(message, config)

    dispatcher.message.register(_start, Command("start"))
    dispatcher.message.register(_menu, Command("menu"))
    dispatcher.callback_query.register(_callback)
    dispatcher.message.register(_text, F.text | F.forward_from | F.forward_sender_name)
    return dispatcher


def _load_bot_config() -> BotConfig:
    config_path = Path("bot.toml")
    return load_config(config_path)


def _ensure_bot_config(config: BotConfig) -> None:
    if not config.telegram_token:
        raise RuntimeError("telegram_token must be set in bot.toml")
    if not config.admin_ids:
        raise RuntimeError("admin_ids must be set in bot.toml")


def run_bot() -> None:
    config = _load_bot_config()
    _ensure_bot_config(config)

    async def _runner() -> None:
        bot = Bot(
            token=config.telegram_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        dispatcher = build_dispatcher(config)
        await dispatcher.start_polling(bot)

    asyncio.run(_runner())


if __name__ == "__main__":
    run_bot()
