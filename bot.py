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
    day = State()
    last_word = State()

# Глобальное хранилище состояния текущей игры
game = {
    "active": False,
    "players": {},       # user_id: {"name": str, "role": str, "alive": bool, "duo_id": int}
    "night_actions": {}, # "mafia_target", "doc_target", "sheriff_target", "judge_target"
    "current_speaker": None,
    "votes": {}
}

MIN_PLAYERS = 3       # Минимальное число игроков для старта
LOBBY_TIMEOUT = 120   # Время автоматического ожидания в секундах (2 минуты)

def get_join_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Войти в игру", callback_data="join")]
    ])

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("👋 Мафия-бот готов к работе! Для создания игры используй /create_game")

@router.message(Command("create_game"))
async def cmd_create_game(message: Message, state: FSMContext):
    if game["active"]:
        await message.answer("⚠️ Игра уже идет или лобби уже открыто!")
        return
    
    game["active"] = True
    game["players"] = {}
    game["night_actions"] = {}
    await state.set_state(GameState.lobby)
    
    await message.answer(
        f"🎲 **Лобби Мафии открыто!**\n"
        f"⏱ У вас есть {LOBBY_TIMEOUT // 60} минуты, чтобы собраться.\n"
        f"👥 Минимум игроков: {MIN_PLAYERS}.\n"
        f"Жмите кнопку ниже для входа!",
        reply_markup=get_join_keyboard(),
        parse_mode="Markdown"
    )

    # Запускаем фоновый таймер на автоматический старт через LOBBY_TIMEOUT секунд
    asyncio.create_task(lobby_timer(message.bot, message.chat.id, state))

async def lobby_timer(bot: Bot, chat_id: int, state: FSMContext):
    await asyncio.sleep(LOBBY_TIMEOUT)
    
    current_state = await state.get_state()
    if game["active"] and current_state == GameState.lobby.state:
        if len(game["players"]) < MIN_PLAYERS:
            await bot.send_message(
                chat_id,
                f"⌛ Время ожидания вышло! Набралось всего {len(game['players'])} из {MIN_PLAYERS} игроков. "
                f"Игра отменена."
            )
            game["active"] = False
            game["players"].clear()
            await state.clear()
        else:
            await bot.send_message(
                chat_id,
                f"🚀 Время вышло! Собралось игроков: {len(game['players'])}. Запускаем игру автоматически!"
            )
            await run_game_start(chat_id, state)

async def run_game_start(chat_id: int, state: FSMContext):
    p_ids = list(game["players"].keys())
    total_players = len(p_ids)
    random.shuffle(p_ids)
    
    # 1. Формула баланса: 3 мирных - 1 Мафия (1 мафия на каждые 4 человека в сумме)
    mafia_count = total_players // 4
    if mafia_count < 1:
        mafia_count = 1  
        
    don_count = 1 if mafia_count >= 2 else 0 
    simple_mafia_count = mafia_count - don_count
    
    # 2. Нейтральная роль (Маньяк): появляется на 11-м игроке, далее каждые 5 человек (11, 16, 21...)
    maniac_count = 0
    if total_players >= 11:
        maniac_count = 1 + (total_players - 11) // 5

    # Спец-роли
    sheriff_count = 2 if total_players >= 10 else 1
    doctor_count = 2 if total_players >= 10 else 1
    judge_count = 1 if total_players >= 7 else 0

    # Собираем пул ролей
    roles_pool = []
    
    if don_count > 0:
        roles_pool.append("Дон Мафии")
    for _ in range(simple_mafia_count):
        roles_pool.append("Мафия")
        
    for i in range(1, sheriff_count + 1):
        roles_pool.append(f"Шериф №{i}")
    for i in range(1, doctor_count + 1):
        roles_pool.append(f"Доктор №{i}")
        
    if judge_count > 0:
        roles_pool.append("Судья")
        
    for i in range(1, maniac_count + 1):
        roles_pool.append(f"Маньяк №{i}" if maniac_count > 1 else "Маньяк")
        
    # Заполняем оставшиеся места мирными жителями
    while len(roles_pool) < total_players:
        roles_pool.append("Мирный житель")
    
    random.shuffle(roles_pool)
    
    sheriffs = []
    doctors = []
    
    for i, uid in enumerate(p_ids):
        assigned_role = roles_pool[i]
        game["players"][uid]["role"] = assigned_role
        
        if "Шериф" in assigned_role:
            sheriffs.append(uid)
        elif "Доктор" in assigned_role:
            doctors.append(uid)

    # Связываем дуэты (Напарники узнают друг друга)
    if len(sheriffs) == 2:
        game["players"][sheriffs[0]]["duo_id"] = sheriffs[1]
        game["players"][sheriffs[1]]["duo_id"] = sheriffs[0]
        
    if len(doctors) == 2:
        game["players"][doctors[0]]["duo_id"] = doctors[1]
        game["players"][doctors[1]]["duo_id"] = doctors[0]

    await state.set_state(GameState.night)
    await bot_instance.send_message(
        chat_id, 
        f"🌙 **Город засыпает. Наступает ночь.**\n"
        f"👥 Всего игроков: {total_players} | Мафий: {mafia_count} | Маньяков: {maniac_count}. Все действия в ЛС!", 
        parse_mode="Markdown"
    )

    # Ночная рассылка кнопок и ролей
    for uid, pdata in game["players"].items():
        role = pdata["role"]
        text = f"🕵️‍♂️ Твоя роль: **{role}**\n"
        
        if pdata["duo_id"]:
            duo_name = game["players"][pdata["duo_id"]]["name"]
            text += f"🤝 Твой напарник: **{duo_name}**\n"
            
        try:
            await bot_instance.send_message(uid, text, parse_mode="Markdown")
        except Exception:
            pass
        
        # Генерация ночного меню действий
        if role in ["Дон Мафии", "Мафия"] or "Маньяк" in role or "Доктор" in role or "Шериф" in role:
            buttons = []
            for target_id, target_data in game["players"].items():
                if target_data["alive"] and target_id != uid:
                    buttons.append([InlineKeyboardButton(
                        text=target_data["name"], 
                        callback_data=f"night_act:{uid}:{target_id}"
                    )])
            if buttons:
                kb = InlineKeyboardMarkup(inline_keyboard=buttons)
                try:
                    await bot_instance.send_message(uid, "🎯 Выбери цель для ночного действия:", reply_markup=kb)
                except Exception:
                    pass

@router.callback_query(F.data == "join")
async def cb_join(callback: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state != GameState.lobby.state:
        await callback.answer("❌ Лобби сейчас закрыто!", show_alert=True)
        return

    uid = callback.from_user.id
    if uid in game["players"]:
        await callback.answer("Ты уже зарегистрирован!", show_alert=True)
        return
    
    game["players"][uid] = {
        "name": callback.from_user.full_name,
        "role": None,
        "alive": True,
        "duo_id": None
    }
    await callback.answer("Успешный вход!")
    
    count = len(game["players"])
    try:
        await callback.message.edit_text(
            f"🎲 **Лобби Мафии открыто!**\n"
            f"👥 Зарегистрировано игроков: **{count}** (нужно мин. {MIN_PLAYERS}).\n"
            "Ждите таймера или запустите игру досрочно командой /start_mafia.",
            reply_markup=callback.message.reply_markup,
            parse_mode="Markdown"
        )
    except Exception:
        pass

@router.message(Command("start_mafia"))
async def cmd_start_mafia(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state != GameState.lobby.state:
        await message.answer("❌ Лобби еще не создано! Напишите /create_game")
        return

    p_ids = list(game["players"].keys())
    if len(p_ids) < MIN_PLAYERS:
        await message.answer(
            f"⚠️ Недостаточно игроков для досрочного старта! "
            f"Сейчас зарегистрировано: {len(p_ids)} из {MIN_PLAYERS} необходимых."
        )
        return

    await message.answer("🎭 Все в сборе! Досрочно начинаем игру...")
    await run_game_start(message.chat.id, state)

@router.callback_query(F.data.startswith("night_act:"))
async def cb_night_action(callback: CallbackQuery):
    _, actor_id, target_id = callback.data.split(":")
    actor_id, target_id = int(actor_id), int(target_id)
    
    role = game["players"][actor_id]["role"]
    target_name = game["players"][target_id]["name"]
    
    if "Мафия" in role or "Дон" in role:
        game["night_actions"]["mafia_target"] = target_id
        await callback.answer(f"Заказ принят: {target_name}")
    elif "Доктор" in role:
        game["night_actions"]["doc_target"] = target_id
        await callback.answer(f"Ты лечишь: {target_name}")
    elif "Шериф" in role:
        target_role = game["players"][target_id]["role"]
        is_bad = "Мафия" in target_role or "Маньяк" in target_role
        res = "🔴 ОПАСЕН (Мафия/Маньяк)" if is_bad else "🟢 ЧИСТ (Мирный)"
        await callback.message.edit_text(f"Проверка игрока {target_name}: {res}")

@router.message(GameState.last_word)
async def handle_last_words(message: Message, state: FSMContext):
    if message.from_user.id != game["current_speaker"]:
        return
    
    text = message.text
    if len(text) > 100:
        await message.reply(f"⚠️ Слишком длинно! Твоё сообщение урезано до 100 символов.\n\nИтог: {text[:100]}")
    else:
        await message.reply(f"💬 Последнее слово выбывшего:\n«{text}»")
        
    game["current_speaker"] = None
    await state.set_state(GameState.day)

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
