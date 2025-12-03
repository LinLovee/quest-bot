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
from aiohttp import web

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.FileHandler("quest_bot.log", encoding="utf-8"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

db_lock = threading.RLock()
conn = sqlite3.connect('quest_bot.db', check_same_thread=False, timeout=30.0)
cursor = conn.cursor()

# ========== БД ==========

cursor.execute('''
CREATE TABLE IF NOT EXISTS players (
    chat_id INTEGER, user_id INTEGER, user_name TEXT,
    class TEXT DEFAULT 'warrior',
    level INTEGER DEFAULT 1, experience INTEGER DEFAULT 0,
    health INTEGER DEFAULT 100, max_health INTEGER DEFAULT 100,
    mana INTEGER DEFAULT 50, max_mana INTEGER DEFAULT 50,
    attack INTEGER DEFAULT 10, defense INTEGER DEFAULT 5,
    inventory_slots INTEGER DEFAULT 20,
    reputation INTEGER DEFAULT 0,
    pet_id TEXT, pet_level INTEGER DEFAULT 1,
    gold INTEGER DEFAULT 0,
    total_kills INTEGER DEFAULT 0,
    last_daily TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (chat_id, user_id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS inventory (
    chat_id INTEGER, user_id INTEGER, item_id TEXT,
    quantity INTEGER, rarity TEXT, class_req TEXT,
    PRIMARY KEY (chat_id, user_id, item_id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS achievements (
    user_id INTEGER, chat_id INTEGER, achievement_id TEXT,
    unlocked_at TIMESTAMP, progress INTEGER,
    PRIMARY KEY (user_id, chat_id, achievement_id)
)
''')

conn.commit()

# ========== КЛАССЫ ПЕРСОНАЖЕЙ ==========

CLASSES = {
    "warrior": {
        "name": "Воин",
        "emoji": "⚔️",
        "description": "Сильная атака и защита",
        "base_attack": 15,
        "base_defense": 8,
        "base_health": 120,
        "base_mana": 30,
    },
    "mage": {
        "name": "Маг",
        "emoji": "🔥",
        "description": "Мощная магия и контроль боя",
        "base_attack": 8,
        "base_defense": 3,
        "base_health": 70,
        "base_mana": 100,
    },
    "rogue": {
        "name": "Разбойник",
        "emoji": "🗡️",
        "description": "Быстрая атака и уворот",
        "base_attack": 18,
        "base_defense": 5,
        "base_health": 80,
        "base_mana": 50,
    },
    "paladin": {
        "name": "Паладин",
        "emoji": "⛪",
        "description": "Защита и исцеление",
        "base_attack": 10,
        "base_defense": 12,
        "base_health": 130,
        "base_mana": 70,
    },
    "ranger": {
        "name": "Рейнджер",
        "emoji": "🏹",
        "description": "Дальняя атака и критические удары",
        "base_attack": 16,
        "base_defense": 6,
        "base_health": 90,
        "base_mana": 60,
    },
}

# ========== ПИТОМЦЫ ==========

PETS = {
    "wolf": {"name": "Волк", "emoji": "🐺", "damage_bonus": 10, "defense_bonus": 3, "xp_bonus": 1.1},
    "dragon": {"name": "Дракон", "emoji": "🐉", "damage_bonus": 25, "defense_bonus": 8, "xp_bonus": 1.5},
    "phoenix": {"name": "Феникс", "emoji": "🔥", "damage_bonus": 20, "defense_bonus": 5, "xp_bonus": 1.4},
    "shadow": {"name": "Тень", "emoji": "⚫", "damage_bonus": 15, "defense_bonus": 4, "xp_bonus": 1.3},
    "bear": {"name": "Медведь", "emoji": "🐻", "damage_bonus": 18, "defense_bonus": 10, "xp_bonus": 1.2},
}

# ========== ВРАГИ ==========

ENEMIES = {
    "goblin": {"name": "Гоблин", "emoji": "👹", "level": 1, "health": 15, "damage": 3, "xp": 25, "gold": 10, "loot": ["copper_coin"]},
    "rat": {"name": "Крыса", "emoji": "🐭", "level": 1, "health": 10, "damage": 2, "xp": 15, "gold": 5, "loot": ["copper_coin"]},
    "skeleton": {"name": "Скелет", "emoji": "☠️", "level": 2, "health": 25, "damage": 5, "xp": 40, "gold": 20, "loot": ["bone_fragment"]},
    "zombie": {"name": "Зомби", "emoji": "🧟", "level": 2, "health": 30, "damage": 6, "xp": 50, "gold": 25, "loot": ["rotten_flesh"]},
    "imp": {"name": "Чертёнок", "emoji": "😈", "level": 2, "health": 20, "damage": 7, "xp": 45, "gold": 15, "loot": ["sulfur"]},
    "orc": {"name": "Орк", "emoji": "🗡️", "level": 3, "health": 45, "damage": 12, "xp": 100, "gold": 50, "loot": ["iron_ore"]},
    "troll": {"name": "Тролль", "emoji": "👹", "level": 3, "health": 60, "damage": 11, "xp": 110, "gold": 60, "loot": ["troll_club", "cave_pearl"]},
    "werewolf": {"name": "Оборотень", "emoji": "🐺", "level": 4, "health": 50, "damage": 15, "xp": 130, "gold": 70, "loot": ["wolf_fur", "silver_coin"]},
    "shadow_knight": {"name": "Рыцарь Теней", "emoji": "⚔️", "level": 4, "health": 65, "damage": 18, "xp": 150, "gold": 80, "loot": ["dark_crystal", "iron_sword"]},
    "witch": {"name": "Ведьма", "emoji": "🧙‍♀️", "level": 4, "health": 40, "damage": 20, "xp": 140, "gold": 75, "loot": ["magic_dust", "cursed_potion"]},
    "basilisk": {"name": "Василиск", "emoji": "🐍", "level": 5, "health": 100, "damage": 25, "xp": 200, "gold": 120, "loot": ["basilisk_fang", "poison_vial"]},
    "ice_mage": {"name": "Ледяной маг", "emoji": "❄️", "level": 5, "health": 55, "damage": 28, "xp": 180, "gold": 110, "loot": ["ice_crystal", "mana_potion"]},
    "demon": {"name": "Демон", "emoji": "😈", "level": 6, "health": 120, "damage": 32, "xp": 250, "gold": 150, "loot": ["demonic_essence", "soul_fragment"]},
    "golem": {"name": "Голем", "emoji": "🪨", "level": 6, "health": 150, "damage": 20, "xp": 220, "gold": 140, "loot": ["stone_heart", "magical_core"]},
    "dragon": {"name": "Дракон", "emoji": "🐉", "level": 7, "health": 200, "damage": 40, "xp": 500, "gold": 300, "loot": ["dragon_scale", "dragon_heart"]},
    "lich": {"name": "Лич", "emoji": "💀", "level": 8, "health": 180, "damage": 45, "xp": 550, "gold": 350, "loot": ["soul_essence", "lich_staff"]},
}

# ========== МАГАЗИН ==========

SHOP_ITEMS = {
    # Универсальные предметы
    "health_potion": {"name": "Зелье здоровья", "emoji": "❤️", "price": 50, "rarity": "common", "class": None},
    "mana_potion": {"name": "Зелье маны", "emoji": "💙", "price": 50, "rarity": "common", "class": None},
    
    # Предметы Воина
    "iron_sword": {"name": "Железный меч", "emoji": "⚔️", "price": 200, "rarity": "uncommon", "class": "warrior", "attack": 5},
    "steel_armor": {"name": "Стальная броня", "emoji": "🛡️", "price": 250, "rarity": "uncommon", "class": "warrior", "defense": 4},
    
    # Предметы Мага
    "fireball_staff": {"name": "Посох огня", "emoji": "🔥", "price": 200, "rarity": "rare", "class": "mage", "attack": 8},
    "mage_robe": {"name": "Мантия мага", "emoji": "👗", "price": 150, "rarity": "uncommon", "class": "mage", "mana": 20},
    
    # Предметы Разбойника
    "dagger_set": {"name": "Набор кинжалов", "emoji": "🗡️", "price": 180, "rarity": "uncommon", "class": "rogue", "attack": 6},
    "shadow_cloak": {"name": "Плащ теней", "emoji": "⚫", "price": 220, "rarity": "rare", "class": "rogue", "defense": 3, "attack": 2},
    
    # Предметы Паладина
    "holy_shield": {"name": "Святой щит", "emoji": "⛪", "price": 300, "rarity": "rare", "class": "paladin", "defense": 6},
    "blessed_armor": {"name": "Благословенная броня", "emoji": "✨", "price": 280, "rarity": "rare", "class": "paladin", "defense": 5, "health": 20},
    
    # Предметы Рейнджера
    "longbow": {"name": "Длинный лук", "emoji": "🏹", "price": 220, "rarity": "uncommon", "class": "ranger", "attack": 7},
    "ranger_armor": {"name": "Лёгкая броня рейнджера", "emoji": "🧥", "price": 180, "rarity": "uncommon", "class": "ranger", "defense": 3, "attack": 2},
}

# ========== ПРЕДМЕТЫ ==========

ITEMS = {
    "copper_coin": {"name": "Медная монета", "rarity": "common", "emoji": "🪙"},
    "silver_coin": {"name": "Серебряная монета", "rarity": "uncommon", "emoji": "🟡"},
    "bone_fragment": {"name": "Фрагмент кости", "rarity": "common", "emoji": "🦴"},
    "rotten_flesh": {"name": "Гнилое мясо", "rarity": "common", "emoji": "🥩"},
    "sulfur": {"name": "Сера", "rarity": "uncommon", "emoji": "💛"},
    "iron_ore": {"name": "Железная руда", "rarity": "uncommon", "emoji": "⛏️"},
    "troll_club": {"name": "Дубина тролля", "rarity": "uncommon", "emoji": "🏏"},
    "cave_pearl": {"name": "Пещерная жемчужина", "rarity": "rare", "emoji": "⚪"},
    "wolf_fur": {"name": "Волчий мех", "rarity": "uncommon", "emoji": "🧥"},
    "dark_crystal": {"name": "Тёмный кристалл", "rarity": "rare", "emoji": "🔮"},
    "magic_dust": {"name": "Магическая пыль", "rarity": "uncommon", "emoji": "✨"},
    "cursed_potion": {"name": "Проклятое зелье", "rarity": "rare", "emoji": "🧪"},
    "basilisk_fang": {"name": "Клык василиска", "rarity": "rare", "emoji": "🦷"},
    "poison_vial": {"name": "Флакон яда", "rarity": "rare", "emoji": "☠️"},
    "ice_crystal": {"name": "Кристалл льда", "rarity": "rare", "emoji": "❄️"},
    "demonic_essence": {"name": "Сущность демона", "rarity": "legendary", "emoji": "💜"},
    "soul_fragment": {"name": "Фрагмент души", "rarity": "rare", "emoji": "👻"},
    "stone_heart": {"name": "Каменное сердце", "rarity": "rare", "emoji": "🪨"},
    "magical_core": {"name": "Магическое ядро", "rarity": "legendary", "emoji": "⚛️"},
    "dragon_scale": {"name": "Чешуя дракона", "rarity": "legendary", "emoji": "🐉"},
    "dragon_heart": {"name": "Сердце дракона", "rarity": "legendary", "emoji": "❤️"},
    "soul_essence": {"name": "Сущность души", "rarity": "legendary", "emoji": "💫"},
    "lich_staff": {"name": "Посох Лича", "rarity": "legendary", "emoji": "🏚️"},
}

LEVEL_REQUIREMENTS = {i: i * 300 for i in range(1, 21)}

# ========== ФУНКЦИИ БД ==========

def safe_db_execute(func):
    def wrapper(*args, **kwargs):
        with db_lock:
            return func(*args, **kwargs)
    return wrapper

@safe_db_execute
def init_player(chat_id, user_id, user_name, player_class="warrior"):
    cursor.execute('SELECT * FROM players WHERE chat_id=? AND user_id=?', (chat_id, user_id))
    if not cursor.fetchone():
        class_info = CLASSES[player_class]
        cursor.execute(
            'INSERT INTO players (chat_id, user_id, user_name, class, attack, defense, health, max_health, mana, max_mana, pet_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (chat_id, user_id, user_name, player_class, class_info["base_attack"], class_info["base_defense"], 
             class_info["base_health"], class_info["base_health"], class_info["base_mana"], class_info["base_mana"], "wolf")
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
            "class": row[3],
            "level": row[4],
            "xp": row[5],
            "health": row[6],
            "max_health": row[7],
            "mana": row[8],
            "max_mana": row[9],
            "attack": row[10],
            "defense": row[11],
            "reputation": row[13],
            "pet_id": row[14],
            "pet_level": row[15],
            "gold": row[16],
            "total_kills": row[17],
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
    leveled_up = False

    while new_level < 20 and new_xp >= LEVEL_REQUIREMENTS.get(new_level + 1, 99999):
        new_level += 1
        leveled_up = True

    cursor.execute(
        'UPDATE players SET experience=?, level=? WHERE chat_id=? AND user_id=?',
        (new_xp, new_level, chat_id, user_id),
    )
    conn.commit()
    return new_xp, new_level, leveled_up

@safe_db_execute
def add_gold(chat_id, user_id, amount):
    cursor.execute('SELECT gold FROM players WHERE chat_id=? AND user_id=?', (chat_id, user_id))
    row = cursor.fetchone()
    new_gold = (row[0] if row else 0) + amount
    cursor.execute(
        'UPDATE players SET gold=? WHERE chat_id=? AND user_id=?',
        (new_gold, chat_id, user_id),
    )
    conn.commit()
    return new_gold

@safe_db_execute
def subtract_gold(chat_id, user_id, amount):
    cursor.execute('SELECT gold FROM players WHERE chat_id=? AND user_id=?', (chat_id, user_id))
    row = cursor.fetchone()
    current_gold = row[0] if row else 0
    if current_gold >= amount:
        new_gold = current_gold - amount
        cursor.execute(
            'UPDATE players SET gold=? WHERE chat_id=? AND user_id=?',
            (new_gold, chat_id, user_id),
        )
        conn.commit()
        return True
    return False

@safe_db_execute
def add_item(chat_id, user_id, item_id, quantity=1):
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
            (chat_id, user_id, item_id, quantity, rarity, None),
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
def add_kill(chat_id, user_id):
    cursor.execute('SELECT total_kills FROM players WHERE chat_id=? AND user_id=?', (chat_id, user_id))
    row = cursor.fetchone()
    new_kills = (row[0] if row else 0) + 1
    cursor.execute(
        'UPDATE players SET total_kills=? WHERE chat_id=? AND user_id=?',
        (new_kills, chat_id, user_id),
    )
    conn.commit()
    return new_kills

@safe_db_execute
def get_top_players(chat_id, limit=10):
    cursor.execute(
        'SELECT user_name, level, total_kills, gold, class FROM players WHERE chat_id=? ORDER BY level DESC, total_kills DESC LIMIT ?',
        (chat_id, limit)
    )
    return cursor.fetchall()

# ========== КОМАНДЫ ==========

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    player = get_player(chat_id, user.id)
    if not player:
        keyboard = []
        for class_id, class_info in CLASSES.items():
            keyboard.append([InlineKeyboardButton(f"{class_info['emoji']} {class_info['name']}", callback_data=f"class_{class_id}")])
        
        await update.message.reply_text(
            "⚔️ QUEST WORLD - RPG ПРИКЛЮЧЕНИЕ ⚔️\n\n"
            "Выбери свой класс для начала приключения!\n\n"
            "Каждый класс имеет свои сильные стороны:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        keyboard = [
            [InlineKeyboardButton("⚔️ БОЙ", callback_data="start_battle")],
            [InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data="show_profile")],
            [InlineKeyboardButton("🐾 ПИТОМЕЦ", callback_data="show_pet"), InlineKeyboardButton("📦 ИНВЕНТАРЬ", callback_data="show_inventory")],
            [InlineKeyboardButton("🛒 МАГАЗИН", callback_data="show_shop")],
            [InlineKeyboardButton("👑 ТОП ИГРОКОВ", callback_data="show_top")],
        ]

        await update.message.reply_text(
            f"⚔️ QUEST WORLD - RPG ПРИКЛЮЧЕНИЕ ⚔️\n\n"
            f"Добро пожаловать, {CLASSES[player['class']]['emoji']} {CLASSES[player['class']]['name']}!\n\n"
            f"Исследуй подземелья и становись легендой!",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

async def select_class(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    class_id = query.data.split("_")[1]
    init_player(chat_id, user.id, user.first_name, class_id)
    
    class_info = CLASSES[class_id]
    text = (
        f"✅ Ты выбрал класс: {class_info['emoji']} {class_info['name']}\n\n"
        f"📝 {class_info['description']}\n\n"
        f"⚔️ Атака: {class_info['base_attack']}\n"
        f"🛡️ Защита: {class_info['base_defense']}\n"
        f"❤️ HP: {class_info['base_health']}\n"
        f"💙 Мана: {class_info['base_mana']}\n\n"
        f"Нажми кнопку ниже для начала игры!"
    )
    
    keyboard = [[InlineKeyboardButton("🎮 НАЧАТЬ ИГРУ", callback_data="main_menu")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = getattr(update, "callback_query", None)
    message = query.message if query else update.message
    user = query.from_user if query else update.effective_user
    chat_id = message.chat_id

    player = get_player(chat_id, user.id)
    pet = get_player_pet(chat_id, user.id)
    pet_info = PETS.get(pet["pet_id"], {})
    class_info = CLASSES[player["class"]]

    xp_percent = int((player["xp"] / LEVEL_REQUIREMENTS.get(player["level"] + 1, 99999)) * 100)

    text = (
        f"👤 {user.first_name}\n"
        f"{'─' * 30}\n\n"
        f"{class_info['emoji']} Класс: {class_info['name']}\n"
        f"⭐ Уровень: {player['level']}/20\n"
        f"📊 XP: {player['xp']}/{LEVEL_REQUIREMENTS.get(player['level'] + 1, 99999)} ({xp_percent}%)\n"
        f"{'█' * (xp_percent // 10)}{'░' * (10 - xp_percent // 10)}\n\n"
        f"❤️ HP: {player['health']}/{player['max_health']}\n"
        f"💙 Мана: {player['mana']}/{player['max_mana']}\n"
        f"⚔️ Атака: {player['attack']}\n"
        f"🛡️ Защита: {player['defense']}\n\n"
        f"💰 Золото: {player['gold']}\n"
        f"🐾 Питомец: {pet_info.get('emoji', '❓')} {pet_info.get('name', 'Нет')} (Ур. {pet['pet_level']})\n"
        f"⚔️ Побед: {player['total_kills']}"
    )

    keyboard = [[InlineKeyboardButton("⬅️ НАЗАД", callback_data="main_menu")]]

    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_pet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id

    pet = get_player_pet(chat_id, user.id)
    pet_info = PETS[pet["pet_id"]]

    text = (
        f"{pet_info['emoji']} {pet_info['name'].upper()}\n"
        f"{'─' * 30}\n\n"
        f"Уровень: {pet['pet_level']}/100\n\n"
        f"⚔️ Бонус атаки: +{pet_info['damage_bonus']}\n"
        f"🛡️ Бонус защиты: +{pet_info['defense_bonus']}\n"
        f"📈 Бонус XP: ×{pet_info['xp_bonus']}"
    )

    keyboard = [[InlineKeyboardButton("⬅️ НАЗАД", callback_data="main_menu")]]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_inventory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id

    cursor.execute('SELECT item_id, quantity, rarity FROM inventory WHERE chat_id=? AND user_id=?', (chat_id, user.id))
    items = cursor.fetchall()

    if not items:
        text = "📦 ИНВЕНТАРЬ\n\n❌ Инвентарь пуст"
    else:
        text = "📦 ИНВЕНТАРЬ\n" + f"{'─' * 30}\n\n"
        for item_id, qty, rarity in items:
            item_info = ITEMS.get(item_id, {})
            rarity_emoji = {"common": "⚪", "uncommon": "🟢", "rare": "🔵", "legendary": "🟡"}.get(rarity, "⚪")
            text += f"{item_info.get('emoji', '?')} {item_info.get('name', item_id)} x{qty} {rarity_emoji}\n"

    keyboard = [[InlineKeyboardButton("⬅️ НАЗАД", callback_data="main_menu")]]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    player = get_player(chat_id, user.id)
    player_class = player["class"]

    text = "🛒 МАГАЗИН\n" + f"{'─' * 30}\n\n"
    text += f"💰 Твоё золото: {player['gold']}\n\n"
    
    keyboard = []
    for item_id, item_info in SHOP_ITEMS.items():
        if item_info["class"] is None or item_info["class"] == player_class:
            keyboard.append([InlineKeyboardButton(
                f"{item_info['emoji']} {item_info['name']} - {item_info['price']}💰",
                callback_data=f"buy_{item_id}"
            )])

    keyboard.append([InlineKeyboardButton("⬅️ НАЗАД", callback_data="main_menu")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def buy_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    item_id = query.data.split("_")[1]
    item_info = SHOP_ITEMS[item_id]
    
    player = get_player(chat_id, user.id)
    
    if player["gold"] >= item_info["price"]:
        if subtract_gold(chat_id, user.id, item_info["price"]):
            add_item(chat_id, user.id, item_id)
            text = f"✅ Ты купил: {item_info['emoji']} {item_info['name']}"
            keyboard = [
                [InlineKeyboardButton("🛒 К МАГАЗИНУ", callback_data="show_shop")],
                [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")],
            ]
        else:
            text = "❌ Не удалось совершить покупку"
            keyboard = [[InlineKeyboardButton("🛒 МАГАЗИН", callback_data="show_shop")]]
    else:
        text = f"❌ Недостаточно золота!\nНужно: {item_info['price']} 💰\nУ тебя: {player['gold']} 💰"
        keyboard = [[InlineKeyboardButton("🛒 МАГАЗИН", callback_data="show_shop")]]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    
    top_players = get_top_players(chat_id, 10)
    
    text = "👑 ТОП 10 ИГРОКОВ\n" + f"{'─' * 30}\n\n"
    
    for i, (name, level, kills, gold, player_class) in enumerate(top_players, 1):
        class_emoji = CLASSES[player_class]["emoji"]
        text += f"{i}. {class_emoji} {name}\n"
        text += f"   ⭐ Ур. {level} | ⚔️ {kills} побед | 💰 {gold} золота\n\n"
    
    if not top_players:
        text = "👑 ТОП 10 ИГРОКОВ\n\n❌ Данных нет"
    
    keyboard = [[InlineKeyboardButton("⬅️ НАЗАД", callback_data="main_menu")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def start_battle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id

    player = get_player(chat_id, user.id)
    pet = get_player_pet(chat_id, user.id)
    pet_info = PETS.get(pet["pet_id"], {})

    enemy_type = random.choice(list(ENEMIES.keys()))
    enemy = ENEMIES[enemy_type]

    player_attack = player["attack"] + pet_info.get("damage_bonus", 0)
    player_defense = player["defense"] + pet_info.get("defense_bonus", 0)

    battle_data = {
        "user_id": user.id,
        "enemy_type": enemy_type,
        "enemy_health": enemy["health"],
        "user_health": player["health"],
        "user_max_health": player["max_health"],
        "user_attack": player_attack,
        "user_defense": player_defense,
        "enemy_attack": enemy["damage"],
        "pet_name": pet_info.get("name", "Питомец"),
        "pet_emoji": pet_info.get("emoji", "❓"),
        "xp_reward": enemy["xp"],
        "gold_reward": enemy["gold"],
        "loot": enemy.get("loot", []),
    }

    context.user_data[f"battle_{chat_id}"] = battle_data

    hp_bar = "█" * (player["health"] // 10) + "░" * (10 - player["health"] // 10)
    enemy_hp_bar = "█" * (enemy["health"] // 10) + "░" * (10 - enemy["health"] // 10)

    text = (
        f"⚔️ БОЙ НАЧАЛАСЬ!\n"
        f"{'─' * 30}\n\n"
        f"{enemy['emoji']} {enemy['name'].upper()}\n"
        f"❤️ [{enemy_hp_bar}] {enemy['health']} HP\n\n"
        f"🐾 {battle_data['pet_emoji']} {battle_data['pet_name']}\n"
        f"❤️ [{hp_bar}] {player['health']} HP\n\n"
        f"Награда: +{enemy['xp']} XP, +{enemy['gold']} 💰"
    )

    keyboard = [
        [InlineKeyboardButton("🗡️ АТАКА", callback_data="battle_attack"), InlineKeyboardButton("🔥 МАГИЯ", callback_data="battle_magic")],
        [InlineKeyboardButton("💚 ЛЕЧЕНИЕ", callback_data="battle_heal"), InlineKeyboardButton("🛡️ ЗАЩИТА", callback_data="battle_defend")],
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def battle_action(update: Update, context: ContextTypes.DEFAULT_TYPE, action):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id

    battle = context.user_data.get(f"battle_{chat_id}")
    if not battle:
        await query.answer("❌ Битва не начата", show_alert=True)
        return

    player_damage = 0
    text = ""

    if action == "attack":
        player_damage = random.randint(battle["user_attack"] - 3, battle["user_attack"] + 5)
        text = f"🗡️ МОЩНАЯ АТАКА!\nУрон: {player_damage}\n\n"

    elif action == "magic":
        player_damage = random.randint(battle["user_attack"] + 5, battle["user_attack"] + 15)
        text = f"🔥 ОГНЕННЫЙ ШАР!\nУрон: {player_damage}\n\n"

    elif action == "heal":
        heal = random.randint(15, 30)
        battle["user_health"] = min(battle["user_max_health"], battle["user_health"] + heal)
        text = f"💚 ИСЦЕЛЕНИЕ!\nВосстановлено: +{heal} HP\n\n"
        player_damage = 0

    elif action == "defend":
        text = f"🛡️ ЗАЩИТА!\nЗащита +50% в этом ходу\n\n"
        player_damage = 0

    battle["enemy_health"] -= player_damage

    if battle["enemy_health"] > 0:
        if action == "defend":
            enemy_damage = random.randint(1, max(1, battle["enemy_attack"] // 2))
        else:
            enemy_damage = random.randint(max(1, battle["enemy_attack"] - battle["user_defense"]), battle["enemy_attack"])
        
        battle["user_health"] -= enemy_damage
        text += f"{ENEMIES[battle['enemy_type']]['emoji']} Враг наносит {enemy_damage} урона!\n"

    if battle["enemy_health"] <= 0:
        add_xp(chat_id, user.id, user.first_name, battle["xp_reward"])
        add_gold(chat_id, user.id, battle["gold_reward"])
        add_kill(chat_id, user.id)
        level_up_pet(chat_id, user.id)

        text += f"\n🎉 ПОБЕДА!\n"
        text += f"⭐ +{battle['xp_reward']} XP\n"
        text += f"💰 +{battle['gold_reward']} золота\n"
        text += f"🐾 Питомец получил опыт!\n\n"
        text += f"📦 ЛOOT:\n"

        for loot_item in battle["loot"]:
            add_item(chat_id, user.id, loot_item)
            item_info = ITEMS.get(loot_item, {})
            text += f"  {item_info.get('emoji', '?')} {item_info.get('name', loot_item)}\n"

        context.user_data.pop(f"battle_{chat_id}", None)

        keyboard = [
            [InlineKeyboardButton("⚔️ ЕЩЕ БОЙ", callback_data="start_battle")],
            [InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data="show_profile"), InlineKeyboardButton("🏠 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if battle["user_health"] <= 0:
        text += f"\n💀 ПОРАЖЕНИЕ!\nТы был повержен в бою..."
        context.user_data.pop(f"battle_{chat_id}", None)

        keyboard = [
            [InlineKeyboardButton("⚔️ ПОПРОБОВАТЬ СНОВА", callback_data="start_battle")],
            [InlineKeyboardButton("🏠 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    hp_bar = "█" * (battle["user_health"] // 10) + "░" * (10 - battle["user_health"] // 10)
    enemy_hp_bar = "█" * max(1, battle["enemy_health"] // 10) + "░" * (10 - max(1, battle["enemy_health"] // 10))

    text += f"\n{ENEMIES[battle['enemy_type']]['emoji']} {ENEMIES[battle['enemy_type']]['name']}\n"
    text += f"❤️ [{enemy_hp_bar}] {battle['enemy_health']} HP\n\n"
    text += f"🐾 {battle['pet_emoji']} {battle['pet_name']}\n"
    text += f"❤️ [{hp_bar}] {battle['user_health']} HP"

    keyboard = [
        [InlineKeyboardButton("🗡️ АТАКА", callback_data="battle_attack"), InlineKeyboardButton("🔥 МАГИЯ", callback_data="battle_magic")],
        [InlineKeyboardButton("💚 ЛЕЧЕНИЕ", callback_data="battle_heal"), InlineKeyboardButton("🛡️ ЗАЩИТА", callback_data="battle_defend")],
    ]

    context.user_data[f"battle_{chat_id}"] = battle
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    try:
        await query.answer()
    except BadRequest:
        return

    if query.data == "main_menu":
        await start_command(update, context)
    elif query.data.startswith("class_"):
        await select_class(update, context)
    elif query.data == "show_profile":
        await show_profile(update, context)
    elif query.data == "show_pet":
        await show_pet(update, context)
    elif query.data == "show_inventory":
        await show_inventory(update, context)
    elif query.data == "show_shop":
        await show_shop(update, context)
    elif query.data.startswith("buy_"):
        await buy_item(update, context)
    elif query.data == "show_top":
        await show_top(update, context)
    elif query.data == "start_battle":
        await start_battle(update, context)
    elif query.data in ["battle_attack", "battle_magic", "battle_heal", "battle_defend"]:
        action = query.data.split("_")[1]
        await battle_action(update, context, action)

# ========== ВЕБХУК ==========

application = None

async def webhook_handler(request):
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return web.Response(status=200)
    except Exception as e:
        logger.error(f"Ошибка в webhook: {e}")
        return web.Response(status=200)

async def health_check(request):
    return web.Response(text="OK", status=200)

def setup_handlers(app):
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("battle", start_battle))
    app.add_handler(CommandHandler("profile", show_profile))
    app.add_handler(CommandHandler("shop", show_shop))
    app.add_handler(CommandHandler("top", show_top))
    app.add_handler(CallbackQueryHandler(button_handler))
    logger.info("✅ Quest Bot Premium готов!")

async def start_server():
    global application
    
    TOKEN = os.getenv("TOKEN")
    if not TOKEN:
        raise RuntimeError("Переменная окружения TOKEN не задана")
    
    application = ApplicationBuilder().token(TOKEN).build()
    setup_handlers(application)
    
    await application.initialize()
    await application.start()
    
    app = web.Application()
    app.router.add_post('/webhook', webhook_handler)
    app.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    
    logger.info(f"🌐 Вебсервер слушает на порту {port}")
    
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("❌ Завершение работы...")
        await application.stop()
        await application.shutdown()

if __name__ == "__main__":
    asyncio.run(start_server())
