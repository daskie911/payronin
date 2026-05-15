"""
Вспомогательные утилиты.
"""
from __future__ import annotations
import re
import logging
from aiogram import Bot
from aiogram.types import ChatMemberAdministrator, ChatMemberOwner

from database import get_user_id_by_username

logger = logging.getLogger(__name__)


async def resolve_user_id(bot: Bot, raw: str, chat_id: int) -> int | None:
    """
    Пытается получить числовой user_id из строки.
    Принимает: числовой ID, @username.
    
    Порядок поиска:
    1. Если число — возвращаем сразу
    2. Ищем в локальном кэше username_cache (БД)
    3. Пробуем Telegram API getChat(@username)
    """
    raw = raw.strip().lstrip("@")

    # 1. Числовой ID
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)

    # 2. Кэш в БД (username → user_id) — самый надёжный способ
    cached = await get_user_id_by_username(raw)
    if cached:
        return cached

    # 3. Telegram API getChat — работает не для всех пользователей
    try:
        chat = await bot.get_chat(f"@{raw}")
        return chat.id
    except Exception:
        pass

    return None


async def bot_is_admin(bot: Bot, chat_id: int) -> bool:
    """Проверить, является ли бот администратором в чате."""
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id, me.id)
        return isinstance(member, (ChatMemberAdministrator, ChatMemberOwner))
    except Exception:
        return False


async def user_is_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    """Проверить, является ли пользователь админом/владельцем."""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return isinstance(member, (ChatMemberAdministrator, ChatMemberOwner))
    except Exception:
        return False


async def user_is_member(bot: Bot, chat_id: int, user_id: int) -> bool:
    """Проверить, есть ли пользователь в чате."""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status not in ("left", "kicked")
    except Exception:
        return False


def format_stars(amount: int) -> str:
    return f"{amount} ⭐"
