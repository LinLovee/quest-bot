"""
MEDIEVAL RPG BOT - Полнофункциональный Telegram RPG
Текстовая RPG-игра про средневековье с боевой системой, крафтингом, подземельями и лидербордом
"""

import os
import random
import logging
import sqlite3
import threading
import asyncio
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, 
    CallbackQueryHandler, filters
)

# ========== КОНФИГУРАЦИЯ ==========
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("medieval_rpg.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ========== БД ИНИЦИАЛИЗАЦИЯ ==========
db_lock = threading.RLock()
conn = sqlite3.connect('medieval_rpg.db', check_same_thread=False, timeout=30.0)
cursor = conn.cursor()

# Создание таблиц
cursor.execute('''
CREATE TABLE IF NOT EXISTS players (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    chat_id INTEGER,
    class TEXT DEFAULT 'warrior',
    level INTEGER DEFAULT 1,
    exp INTEGER DEFAULT 0,
    health INTEGER DEFAULT 100,
    max_health INTEGER DEFAULT 100,
    damage INTEGER DEFAULT 10,
    defense INTEGER DEFAULT 5,
    gold INTEGER DEFAULT 0,
    dungeon_rating INTEGER DEFAULT 0,
    total_kills INTEGER DEFAULT 0,
    total_bosses_killed INTEGER DEFAULT 0,
    equipped_weapon TEXT,
    equipped_armor TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS inventory (
    user_id INTEGER,
    item_id TEXT,
    item_name TEXT,
    item_type TEXT,
    rarity TEXT,
    quantity INTEGER DEFAULT 1,
    stats TEXT,
    equipped INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, item_id),
    FOREIGN KEY (user_id) REFERENCES players(user_id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS dungeon_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    floor_reached INTEGER,
    score INTEGER,
    rewards TEXT,
    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES players(user_id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS crafting_materials (
    user_id INTEGER,
    material_id TEXT,
    quantity INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, material_id),
    FOREIGN KEY (user_id) REFERENCES players(user_id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS battles (
    user_id INTEGER PRIMARY KEY,
    enemy_id TEXT,
    enemy_health INTEGER,
    player_health INTEGER,
    FOREIGN KEY (user_id) REFERENCES players(user_id)
)
''')

conn.commit()

# ========== ИГРОВЫЕ КОНСТАНТЫ ==========

# Классы
CLASSES = {
    "warrior": {
        "name": "Воин",
        "emoji": "⚔️",
        "description": "Сильная атака и защита",
        "base_hp": 100,
        "base_damage": 10,
        "base_defense": 5
    },
    "mage": {
        "name": "Маг",
        "emoji": "🔥",
        "description": "Мощная магия и урон",
        "base_hp": 70,
        "base_damage": 15,
        "base_defense": 2
    },
    "rogue": {
        "name": "Разбойник",
        "emoji": "🗡️",
        "description": "Быстрая атака и крит",
        "base_hp": 80,
        "base_damage": 12,
        "base_defense": 3
    },
    "paladin": {
        "name": "Паладин",
        "emoji": "⛪",
        "description": "Защита и исцеление",
        "base_hp": 120,
        "base_damage": 9,
        "base_defense": 8
    }
}

# Редкость предметов
RARITY = {
    "common": {"emoji": "⚪️", "chance": 60, "multiplier": 1.0},
    "uncommon": {"emoji": "🟢", "chance": 25, "multiplier": 1.3},
    "rare": {"emoji": "🔵", "chance": 10, "multiplier": 1.7},
    "epic": {"emoji": "🟣", "chance": 4, "multiplier": 2.2},
    "legendary": {"emoji": "🟠", "chance": 1, "multiplier": 3.0}
}

# Враги по локациям
ENEMIES = {
    # Темный лес (ур. 1-10)
    "goblin": {"name": "Гоблин", "emoji": "👹", "level": 1, "hp": 15, "damage": 3, "xp": 25, "gold": 10, "loot": ["copper_ore"], "boss": False},
    "wolf": {"name": "Волк", "emoji": "🐺", "level": 2, "hp": 20, "damage": 5, "xp": 35, "gold": 15, "loot": ["wolf_fang"], "boss": False},
    "skeleton": {"name": "Скелет", "emoji": "☠️", "level": 3, "hp": 25, "damage": 6, "xp": 50, "gold": 20, "loot": ["bone"], "boss": False},
    "orc": {"name": "Орк", "emoji": "🗡️", "level": 4, "hp": 35, "damage": 8, "xp": 75, "gold": 30, "loot": ["iron_ore"], "boss": False},
    "troll": {"name": "Тролль", "emoji": "🏔️", "level": 5, "hp": 50, "damage": 10, "xp": 100, "gold": 50, "loot": ["mithril_ore"], "boss": False},
    "basilisk": {"name": "Василиск", "emoji": "🐍", "level": 6, "hp": 70, "damage": 12, "xp": 150, "gold": 75, "loot": ["fang", "scale"], "boss": False},
    "ice_wizard": {"name": "Ледяной маг", "emoji": "❄️", "level": 7, "hp": 60, "damage": 15, "xp": 200, "gold": 100, "loot": ["ice_crystal"], "boss": False},
    "demon": {"name": "Демон", "emoji": "😈", "level": 8, "hp": 100, "damage": 18, "xp": 300, "gold": 150, "loot": ["demonic_core"], "boss": True},
    "dragon": {"name": "Дракон", "emoji": "🐉", "level": 10, "hp": 200, "damage": 25, "xp": 500, "gold": 300, "loot": ["dragon_scale", "dragon_heart"], "boss": True}
}

# Локации
LOCATIONS = {
    "dark_forest": {
        "name": "Тёмный лес",
        "emoji": "🌲",
        "level_min": 1,
        "level_max": 10,
        "enemies": ["goblin", "wolf", "skeleton"]
    },
    "mountain_caves": {
        "name": "Горные пещеры",
        "emoji": "⛰️",
        "level_min": 10,
        "level_max": 25,
        "enemies": ["orc", "troll", "basilisk"]
    },
    "castle_ruins": {
        "name": "Руины замка",
        "emoji": "🏚️",
        "level_min": 25,
        "level_max": 50,
        "enemies": ["ice_wizard", "demon"]
    },
    "volcano": {
        "name": "Вулкан",
        "emoji": "🌋",
        "level_min": 50,
        "level_max": 75,
        "enemies": ["demon", "dragon"]
    },
    "demon_lair": {
        "name": "Логово демонов",
        "emoji": "👹",
        "level_min": 75,
        "level_max": 100,
        "enemies": ["dragon"]
    }
}

# Предметы (оружие/броня)
EQUIPMENT = {
    "iron_sword": {
        "name": "Железный меч",
        "emoji": "⚔️",
        "type": "weapon",
        "damage": 5,
        "level": 1,
        "price": 100
    },
    "steel_sword": {
        "name": "Стальной меч",
        "emoji": "🗡️",
        "type": "weapon",
        "damage": 15,
        "level": 5,
        "price": 500
    },
    "legendary_blade": {
        "name": "Легендарный клинок",
        "emoji": "⚡",
        "type": "weapon",
        "damage": 50,
        "level": 20,
        "price": 5000
    },
    "iron_armor": {
        "name": "Железная броня",
        "emoji": "🛡️",
        "type": "armor",
        "defense": 4,
        "level": 1,
        "price": 150
    },
    "steel_armor": {
        "name": "Стальная броня",
        "emoji": "🛡️",
        "type": "armor",
        "defense": 10,
        "level": 5,
        "price": 600
    },
    "legendary_armor": {
        "name": "Легендарная броня",
        "emoji": "👑",
        "type": "armor",
        "defense": 40,
        "level": 20,
        "price": 5000
    }
}

# Материалы для крафта
MATERIALS = {
    "copper_ore": {"name": "Медная руда", "emoji": "🟠"},
    "iron_ore": {"name": "Железная руда", "emoji": "⛏️"},
    "mithril_ore": {"name": "Мифриловая руда", "emoji": "💎"},
    "bone": {"name": "Кость", "emoji": "🦴"},
    "wolf_fang": {"name": "Клык волка", "emoji": "🦷"},
    "dragon_scale": {"name": "Чешуя дракона", "emoji": "🐉"},
    "dragon_heart": {"name": "Сердце дракона", "emoji": "❤️"},
    "demonic_core": {"name": "Демонический ядро", "emoji": "🔴"},
    "ice_crystal": {"name": "Кристалл льда", "emoji": "❄️"},
    "fang": {"name": "Клык", "emoji": "🦷"},
    "scale": {"name": "Чешуя", "emoji": "🐍"}
}

# Рецепты крафта
RECIPES = {
    "iron_sword": {
        "name": "Создать Железный меч",
        "emoji": "⚔️",
        "materials": {"copper_ore": 5, "iron_ore": 10},
        "result": "iron_sword",
        "level": 1
    },
    "steel_sword": {
        "name": "Создать Стальной меч",
        "emoji": "🗡️",
        "materials": {"iron_ore": 20, "mithril_ore": 10},
        "result": "steel_sword",
        "level": 5
    }
}

# Константы игры
MAX_LEVEL = 50
EXP_BASE = 100
INVENTORY_MAX = 50

def get_exp_for_level(level):
    """Формула для опыта до следующего уровня"""
    return int(EXP_BASE * (level ** 1.5))

# ========== ФУНКЦИИ БД ==========

def safe_db(func):
    """Декоратор для безопасного доступа к БД"""
    def wrapper(*args, **kwargs):
        with db_lock:
            return func(*args, **kwargs)
    return wrapper

@safe_db
def init_player(user_id, username, chat_id, player_class="warrior"):
    """Инициализация нового игрока"""
    cursor.execute('SELECT * FROM players WHERE user_id=?', (user_id,))
    if not cursor.fetchone():
        class_info = CLASSES[player_class]
        cursor.execute('''
            INSERT INTO players 
            (user_id, username, chat_id, class, level, exp, health, max_health, damage, defense, gold)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, username, chat_id, player_class, 1, 0, class_info["base_hp"], 
              class_info["base_hp"], class_info["base_damage"], class_info["base_defense"], 0))
        conn.commit()
        return True
    return False

@safe_db
def get_player(user_id):
    """Получить данные игрока"""
    cursor.execute('SELECT * FROM players WHERE user_id=?', (user_id,))
    row = cursor.fetchone()
    if row:
        return {
            "user_id": row[0],
            "username": row[1],
            "class": row[3],
            "level": row[4],
            "exp": row[5],
            "health": row[6],
            "max_health": row[7],
            "damage": row[8],
            "defense": row[9],
            "gold": row[10],
            "dungeon_rating": row[11],
            "total_kills": row[12],
            "total_bosses": row[13],
            "equipped_weapon": row[14],
            "equipped_armor": row[15]
        }
    return None

@safe_db
def add_exp(user_id, amount):
    """Добавить опыт с проверкой повышения уровня"""
    player = get_player(user_id)
    if not player:
        return
    
    new_exp = player["exp"] + amount
    new_level = player["level"]
    
    while new_level < MAX_LEVEL and new_exp >= get_exp_for_level(new_level):
        new_exp -= get_exp_for_level(new_level)
        new_level += 1
    
    # Увеличение характеристик при повышении уровня
    new_hp = player["max_health"] + (new_level - player["level"]) * 20
    new_damage = player["damage"] + (new_level - player["level"]) * 5
    
    cursor.execute('''
        UPDATE players 
        SET exp=?, level=?, max_health=?, health=?, damage=?
        WHERE user_id=?
    ''', (new_exp, new_level, new_hp, new_hp, new_damage, user_id))
    conn.commit()
    
    return new_level > player["level"]

@safe_db
def add_gold(user_id, amount):
    """Добавить золото"""
    cursor.execute('UPDATE players SET gold=gold+? WHERE user_id=?', (amount, user_id))
    conn.commit()

@safe_db
def subtract_gold(user_id, amount):
    """Вычесть золото"""
    player = get_player(user_id)
    if player and player["gold"] >= amount:
        cursor.execute('UPDATE players SET gold=gold-? WHERE user_id=?', (amount, user_id))
        conn.commit()
        return True
    return False

@safe_db
def add_item(user_id, item_id, quantity=1):
    """Добавить предмет в инвентарь"""
    cursor.execute(
        'SELECT quantity FROM inventory WHERE user_id=? AND item_id=?',
        (user_id, item_id)
    )
    row = cursor.fetchone()
    if row:
        cursor.execute(
            'UPDATE inventory SET quantity=quantity+? WHERE user_id=? AND item_id=?',
            (quantity, user_id, item_id)
        )
    else:
        cursor.execute(
            'INSERT INTO inventory (user_id, item_id, item_name, item_type, rarity, quantity) VALUES (?, ?, ?, ?, ?, ?)',
            (user_id, item_id, MATERIALS.get(item_id, {}).get("name", item_id), "material", "common", quantity)
        )
    conn.commit()

@safe_db
def get_inventory(user_id):
    """Получить инвентарь"""
    cursor.execute('SELECT item_id, item_name, quantity, rarity FROM inventory WHERE user_id=?', (user_id,))
    return cursor.fetchall()

@safe_db
def get_materials(user_id):
    """Получить материалы для крафта"""
    cursor.execute(
        'SELECT material_id, quantity FROM crafting_materials WHERE user_id=?',
        (user_id,)
    )
    return {row[0]: row[1] for row in cursor.fetchall()}

@safe_db
def add_material(user_id, material_id, quantity=1):
    """Добавить материал"""
    cursor.execute(
        'SELECT quantity FROM crafting_materials WHERE user_id=? AND material_id=?',
        (user_id, material_id)
    )
    row = cursor.fetchone()
    if row:
        cursor.execute(
            'UPDATE crafting_materials SET quantity=quantity+? WHERE user_id=? AND material_id=?',
            (quantity, user_id, material_id)
        )
    else:
        cursor.execute(
            'INSERT INTO crafting_materials (user_id, material_id, quantity) VALUES (?, ?, ?)',
            (user_id, material_id, quantity)
        )
    conn.commit()

@safe_db
def subtract_material(user_id, material_id, quantity):
    """Вычесть материал"""
    cursor.execute(
        'SELECT quantity FROM crafting_materials WHERE user_id=? AND material_id=?',
        (user_id, material_id)
    )
    row = cursor.fetchone()
    if row and row[0] >= quantity:
        cursor.execute(
            'UPDATE crafting_materials SET quantity=quantity-? WHERE user_id=? AND material_id=?',
            (quantity, user_id, material_id)
        )
        conn.commit()
        return True
    return False

@safe_db
def equip_item(user_id, item_id):
    """Экипировать предмет"""
    item = EQUIPMENT.get(item_id)
    if not item:
        return False
    
    if item["type"] == "weapon":
        cursor.execute('UPDATE players SET equipped_weapon=? WHERE user_id=?', (item_id, user_id))
    else:
        cursor.execute('UPDATE players SET equipped_armor=? WHERE user_id=?', (item_id, user_id))
    
    conn.commit()
    return True

@safe_db
def get_leaderboard(limit=10):
    """Получить лидербо"""
    cursor.execute('''
        SELECT username, level, total_kills, gold, dungeon_rating
        FROM players
        ORDER BY dungeon_rating DESC, level DESC, gold DESC
        LIMIT ?
    ''', (limit,))
    return cursor.fetchall()

@safe_db
def save_dungeon_run(user_id, floor, score, rewards):
    """Сохранить прохождение подземелья"""
    cursor.execute('''
        INSERT INTO dungeon_runs (user_id, floor_reached, score, rewards)
        VALUES (?, ?, ?, ?)
    ''', (user_id, floor, score, json.dumps(rewards)))
    conn.commit()
    
    # Обновить рейтинг
    cursor.execute('SELECT dungeon_rating FROM players WHERE user_id=?', (user_id,))
    current_rating = cursor.fetchone()[0]
    if floor > current_rating:
        cursor.execute('UPDATE players SET dungeon_rating=? WHERE user_id=?', (floor, user_id))
        conn.commit()

@safe_db
def start_battle(user_id, player_level):
    """Начать новый бой"""
    # Выбрать врага подходящего уровня
    suitable_enemies = [e for e in ENEMIES.values() if abs(e["level"] - player_level) <= 2]
    if not suitable_enemies:
        suitable_enemies = list(ENEMIES.values())
    
    enemy_key = random.choice([k for k, v in ENEMIES.items() if v in suitable_enemies])
    enemy = ENEMIES[enemy_key]
    
    # Сохранить бой в БД
    cursor.execute('DELETE FROM battles WHERE user_id=?', (user_id,))
    cursor.execute(
        'INSERT INTO battles (user_id, enemy_id, enemy_health, player_health) VALUES (?, ?, ?, ?)',
        (user_id, enemy_key, enemy["hp"], 0)
    )
    conn.commit()
    return enemy_key

@safe_db
def get_battle(user_id):
    """Получить текущий бой"""
    cursor.execute('SELECT enemy_id, enemy_health, player_health FROM battles WHERE user_id=?', (user_id,))
    row = cursor.fetchone()
    if row:
        return {"enemy_id": row[0], "enemy_health": row[1], "player_health": row[2]}
    return None

@safe_db
def update_battle(user_id, enemy_health, player_health):
    """Обновить состояние боя"""
    cursor.execute(
        'UPDATE battles SET enemy_health=?, player_health=? WHERE user_id=?',
        (enemy_health, player_health, user_id)
    )
    conn.commit()

@safe_db
def end_battle(user_id):
    """Завершить бой"""
    cursor.execute('DELETE FROM battles WHERE user_id=?', (user_id,))
    conn.commit()

# ========== ОБРАБОТЧИКИ КОМАНД ==========

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    player = get_player(user.id)
    
    if not player:
        # Выбор класса
        keyboard = []
        for class_id, class_info in CLASSES.items():
            keyboard.append([InlineKeyboardButton(
                f"{class_info['emoji']} {class_info['name']}",
                callback_data=f"class_{class_id}"
            )])
        
        text = (
            "⚔️ MEDIEVAL RPG ⚔️\n\n"
            "Добро пожаловать в средневековую RPG!\n\n"
            "Выбери класс для начала приключения:\n\n"
        )
        
        for class_id, class_info in CLASSES.items():
            text += f"{class_info['emoji']} {class_info['name']}: {class_info['description']}\n"
        
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await show_main_menu(update, context, user.id)

async def select_class(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор класса"""
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    class_id = query.data.split("_")[1]
    
    init_player(user.id, user.first_name, chat_id, class_id)
    class_info = CLASSES[class_id]
    
    text = (
        f"✅ Ты выбрал класс: {class_info['emoji']} {class_info['name']}\n\n"
        f"{class_info['description']}\n\n"
        f"⚔️ Урон: {class_info['base_damage']}\n"
        f"🛡️ Защита: {class_info['base_defense']}\n"
        f"❤️ HP: {class_info['base_hp']}\n\n"
        f"Теперь начни свое приключение!"
    )
    
    keyboard = [[InlineKeyboardButton("🎮 В ИГРУ", callback_data="main_menu")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id=None):
    """Главное меню"""
    if update.callback_query:
        query = update.callback_query
        user = query.from_user
    else:
        user = update.effective_user
    
    if user_id is None:
        user_id = user.id
    
    player = get_player(user_id)
    if not player:
        return
    
    class_info = CLASSES[player["class"]]
    
    text = (
        f"⚔️ MEDIEVAL RPG ⚔️\n"
        f"{'━' * 30}\n\n"
        f"{class_info['emoji']} {class_info['name']} | Ур. {player['level']}\n"
        f"❤️ HP: {player['health']}/{player['max_health']}\n"
        f"⚔️ Урон: {player['damage']}\n"
        f"🛡️ Защита: {player['defense']}\n"
        f"💰 Золото: {player['gold']}\n\n"
        f"Выбери действие:"
    )
    
    keyboard = [
        [InlineKeyboardButton("⚔️ БОЙ", callback_data="start_battle"),
         InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data="show_profile")],
        [InlineKeyboardButton("🎒 ИНВЕНТАРЬ", callback_data="show_inventory"),
         InlineKeyboardButton("🛡️ ЭКИПИРОВКА", callback_data="show_equipment")],
        [InlineKeyboardButton("🏰 ЛОКАЦИИ", callback_data="show_locations"),
         InlineKeyboardButton("🔨 КРАФТ", callback_data="show_crafting")],
        [InlineKeyboardButton("🏆 ПОДЗЕМЕЛЬЕ", callback_data="show_dungeon"),
         InlineKeyboardButton("📊 ЛИДЕРБО", callback_data="show_leaderboard")],
    ]
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Профиль игрока"""
    query = update.callback_query
    player = get_player(query.from_user.id)
    
    if not player:
        await query.answer("❌ Профиль не найден", show_alert=True)
        return
    
    class_info = CLASSES[player["class"]]
    exp_next = get_exp_for_level(player["level"])
    exp_percent = int((player["exp"] / exp_next) * 100) if exp_next > 0 else 0
    
    equipped_weapon = ""
    equipped_armor = ""
    
    if player["equipped_weapon"]:
        w = EQUIPMENT.get(player["equipped_weapon"], {})
        equipped_weapon = f"⚔️ {w.get('name', '?')}\n"
    if player["equipped_armor"]:
        a = EQUIPMENT.get(player["equipped_armor"], {})
        equipped_armor = f"🛡️ {a.get('name', '?')}\n"
    
    text = (
        f"👤 ПРОФИЛЬ\n"
        f"{'━' * 30}\n\n"
        f"{class_info['emoji']} Класс: {class_info['name']}\n"
        f"⭐ Уровень: {player['level']}/{MAX_LEVEL}\n"
        f"📊 Опыт: {player['exp']}/{exp_next} ({exp_percent}%)\n"
        f"{'█' * (exp_percent // 10)}{'░' * (10 - exp_percent // 10)}\n\n"
        f"❤️ Здоровье: {player['health']}/{player['max_health']}\n"
        f"⚔️ Урон: {player['damage']}\n"
        f"🛡️ Защита: {player['defense']}\n"
        f"💰 Золото: {player['gold']}\n\n"
        f"🎖️ СТАТИСТИКА:\n"
        f"⚔️ Побед: {player['total_kills']}\n"
        f"👹 Боссов убито: {player['total_bosses']}\n"
        f"🏆 Рейтинг подземелья: {player['dungeon_rating']}\n\n"
        f"🛡️ ЭКИПИРОВКА:\n"
        f"{equipped_weapon if equipped_weapon else '❌ Нет оружия\n'}"
        f"{equipped_armor if equipped_armor else '❌ Нет брони\n'}"
    )
    
    keyboard = [[InlineKeyboardButton("⬅️ МЕНЮ", callback_data="main_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_inventory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Инвентарь"""
    query = update.callback_query
    user_id = query.from_user.id
    
    inventory = get_inventory(user_id)
    
    if not inventory:
        text = "📦 ИНВЕНТАРЬ\n\n❌ Инвентарь пуст"
    else:
        text = "📦 ИНВЕНТАРЬ\n" + "━" * 30 + "\n\n"
        for item_id, name, qty, rarity in inventory:
            rarity_info = RARITY.get(rarity, {})
            text += f"{rarity_info.get('emoji', '?')} {name} x{qty}\n"
    
    keyboard = [[InlineKeyboardButton("⬅️ МЕНЮ", callback_data="main_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_equipment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Экипировка"""
    query = update.callback_query
    player = get_player(query.from_user.id)
    
    text = "🛡️ ЭКИПИРОВКА\n" + "━" * 30 + "\n\n"
    
    if player["equipped_weapon"]:
        w = EQUIPMENT[player["equipped_weapon"]]
        text += f"⚔️ Оружие: {w['name']} (+{w['damage']} урона)\n"
    else:
        text += "⚔️ Оружие: ❌ Не надетого\n"
    
    if player["equipped_armor"]:
        a = EQUIPMENT[player["equipped_armor"]]
        text += f"🛡️ Броня: {a['name']} (+{a['defense']} защиты)\n"
    else:
        text += "🛡️ Броня: ❌ Не надетого\n"
    
    text += f"\n📊 ВСЕГО:\n"
    text += f"⚔️ Урон: {player['damage']}\n"
    text += f"🛡️ Защита: {player['defense']}\n"
    
    keyboard = [
        [InlineKeyboardButton("⚔️ ОРУЖИЕ", callback_data="equipment_weapons"),
         InlineKeyboardButton("🛡️ БРОНЯ", callback_data="equipment_armor")],
        [InlineKeyboardButton("⬅️ МЕНЮ", callback_data="main_menu")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def equipment_weapons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор оружия"""
    query = update.callback_query
    player = get_player(query.from_user.id)
    
    text = "⚔️ ВЫБЕРИТЕ ОРУЖИЕ\n" + "━" * 30 + "\n\n"
    keyboard = []
    
    for item_id, item_info in EQUIPMENT.items():
        if item_info["type"] == "weapon":
            can_equip = "✅" if player["level"] >= item_info["level"] else "❌"
            text += f"{item_info['emoji']} {item_info['name']} (Ур. {item_info['level']}, +{item_info['damage']})\n{can_equip}\n"
            keyboard.append([InlineKeyboardButton(f"Надеть {item_info['emoji']}", callback_data=f"equip_{item_id}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ НАЗАД", callback_data="show_equipment")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def equipment_armor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор брони"""
    query = update.callback_query
    player = get_player(query.from_user.id)
    
    text = "🛡️ ВЫБЕРИТЕ БРОНЮ\n" + "━" * 30 + "\n\n"
    keyboard = []
    
    for item_id, item_info in EQUIPMENT.items():
        if item_info["type"] == "armor":
            can_equip = "✅" if player["level"] >= item_info["level"] else "❌"
            text += f"{item_info['emoji']} {item_info['name']} (Ур. {item_info['level']}, +{item_info['defense']})\n{can_equip}\n"
            keyboard.append([InlineKeyboardButton(f"Надеть {item_info['emoji']}", callback_data=f"equip_{item_id}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ НАЗАД", callback_data="show_equipment")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def equip_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Экипировать предмет"""
    query = update.callback_query
    item_id = query.data.split("_")[1]
    player = get_player(query.from_user.id)
    
    item = EQUIPMENT.get(item_id)
    if not item or player["level"] < item["level"]:
        await query.answer("❌ Не можешь экипировать этот предмет!", show_alert=True)
        return
    
    equip_item(query.from_user.id, item_id)
    
    text = f"✅ Ты экипировал: {item['emoji']} {item['name']}\n\n"
    text += "Вернись в меню, чтобы увидеть обновленные характеристики"
    
    keyboard = [[InlineKeyboardButton("🛡️ ЭКИПИРОВКА", callback_data="show_equipment")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_locations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор локации"""
    query = update.callback_query
    player = get_player(query.from_user.id)
    
    text = "🏰 ВЫБЕРИТЕ ЛОКАЦИЮ\n" + "━" * 30 + "\n\n"
    keyboard = []
    
    for loc_id, loc_info in LOCATIONS.items():
        level_ok = "✅" if player["level"] >= loc_info["level_min"] else "⚠️"
        text += f"{loc_info['emoji']} {loc_info['name']} (Ур. {loc_info['level_min']}-{loc_info['level_max']}) {level_ok}\n"
        keyboard.append([InlineKeyboardButton(f"{loc_info['emoji']}", callback_data=f"location_{loc_id}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ МЕНЮ", callback_data="main_menu")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def location_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбрана локация"""
    query = update.callback_query
    loc_id = query.data.split("_")[1]
    location = LOCATIONS[loc_id]
    
    text = (
        f"{location['emoji']} {location['name']}\n"
        f"{'━' * 30}\n\n"
        f"Уровень: {location['level_min']}-{location['level_max']}\n"
        f"Враги: {', '.join([ENEMIES[e]['name'] for e in location['enemies']])}\n\n"
        f"Начать бой?"
    )
    
    context.user_data["current_location"] = loc_id
    keyboard = [
        [InlineKeyboardButton("⚔️ НАЧАТЬ БОЙ", callback_data="start_battle_in_location")],
        [InlineKeyboardButton("⬅️ ВЫБРАТЬ ЛОКАЦИЮ", callback_data="show_locations")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def start_battle_in_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать бой в выбранной локации"""
    query = update.callback_query
    user_id = query.from_user.id
    player = get_player(user_id)
    
    loc_id = context.user_data.get("current_location")
    location = LOCATIONS[loc_id]
    
    # Выбрать врага из списка локации
    enemy_key = random.choice(location["enemies"])
    enemy = ENEMIES[enemy_key]
    
    # Сохранить бой в БД
    cursor.execute('DELETE FROM battles WHERE user_id=?', (user_id,))
    cursor.execute(
        'INSERT INTO battles (user_id, enemy_id, enemy_health, player_health) VALUES (?, ?, ?, ?)',
        (user_id, enemy_key, enemy["hp"], player["health"])
    )
    conn.commit()
    
    text = (
        f"⚔️ БОЙ\n"
        f"{'━' * 30}\n\n"
        f"👤 Твоё здоровье: {player['health']}/{player['max_health']}\n\n"
        f"{enemy['emoji']} {enemy['name']} (Ур. {enemy['level']})\n"
        f"HP: {enemy['hp']}\n"
        f"⚔️ Урон: {enemy['damage']}\n\n"
        f"Выбери действие:"
    )
    
    keyboard = [
        [InlineKeyboardButton("⚔️ АТАКОВАТЬ", callback_data="battle_attack"),
         InlineKeyboardButton("🏥 ЛЕЧИТЬСЯ", callback_data="battle_heal")],
        [InlineKeyboardButton("❌ СБЕЖАТЬ", callback_data="battle_flee")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def start_battle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать обычный бой"""
    query = update.callback_query
    user_id = query.from_user.id
    player = get_player(user_id)
    
    enemy_key = start_battle(user_id, player["level"])
    enemy = ENEMIES[enemy_key]
    
    text = (
        f"⚔️ БОЙ\n"
        f"{'━' * 30}\n\n"
        f"👤 Твоё здоровье: {player['health']}/{player['max_health']}\n\n"
        f"{enemy['emoji']} {enemy['name']} (Ур. {enemy['level']})\n"
        f"HP: {enemy['hp']}\n"
        f"⚔️ Урон: {enemy['damage']}\n\n"
        f"Выбери действие:"
    )
    
    keyboard = [
        [InlineKeyboardButton("⚔️ АТАКОВАТЬ", callback_data="battle_attack"),
         InlineKeyboardButton("🏥 ЛЕЧИТЬСЯ", callback_data="battle_heal")],
        [InlineKeyboardButton("❌ СБЕЖАТЬ", callback_data="battle_flee")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def battle_attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Атака"""
    query = update.callback_query
    user_id = query.from_user.id
    player = get_player(user_id)
    battle = get_battle(user_id)
    
    if not battle:
        await query.answer("❌ Боя нет!", show_alert=True)
        return
    
    enemy = ENEMIES[battle["enemy_id"]]
    
    # Расчет урона
    player_damage = player["damage"] + random.randint(-2, 5)
    enemy_damage = enemy["damage"] + random.randint(-1, 3)
    
    new_enemy_health = max(0, battle["enemy_health"] - player_damage)
    new_player_health = max(0, player["health"] - enemy_damage)
    
    update_battle(user_id, new_enemy_health, new_player_health)
    
    text = (
        f"⚔️ АТАКА\n"
        f"{'━' * 30}\n\n"
        f"💥 Ты нанес {player_damage} урона!\n"
        f"⚔️ Враг нанес {enemy_damage} урона!\n\n"
        f"👤 Твоё здоровье: {new_player_health}/{player['max_health']}\n"
        f"{enemy['emoji']} Здоровье врага: {new_enemy_health}\n\n"
    )
    
    if new_enemy_health <= 0:
        # Победа
        xp_reward = int(enemy["xp"] * 1.2)
        gold_reward = enemy["gold"]
        
        add_exp(user_id, xp_reward)
        add_gold(user_id, gold_reward)
        
        cursor.execute('UPDATE players SET total_kills=total_kills+1 WHERE user_id=?', (user_id,))
        if enemy["boss"]:
            cursor.execute('UPDATE players SET total_bosses_killed=total_bosses_killed+1 WHERE user_id=?', (user_id,))
        
        # Дроп лута
        loot_text = ""
        for loot_item in enemy.get("loot", []):
            add_material(user_id, loot_item)
            loot_text += f"{MATERIALS.get(loot_item, {}).get('emoji', '?')} {MATERIALS.get(loot_item, {}).get('name', loot_item)}\n"
        
        conn.commit()
        end_battle(user_id)
        
        text = (
            f"🎉 ПОБЕДА!\n"
            f"{'━' * 30}\n\n"
            f"{enemy['emoji']} {enemy['name']} разбит!\n\n"
            f"📊 НАГРАДА:\n"
            f"+{xp_reward} XP\n"
            f"+{gold_reward} 💰\n\n"
            f"📦 ЛУТ:\n"
            f"{loot_text if loot_text else 'Ничего'}\n"
        )
        
        keyboard = [
            [InlineKeyboardButton("⚔️ НОВЫЙ БОЙ", callback_data="start_battle")],
            [InlineKeyboardButton("⬅️ МЕНЮ", callback_data="main_menu")]
        ]
    
    elif new_player_health <= 0:
        # Поражение
        end_battle(user_id)
        cursor.execute('UPDATE players SET health=? WHERE user_id=?', (player["max_health"], user_id))
        conn.commit()
        
        text = (
            f"💀 ПОРАЖЕНИЕ\n"
            f"{'━' * 30}\n\n"
            f"Ты был побеждён {enemy['emoji']} {enemy['name']}...\n\n"
            f"Твоё здоровье полностью восстановлено.\n"
        )
        
        keyboard = [
            [InlineKeyboardButton("⚔️ НОВЫЙ БОЙ", callback_data="start_battle")],
            [InlineKeyboardButton("⬅️ МЕНЮ", callback_data="main_menu")]
        ]
    
    else:
        # Бой продолжается
        keyboard = [
            [InlineKeyboardButton("⚔️ АТАКОВАТЬ", callback_data="battle_attack"),
             InlineKeyboardButton("🏥 ЛЕЧИТЬСЯ", callback_data="battle_heal")],
            [InlineKeyboardButton("❌ СБЕЖАТЬ", callback_data="battle_flee")]
        ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def battle_heal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Лечение"""
    query = update.callback_query
    user_id = query.from_user.id
    player = get_player(user_id)
    battle = get_battle(user_id)
    
    if not battle:
        await query.answer("❌ Боя нет!", show_alert=True)
        return
    
    enemy = ENEMIES[battle["enemy_id"]]
    
    heal_amount = 30
    new_player_health = min(player["max_health"], player["health"] + heal_amount)
    enemy_damage = enemy["damage"] + random.randint(-1, 3)
    new_player_health = max(0, new_player_health - enemy_damage)
    
    update_battle(user_id, battle["enemy_health"], new_player_health)
    cursor.execute('UPDATE players SET health=? WHERE user_id=?', (new_player_health, user_id))
    conn.commit()
    
    text = (
        f"🏥 ЛЕЧЕНИЕ\n"
        f"{'━' * 30}\n\n"
        f"✨ Ты исцелился на {heal_amount} HP!\n"
        f"⚔️ Враг нанес {enemy_damage} урона!\n\n"
        f"👤 Твоё здоровье: {new_player_health}/{player['max_health']}\n"
        f"{enemy['emoji']} Здоровье врага: {battle['enemy_health']}\n\n"
    )
    
    if new_player_health <= 0:
        end_battle(user_id)
        cursor.execute('UPDATE players SET health=? WHERE user_id=?', (player["max_health"], user_id))
        conn.commit()
        
        text = (
            f"💀 ПОРАЖЕНИЕ\n"
            f"{'━' * 30}\n\n"
            f"Ты был побеждён {enemy['emoji']} {enemy['name']}...\n"
        )
        
        keyboard = [
            [InlineKeyboardButton("⚔️ НОВЫЙ БОЙ", callback_data="start_battle")],
            [InlineKeyboardButton("⬅️ МЕНЮ", callback_data="main_menu")]
        ]
    
    else:
        keyboard = [
            [InlineKeyboardButton("⚔️ АТАКОВАТЬ", callback_data="battle_attack"),
             InlineKeyboardButton("🏥 ЛЕЧИТЬСЯ", callback_data="battle_heal")],
            [InlineKeyboardButton("❌ СБЕЖАТЬ", callback_data="battle_flee")]
        ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def battle_flee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сбежать"""
    query = update.callback_query
    user_id = query.from_user.id
    player = get_player(user_id)
    battle = get_battle(user_id)
    
    if not battle:
        await query.answer("❌ Боя нет!", show_alert=True)
        return
    
    enemy = ENEMIES[battle["enemy_id"]]
    
    if random.random() < 0.5:
        # Успешное бегство
        end_battle(user_id)
        text = f"✅ Ты успешно сбежал от {enemy['emoji']} {enemy['name']}!"
        
        keyboard = [
            [InlineKeyboardButton("⚔️ БОЙ", callback_data="start_battle")],
            [InlineKeyboardButton("⬅️ МЕНЮ", callback_data="main_menu")]
        ]
    
    else:
        # Неудачное бегство
        enemy_damage = enemy["damage"] + random.randint(5, 10)
        new_player_health = max(0, player["health"] - enemy_damage)
        
        if new_player_health <= 0:
            end_battle(user_id)
            cursor.execute('UPDATE players SET health=? WHERE user_id=?', (player["max_health"], user_id))
            conn.commit()
            
            text = (
                f"❌ НЕУДАЧА!\n"
                f"{'━' * 30}\n\n"
                f"Враг перехватил тебя!\n"
                f"-{enemy_damage} HP\n\n"
                f"💀 Ты был повержен!\n"
            )
            
            keyboard = [
                [InlineKeyboardButton("⚔️ НОВЫЙ БОЙ", callback_data="start_battle")],
                [InlineKeyboardButton("⬅️ МЕНЮ", callback_data="main_menu")]
            ]
        
        else:
            update_battle(user_id, battle["enemy_health"], new_player_health)
            cursor.execute('UPDATE players SET health=? WHERE user_id=?', (new_player_health, user_id))
            conn.commit()
            
            text = (
                f"❌ НЕУДАЧА!\n"
                f"{'━' * 30}\n\n"
                f"Враг перехватил тебя!\n"
                f"-{enemy_damage} HP\n\n"
                f"👤 Твоё здоровье: {new_player_health}/{player['max_health']}\n"
            )
            
            keyboard = [
                [InlineKeyboardButton("⚔️ АТАКОВАТЬ", callback_data="battle_attack"),
                 InlineKeyboardButton("🏥 ЛЕЧИТЬСЯ", callback_data="battle_heal")],
                [InlineKeyboardButton("❌ СБЕЖАТЬ", callback_data="battle_flee")]
            ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_crafting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Крафтинг"""
    query = update.callback_query
    user_id = query.from_user.id
    player = get_player(user_id)
    materials = get_materials(user_id)
    
    text = "⚙️ КРАФТИНГ\n" + "━" * 30 + "\n\n"
    text += f"⭐ Уровень: {player['level']}\n\n"
    text += "📦 ВАШ МАТЕРИАЛЫ:\n"
    
    if materials:
        for mat_id, qty in materials.items():
            mat_info = MATERIALS.get(mat_id, {})
            text += f"{mat_info.get('emoji', '?')} {mat_info.get('name', mat_id)}: {qty}\n"
    else:
        text += "❌ Материалов нет (убивайте мобов)\n"
    
    text += f"\n🔨 ДОСТУПНЫЕ РЕЦЕПТЫ:\n\n"
    
    keyboard = []
    
    for recipe_id, recipe_info in RECIPES.items():
        if player["level"] >= recipe_info["level"]:
            can_craft = True
            needs_text = ""
            
            for mat_id, needed_qty in recipe_info["materials"].items():
                current = materials.get(mat_id, 0)
                mat_info = MATERIALS.get(mat_id, {})
                needs_text += f"{current}/{needed_qty} {mat_info.get('emoji', '?')} "
                
                if current < needed_qty:
                    can_craft = False
            
            status = "✅" if can_craft else "❌"
            text += f"{status} {recipe_info['emoji']} {recipe_info['name']}\n"
            text += f"{needs_text}\n"
            
            if can_craft:
                keyboard.append([InlineKeyboardButton(f"Создать {recipe_info['emoji']}", callback_data=f"craft_{recipe_id}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ МЕНЮ", callback_data="main_menu")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def craft_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создать предмет через крафт"""
    query = update.callback_query
    user_id = query.from_user.id
    recipe_id = query.data.split("_")[1]
    
    recipe = RECIPES.get(recipe_id)
    if not recipe:
        await query.answer("❌ Рецепт не найден", show_alert=True)
        return
    
    materials = get_materials(user_id)
    
    can_craft = True
    for mat_id, needed_qty in recipe["materials"].items():
        if materials.get(mat_id, 0) < needed_qty:
            can_craft = False
            break
    
    if can_craft:
        for mat_id, needed_qty in recipe["materials"].items():
            subtract_material(user_id, mat_id, needed_qty)
        
        add_material(user_id, recipe["result"], 1)
        
        text = f"✅ Создано: {recipe['emoji']} {recipe['name']}\n+1 {MATERIALS.get(recipe['result'], {}).get('name', '?')}"
        
        keyboard = [
            [InlineKeyboardButton("⚙️ КРАФТ", callback_data="show_crafting")],
            [InlineKeyboardButton("⬅️ МЕНЮ", callback_data="main_menu")]
        ]
    
    else:
        text = f"❌ Недостаточно материалов!\n\nНужно:\n"
        for mat_id, needed_qty in recipe["materials"].items():
            mat_info = MATERIALS.get(mat_id, {})
            current = materials.get(mat_id, 0)
            text += f"{mat_info.get('emoji', '?')} {mat_info.get('name', mat_id)}: {current}/{needed_qty}\n"
        
        keyboard = [[InlineKeyboardButton("⚙️ КРАФТ", callback_data="show_crafting")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_dungeon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Рейтинговое подземелье"""
    query = update.callback_query
    player = get_player(query.from_user.id)
    
    text = (
        f"🏆 РЕЙТИНГОВОЕ ПОДЗЕМЕЛЬЕ\n"
        f"{'━' * 30}\n\n"
        f"Это бесконечный режим, где ты сражаешься с монстрами,\n"
        f"которые становятся все сильнее.\n\n"
        f"📊 ВАШ РЕКОРД:\n"
        f"🏆 Этаж: {player['dungeon_rating']}\n\n"
        f"⚙️ КАК ЭТО РАБОТАЕТ:\n"
        f"1. Начинаешь с этажа 1\n"
        f"2. Каждый бой - следующий этаж\n"
        f"3. На каждый этаж враг на 1 уровень сильнее\n"
        f"4. Если умрешь - выходишь из подземелья\n"
        f"5. Чем глубже зайдешь - выше рейтинг\n"
    )
    
    keyboard = [[InlineKeyboardButton("🏆 НАЧАТЬ ПРОХОЖДЕНИЕ", callback_data="start_dungeon_run")],
                [InlineKeyboardButton("⬅️ МЕНЮ", callback_data="main_menu")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Таблица лидеров"""
    query = update.callback_query
    
    leaders = get_leaderboard(10)
    
    text = "👑 ТАБЛИЦА ЛИДЕРОВ\n" + "━" * 30 + "\n\n"
    
    if leaders:
        medals = ["👑", "🥈", "🥉"]
        for i, (username, level, kills, gold, rating) in enumerate(leaders, 1):
            medal = medals[i - 1] if i <= 3 else f"{i}."
            text += f"{medal} {username} - Этаж {rating} | Ур. {level}\n"
            text += f"  ⚔️ {kills} | 💰 {gold}\n"
    else:
        text += "❌ Данных нет"
    
    keyboard = [[InlineKeyboardButton("⬅️ МЕНЮ", callback_data="main_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ========== ЗАПУСК БОТА ==========

async def main():
    """Главная функция запуска"""
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не найден в .env!")
        return
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start_command))
    
    # Колбеки
    callbacks = [
        ("^class_", select_class),
        ("^main_menu$", show_main_menu),
        ("^show_profile$", show_profile),
        ("^show_inventory$", show_inventory),
        ("^show_equipment$", show_equipment),
        ("^equipment_weapons$", equipment_weapons),
        ("^equipment_armor$", equipment_armor),
        ("^equip_", equip_item),
        ("^show_locations$", show_locations),
        ("^location_", location_select),
        ("^start_battle_in_location$", start_battle_in_location),
        ("^start_battle$", start_battle),
        ("^battle_attack$", battle_attack),
        ("^battle_heal$", battle_heal),
        ("^battle_flee$", battle_flee),
        ("^show_crafting$", show_crafting),
        ("^craft_", craft_item),
        ("^show_dungeon$", show_dungeon),
        ("^show_leaderboard$", show_leaderboard),
    ]
    
    for pattern, handler in callbacks:
        app.add_handler(CallbackQueryHandler(handler, pattern=pattern))
    
    # Запуск
    await app.initialize()
    await app.start()
    
    if WEBHOOK_URL:
        await app.bot.set_webhook(WEBHOOK_URL)
        logger.info(f"✅ Вебхук установлен: {WEBHOOK_URL}")
    else:
        logger.info("✅ Бот запущен в режиме polling...")
        await app.updater.start_polling()
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹️ Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
