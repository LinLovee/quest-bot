import os
import random
import asyncio
import logging
import sqlite3
import threading
import json
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
from telegram.error import BadRequest

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.FileHandler("quest_bot.log", encoding="utf-8"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ========== БД ==========

db_lock = threading.RLock()
conn = sqlite3.connect('quest_bot.db', check_same_thread=False, timeout=30.0)
cursor = conn.cursor()

# Таблицы
cursor.execute('''
CREATE TABLE IF NOT EXISTS players (
    chat_id INTEGER, user_id INTEGER, user_name TEXT,
    level INTEGER DEFAULT 1, experience INTEGER DEFAULT 0,
    health INTEGER DEFAULT 100, mana INTEGER DEFAULT 50,
    inventory_slots INTEGER DEFAULT 10,
    reputation INTEGER DEFAULT 0,
    pet_id TEXT, pet_level INTEGER DEFAULT 1,
    last_daily TIMESTAMP,
    PRIMARY KEY (chat_id, user_id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS quests (
    quest_id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER, user_id INTEGER, quest_type TEXT,
    status TEXT, reward_xp INTEGER, reward_items TEXT,
    progress INTEGER, target INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, completed_at TIMESTAMP
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS inventory (
    chat_id INTEGER, user_id INTEGER, item_id TEXT,
    quantity INTEGER, rarity TEXT, enchantment TEXT,
    PRIMARY KEY (chat_id, user_id, item_id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS bosses (
    boss_id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER, boss_type TEXT,
    health INTEGER, max_health INTEGER,
    participants_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS expeditions (
    expedition_id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER, user_id INTEGER,
    expedition_type TEXT, difficulty TEXT,
    status TEXT, rewards_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS achievements (
    user_id INTEGER, chat_id INTEGER, achievement_id TEXT,
    unlocked_at TIMESTAMP, progress INTEGER,
    PRIMARY KEY (user_id, chat_id, achievement_id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS trading_posts (
    trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER, from_user INTEGER, to_user INTEGER,
    offer_items TEXT, request_items TEXT,
    status TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS dungeons (
    dungeon_id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER, user_id INTEGER,
    floor INTEGER, reward_multiplier REAL,
    visited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER, event_type TEXT,
    active BOOLEAN DEFAULT 1,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ends_at TIMESTAMP
)
''')

conn.commit()

# ========== КОНТЕНТ: НОВЫЕ СИСТЕМЫ ==========

# 🐾 ПИТОМЦЫ
PETS = {
    "wolf": {
        "name": "Волк",
        "emoji": "🐺",
        "damage_bonus": 10,
        "xp_bonus": 1.1,
        "abilities": ["howl", "pounce"]
    },
    "dragon": {
        "name": "Маленький Дракон",
        "emoji": "🐉",
        "damage_bonus": 20,
        "xp_bonus": 1.5,
        "abilities": ["fire_breath", "fly"]
    },
    "phoenix": {
        "name": "Феникс",
        "emoji": "🔥",
        "damage_bonus": 15,
        "xp_bonus": 1.3,
        "special": "revive_on_death"
    },
    "shadow": {
        "name": "Тень",
        "emoji": "⚫",
        "damage_bonus": 12,
        "xp_bonus": 1.2,
        "abilities": ["invisibility"]
    }
}

# ⚔️ РЕЙДОВЫЕ БОССЫ
RAID_BOSSES = {
    "ancient_lich": {
        "name": "Древний Лич",
        "emoji": "💀",
        "health": 500,
        "difficulty": "Легендарно",
        "rewards_per_player": 300,
        "loot": ["lich_staff", "soul_crystal"],
        "min_players": 3
    },
    "world_serpent": {
        "name": "Мировой Змей",
        "emoji": "🐍",
        "health": 800,
        "difficulty": "Эпик",
        "rewards_per_player": 400,
        "loot": ["serpent_scale", "eternal_gem"],
        "min_players": 5
    },
    "time_lord": {
        "name": "Лорд Времени",
        "emoji": "⏰",
        "health": 600,
        "difficulty": "Смертельно",
        "rewards_per_player": 350,
        "loot": ["chronometer", "time_crystal"],
        "min_players": 4
    }
}

# 🏰 ПОДЗЕМЕЛЬЯ
DUNGEONS_LIST = {
    "starter": {
        "name": "Пещера началась",
        "floors": 3,
        "enemies": ["goblin", "wolf"],
        "xp_per_floor": 50,
        "loot_rarity": ["common", "uncommon"]
    },
    "dark_forest": {
        "name": "Тёмный лес",
        "floors": 5,
        "enemies": ["orc", "shadow_knight"],
        "xp_per_floor": 100,
        "loot_rarity": ["uncommon", "rare"]
    },
    "forbidden_temple": {
        "name": "Запретный храм",
        "floors": 10,
        "enemies": ["dragon", "shadow_knight", "lich"],
        "xp_per_floor": 200,
        "loot_rarity": ["rare", "legendary"]
    }
}

# 🎁 СОБЫТИЯ
ACTIVE_EVENTS = {
    "halloween": {
        "name": "Хеллоуин",
        "emoji": "🎃",
        "xp_multiplier": 1.5,
        "extra_drops": ["cursed_scroll"],
        "duration_days": 7
    },
    "christmas": {
        "name": "Рождество",
        "emoji": "🎄",
        "xp_multiplier": 1.3,
        "extra_drops": ["gift_box"],
        "duration_days": 14
    },
    "summer_adventure": {
        "name": "Летнее приключение",
        "emoji": "☀️",
        "xp_multiplier": 1.2,
        "extra_drops": ["beach_treasure"],
        "duration_days": 30
    }
}

# 🎁 ЕЖЕДНЕВНЫЕ ЧЕЛЛЕНДЖИ
DAILY_CHALLENGES = {
    "dragon_slayer": {
        "name": "Охотник на драконов",
        "description": "Победи 5 драконов",
        "reward_xp": 500,
        "reward_items": ["dragon_scale"],
        "emoji": "🐉"
    },
    "collector": {
        "name": "Коллекционер",
        "description": "Собери 10 разных предметов",
        "reward_xp": 300,
        "reward_items": ["rare_gem"],
        "emoji": "💎"
    },
    "exploration": {
        "name": "Путешественник",
        "description": "Открой 3 подземелья",
        "reward_xp": 400,
        "reward_items": ["map_fragment"],
        "emoji": "🗺️"
    }
}

# 🔧 УЛУЧШЕНИЯ ПРЕДМЕТОВ
ENCHANTMENTS = {
    "fire": {"name": "Огненное", "damage_bonus": 5, "emoji": "🔥"},
    "ice": {"name": "Ледяное", "defense_bonus": 5, "emoji": "❄️"},
    "lightning": {"name": "Молния", "damage_bonus": 8, "emoji": "⚡"},
    "shadow": {"name": "Тень", "damage_bonus": 6, "emoji": "⚫"}
}

# 👑 РЕПУТАЦИЯ
REPUTATION_LEVELS = {
    0: {"name": "Неизвестный", "emoji": "❓", "min_rep": 0},
    1: {"name": "Любитель", "emoji": "🟢", "min_rep": 100},
    2: {"name": "Герой", "emoji": "🟢🟢", "min_rep": 500},
    3: {"name": "Легенда", "emoji": "🟢🟢🟢", "min_rep": 1000},
    4: {"name": "Божество", "emoji": "👑", "min_rep": 2000}
}

ENEMIES = {
    "goblin": {"name": "Гоблин", "health": 20, "damage": 5, "xp": 50, "loot": ["copper_coin"], "emoji": "👹"},
    "orc": {"name": "Орк", "health": 40, "damage": 10, "xp": 100, "loot": ["iron_ore"], "emoji": "🗡️"},
    "dragon": {"name": "Дракон", "health": 150, "damage": 30, "xp": 500, "loot": ["dragon_scale"], "emoji": "🐉"},
    "shadow_knight": {"name": "Рыцарь Теней", "health": 80, "damage": 20, "xp": 250, "loot": ["dark_crystal"], "emoji": "⚔️"},
    "wolf": {"name": "Волк", "health": 15, "damage": 5, "xp": 30, "loot": ["wolf_fang"], "emoji": "🐺"},
    "lich": {"name": "Лич", "health": 200, "damage": 40, "xp": 600, "loot": ["soul_essence"], "emoji": "💀"}
}

ITEMS = {
    "copper_coin": {"name": "Медная монета", "rarity": "common", "emoji": "🪙"},
    "gold_coin": {"name": "Золотая монета", "rarity": "uncommon", "emoji": "✨"},
    "gem": {"name": "Драгоценный камень", "rarity": "rare", "emoji": "💎"},
    "dragon_scale": {"name": "Чешуя дракона", "rarity": "legendary", "emoji": "🐉"},
    "cursed_scroll": {"name": "Проклятый свиток", "rarity": "rare", "emoji": "📜"},
    "gift_box": {"name": "Подарочный ящик", "rarity": "uncommon", "emoji": "🎁"},
    "artifact": {"name": "Артефакт", "rarity": "rare", "emoji": "🏛️"},
    "health_potion": {"name": "Зелье здоровья", "rarity": "common", "emoji": "❤️"},
}

LEVEL_REQUIREMENTS = {i: i * 250 for i in range(1, 21)}

# ========== ФУНКЦИИ БД ==========

def safe_db_execute(func):
    def wrapper(*args, **kwargs):
        with db_lock:
            return func(*args, **kwargs)
    return wrapper

@safe_db_execute
def init_player(chat_id, user_id, user_name):
    cursor.execute('SELECT * FROM players WHERE chat_id=? AND user_id=?', (chat_id, user_id))
    if not cursor.fetchone():
        cursor.execute(
            'INSERT INTO players (chat_id, user_id, user_name, pet_id) VALUES (?, ?, ?, ?)',
            (chat_id, user_id, user_name, "wolf")
        )
        conn.commit()
        return True
    return False

@safe_db_execute
def get_player(chat_id, user_id):
    cursor.execute('SELECT * FROM players WHERE chat_id=? AND user_id=?', (chat_id, user_id))
    row = cursor.fetchone()
    if row:
        return {
            "level": row[3],
            "xp": row[4],
            "health": row[5],
            "mana": row[6],
            "reputation": row[8],
            "pet_id": row[9],
            "pet_level": row[10],
        }
    return None

@safe_db_execute
def add_xp(chat_id, user_id, user_name, xp_amount):
    player = get_player(chat_id, user_id)
    if not player:
        init_player(chat_id, user_id, user_name)
        player = get_player(chat_id, user_id)

    new_xp = player["xp"] + xp_amount
    new_level = player["level"]

    while new_level < 20 and new_xp >= LEVEL_REQUIREMENTS.get(new_level + 1, 99999):
        new_level += 1

    cursor.execute(
        'UPDATE players SET experience=?, level=? WHERE chat_id=? AND user_id=?',
        (new_xp, new_level, chat_id, user_id),
    )
    conn.commit()
    return new_xp, new_level, new_level > player["level"]

@safe_db_execute
def add_reputation(chat_id, user_id, amount):
    cursor.execute('SELECT reputation FROM players WHERE chat_id=? AND user_id=?', (chat_id, user_id))
    row = cursor.fetchone()
    new_rep = (row[0] if row else 0) + amount
    cursor.execute(
        'UPDATE players SET reputation=? WHERE chat_id=? AND user_id=?',
        (new_rep, chat_id, user_id),
    )
    conn.commit()
    return new_rep

@safe_db_execute
def add_item(chat_id, user_id, item_id, quantity=1, enchantment=None):
    rarity = ITEMS.get(item_id, {}).get("rarity", "common")
    cursor.execute(
        'SELECT quantity FROM inventory WHERE chat_id=? AND user_id=? AND item_id=?',
        (chat_id, user_id, item_id),
    )
    row = cursor.fetchone()

    if row:
        cursor.execute(
            'UPDATE inventory SET quantity=? WHERE chat_id=? AND user_id=? AND item_id=?',
            (row[0] + quantity, chat_id, user_id, item_id),
        )
    else:
        cursor.execute(
            'INSERT INTO inventory VALUES (?, ?, ?, ?, ?, ?)',
            (chat_id, user_id, item_id, quantity, rarity, enchantment),
        )
    conn.commit()

@safe_db_execute
def get_player_pet(chat_id, user_id):
    cursor.execute('SELECT pet_id, pet_level FROM players WHERE chat_id=? AND user_id=?', (chat_id, user_id))
    row = cursor.fetchone()
    if row:
        return {"pet_id": row[0], "pet_level": row[1]}
    return None

@safe_db_execute
def level_up_pet(chat_id, user_id):
    cursor.execute('SELECT pet_level FROM players WHERE chat_id=? AND user_id=?', (chat_id, user_id))
    row = cursor.fetchone()
    if row:
        new_level = min(row[0] + 1, 100)
        cursor.execute(
            'UPDATE players SET pet_level=? WHERE chat_id=? AND user_id=?',
            (new_level, chat_id, user_id),
        )
        conn.commit()
        return new_level
    return 0

@safe_db_execute
def start_raid(chat_id, boss_type):
    boss = RAID_BOSSES[boss_type]
    cursor.execute(
        'INSERT INTO bosses (chat_id, boss_type, health, max_health, participants_json) '
        'VALUES (?, ?, ?, ?, ?)',
        (chat_id, boss_type, boss["health"], boss["health"], json.dumps([])),
    )
    conn.commit()
    cursor.execute(
        'SELECT boss_id FROM bosses WHERE chat_id=? AND boss_type=? '
        'ORDER BY boss_id DESC LIMIT 1',
        (chat_id, boss_type),
    )
    return cursor.fetchone()[0]

@safe_db_execute
def get_active_raid(chat_id):
    cursor.execute(
        'SELECT boss_id, boss_type, health FROM bosses '
        'WHERE chat_id=? ORDER BY boss_id DESC LIMIT 1',
        (chat_id,),
    )
    return cursor.fetchone()

# ========== КОМАНДЫ: ОСНОВНЫЕ ==========

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    init_player(chat_id, user.id, user.first_name)

    keyboard = [
        [InlineKeyboardButton("⚔️ Начать битву", callback_data="start_battle")],
        [InlineKeyboardButton("📜 Квесты", callback_data="show_quests")],
        [InlineKeyboardButton("👤 Профиль", callback_data="show_profile")],
        [InlineKeyboardButton("🐾 Питомец", callback_data="show_pet")],
        [InlineKeyboardButton("⚔️ РЕЙД", callback_data="show_raids")],
        [InlineKeyboardButton("🏰 Подземелья", callback_data="show_dungeons")],
    ]

    await update.message.reply_text(
        "🧙‍♂️ QUEST WORLD - Легендарные приключения!\n\n"
        "⚔️ /battle - Сразиться\n"
        "👤 /profile - Профиль\n"
        "📦 /inventory - Инвентарь\n"
        "🏰 /dungeon - Подземелья\n"
        "👥 /raid - Групповой рейд\n"
        "🎁 /daily - Ежедневный челлендж\n"
        "🐾 /pet - Питомец\n"
        "📊 /leaderboard - Топ героев",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = getattr(update, "callback_query", None)
    message = query.message if query else update.message
    user = query.from_user if query else update.effective_user
    chat_id = message.chat_id

    init_player(chat_id, user.id, user.first_name)
    player = get_player(chat_id, user.id)
    pet = get_player_pet(chat_id, user.id)

    rep_level = 0
    for level, info in REPUTATION_LEVELS.items():
        if player["reputation"] >= info["min_rep"]:
            rep_level = level

    rep_info = REPUTATION_LEVELS[rep_level]
    pet_info = PETS.get(pet["pet_id"], {})

    text = (
        f"👤 {user.first_name}\n"
        f"⭐ Уровень: {player['level']}/20\n"
        f"📈 XP: {player['xp']}/{LEVEL_REQUIREMENTS.get(player['level'] + 1, 99999)}\n"
        f"❤️ Здоровье: {player['health']}/100\n"
        f"💙 Мана: {player['mana']}/50\n\n"
        f"{rep_info['emoji']} Репутация: {rep_info['name']} ({player['reputation']} pts)\n\n"
        f"🐾 Питомец: {pet_info.get('emoji', '❓')} "
        f"{pet_info.get('name', 'Неизвестный')} (Уровень {pet['pet_level']})"
    )

    if query:
        await query.edit_message_text(text)
    else:
        await message.reply_text(text)

async def show_pet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id

    pet = get_player_pet(chat_id, user.id)
    pet_info = PETS[pet["pet_id"]]

    text = (
        f"{pet_info['emoji']} {pet_info['name']}\n\n"
        f"Уровень: {pet['pet_level']}\n"
        f"💪 Бонус урона: +{pet_info['damage_bonus'] * (1 + (pet['pet_level'] - 1) * 0.1):.0f}\n"
        f"📈 Бонус XP: ×{pet_info['xp_bonus']}\n\n"
        f"Умения: {', '.join(pet_info.get('abilities', []))}"
    )

    keyboard = [
        [InlineKeyboardButton("🍖 Накормить (+10 XP)", callback_data="feed_pet")],
        [InlineKeyboardButton("🔄 Изменить питомца", callback_data="change_pet")],
        [InlineKeyboardButton("👤 Профиль", callback_data="show_profile")],
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_raids(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id

    text = "⚔️ ГРУППОВЫЕ РЕЙДЫ (нужна команда!)\n\n"
    keyboard = []

    for raid_id, raid_info in RAID_BOSSES.items():
        text += f"{raid_info['emoji']} {raid_info['name']}\n"
        text += f"   ⚡ Сложность: {raid_info['difficulty']}\n"
        text += f"   👥 Минимум: {raid_info['min_players']} героев\n"
        text += f"   ⭐ Награда: {raid_info['rewards_per_player']} XP на героя\n\n"

        keyboard.append(
            [InlineKeyboardButton(f"Начать {raid_info['emoji']}", callback_data=f"start_raid_{raid_id}")]
        )

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="start_adventure")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_dungeons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id

    text = "🏰 ПОДЗЕМЕЛЬЯ С ПРОГРЕССИЕЙ\n\n"
    text += "Преодолей все этажи подземелья, враги становятся сильнее!\n"
    text += "Дроп редких предметов с каждым этажом.\n\n"

    keyboard = []
    for dungeon_id, dungeon_info in DUNGEONS_LIST.items():
        text += f"🏰 {dungeon_info['name']}\n"
        text += f"   📊 Этажей: {dungeon_info['floors']}\n"
        text += f"   ⭐ XP за этаж: {dungeon_info['xp_per_floor']}\n\n"

        keyboard.append(
            [InlineKeyboardButton(f"Войти {dungeon_info['name']}", callback_data=f"enter_dungeon_{dungeon_id}")]
        )

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="start_adventure")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_daily_challenges(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id

    text = "🎁 ЕЖЕДНЕВНЫЕ ЧЕЛЛЕНДЖИ\n"
    text += "Выполняй челленджи для больших наград!\n\n"

    keyboard = []
    for challenge_id, challenge_info in DAILY_CHALLENGES.items():
        text += f"{challenge_info['emoji']} {challenge_info['name']}\n"
        text += f"   📝 {challenge_info['description']}\n"
        text += f"   ⭐ Награда: {challenge_info['reward_xp']} XP\n\n"

        keyboard.append(
            [
                InlineKeyboardButton(
                    f"Выполнить {challenge_info['emoji']}",
                    callback_data=f"start_challenge_{challenge_id}",
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="start_adventure")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def start_battle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id

    enemy_type = random.choice(list(ENEMIES.keys()))
    enemy = ENEMIES[enemy_type]

    player = get_player(chat_id, user.id)
    pet = get_player_pet(chat_id, user.id)
    pet_info = PETS.get(pet["pet_id"], {})

    battle_data = {
        "user_id": user.id,
        "enemy_type": enemy_type,
        "enemy_health": enemy["health"],
        "user_health": player["health"],
        "user_mana": player["mana"],
        "pet_damage_bonus": pet_info.get("damage_bonus", 0),
    }

    context.user_data[f"battle_{chat_id}"] = battle_data

    text = (
        f"⚔️ НАЧАЛО БИТВЫ!\n\n"
        f"Противник: {enemy['emoji']} {enemy['name']}\n"
        f"❤️ Его здоровье: {enemy['health']}\n"
        f"🐾 Твой питомец: {pet_info.get('emoji', '❓')} "
        f"{pet_info.get('name', 'Неизвестный')} (+{pet_info.get('damage_bonus', 0)} урона)"
    )

    keyboard = [
        [InlineKeyboardButton("🗡️ Атаковать", callback_data="battle_attack")],
        [InlineKeyboardButton("🔥 Магия", callback_data="battle_magic")],
        [InlineKeyboardButton("🐾 Питомец", callback_data="battle_pet_attack")],
        [InlineKeyboardButton("💚 Исцелить", callback_data="battle_heal")],
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def battle_attack(update: Update, context: ContextTypes.DEFAULT_TYPE, action_type):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id

    battle = context.user_data.get(f"battle_{chat_id}")
    if not battle:
        await query.answer("❌ Битва не начата", show_alert=True)
        return

    enemy = ENEMIES[battle["enemy_type"]]

    if action_type == "attack":
        damage = random.randint(5, 15)
        battle["enemy_health"] -= damage
        text = f"🗡️ Обычная атака! Урон: {damage}\n"

    elif action_type == "magic":
        damage = 15 + battle["pet_damage_bonus"]
        battle["enemy_health"] -= damage
        text = f"🔥 Огненный шар! Урон: {damage}\n"

    elif action_type == "pet_attack":
        damage = battle["pet_damage_bonus"] + random.randint(5, 10)
        battle["enemy_health"] -= damage
        text = f"🐾 Питомец атакует! Урон: {damage}\n"

    elif action_type == "heal":
        heal = 20
        battle["user_health"] = min(100, battle["user_health"] + heal)
        text = f"💚 Исцеление! +{heal} HP\n"

    # Враг бьёт
    if battle["enemy_health"] > 0:
        enemy_damage = random.randint(enemy["damage"] - 5, enemy["damage"] + 5)
        battle["user_health"] -= enemy_damage
        text += f"{enemy['emoji']} Враг наносит {enemy_damage} урона!\n"

    if battle["enemy_health"] <= 0:
        xp_reward = enemy["xp"]
        new_xp, new_level, leveled_up = add_xp(chat_id, user.id, user.first_name, xp_reward)
        add_reputation(chat_id, user.id, 10)
        level_up_pet(chat_id, user.id)

        for loot_item in enemy.get("loot", []):
            add_item(chat_id, user.id, loot_item)

        text += "\n🎉 ПОБЕДА!\n"
        text += f"⭐ +{xp_reward} XP\n"
        text += "👁️ +10 Репутация\n"
        text += "🐾 Питомец получил опыт!\n"
        text += "📦 Лут:"
        for item in enemy.get("loot", []):
            text += f"\n   • {ITEMS[item]['emoji']} {ITEMS[item]['name']}"

        if leveled_up:
            text += "\n\n🌟 ПОВЫШЕНИЕ УРОВНЯ!"

        context.user_data.pop(f"battle_{chat_id}", None)

        keyboard = [
            [InlineKeyboardButton("⚔️ Ещё одна битва", callback_data="start_battle")],
            [InlineKeyboardButton("👤 Профиль", callback_data="show_profile")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if battle["user_health"] <= 0:
        text += "\n💀 ПОРАЖЕНИЕ!\nТы повержен в бою..."
        context.user_data.pop(f"battle_{chat_id}", None)

        keyboard = [
            [InlineKeyboardButton("⚔️ Попробовать снова", callback_data="start_battle")],
            [InlineKeyboardButton("👤 Профиль", callback_data="show_profile")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    text += f"\n❤️ Твоё здоровье: {battle['user_health']}/100"
    text += f"\n❤️ Здоровье врага: {battle['enemy_health']}/{enemy['health']}"

    keyboard = [
        [InlineKeyboardButton("🗡️ Атаковать", callback_data="battle_attack")],
        [InlineKeyboardButton("🔥 Магия", callback_data="battle_magic")],
        [InlineKeyboardButton("🐾 Питомец", callback_data="battle_pet_attack")],
        [InlineKeyboardButton("💚 Исцелить", callback_data="battle_heal")],
    ]

    context.user_data[f"battle_{chat_id}"] = battle
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ========== ОБРАБОТЧИК КНОПОК ==========

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    try:
        await query.answer()
    except BadRequest:
        return

    if query.data == "show_profile":
        await show_profile(update, context)
    elif query.data == "show_pet":
        await show_pet(update, context)
    elif query.data == "show_raids":
        await show_raids(update, context)
    elif query.data == "show_dungeons":
        await show_dungeons(update, context)
    elif query.data == "show_challenges":
        await show_daily_challenges(update, context)
    elif query.data == "start_battle":
        await start_battle(update, context)
    elif query.data.startswith("battle_"):
        action = query.data.split("_", 1)[1]
        await battle_attack(update, context, action)

# ========== РЕГИСТРАЦИЯ ==========

def setup_handlers(application):
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("profile", show_profile))
    application.add_handler(CommandHandler("pet", show_pet))
    application.add_handler(CommandHandler("raid", show_raids))
    application.add_handler(CommandHandler("dungeon", show_dungeons))
    application.add_handler(CommandHandler("daily", show_daily_challenges))
    application.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Quest Bot Premium готов!")

import os

if __name__ == "__main__":
    TOKEN = os.getenv("TOKEN")
    if not TOKEN:
        raise RuntimeError("Переменная окружения TOKEN не задана")
    application = ApplicationBuilder().token(TOKEN).build()
    setup_handlers(application)
    application.run_polling(drop_pending_updates=True)
