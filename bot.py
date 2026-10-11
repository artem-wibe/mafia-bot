# -*- coding: utf-8 -*-
import asyncio
import logging
import random
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery

TOKEN = "8619385160:AAEZGY1h9uLmPlqqDvaowRVilUinUf5JDo4"

logging.basicConfig(level=logging.INFO)
router = Router()

class GameState(StatesGroup):
    lobby = State()
    night = State()
    day_discussion = State()
    day_voting = State()

# Глобальное состояние игры
game = {
    "active": False,
    "players": {},       # user_id: {"name": str, "role": str, "alive": bool, "silenced": bool}
    "night_actions": {}, # действия за текущую ночь
    "votes": {},         # голоса игроков днем: {voter_id: target_id}
    "sheriff_id": None,
    "deputy_id": None,
    "doctor_id": None,
    "intern_id": None,
    "mafia_ids": []
}

MIN_PLAYERS = 3
LOBBY_TIMEOUT = 120
NIGHT_TIMEOUT = 45     # Время на ночные ходы
DISCUSSION_TIMEOUT = 45 # Время на дневное обсуждение
VOTING_TIMEOUT = 30    # Время на дневное голосование

def get_join_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Войти в игру", callback_data="join")]
    ])

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("👋 Мафия-бот готов к работе! Наберите /create_game для запуска лобби.")

    @router.message(Command("create_game"))
async def cmd_create_game(message: Message, state: FSMContext):
    if message.chat.type in ["group", "supergroup"]:
        member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in ["administrator", "creator"]:
            await message.reply("⛔ **Доступ запрещен!**\nСоздавать лобби могут только администраторы чата.")
            return

    if game["active"]:
        await message.answer("⚠️ Игра уже запущена или лобби открыто!")
        return

    game["active"] = True
    game["players"] = {}
    game["night_actions"] = {}
    game["votes"] = {}
    game["sheriff_id"] = None
    game["deputy_id"] = None
    game["doctor_id"] = None
    game["intern_id"] = None
    game["mafia_ids"] = []

    await state.set_state(GameState.lobby)

    await message.answer(
        f"🎲 **Лобби Мафии открыто!**\n"
        f"⏰ Время сбора: {LOBBY_TIMEOUT // 60} мин.\n"
        f"👥 Минимум участников: {MIN_PLAYERS}.\n"
        f"Нажмите кнопку ниже, чтобы войти в игру!",
        reply_markup=get_join_keyboard(),
        parse_mode="Markdown"
    )

    asyncio.create_task(lobby_timer(message.bot, message.chat.id, state))

async def lobby_timer(bot: Bot, chat_id: int, state: FSMContext):
    await asyncio.sleep(LOBBY_TIMEOUT)
    current_state = await state.get_state()
    if game["active"] and current_state == GameState.lobby.state:
        if len(game["players"]) < MIN_PLAYERS:
            await bot.send_message(chat_id, f"⌛ Набралось всего {len(game['players'])} чел. Игра отменена.")
            game["active"] = False
            game["players"].clear()
            await state.clear()
        else:
            await bot.send_message(chat_id, "🚀 Время вышло! Начинаем партию!")
            await run_game_start(chat_id, state)

async def notify_team(user_ids: list, message_text: str):
    for uid in user_ids:
        if uid and game["players"].get(uid, {}).get("alive", False):
            try:
                await bot_instance.send_message(uid, message_text, parse_mode="Markdown")
            except Exception:
                pass

async def run_game_start(chat_id: int, state: FSMContext):
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
    roles_pool.append("Самоубийца")
    
    if total_players >= 11:
        roles_pool.append("Пеннивайз")

    while len(roles_pool) < total_players:
        roles_pool.append("Мирный житель")

    random.shuffle(roles_pool)

    for i, uid in enumerate(p_ids):
        assigned_role = roles_pool[i]
        game["players"][uid]["role"] = assigned_role
        game["players"][uid]["silenced"] = False
        
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

    await state.set_state(GameState.night)
    await bot_instance.send_message(
        chat_id,
        f"🌙 **Город засыпает. Наступает ночь.**\n"
        f"🤫 Комендантский час! Ни живым, ни мертвым писать в общий чат нельзя.\n"
        f"👥 Инструкции и ночные меню отправлены в ЛС!",
        parse_mode="Markdown"
    )

    for uid, pdata in game["players"].items():
        role = pdata["role"]
        text = f"🕵️‍♂️ Твоя роль: **{role}**\n"
        if role == "Самоубийца":
            text += "🎯 Твоя цель: добиться своей казни на дневном голосовании!"
        elif role == "Пеннивайз":
            text += "🎈 Твоя цель: сеять хаос! Выбирай: убить 1 игрока ИЛИ заглушить до 3 человек."
        elif role == "Эскортница":
            text += "💋 Заблокируй ночное действие игрока и лиши его права голоса на весь день."
        elif role == "Депути":
            text += "🛡 Ты в отряде с Шерифом. Примешь его полномочия, если он погибнет или ошибется."
        elif role == "Интерн":
            text += "🩺 Ты ассистируешь Доктору и унаследуешь его практику, если тот выбывает."

        try:
            await bot_instance.send_message(uid, text, parse_mode="Markdown")
        except Exception:
            pass

        await send_night_menu(uid, role)

    asyncio.create_task(night_timer(chat_id, state))

# Жесткий фильтр ночного чата
@router.message(GameState.night, F.text)
async def catch_night_chat_flood(message: Message):
    if message.chat.type in ["group", "supergroup"]:
        try:
            await message.delete()
            await message.bot.send_message(
                message.from_user.id, 
                "🤫 **Ночь в городе!** Общий чат заблокирован для всех. Общайтесь только в ЛС с ботом.", 
                parse_mode="Markdown"
            )
        except Exception:
            pass

async def night_timer(chat_id: int, state: FSMContext):
    await asyncio.sleep(NIGHT_TIMEOUT)
    current_state = await state.get_state()
    if current_state == GameState.night.state:
        await resolve_night_phase(chat_id, state)

async def send_night_menu(uid: int, role: str):
    targets = [
        [InlineKeyboardButton(text=p["name"], callback_data=f"act:{uid}:{tid}")]
        for tid, p in game["players"].items() if p["alive"] and tid != uid
    ]

    if role in ["Дон Мафии", "Мафия"]:
        kb = InlineKeyboardMarkup(inline_keyboard=targets)
        await bot_instance.send_message(uid, "🎯 [Чат Мафии] Выберите цель для выстрела:", reply_markup=kb)
    elif role == "Доктор":
        kb = InlineKeyboardMarkup(inline_keyboard=targets)
        await bot_instance.send_message(uid, "🩺 [Мед. Кабинет] Выберите, кого исцелить этой ночью:", reply_markup=kb)
    elif role == "Интерн":
        await bot_instance.send_message(uid, "🩺 [Мед. Кабинет] Вы наблюдаете за действиями Доктора этой ночью.")
    elif role == "Депути":
        await bot_instance.send_message(uid, "🛡 [Полицейский Участок] Вы ассистируете Шерифу и видите результаты его ночной работы.")
    elif role == "Эскортница":
        kb = InlineKeyboardMarkup(inline_keyboard=targets)
        await bot_instance.send_message(uid, "💋 Выберите цель для блокировки:", reply_markup=kb)
    elif role == "Шериф":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Проверить точную роль", callback_data=f"sh_mode:{uid}:check")],
            [InlineKeyboardButton(text="🔫 Выстрелить", callback_data=f"sh_mode:{uid}:shoot")]
        ])
        await bot_instance.send_message(uid, "🤠 [Полицейский Участок] Выберите действие:", reply_markup=kb)
    elif role == "Пеннивайз":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔪 Убить 1 игрока", callback_data=f"pw_mode:{uid}:kill")],
            [InlineKeyboardButton(text="🎈 Заглушить до 3 игроков", callback_data=f"pw_mode:{uid}:silence")]
        ])
        await bot_instance.send_message(uid, "🤡 Выберите режим проведения ночи:", reply_markup=kb)

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

@router.callback_query(F.data.startswith("pw_mode:"))
async def cb_pennywise_mode(callback: CallbackQuery):
    _, uid, mode = callback.data.split(":")
    uid = int(uid)
    targets = [
        [InlineKeyboardButton(text=p["name"], callback_data=f"pw_act:{uid}:{mode}:{tid}")]
        for tid, p in game["players"].items() if p["alive"] and tid != uid
    ]
    if mode == "kill":
        await callback.message.edit_text("🔪 Выберите жертву:", reply_markup=InlineKeyboardMarkup(inline_keyboard=targets))
    else:
        game["night_actions"]["pennywise_silence"] = []
        await callback.message.edit_text("🎈 Выберите 1-ю цель для блокировки:", reply_markup=InlineKeyboardMarkup(inline_keyboard=targets))

@router.callback_query(F.data.startswith("act:"))
async def cb_generic_action(callback: CallbackQuery):
    _, actor_id, target_id = callback.data.split(":")
    actor_id, target_id = int(actor_id), int(target_id)
    role = game["players"][actor_id]["role"]
    t_name = game["players"][target_id]["name"]
    
    if "Мафия" in role or role == "Дон Мафии":
        game["night_actions"]["mafia_target"] = target_id
        await notify_team(game["mafia_ids"], f"🩸 **[Чат Мафии]** Наведен прицел на игрока: **{t_name}**")
    elif role == "Доктор":
        game["night_actions"]["doc_target"] = target_id
        await notify_team([game["doctor_id"], game["intern_id"]], f"🩺 **[Мед. Кабинет]** Доктор решил исцелить: **{t_name}**")
    elif role == "Эскортница":
        game["night_actions"]["escort_target"] = target_id
        await callback.answer(f"Заблокирован: {t_name}")
    await callback.answer("Принято!")

@router.callback_query(F.data.startswith("sh_act:"))
async def cb_sheriff_action(callback: CallbackQuery):
    _, uid, mode, target_id = callback.data.split(":")
    uid, target_id = int(uid), int(target_id)
    target_p = game["players"][target_id]
    police_team = [game["sheriff_id"], game["deputy_id"]]

    if mode == "check":
        res_text = f"🔍 **[Полицейский Участок]** Проверка игрока **{target_p['name']}**: Роль — **{target_p['role']}**"
        game["night_actions"]["sheriff_check"] = target_id
        await notify_team(police_team, res_text)
        await callback.message.edit_text("Результат проверки отправлен в участок!")
    else:
        game["night_actions"]["sheriff_shot"] = target_id
        shot_text = f"🔫 **[Полицейский Участок]** Шериф навел выстрел на: **{target_p['name']}**"
        await notify_team(police_team, shot_text)
        await callback.message.edit_text("Прицел зафиксирован!")

@router.callback_query(F.data.startswith("pw_act:"))
async def cb_pennywise_action(callback: CallbackQuery):
    _, uid, mode, target_id = callback.data.split(":")
    uid, target_id = int(uid), int(target_id)
    
    if mode == "kill":
        game["night_actions"]["pennywise_kill"] = target_id
        await callback.message.edit_text(f"🔪 Цель выбрана: {game['players'][target_id]['name']}")
    else:
        silence_list = game["night_actions"].get("pennywise_silence", [])
        if target_id not in silence_list:
            silence_list.append(target_id)
            game["night_actions"]["pennywise_silence"] = silence_list
            
        if len(silence_list) < 3:
            targets = [
                [InlineKeyboardButton(text=p["name"], callback_data=f"pw_act:{uid}:silence:{tid}")]
                for tid, p in game["players"].items() if p["alive"] and tid != uid and tid not in silence_list
            ]
            await callback.message.edit_text(f"🎈 Выбрано целей: {len(silence_list)}/3.", reply_markup=InlineKeyboardMarkup(inline_keyboard=targets))
        else:
            await callback.message.edit_text("🎈 Выбраны все 3 цели!")

async def resolve_night_phase(chat_id: int, state: FSMContext):
    actions = game["night_actions"]
    mafia_target = actions.get("mafia_target")
    doc_target = actions.get("doc_target")
    escort_target = actions.get("escort_target")
    sheriff_shot = actions.get("sheriff_shot")
    penny_kill = actions.get("pennywise_kill")
    penny_silence = actions.get("pennywise_silence", [])

    killed_tonight = set()
    
    don_id = next((uid for uid, p in game["players"].items() if p["role"] == "Дон Мафии" and p["alive"]), None)
    don_blocked = (don_id and (don_id == escort_target or don_id in penny_silence))
    if don_id and don_blocked and mafia_target == escort_target:
        don_blocked = False

    if mafia_target and not don_blocked:
        if mafia_target != doc_target:
            killed_tonight.add(mafia_target)

    if sheriff_shot:
        if sheriff_shot != doc_target:
            killed_tonight.add(sheriff_shot)
        target_role = game["players"][sheriff_shot]["role"]
        if target_role in ["Мирный житель", "Эскортница"]:
            if game["deputy_id"] and game["players"][game["deputy_id"]]["alive"]:
                game["sheriff_id"] = game["deputy_id"]
                game["players"][game["deputy_id"]]["role"] = "Шериф"
                await notify_team([game["deputy_id"]], "🚨 Шериф ошибся выстрелом! **Ты стал новым Шерифом!**")
            game["sheriff_id"] = None

    if penny_kill and penny_kill != doc_target:
        killed_tonight.add(penny_kill)

    sheriff_uid = game["sheriff_id"]
    if sheriff_uid and sheriff_uid in killed_tonight:
        if game["deputy_id"] and game["players"][game["deputy_id"]]["alive"]:
            game["sheriff_id"] = game["deputy_id"]
            game["players"][game["deputy_id"]]["role"] = "Шериф"
            await notify_team([game["deputy_id"]], "⚠️ Шериф погиб ночью. **Ты принял его полномочия!**")

    doctor_uid = game["doctor_id"]
    if doctor_uid and doctor_uid in killed_tonight:
        if game["intern_id"] and game["players"][game["intern_id"]]["alive"]:
            game["doctor_id"] = game["intern_id"]
            game["players"][game["intern_id"]]["role"] = "Доктор"
            await notify_team([game["intern_id"]], "🩺 Доктор пал жертвой. **Ты стал новым Доктором!**")

    report_lines = ["🌅 **Город просыпается. Итоги ночи:**"]
    for uid in killed_tonight:
        game["players"][uid]["alive"] = False
        report_lines.append(f"❌ Убит: **{game['players'][uid]['name']}**")

    if len(killed_tonight) == 0:
        report_lines.append("✨ Ночь прошла спокойно, никто не погиб.")

    game["night_actions"].clear()
    await bot_instance.send_message(chat_id, "\n".join(report_lines), parse_mode="Markdown")

    # Проверка победы после ночи
    if await check_win_conditions(chat_id, state):
        return

    # Переход к дневному обсуждению
    await start_day_discussion(chat_id, state)

async def start_day_discussion(chat_id: int, state: FSMContext):
    await state.set_state(GameState.day_discussion)
    await bot_instance.send_message(
        chat_id, 
        f"☀️ **Наступил день!** Открывается общее обсуждение.\n"
        f"У вас есть {DISCUSSION_TIMEOUT} секунд на дебаты и поиск подозреваемых.", 
        parse_mode="Markdown"
    )
    await asyncio.sleep(DISCUSSION_TIMEOUT)
    await start_day_voting(chat_id, state)

async def start_day_voting(chat_id: int, state: FSMContext):
    await state.set_state(GameState.day_voting)
    game["votes"].clear()
    
    alive_targets = [
        [InlineKeyboardButton(text=p["name"], callback_data=f"vote:{uid}")]
        for uid, p in game["players"].items() if p["alive"]
    ]
    
    if not alive_targets:
        return

    kb = InlineKeyboardMarkup(inline_keyboard=alive_targets)
    await bot_instance.send_message(
        chat_id, 
        "⚖️ **Время дневного голосования!** Выберите игрока для отправки на виселицу:", 
        reply_markup=kb,
        parse_mode="Markdown"
    )
    
    await asyncio.sleep(VOTING_TIMEOUT)
    await resolve_voting(chat_id, state)

@router.callback_query(F.data.startswith("vote:"))
async def cb_vote(callback: CallbackQuery):
    voter_id = callback.from_user.id
    if voter_id not in game["players"] or not game["players"][voter_id]["alive"]:
        await callback.answer("Мертвые не голосуют!", show_alert=True)
        return
        
    _, target_id = callback.data.split(":")
    target_id = int(target_id)
    
    game["votes"][voter_id] = target_id
    await callback.answer(f"Ваш голос за: {game['players'][target_id]['name']}")

async def resolve_voting(chat_id: int, state: FSMContext):
    current_state = await state.get_state()
    if current_state != GameState.day_voting.state:
        return

    votes = game["votes"]
    if not votes:
        await bot_instance.send_message(chat_id, "🗳 Никто не проголосовал днем. Казнь отменяется, наступает ночь.")
        await start_night_phase(chat_id, state)
        return

    vote_counts = {}
    for target in votes.values():
        vote_counts[target] = vote_counts.get(target, 0) + 1

    max_votes = max(vote_counts.values())
    candidates = [uid for uid, count in vote_counts.items() if count == max_votes]

    if len(candidates) == 1:
        lynched_uid = candidates[0]
        game["players"][lynched_uid]["alive"] = False
        lynched_name = game["players"][lynched_uid]["name"]
        
        await bot_instance.send_message(
            chat_id, 
            f"⚖️ **Результаты голосования:** Большинством голосов казнен **{lynched_name}**!", 
            parse_mode="Markdown"
        )

        # Проверка победы (включая триумф Самоубийцы)
        if await check_win_conditions(chat_id, state, lynched_uid=lynched_uid):
            return
    else:
        await bot_instance.send_message(chat_id, "🤝 Ничья на голосовании. Никто не казнен!")

    # Если игра продолжается, уходим в ночь
    if game["active"]:
        await start_night_phase(chat_id, state)

async def start_night_phase(chat_id: int, state: FSMContext):
    await state.set_state(GameState.night)
    await bot_instance.send_message(
        chat_id, 
        "🌙 **Город снова погружается во тьму...** Наступает ночь. Комендантский час активен!", 
        parse_mode="Markdown"
    )
    
    for uid, pdata in game["players"].items():
        if pdata["alive"]:
            await send_night_menu(uid, pdata["role"])

    asyncio.create_task(night_timer(chat_id, state))

async def check_win_conditions(chat_id: int, state: FSMContext, lynched_uid: int = None) -> bool:
    # 1. Проверка победы Самоубийцы (СТРОГО при дневном повешении)
    if lynched_uid:
        lynched_role = game["players"][lynched_uid]["role"]
        if lynched_role == "Самоубийца":
            await bot_instance.send_message(
                chat_id,
                f"🎉 **ПОБЕДА НЕЙТРАЛА!**\n\n"
                f"🤡 Игрок **{game['players'][lynched_uid]['name']}** оказался **Самоубийцей**! "
                f"Город попался на уловку и казнил его. Самоубийца побеждает единолично! 🏆",
                parse_mode="Markdown"
            )
            game["active"] = False
            await state.clear()
            return True

    alive_players = [p for p in game["players"].values() if p["alive"]]
    alive_count = len(alive_players)

    mafia_alive = [p for p in alive_players if "Мафия" in p["role"] or p["role"] == "Дон Мафии"]
    penny_alive = [p for p in alive_players if p["role"] == "Пеннивайз"]
    manc_alive = [p for p in alive_players if p["role"] == "Маньяк"]
    town_alive = [p for p in alive_players if p not in mafia_alive and p not in penny_alive and p not in manc_alive]

    # 2. Победа Пеннивайза / Маньяка (1 на 1 или один)
    if len(penny_alive) == 1 and alive_count <= 2 and len(mafia_alive) == 0:
        await bot_instance.send_message(
            chat_id,
            f"🎈 **ПОБЕДА ПЕННИВАЙЗА!**\n\n"
            f"🤡 **{penny_alive[0]['name']}** уничтожил всех и погрузил город в хаос!",
            parse_mode="Markdown"
        )
        game["active"] = False
        await state.clear()
        return True

    if len(manc_alive) == 1 and alive_count <= 2 and len(mafia_alive) == 0:
        await bot_instance.send_message(
            chat_id,
            f"🔪 **ПОБЕДА МАНЬЯКА!**\n\n"
            f"🩸 **{manc_alive[0]['name']}** остался последним выжившим!",
            parse_mode="Markdown"
        )
        game["active"] = False
        await state.clear()
        return True

    # 3. Победа Мафии
    if len(mafia_alive) >= len(town_alive) and len(penny_alive) == 0 and len(manc_alive) == 0 and len(mafia_alive) > 0:
        await bot_instance.send_message(
            chat_id,
            f"🩸 **ПОБЕДА МАФИИ!**\n\n"
            f"🎩 Мафия установила полный контроль над городом.",
            parse_mode="Markdown"
        )
        game["active"] = False
        await state.clear()
        return True

    # 4. Победа Города
    if len(mafia_alive) == 0 and len(penny_alive) == 0 and len(manc_alive) == 0:
        await bot_instance.send_message(
            chat_id,
            f"🕊 **ПОБЕДА МИРНЫХ ЖИТЕЛЕЙ!**\n\n"
            f"⚖️ Вся преступность полностью ликвидирована в городе!",
            parse_mode="Markdown"
        )
        game["active"] = False
        await state.clear()
        return True

    return False

@router.callback_query(F.data == "join")
async def cb_join(callback: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state != GameState.lobby.state:
        await callback.answer("❌ Лобби закрыто!", show_alert=True)
        return

    uid = callback.from_user.id
    if uid in game["players"]:
        await callback.answer("Вы уже в игре!", show_alert=True)
        return
    
    game["players"][uid] = {
        "name": callback.from_user.full_name,
        "role": None,
        "alive": True,
        "silenced": False
    }
    await callback.answer("Успешный вход!")
    
    count = len(game["players"])
    try:
        await callback.message.edit_text(
            f"🎲 **Лобби открыто!**\n"
            f"👥 Зарегистрировано: **{count}** (мин. {MIN_PLAYERS}).\n"
            "Ожидайте автоматического запуска или введите /start_mafia.",
            reply_markup=callback.message.reply_markup,
            parse_mode="Markdown"
        )
    except Exception:
        pass

@router.message(Command("start_mafia"))
async def cmd_start_mafia(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state != GameState.lobby.state:
        await message.answer("❌ Лобби еще не создано!")
        return
    if len(game["players"]) < MIN_PLAYERS:
        await message.answer(f"⚠️ Нужно минимум {MIN_PLAYERS} участников.")
        return
    await run_game_start(message.chat.id, state)

async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    
    global bot_instance
    bot_instance = bot

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    bot_instance = None
    asyncio.run(main())