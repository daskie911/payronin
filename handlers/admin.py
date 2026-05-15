"""
Админ-панель бота.
/admin → 📊 Статистика, 👥 Пользователи, ⭐ Выдать звёзды, 💰 Цены.
"""
from __future__ import annotations

import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMINS, GROUP_ID, SERVICES, PRICES, DURATION_LABELS
from keyboards.inline import admin_menu_kb, admin_back_kb, admin_prices_kb
from database import (
    get_all_users, get_users_count, get_total_stars, get_total_revenue,
    get_purchases_count, get_user, ensure_user, add_balance,
)
from utils import bot_is_admin, format_stars

logger = logging.getLogger(__name__)
router = Router()


class AdminState(StatesGroup):
    waiting_give_stars = State()
    waiting_price_edit = State()


def is_admin(user_id: int) -> bool:
    return user_id in ADMINS


# ── /admin ───────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к админ-панели.")
        return
    await state.clear()
    await message.answer(
        "🔐 <b>Админ-панель</b>\n\nВыберите действие:",
        reply_markup=admin_menu_kb(),
    )


@router.callback_query(F.data == "adm:menu")
async def adm_menu(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("⛔ Нет доступа", show_alert=True)
        return
    await state.clear()
    await call.message.edit_text(
        "🔐 <b>Админ-панель</b>\n\nВыберите действие:",
        reply_markup=admin_menu_kb(),
    )
    await call.answer()


# ── 📊 Статистика ────────────────────────────────────────────

@router.callback_query(F.data == "adm:stats")
async def adm_stats(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        await call.answer("⛔ Нет доступа", show_alert=True)
        return

    users_count = await get_users_count()
    total_stars = await get_total_stars()
    total_revenue = await get_total_revenue()
    purchases_count = await get_purchases_count()
    is_bot_admin = await bot_is_admin(bot, GROUP_ID)

    try:
        chat = await bot.get_chat(GROUP_ID)
        chat_title = chat.title or "—"
    except Exception:
        chat_title = "❌ Не удалось получить"

    text = (
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 <b>Пользователей:</b> {users_count}\n"
        f"⭐ <b>Общий баланс:</b> {format_stars(total_stars)}\n"
        f"💰 <b>Потрачено на услуги:</b> {format_stars(total_revenue)}\n"
        f"🛒 <b>Покупок:</b> {purchases_count}\n\n"
        f"💬 <b>Группа:</b> {chat_title}\n"
        f"🤖 <b>Бот — админ:</b> {'✅' if is_bot_admin else '❌'}"
    )
    await call.message.edit_text(text, reply_markup=admin_back_kb())
    await call.answer()


# ── 👥 Все пользователи ──────────────────────────────────────

@router.callback_query(F.data == "adm:users")
async def adm_users(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("⛔ Нет доступа", show_alert=True)
        return

    users = await get_all_users()
    if not users:
        await call.message.edit_text(
            "👥 <b>Пользователи</b>\n\nПока нет ни одного пользователя.",
            reply_markup=admin_back_kb(),
        )
        await call.answer()
        return

    lines = ["👥 <b>Все пользователи</b>\n"]
    for i, u in enumerate(users[:50], 1):
        username = f"@{u['username']}" if u.get("username") else "—"
        name = u.get("first_name") or "—"
        lines.append(
            f"{i}. <code>{u['user_id']}</code> | "
            f"{name} ({username}) | "
            f"{format_stars(u['balance'])}"
        )

    if len(users) > 50:
        lines.append(f"\n<i>…и ещё {len(users) - 50}</i>")

    await call.message.edit_text("\n".join(lines), reply_markup=admin_back_kb())
    await call.answer()


# ── ⭐ Выдать звёзды ─────────────────────────────────────────

@router.callback_query(F.data == "adm:give_stars")
async def adm_give_stars_prompt(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminState.waiting_give_stars)
    await call.message.edit_text(
        "⭐ <b>Выдать звёзды</b>\n\n"
        "Отправьте сообщение в формате:\n"
        "<code>USER_ID КОЛИЧЕСТВО</code>\n\n"
        "Примеры:\n"
        "• <code>123456789 100</code> — выдать 100 ⭐\n"
        "• <code>123456789 -50</code> — забрать 50 ⭐",
        reply_markup=admin_back_kb(),
    )
    await call.answer()


@router.message(AdminState.waiting_give_stars)
async def adm_give_stars_process(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    parts = (message.text or "").strip().split()
    if len(parts) != 2:
        await message.answer(
            "❌ Формат: <code>USER_ID КОЛИЧЕСТВО</code>\n"
            "Например: <code>123456789 100</code>"
        )
        return

    try:
        target_id = int(parts[0])
        amount = int(parts[1])
    except ValueError:
        await message.answer("❌ USER_ID и КОЛИЧЕСТВО должны быть числами.")
        return

    user = await get_user(target_id)
    if not user:
        await ensure_user(target_id)

    new_balance = await add_balance(target_id, amount)
    action = "выдано" if amount >= 0 else "забрано"

    await message.answer(
        f"✅ <b>Готово!</b>\n\n"
        f"👤 Пользователь: <code>{target_id}</code>\n"
        f"⭐ {action.capitalize()}: <b>{abs(amount)}</b> ⭐\n"
        f"💰 Новый баланс: <b>{format_stars(new_balance)}</b>",
        reply_markup=admin_back_kb(),
    )
    await state.clear()


# ── 💰 Изменить цены ─────────────────────────────────────────

@router.callback_query(F.data == "adm:prices")
async def adm_prices(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("⛔ Нет доступа", show_alert=True)
        return
    await call.message.edit_text(
        "💰 <b>Изменение цен</b>\n\nВыберите услугу:",
        reply_markup=admin_prices_kb(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:price:"))
async def adm_price_detail(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("⛔ Нет доступа", show_alert=True)
        return

    service_key = call.data.split(":")[2]
    svc_info = SERVICES.get(service_key)
    if not svc_info:
        await call.answer("Услуга не найдена", show_alert=True)
        return

    name, emoji, _ = svc_info
    prices = PRICES.get(service_key, {})

    lines = [f"{emoji} <b>{name} — текущие цены:</b>\n"]
    for dur_key, price in prices.items():
        dur_label = DURATION_LABELS.get(dur_key, dur_key)
        lines.append(f"  <code>{dur_key}</code> ({dur_label}) → <b>{price}</b> ⭐")
    lines.append(
        "\n\nЧтобы изменить, отправьте:\n<code>СРОК ЦЕНА</code>\n"
        "Например: <code>1h 10</code>"
    )

    await state.set_state(AdminState.waiting_price_edit)
    await state.update_data(edit_service=service_key)
    await call.message.edit_text("\n".join(lines), reply_markup=admin_back_kb())
    await call.answer()


@router.message(AdminState.waiting_price_edit)
async def adm_price_edit_process(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    service_key = data.get("edit_service", "")
    prices = PRICES.get(service_key)
    if prices is None:
        await message.answer("❌ Услуга не найдена.")
        await state.clear()
        return

    parts = (message.text or "").strip().split()
    if len(parts) != 2:
        await message.answer("❌ Формат: <code>СРОК ЦЕНА</code>")
        return

    dur_key = parts[0]
    try:
        new_price = int(parts[1])
    except ValueError:
        await message.answer("❌ Цена должна быть числом.")
        return

    if new_price < 1:
        await message.answer("❌ Цена должна быть ≥ 1.")
        return

    if dur_key not in prices:
        valid = ", ".join(f"<code>{k}</code>" for k in prices.keys())
        await message.answer(f"❌ Неизвестный срок. Доступные: {valid}")
        return

    old_price = prices[dur_key]
    prices[dur_key] = new_price
    svc_info = SERVICES.get(service_key, ("?", "?", "?"))
    dur_label = DURATION_LABELS.get(dur_key, dur_key)

    await message.answer(
        f"✅ <b>Цена обновлена!</b>\n\n"
        f"🏷 {svc_info[1]} {svc_info[0]}\n"
        f"🕐 {dur_label}\n"
        f"💰 {old_price} ⭐ → <b>{new_price} ⭐</b>\n\n"
        f"<i>⚠️ Действует до перезапуска бота</i>",
        reply_markup=admin_back_kb(),
    )
    await state.clear()


# ── /status и /check ─────────────────────────────────────────

@router.message(Command("status"))
async def cmd_status(message: Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    is_bot_admin = await bot_is_admin(bot, GROUP_ID)
    try:
        chat = await bot.get_chat(GROUP_ID)
        chat_title = chat.title
    except Exception:
        chat_title = "❌ Не удалось получить"
    me = await bot.get_me()
    await message.answer(
        f"🤖 <b>Статус</b>\n\n"
        f"Бот: @{me.username}\n"
        f"Группа: {chat_title} (<code>{GROUP_ID}</code>)\n"
        f"Админ: {'✅' if is_bot_admin else '❌'}",
        reply_markup=admin_menu_kb(),
    )


@router.message(Command("check"))
async def cmd_check(message: Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(GROUP_ID, me.id)
        rights = []
        for attr, label in [
            ("can_restrict_members", "Ограничение участников"),
            ("can_pin_messages", "Закреп сообщений"),
            ("can_change_info", "Изменение информации"),
            ("can_promote_members", "Повышение участников"),
            ("can_delete_messages", "Удаление сообщений"),
        ]:
            has = getattr(member, attr, False)
            rights.append(f"{'✅' if has else '❌'} {label}")
        text = "🔑 <b>Права бота:</b>\n\n" + "\n".join(rights)
    except Exception as e:
        text = f"❌ Ошибка: {e}"
    await message.answer(text, reply_markup=admin_back_kb())
