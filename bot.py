# -*- coding: utf-8 -*-
import asyncio
import logging
import random
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery

TOKEN = "8619385160:AAGojtV7nGKreWXJaQezCxCW_T_m3PaSo74"

logging.basicConfig(level=logging.INFO)
router = Router()

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
        await message.answer("👋 Мафия-бот готов к работе! Наберите /create_game для запуска лобби.")

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

    roles_pool.append("Эскортница")
    
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
            elif role == "Эскортница":
                text += "💋 Заблокируй ночное действие игрока."
            elif role == "Шериф":
                text += "🤠 Проверяй игроков или делай выстрел."

            try:
                await bot.send_message(uid, text, parse_mode="Markdown")
                await send_night_menu(bot, uid, role)
            except Exception:
                await bot.send_message(
                    chat_id, 
                    f"⚠️ Игрок **{pdata['name']}** не активировал бота в ЛС (@MyServerMafiaBot) и пропускает свой ход!"
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
    elif role == "Эскортница":
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
    elif role == "Эскортница":
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

async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
