from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
import secrets
from typing import Callable

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
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
from trusttunel_bot.user_management import add_user, delete_user


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
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=keyboard,
        )
        return
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
        state.mode = "delete_user"
        await _upsert_message(
            callback.bot,
            chat_id,
            "Введите username для удаления (без @).",
            _menu_keyboard(is_admin),
        )
    elif action == "admin_config":
        state.mode = "admin_config"
        await _upsert_message(
            callback.bot,
            chat_id,
            "Введите username, для которого нужен конфиг.",
            _menu_keyboard(is_admin),
        )
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
    elif state.mode == "delete_user":
        await _handle_delete_user(message, config)
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


async def _handle_delete_user(message: Message, config: BotConfig) -> None:
    username = _normalize_username(message.text or "")
    if not username:
        await message.answer("Введите username (без @).")
        return
    try:
        delete_user(config, username=username)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await message.answer(f"Пользователь {username} удалён.")
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
        await bot.send_message(chat_id=chat_id, text=f"Ошибка генерации: {exc}")
        return
    await bot.send_document(chat_id=chat_id, document=FSInputFile(endpoint.output_path))
    await bot.send_document(chat_id=chat_id, document=FSInputFile(client_config.output_path))
    await bot.send_message(chat_id=chat_id, text=format_connection_profile(profile))


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


def build_dispatcher(config: BotConfig) -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.message.register(lambda message: handle_start(message, config), Command("start"))
    dispatcher.message.register(lambda message: handle_start(message, config), Command("menu"))
    dispatcher.callback_query.register(lambda callback: handle_callback(callback, config))
    dispatcher.message.register(
        lambda message: handle_text(message, config),
        F.text | F.forward_from | F.forward_sender_name,
    )
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
