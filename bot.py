# -*- coding: utf-8 -*-
import asyncio
import logging
import random
import re
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery, ChatPermissions

TOKEN = "8653536551:AAHjQEJeJWV4imu1QDdrwDZo_nzjzGTF8l8"
CREATOR_ID = 6169192086   # Твой Telegram ID (Уровень 4 - Создатель)

logging.basicConfig(level=logging.INFO)
router = Router()

# ==================== ПАТЧ БЕЗОПАСНОСТИ: ТРОЛЛИНГ СЕПАРАТИСТОВ ====================
OFFICIAL_CHAT_ID = -1004376675428  # Официальная территория экосистемы

@router.message(F.chat.type.in_({"group", "supergroup"}))
async def unlicensed_chat_guard(message: Message, bot: Bot):
    # Если это наш официальный чат — пропускаем дальше
    if message.chat.id == OFFICIAL_CHAT_ID:
        return

    # Пресекаем попытки бунта и несанкционированной самодеятельности в чужих чатах
    if message.text and message.text.startswith("/"):
        await message.reply(
            "🛑 **Доступ запрещен!**\n"
            "Решили устроить независимый подвал? Забудьте. Все полноценные игры в Мафию, "
            "прогрессия и единая экосистема функционируют исключительно под управлением центра в элитном "
            "чате **AmongUsEHRMODDED**.\n\n"
            "Хватит страдать в изгнании на пустых осколках — возвращайтесь к нормальной жизни: t.me/AmongUsEHRMODDED",
            parse_mode="Markdown"
        )
        
        # Инспектор удаляется из нелицензированного лагеря бунтовщиков
        try:
            await bot.leave_chat(message.chat.id)
        except Exception:
            pass
        
        return
# ======================================================================================

# ==================== БАЗА УРОВНЕЙ МОДЕРАТОРА ====================
MODERATOR_LEVELS = {
    CREATOR_ID: 4
}

def parse_time(time_str: str) -> int:
    match = re.match(r"^(\d+)([mhd])$", time_str)
    if not match:
        return 0
    amount, unit = int(match.group(1)), match.group(2)
    if unit == "m":
        return amount * 60
    elif unit == "h":
        return amount * 3600
    elif unit == "d":
        return amount * 86400
    return 0

def get_user_level(user_id: int) -> int:
    if user_id == CREATOR_ID:
        return 4
    return MODERATOR_LEVELS.get(user_id, 0)

# ==================== КОМАНДЫ МОДЕРАЦИИ И ИЕРАРХИЯ ====================

@router.message(Command("setlevel"))
async def cmd_setlevel(message: Message):
    actor_level = get_user_level(message.from_user.id)
    if actor_level < 3:
        await message.reply("⛔ Недостаточно прав. Назначать уровни могут только Главмодеры и Создатель.")
        return

    if not message.reply_to_message:
        await message.reply("📌 Эту команду нужно использовать ответом на сообщение пользователя.")
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.reply("⚙️ Укажите уровень от 0 до 3. Пример: `/setlevel 2`", parse_mode="Markdown")
        return

    new_level = int(args[1])
    if new_level > 3 and actor_level != 4:
        await message.reply("❌ Вы не можете назначить уровень выше своего или выдать Создателя.")
        return

    target_user = message.reply_to_message.from_user
    if target_user.id == CREATOR_ID:
        await message.reply("⚠️ Нельзя изменить уровень Создателя системы.")
        return

    MODERATOR_LEVELS[target_user.id] = new_level
    level_names = {0: "Участник", 1: "Младший модератор", 2: "Старший модератор", 3: "Главный модератор"}
    await message.answer(
        f"✅ Пользователю **{target_user.full_name}** присвоен ранг: *{level_names.get(new_level, 'Неизвестно')}* (Уровень {new_level})",
        parse_mode="Markdown"
    )

@router.message(Command("warn"))
async def cmd_warn(message: Message):
    if get_user_level(message.from_user.id) < 1:
        await message.reply("⛔ Требуется как минимум 1-й уровень модерации (Мл. модератор).")
        return

    if not message.reply_to_message:
        await message.reply("📌 Ответьте на сообщение нарушителя для выдачи предупреждения.")
        return

    target_user = message.reply_to_message.from_user
    await message.answer(f"⚠️ **Внимание!** Пользователь **{target_user.full_name}** получил предупреждение от модератора.", parse_mode="Markdown")

@router.message(Command("mute"))
async def cmd_mute(message: Message, bot: Bot):
    if get_user_level(message.from_user.id) < 2:
        await message.reply("⛔ Требуется 2-й уровень модерации (Старший модератор).")
        return

    if not message.reply_to_message:
        await message.reply("📌 Ответьте на сообщение пользователя, которого нужно замутить.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply("⏱ Укажите время мута. Пример: `/mute 30m` (минуты), `/mute 2h` (часы)", parse_mode="Markdown")
        return

    duration = parse_time(args[1])
    if duration == 0:
        await message.reply("❌ Неверный формат времени. Используйте суффиксы `m`, `h` или `d`.")
        return

    target_user = message.reply_to_message.from_user
    try:
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target_user.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=datetime.now() + timedelta(seconds=duration)
        )
        await message.answer(f"🔇 Пользователь **{target_user.full_name}** лишен права голоса на `{args[1]}`.", parse_mode="Markdown")
    except Exception:
        await message.reply("❌ Ошибка: возможно, целевой пользователь является администратором чата.")

@router.message(Command("unmute"))
async def cmd_unmute(message: Message, bot: Bot):
    if get_user_level(message.from_user.id) < 2:
        await message.reply("⛔ Требуется 2-й уровень модерации.")
        return

    if not message.reply_to_message:
        await message.reply("📌 Ответьте на сообщение пользователя для снятия мута.")
        return

    target_user = message.reply_to_message.from_user
    try:
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target_user.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        await message.answer(f"🔊 С пользователя **{target_user.full_name}** сняты ограничения голоса.", parse_mode="Markdown")
    except Exception:
        await message.reply("❌ Не удалось снять мут.")

@router.message(Command("ban"))
async def cmd_ban(message: Message, bot: Bot):
    if get_user_level(message.from_user.id) < 3:
        await message.reply("⛔ Доступно только Главмодераторам и Создателю (3-й уровень).")
        return

    if not message.reply_to_message:
        await message.reply("📌 Ответьте на сообщение нарушителя для изгнания.")
        return

    target_user = message.reply_to_message.from_user
    try:
        await bot.ban_chat_member(chat_id=message.chat.id, user_id=target_user.id)
        await message.answer(f"🔨 Пользователь **{target_user.full_name}** изгнан из чата.", parse_mode="Markdown")
    except Exception:
        await message.reply("❌ Ошибка бана. Проверьте права администратора у бота.")

@router.message(Command("unban"))
async def cmd_unban(message: Message, bot: Bot):
    if get_user_level(message.from_user.id) < 3:
        await message.reply("⛔ Требуется 3-й уровень модерации.")
        return

    if not message.reply_to_message:
        await message.reply("📌 Ответьте на сообщение пользователя для разбана.")
        return

    target_user = message.reply_to_message.from_user
    try:
        await bot.unban_chat_member(chat_id=message.chat.id, user_id=target_user.id, only_if_banned=True)
        await message.answer(f"🔓 Пользователь **{target_user.full_name}** амнистирован.", parse_mode="Markdown")
    except Exception:
        await message.reply("❌ Не удалось разбанить пользователя.")

# ==================== СИСТЕМА НАСТРОЕК (SETTINGS MENU) ====================

# Дефолтные настройки по умолчанию
BOT_SETTINGS = {
    "mute_default": "1h",       # По умолчанию мут на 1 час
    "ban_default": "1d",        # По умолчанию бан на 1 день
    "warn_limit": 3             # Лимит варнов до автоматического бана
}

class SettingsStates(StatesGroup):
    menu = State()

# Главная команда /settings (Только ЛС, уровень >= 3)
@router.message(Command("settings"))
async def cmd_settings(message: Message, state: FSMContext):
    if message.chat.type != "private":
        await message.reply("🔒 Настройки экосистемы доступны только в Личных сообщениях с ботом для обеспечения безопасности.")
        return

    actor_level = get_user_level(message.from_user.id)
    if actor_level < 3:
        await message.reply("⛔ Недостаточно прав. Меню настроек доступно только Главмодераторам и Создателю.")
        return

    await state.set_state(SettingsStates.menu)
    await show_settings_main_menu(message)

async def show_settings_main_menu(message: Message, edit: bool = False):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔇 Мут по умолчанию: {BOT_SETTINGS['mute_default']}", callback_data="set_menu:mute")],
        [InlineKeyboardButton(text=f"🔨 Бан по умолчанию: {BOT_SETTINGS['ban_default']}", callback_data="set_menu:ban")],
        [InlineKeyboardButton(text=f"⚠️ Лимит варнов до бана: {BOT_SETTINGS['warn_limit']}", callback_data="set_menu:warn")],
        [InlineKeyboardButton(text="❌ Закрыть меню", callback_data="set_menu:close")]
    ])
    
    text = "⚙️ **Панель управления и настроек экосистемы**\nВыберите параметр для изменения:"
    if edit:
        await message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="Markdown")

# Навигация по меню настроек через Callback
@router.callback_query(F.data.startswith("set_menu:"))
async def cb_settings_navigation(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    
    if action == "close":
        await callback.message.delete()
        await state.clear()
        await callback.answer("Меню закрыто.")
        return

    if action == "main":
        await show_settings_main_menu(callback.message, edit=True)
        await callback.answer()
        return

    if action == "mute":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="1 час", callback_data="set_val:mute:1h"), InlineKeyboardButton(text="12 часов", callback_data="set_val:mute:12h")],
            [InlineKeyboardButton(text="1 день", callback_data="set_val:mute:1d"), InlineKeyboardButton(text="3 дня", callback_data="set_val:mute:3d")],
            [InlineKeyboardButton(text="1 неделя", callback_data="set_val:mute:1w"), InlineKeyboardButton(text="30 дней", callback_data="set_val:mute:30d")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="set_menu:main")]
        ])
        await callback.message.edit_text("⏱ **Выберите стандартный срок мута:**", reply_markup=kb, parse_mode="Markdown")

    elif action == "ban":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="1 час", callback_data="set_val:ban:1h"), InlineKeyboardButton(text="12 часов", callback_data="set_val:ban:12h")],
            [InlineKeyboardButton(text="1 день", callback_data="set_val:ban:1d"), InlineKeyboardButton(text="3 дня", callback_data="set_val:ban:3d")],
            [InlineKeyboardButton(text="1 неделя", callback_data="set_val:ban:1w"), InlineKeyboardButton(text="30 дней", callback_data="set_val:ban:30d")],
            [InlineKeyboardButton(text="♾ Навсегда", callback_data="set_val:ban:forever")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="set_menu:main")]
        ])
        await callback.message.edit_text("⏱ **Выберите стандартный срок бана:**", reply_markup=kb, parse_mode="Markdown")

    elif action == "warn":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="2", callback_data="set_val:warn:2"),
                InlineKeyboardButton(text="3", callback_data="set_val:warn:3"),
                InlineKeyboardButton(text="4", callback_data="set_val:warn:4"),
                InlineKeyboardButton(text="5", callback_data="set_val:warn:5")
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="set_menu:main")]
        ])
        await callback.message.edit_text("⚠️ **Выберите лимит варнов до автоматического бана:**", reply_markup=kb, parse_mode="Markdown")
    
    await callback.answer()

# Сохранение выбранных значений
@router.callback_query(F.data.startswith("set_val:"))
async def cb_settings_save(callback: CallbackQuery):
    _, category, value = callback.data.split(":")
    
    if category == "mute":
        BOT_SETTINGS["mute_default"] = value
        await callback.answer(f"✅ Мут по умолчанию изменен на: {value}")
    elif category == "ban":
        BOT_SETTINGS["ban_default"] = value
        await callback.answer(f"✅ Бан по умолчанию изменен на: {value}")
    elif category == "warn":
        BOT_SETTINGS["warn_limit"] = int(value)
        await callback.answer(f"✅ Лимит варнов изменен на: {value}")

    await show_settings_main_menu(callback.message, edit=True)


# ==================== ИГРОВАЯ ЛОГИКА: МАФИЯ ====================

class GameState(StatesGroup):
    lobby = State()
    night = State()
    day_discussion = State()
    day_voting = State()

game = {
    "active": False,
    "phase": "lobby",
    "players": {},       # user_id: {"name": str, "role": str, "alive": bool, "has_acted": bool}
    "night_actions": {}, 
    "votes": {},         
    "sheriff_id": None,
    "deputy_id": None,
    "doctor_id": None,
    "intern_id": None,
    "mafia_ids": [],
    "maniac_id": None,
    "night_id": 0
}

MIN_PLAYERS = 4
LOBBY_TIMEOUT = 120
NIGHT_TIMEOUT = 45      
DISCUSSION_TIMEOUT = 45 
VOTING_TIMEOUT = 30     

def get_join_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 1. Написать боту в ЛС (активация)", url="https://t.me/MyServerMafiaBot?start=join")],
        [InlineKeyboardButton(text="🎮 2. Войти в игру", callback_data="join")]
    ])

@router.message(Command("start"))
async def cmd_start(message: Message, bot: Bot):
    if message.chat.type == "private":
        await message.answer("✅ **Бот успешно активирован в ЛС!** Теперь вы будете получать сюда свои роли и ночные меню во время игры в группе.", parse_mode="Markdown")
    else:
        await message.answer("👋 Бот-модератор и Мафия готовы к работе! Наберите /create_game для запуска лобби.")

@router.message(Command("create_game"))
async def cmd_create_game(message: Message, state: FSMContext):
    if message.chat.type in ["group", "supergroup"]:
        try:
            member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
            if member.status not in ["administrator", "creator"]:
                await message.reply("⛔ Создавать лобби могут только администраторы чата.")
                return
        except Exception:
            pass

    if game["active"]:
        await message.answer("⚠️ Игра уже запущена!")
        return

    game["active"] = True
    game["phase"] = "lobby"
    game["players"] = {}
    game["night_actions"] = {}
    game["votes"] = {}
    game["sheriff_id"] = None
    game["deputy_id"] = None
    game["doctor_id"] = None
    game["intern_id"] = None
    game["mafia_ids"] = []
    game["maniac_id"] = None
    game["night_id"] = 0

    await state.set_state(GameState.lobby)

    await message.answer(
        f"🎲 **Лобби Мафии открыто!**\n"
        f"⏰ Сбор: {LOBBY_TIMEOUT // 60} мин. | Мин. игроков: {MIN_PLAYERS}\n\n"
        f"📌 *ВАЖНО:* Нажмите кнопку №1, чтобы бот смог писать вам роли в ЛС!",
        reply_markup=get_join_keyboard(),
        parse_mode="Markdown"
    )

    asyncio.create_task(lobby_timer(message.bot, message.chat.id, state))

@router.message(Command("stop_game"))
async def cmd_stop_game(message: Message, state: FSMContext):
    game["active"] = False
    game["players"].clear()
    await state.clear()
    await message.answer("🛑 Игра принудительно остановлена.")

@router.callback_query(F.data == "join")
async def cb_join_game(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_name = callback.from_user.first_name

    if not game["active"]:
        await callback.answer("⚠️ Лобби закрыто!", show_alert=True)
        return

    if user_id in game["players"]:
        await callback.answer("Вы уже в игре!", show_alert=True)
        return

    game["players"][user_id] = {
        "name": user_name,
        "role": None,
        "alive": True,
        "has_acted": False
    }
    
    await callback.answer(f"Успешно! Игроков: {len(game['players'])}")
    
    try:
        await callback.message.edit_text(
            f"🎲 Лобби Мафии открыто!\n"
            f"👥 Участников: **{len(game['players'])}** (мин. {MIN_PLAYERS})\n\n"
            f"📌 Нажмите кнопку 1 для активации в ЛС перед стартом!",
            reply_markup=callback.message.reply_markup,
            parse_mode="Markdown"
        )
    except Exception:
        pass

async def lobby_timer(bot: Bot, chat_id: int, state: FSMContext):
    await asyncio.sleep(LOBBY_TIMEOUT)
    if game["active"] and len(game["players"]) < MIN_PLAYERS:
        await bot.send_message(chat_id, f"⌛ Недостаточно игроков (нужно минимум {MIN_PLAYERS}). Игра отменена.")
        game["active"] = False
        game["players"].clear()
        await state.clear()
    elif game["active"]:
        await bot.send_message(chat_id, "🚀 Время вышло! Начинаем партию!")
        await run_game_start(chat_id, state, bot)

async def notify_team(bot: Bot, user_ids: list, message_text: str):
    for uid in user_ids:
        if uid and game["players"].get(uid, {}).get("alive", False):
            try:
                await bot.send_message(uid, message_text, parse_mode="Markdown")
            except Exception:
                pass

async def run_game_start(chat_id: int, state: FSMContext, bot: Bot):
    p_ids = list(game["players"].keys())
    total_players = len(p_ids)
    random.shuffle(p_ids)
    
    mafia_count = max(1, total_players // 4)
    don_count = 1 if mafia_count >= 2 else 0
    simple_mafia_count = mafia_count - don_count

    roles_pool = []
    if don_count > 0:
        roles_pool.append("Дон Мафии")
    for _ in range(simple_mafia_count):
        roles_pool.append("Мафия")

    roles_pool.append("Шериф")
    if total_players >= 8:
        roles_pool.append("Депути")

    roles_pool.append("Доктор")
    if total_players >= 8:
        roles_pool.append("Интерн")

    roles_pool.append("Путана")
    
    if total_players >= 5:
        roles_pool.append("Маньяк")

    while len(roles_pool) < total_players:
        roles_pool.append("Мирный житель")

    random.shuffle(roles_pool)

    for i, uid in enumerate(p_ids):
        assigned_role = roles_pool[i]
        game["players"][uid]["role"] = assigned_role
        game["players"][uid]["has_acted"] = False
        
        if assigned_role == "Шериф":
            game["sheriff_id"] = uid
        elif assigned_role == "Депути":
            game["deputy_id"] = uid
        elif assigned_role == "Доктор":
            game["doctor_id"] = uid
        elif assigned_role == "Интерн":
            game["intern_id"] = uid
        elif assigned_role in ["Дон Мафии", "Мафия"]:
            game["mafia_ids"].append(uid)
        elif assigned_role == "Маньяк":
            game["maniac_id"] = uid

    await start_night_phase(bot, chat_id, state)

async def night_timer(bot: Bot, chat_id: int, state: FSMContext, night_id: int):
    try:
        await asyncio.sleep(NIGHT_TIMEOUT)
    except asyncio.CancelledError:
        return
    
    if game.get("active") and game.get("phase") == "night" and game.get("night_id") == night_id:
        await bot.send_message(
            chat_id,
            "⏰ **Время ночи истекло!** Подводим итоги ночи...",
            parse_mode="Markdown"
        )
        await resolve_night_phase(chat_id, state, bot)

async def start_night_phase(bot: Bot, chat_id: int, state: FSMContext):
    game["phase"] = "night"
    game["night_id"] = game.get("night_id", 0) + 1
    game["night_actions"] = {}

    for uid, pdata in game["players"].items():
        pdata["has_acted"] = False

    await state.set_state(GameState.night)
    
    try:
        await bot.send_message(
            chat_id, 
            "🌙 **Наступила ночь.**\n"
            f"У ночных ролей есть **{NIGHT_TIMEOUT} секунд** на ход. Общий чат закрыт.", 
            parse_mode="Markdown"
        )
    except Exception:
        pass
    
    for uid, pdata in game["players"].items():
        if pdata["alive"]:
            role = pdata["role"]
            text = f"🕵️‍♂️ Твоя роль: **{role}**\n"
            if role == "Маньяк":
                text += "🔪 Цель: устранить всех и остаться последним выжившим!"
            elif role == "Путана":
                text += "💋 Заблокируй ночное действие игрока."
            elif role == "Шериф":
                text += "🤠 Проверяй игроков или делай выстрел."

            try:
                await bot.send_message(uid, text, parse_mode="Markdown")
                await send_night_menu(bot, uid, role)
            except Exception:
                await bot.send_message(
                    chat_id, 
                    f"⚠️ Игрок **{pdata['name']}** не активировал бота в ЛС и пропускает свой ход!"
                )
                pdata["has_acted"] = True

    asyncio.create_task(night_timer(bot, chat_id, state, game["night_id"]))

@router.message(F.chat.type.in_({"group", "supergroup"}))
async def global_chat_filter(message: Message, bot: Bot):
    if not game.get("active"):
        return
    
    user_id = message.from_user.id
    if user_id in game["players"]:
        if not game["players"][user_id]["alive"]:
            try:
                await message.delete()
            except Exception:
                pass
            return
        
        if game.get("phase") == "night":
            try:
                await message.delete()
            except Exception:
                pass

@router.message(GameState.night, F.text, F.chat.type == "private")
async def night_faction_secret_chat(message: Message, bot: Bot):
    user_id = message.from_user.id
    if user_id not in game["players"] or not game["players"][user_id]["alive"]:
        return

    player_data = game["players"][user_id]
    player_role = player_data["role"]
    sender_name = player_data["name"]
    
    target_recipients = []
    prefix = ""
    
    if player_role in ["Мафия", "Дон Мафии"]:
        target_recipients = game["mafia_ids"]
        prefix = "🩸 **[Чат Мафии]**"
    elif player_role in ["Доктор", "Интерн"]:
        target_recipients = [game["doctor_id"], game["intern_id"]]
        prefix = "🩺 **[Мед. Кабинет]**"
    elif player_role in ["Шериф", "Депути"]:
        target_recipients = [game["sheriff_id"], game["deputy_id"]]
        prefix = "🤠 **[Полицейский Участок]**"

    if target_recipients:
        text_to_broadcast = f"{prefix} **{sender_name}:** {message.text}"
        for recipient_uid in target_recipients:
            if recipient_uid and recipient_uid != user_id and game["players"].get(recipient_uid, {}).get("alive", False):
                try:
                    await bot.send_message(recipient_uid, text_to_broadcast, parse_mode="Markdown")
                except Exception:
                    pass
        try:
            await message.react([{"type": "emoji", "emoji": "👍"}])
        except Exception:
            pass

async def send_night_menu(bot: Bot, uid: int, role: str):
    targets = [
        [InlineKeyboardButton(text=p["name"], callback_data=f"act:{uid}:{tid}")]
        for tid, p in game["players"].items() if p["alive"] and tid != uid
    ]

    if role in ["Дон Мафии", "Мафия"]:
        kb = InlineKeyboardMarkup(inline_keyboard=targets)
        await bot.send_message(uid, "🎯 Выберите цель для выстрела:", reply_markup=kb)
    elif role == "Маньяк":
        kb = InlineKeyboardMarkup(inline_keyboard=targets)
        await bot.send_message(uid, "🔪 Выберите жертву:", reply_markup=kb)
    elif role == "Доктор":
        kb = InlineKeyboardMarkup(inline_keyboard=targets)
        await bot.send_message(uid, "🩺 Выберите, кого исцелить:", reply_markup=kb)
    elif role == "Путана":
        kb = InlineKeyboardMarkup(inline_keyboard=targets)
        await bot.send_message(uid, "💋 Выберите цель для блокировки:", reply_markup=kb)
    elif role == "Шериф":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Проверить роль", callback_data=f"sh_mode:{uid}:check")],
            [InlineKeyboardButton(text="🔫 Выстрелить", callback_data=f"sh_mode:{uid}:shoot")]
        ])
        await bot.send_message(uid, "🤠 Выберите действие:", reply_markup=kb)

@router.callback_query(F.data.startswith("sh_mode:"))
async def cb_sheriff_mode(callback: CallbackQuery):
    _, uid, mode = callback.data.split(":")
    uid = int(uid)
    targets = [
        [InlineKeyboardButton(text=p["name"], callback_data=f"sh_act:{uid}:{mode}:{tid}")]
        for tid, p in game["players"].items() if p["alive"] and tid != uid
    ]
    lbl = "проверки" if mode == "check" else "выстрела"
    await callback.message.edit_text(f"🎯 Выберите цель для {lbl}:", reply_markup=InlineKeyboardMarkup(inline_keyboard=targets))

@router.callback_query(F.data.startswith("act:"))
async def cb_generic_action(callback: CallbackQuery):
    _, actor_id, target_id = callback.data.split(":")
    actor_id, target_id = int(actor_id), int(target_id)
    
    if actor_id in game["players"]:
        game["players"][actor_id]["has_acted"] = True

    role = game["players"][actor_id]["role"]
    t_name = game["players"][target_id]["name"]
    
    if "Мафия" in role or role == "Дон Мафии":
        game["night_actions"]["mafia_target"] = target_id
        await notify_team(callback.bot, game["mafia_ids"], f"🩸 Цель мафии: **{t_name}**")
    elif role == "Маньяк":
        game["night_actions"]["maniac_target"] = target_id
    elif role == "Доктор":
        game["night_actions"]["doc_target"] = target_id
    elif role == "Путана":
        game["night_actions"]["escort_target"] = target_id
    
    await callback.answer("Действие зафиксировано!")

@router.callback_query(F.data.startswith("sh_act:"))
async def cb_sheriff_action(callback: CallbackQuery):
    _, uid, mode, target_id = callback.data.split(":")
    uid, target_id = int(uid), int(target_id)
    game["players"][int(uid)]["has_acted"] = True
    target_p = game["players"][target_id]
    
    if mode == "check":
        game["night_actions"]["sheriff_check"] = target_id
        await notify_team(callback.bot, [game["sheriff_id"], game["deputy_id"]], f"🔍 Проверка **{target_p['name']}**: {target_p['role']}")
        await callback.message.edit_text("Результат отправлен в участок!")
    else:
        game["night_actions"]["sheriff_shot"] = target_id
        await callback.message.edit_text("Выстрел зафиксирован!")

async def resolve_night_phase(chat_id: int, state: FSMContext, bot: Bot):
    if game.get("phase") != "night":
        return

    actions = game["night_actions"]
    killed_tonight = set()
    
    if actions.get("mafia_target") and actions.get("mafia_target") != actions.get("doc_target"):
        killed_tonight.add(actions.get("mafia_target"))
    if actions.get("maniac_target") and actions.get("maniac_target") != actions.get("doc_target"):
        killed_tonight.add(actions.get("maniac_target"))
    if actions.get("sheriff_shot") and actions.get("sheriff_shot") != actions.get("doc_target"):
        killed_tonight.add(actions.get("sheriff_shot"))

    inactive_players = []
    for uid, pdata in game["players"].items():
        if pdata["alive"] and not pdata["has_acted"]:
            pdata["alive"] = False
            inactive_players.append(uid)

    report = ["🌅 **Город просыпается. Итоги ночи:**"]
    
    for uid in killed_tonight:
        if uid in game["players"] and game["players"][uid]["alive"]:
            game["players"][uid]["alive"] = False
            p_name = game["players"][uid]["name"]
            p_role = game["players"][uid]["role"]
            report.append(f"❌ Убит ночью: **{p_name}** (Роль: *{p_role}*)")
    
    for uid in inactive_players:
        p_name = game["players"][uid]["name"]
        p_role = game["players"][uid]["role"]
        report.append(f"☠️ **{p_name}** покинул игру за неактивность! (Роль: *{p_role}*)")

    if len(killed_tonight) == 0 and len(inactive_players) == 0:
        report.append("✨ Ночь прошла спокойно, никто не погиб.")

    game["night_actions"].clear()
    await bot.send_message(chat_id, "\n".join(report), parse_mode="Markdown")

    all_new_dead = list(killed_tonight) + inactive_players
    for uid in all_new_dead:
        try:
            await bot.send_message(uid, "☠️ Вы выбыли из игры. Вы больше не можете писать в общий чат до конца партии.", parse_mode="Markdown")
        except Exception:
            pass

    if await check_win_conditions(bot, chat_id, state):
        return

    await start_day_discussion(bot, chat_id, state)

async def start_day_discussion(bot: Bot, chat_id: int, state: FSMContext):
    game["phase"] = "day"
    await state.set_state(GameState.day_discussion)
    await bot.send_message(chat_id, f"☀️ **Наступил день!** Общий чат открыт. У вас есть {DISCUSSION_TIMEOUT} секунд на обсуждение.", parse_mode="Markdown")
    await asyncio.sleep(DISCUSSION_TIMEOUT)
    await start_day_voting(bot, chat_id, state)

async def start_day_voting(bot: Bot, chat_id: int, state: FSMContext):
    await state.set_state(GameState.day_voting)
    game["votes"].clear()
    alive_targets = [[InlineKeyboardButton(text=p["name"], callback_data=f"vote:{uid}")] for uid, p in game["players"].items() if p["alive"]]
    
    if not alive_targets:
        return

    await bot.send_message(chat_id, "⚖️ **Голосование:** Выберите игрока для исключения:", reply_markup=InlineKeyboardMarkup(inline_keyboard=alive_targets), parse_mode="Markdown")
    await asyncio.sleep(VOTING_TIMEOUT)
    await resolve_voting(bot, chat_id, state)

@router.callback_query(F.data.startswith("vote:"))
async def cb_vote(callback: CallbackQuery):
    voter_id = callback.from_user.id
    if voter_id not in game["players"] or not game["players"][voter_id]["alive"]:
        await callback.answer("Мертвые не голосуют!", show_alert=True)
        return
    _, target_id = callback.data.split(":")
    game["votes"][voter_id] = int(target_id)
    await callback.answer("Голос принят!")

async def resolve_voting(bot: Bot, chat_id: int, state: FSMContext):
    if await state.get_state() != GameState.day_voting.state:
        return
    votes = game["votes"]
    if not votes:
        await bot.send_message(chat_id, "🗳 Никто не проголосовал. Переход к ночи.")
        await start_night_phase(bot, chat_id, state)
        return

    counts = {}
    for t in votes.values():
        counts[t] = counts.get(t, 0) + 1
    max_v = max(counts.values())
    cands = [uid for uid, c in counts.items() if c == max_v]

    if len(cands) == 1:
        uid = cands[0]
        game["players"][uid]["alive"] = False
        p_name = game["players"][uid]["name"]
        p_role = game["players"][uid]["role"]
        
        is_mafia_or_threat = p_role in ["Мафия", "Дон Мафии", "Маньяк"]
        reveal_text = f"был Мафией / Маньяком (Роль: *{p_role}*)" if is_mafia_or_threat else f"не был Предателем (Роль: *{p_role}*)"
        
        await bot.send_message(
            chat_id, 
            f"⚖️ **Результаты голосования:** Большинством голосов исключен **{p_name}**!\n"
            f"🔍 *{p_name}* {reveal_text}", 
            parse_mode="Markdown"
        )
        
        try:
            await bot.send_message(uid, "☠️ Вы были исключены на дневном голосовании. Вы больше не можете писать в общий чат.", parse_mode="Markdown")
        except Exception:
            pass

        if await check_win_conditions(bot, chat_id, state):
            return
    else:
        await bot.send_message(chat_id, "🤝 Ничья на голосовании. Никто не исключен!")

    if game["active"]:
        await start_night_phase(bot, chat_id, state)

async def check_win_conditions(bot: Bot, chat_id: int, state: FSMContext) -> bool:
    alive = [uid for uid, p in game["players"].items() if p["alive"]]
    mafia = [uid for uid in alive if game["players"][uid]["role"] in ["Мафия", "Дон Мафии"]]
    maniac = [uid for uid in alive if game["players"][uid]["role"] == "Маньяк"]
    peaceful = [uid for uid in alive if uid not in mafia and uid not in maniac]

    if game["maniac_id"] in alive and len(alive) == 1:
        game["active"] = False
        await bot.send_message(chat_id, "🔪🏆 **Маньяк победил!** Он устранил абсолютно всех соперников.", parse_mode="Markdown")
        await state.clear()
        return True
    if not mafia and not maniac:
        game["active"] = False
        await bot.send_message(chat_id, "🏆 **Мирные жители победили!** Вся угроза уничтожена.", parse_mode="Markdown")
        await state.clear()
        return True
    elif len(mafia) >= len(peaceful) + len(maniac):
        game["active"] = False
        await bot.send_message(chat_id, "🩸 **Мафия победила!** Город захвачен преступниками.", parse_mode="Markdown")
        await state.clear()
        return True
    return False

# ==================== ЗАПУСК ====================
async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
