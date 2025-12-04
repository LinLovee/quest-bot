"""╔════════════════════════════════════════════════════════════════════════════╗
║                                                                            ║
║ 🎮 RUNEQUESTRPG BOT - ПОЛНОФУНКЦИОНАЛЬНАЯ RPG В TELEGRAM 🎮              ║
║                                                                            ║
║ Версия: 5.1 ADVANCED (около 4000 строк кода)                             ║
║ Статус: ✅ ЛОКАЦИИ, КЛАСС-СПЕЦИФИЧНОЕ ОРУЖИЕ, ПВП ОЧЕРЕДЬ, ПОДЗЕМЕЛЬЯ     ║
║ Автор: AI Developer                                                        ║
║ Дата: 2024-2025                                                            ║
║ Язык: Python 3.13+                                                         ║
║ Фреймворк: python-telegram-bot 20.3+                                      ║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝"""

# ─────────────────────────────────────────────────────────────────────────────
# 📦 ИМПОРТЫ
# ─────────────────────────────────────────────────────────────────────────────
import os
import sqlite3
import random
import logging
import signal
import sys
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, Optional, Tuple, List, Callable
from functools import wraps
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import TelegramError

# ─────────────────────────────────────────────────────────────────────────────
# 🔐 ЗАГРУЗКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ
# ─────────────────────────────────────────────────────────────────────────────
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден в .env файле!")

# ─────────────────────────────────────────────────────────────────────────────
# 🧾 ЛОГИРОВАНИЕ
# ─────────────────────────────────────────────────────────────────────────────
if not os.path.exists("logs"):
    os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("logs/runequestrpg.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("RuneQuestRPG")

# ─────────────────────────────────────────────────────────────────────────────
# 🧠 ЭНУМЫ И КОНСТАНТЫ
# ─────────────────────────────────────────────────────────────────────────────
class Rarity(Enum):
    COMMON = "Обычный"
    UNCOMMON = "Необычный"
    RARE = "Редкий"
    EPIC = "Эпический"
    LEGENDARY = "Легендарный"

class Element(Enum):
    PHYSICAL = "Физический"
    FIRE = "Огонь"
    ICE = "Лёд"
    SHADOW = "Тьма"
    HOLY = "Свет"
    POISON = "Яд"
    ARCANE = "Тайная магия"

class RuneType(Enum):
    OFFENSIVE = "Атакующая"
    DEFENSIVE = "Защитная"
    UTILITY = "Утилитарная"

MAX_LEVEL = 100
LEVEL_UP_BASE = 100
STATS_PER_LEVEL = {"health": 20, "mana": 15, "attack": 5, "defense": 2}
PVP_SEARCH_TIMEOUT = 300  # 5 минут поиска

# ─────────────────────────────────────────────────────────────────────────────
# 🎭 КЛАССЫ ПЕРСОНАЖЕЙ
# ─────────────────────────────────────────────────────────────────────────────
CLASSES: Dict[str, Dict[str, Any]] = {
    "warrior": {
        "name": "Воин",
        "emoji": "⚔️",
        "description": "Универсальный боец ближнего боя",
        "health": 120,
        "mana": 30,
        "attack": 15,
        "defense": 8,
        "crit_chance": 5,
        "starting_gold": 100,
        "spell_power": 0,
        "dodge_chance": 3,
        "element": Element.PHYSICAL.value,
    },
    "mage": {
        "name": "Маг",
        "emoji": "🔥",
        "description": "Мастер разрушительной магии",
        "health": 70,
        "mana": 130,
        "attack": 8,
        "defense": 3,
        "crit_chance": 8,
        "starting_gold": 150,
        "spell_power": 25,
        "dodge_chance": 2,
        "element": Element.ARCANE.value,
    },
    "rogue": {
        "name": "Разбойник",
        "emoji": "🗡️",
        "description": "Ловкий ассасин с высоким критом",
        "health": 85,
        "mana": 50,
        "attack": 19,
        "defense": 5,
        "crit_chance": 22,
        "starting_gold": 130,
        "spell_power": 5,
        "dodge_chance": 12,
        "element": Element.SHADOW.value,
    },
    "paladin": {
        "name": "Паладин",
        "emoji": "⛪",
        "description": "Святой воин со светлой магией",
        "health": 140,
        "mana": 80,
        "attack": 13,
        "defense": 15,
        "crit_chance": 4,
        "starting_gold": 140,
        "spell_power": 12,
        "dodge_chance": 4,
        "element": Element.HOLY.value,
    },
    "ranger": {
        "name": "Рейнджер",
        "emoji": "🏹",
        "description": "Мастер дальнего боя и ловкости",
        "health": 95,
        "mana": 65,
        "attack": 17,
        "defense": 6,
        "crit_chance": 16,
        "starting_gold": 120,
        "spell_power": 8,
        "dodge_chance": 9,
        "element": Element.POISON.value,
    },
    "necromancer": {
        "name": "Некромант",
        "emoji": "💀",
        "description": "Повелитель смерти и тьмы",
        "health": 80,
        "mana": 135,
        "attack": 10,
        "defense": 4,
        "crit_chance": 7,
        "starting_gold": 160,
        "spell_power": 30,
        "dodge_chance": 3,
        "element": Element.SHADOW.value,
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# 👹 ВРАГИ
# ─────────────────────────────────────────────────────────────────────────────
ENEMIES: Dict[str, Dict[str, Any]] = {
    "goblin": {
        "name": "Гоблин",
        "emoji": "👹",
        "level": 1,
        "hp": 25,
        "damage": 5,
        "xp": 30,
        "gold": 10,
        "loot": ["copper_ore", "bone"],
        "boss": False,
        "element": Element.PHYSICAL.value,
    },
    "wolf": {
        "name": "Волк",
        "emoji": "🐺",
        "level": 2,
        "hp": 35,
        "damage": 8,
        "xp": 50,
        "gold": 15,
        "loot": ["copper_ore", "wolf_fang"],
        "boss": False,
        "element": Element.PHYSICAL.value,
    },
    "skeleton": {
        "name": "Скелет",
        "emoji": "💀",
        "level": 3,
        "hp": 40,
        "damage": 10,
        "xp": 70,
        "gold": 20,
        "loot": ["bone", "copper_ore"],
        "boss": False,
        "element": Element.SHADOW.value,
    },
    "orc": {
        "name": "Орк",
        "emoji": "👺",
        "level": 4,
        "hp": 55,
        "damage": 13,
        "xp": 110,
        "gold": 35,
        "loot": ["iron_ore", "bone"],
        "boss": False,
        "element": Element.PHYSICAL.value,
    },
    "troll": {
        "name": "Тролль",
        "emoji": "🗻",
        "level": 5,
        "hp": 75,
        "damage": 16,
        "xp": 160,
        "gold": 55,
        "loot": ["iron_ore", "troll_hide"],
        "boss": False,
        "element": Element.PHYSICAL.value,
    },
    "basilisk": {
        "name": "Василиск",
        "emoji": "🐍",
        "level": 7,
        "hp": 90,
        "damage": 20,
        "xp": 230,
        "gold": 80,
        "loot": ["mithril_ore", "basilisk_scale"],
        "boss": False,
        "element": Element.POISON.value,
    },
    "ice_mage": {
        "name": "Ледяной маг",
        "emoji": "❄️",
        "level": 8,
        "hp": 70,
        "damage": 23,
        "xp": 260,
        "gold": 110,
        "loot": ["mithril_ore", "ice_crystal"],
        "boss": False,
        "element": Element.ICE.value,
    },
    "demon": {
        "name": "Демон",
        "emoji": "😈",
        "level": 10,
        "hp": 110,
        "damage": 28,
        "xp": 380,
        "gold": 170,
        "loot": ["demon_essence", "mithril_ore"],
        "boss": False,
        "element": Element.FIRE.value,
    },
    "vampire": {
        "name": "Вампир",
        "emoji": "🧛",
        "level": 12,
        "hp": 100,
        "damage": 30,
        "xp": 420,
        "gold": 190,
        "loot": ["blood_crystal", "demon_essence"],
        "boss": False,
        "element": Element.SHADOW.value,
    },
    "dragon_boss": {
        "name": "Древний Дракон",
        "emoji": "🐉",
        "level": 15,
        "hp": 280,
        "damage": 48,
        "xp": 1600,
        "gold": 550,
        "loot": ["dragon_scale", "dragon_heart"],
        "boss": True,
        "element": Element.FIRE.value,
    },
    "lich_boss": {
        "name": "Лич",
        "emoji": "☠️",
        "level": 18,
        "hp": 320,
        "damage": 52,
        "xp": 2100,
        "gold": 820,
        "loot": ["lich_stone", "soul_essence"],
        "boss": True,
        "element": Element.SHADOW.value,
    },
    "demon_lord": {
        "name": "Демонический Лорд",
        "emoji": "👹",
        "level": 22,
        "hp": 420,
        "damage": 65,
        "xp": 3200,
        "gold": 1300,
        "loot": ["lord_essence", "ancient_gem"],
        "boss": True,
        "element": Element.FIRE.value,
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# 🏰 ЛОКАЦИИ
# ─────────────────────────────────────────────────────────────────────────────
LOCATIONS: Dict[str, Dict[str, Any]] = {
    "dark_forest": {
        "name": "Тёмный лес",
        "emoji": "🌲",
        "min_level": 1,
        "max_level": 10,
        "description": "Густый лес с опасными тварями",
        "enemies": ["goblin", "wolf", "skeleton"],
    },
    "mountain_cave": {
        "name": "Горные пещеры",
        "emoji": "⛰️",
        "min_level": 10,
        "max_level": 25,
        "description": "Холодные пещеры с тварями глубин",
        "enemies": ["troll", "basilisk", "ice_mage"],
    },
    "castle_ruins": {
        "name": "Руины замка",
        "emoji": "🏚️",
        "min_level": 25,
        "max_level": 45,
        "description": "Древние руины, населённые нежитью",
        "enemies": ["demon", "skeleton", "orc"],
    },
    "volcano": {
        "name": "Вулкан",
        "emoji": "🌋",
        "min_level": 45,
        "max_level": 65,
        "description": "Обитель огненных монстров",
        "enemies": ["demon", "dragon_boss", "basilisk"],
    },
    "demon_lair": {
        "name": "Логово демонов",
        "emoji": "👹",
        "min_level": 65,
        "max_level": 90,
        "description": "Адское логово древних демонов",
        "enemies": ["demon", "vampire", "demon_lord"],
    },
    "frozen_peak": {
        "name": "Мёрзлый пик",
        "emoji": "❄️",
        "min_level": 20,
        "max_level": 40,
        "description": "Ледяные вершины с магами и чудищами",
        "enemies": ["ice_mage", "basilisk", "wolf"],
    },
    "shadow_valley": {
        "name": "Долина теней",
        "emoji": "🌑",
        "min_level": 30,
        "max_level": 60,
        "description": "Мрачная долина, где царит вечная тьма",
        "enemies": ["vampire", "skeleton", "lich_boss"],
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# 📦 МАТЕРИАЛЫ, РУНЫ, КРАФТ
# ─────────────────────────────────────────────────────────────────────────────
MATERIALS: Dict[str, Dict[str, Any]] = {
    "copper_ore": {"name": "Медная руда", "emoji": "🪨", "value": 10},
    "iron_ore": {"name": "Железная руда", "emoji": "🪨", "value": 20},
    "mithril_ore": {"name": "Мифриловая руда", "emoji": "✨", "value": 50},
    "bone": {"name": "Кость", "emoji": "🦴", "value": 15},
    "wolf_fang": {"name": "Клык волка", "emoji": "🐺", "value": 25},
    "troll_hide": {"name": "Шкура тролля", "emoji": "🪵", "value": 30},
    "basilisk_scale": {"name": "Чешуя василиска", "emoji": "🐍", "value": 40},
    "ice_crystal": {"name": "Ледяной кристалл", "emoji": "❄️", "value": 60},
    "demon_essence": {"name": "Сущность демона", "emoji": "😈", "value": 100},
    "dragon_scale": {"name": "Чешуя дракона", "emoji": "🐉", "value": 200},
    "dragon_heart": {"name": "Сердце дракона", "emoji": "❤️", "value": 300},
    "blood_crystal": {"name": "Кровавый кристалл", "emoji": "🩸", "value": 80},
    "soul_essence": {"name": "Сущность души", "emoji": "👻", "value": 120},
    "lich_stone": {"name": "Камень Лича", "emoji": "🟣", "value": 150},
    "ancient_gem": {"name": "Древний самоцвет", "emoji": "💎", "value": 250},
    "lord_essence": {"name": "Сущность лорда", "emoji": "🔮", "value": 300},
}

RUNES: Dict[str, Dict[str, Any]] = {
    "rune_of_power": {
        "name": "Руна силы",
        "emoji": "💥",
        "type": RuneType.OFFENSIVE.value,
        "attack_bonus": 10,
        "defense_bonus": 0,
        "crit_bonus": 5,
        "price": 800,
    },
    "rune_of_protection": {
        "name": "Руна защиты",
        "emoji": "🛡️",
        "type": RuneType.DEFENSIVE.value,
        "attack_bonus": 0,
        "defense_bonus": 12,
        "crit_bonus": 0,
        "price": 900,
    },
    "rune_of_focus": {
        "name": "Руна сосредоточения",
        "emoji": "♻️",
        "type": RuneType.UTILITY.value,
        "attack_bonus": 5,
        "defense_bonus": 5,
        "crit_bonus": 3,
        "price": 700,
    },
}

CRAFTING_RECIPES: Dict[str, Dict[str, Any]] = {
    "copper_bar": {
        "name": "Медный слиток",
        "emoji": "🔨",
        "materials": {"copper_ore": 5},
        "gold": 20,
        "level": 1,
        "result": "copper_bar",
    },
    "iron_bar": {
        "name": "Железный слиток",
        "emoji": "🔨",
        "materials": {"iron_ore": 5},
        "gold": 55,
        "level": 3,
        "result": "iron_bar",
    },
    "mithril_bar": {
        "name": "Мифриловый слиток",
        "emoji": "🔨",
        "materials": {"mithril_ore": 3, "ice_crystal": 1},
        "gold": 210,
        "level": 10,
        "result": "mithril_bar",
    },
    "health_potion": {
        "name": "Зелье здоровья",
        "emoji": "🧪",
        "materials": {"bone": 2, "copper_ore": 1},
        "gold": 35,
        "level": 1,
        "result": "health_potion",
    },
    "mana_potion": {
        "name": "Зелье маны",
        "emoji": "🧪",
        "materials": {"ice_crystal": 1},
        "gold": 85,
        "level": 5,
        "result": "mana_potion",
    },
    "strength_potion": {
        "name": "Зелье силы",
        "emoji": "💪",
        "materials": {"troll_hide": 1, "wolf_fang": 2},
        "gold": 110,
        "level": 7,
        "result": "strength_potion",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# 🎨 ОРУЖИЕ, БРОНЯ, ПИТОМЦЫ
# ─────────────────────────────────────────────────────────────────────────────
WEAPONS: Dict[str, Dict[str, Any]] = {
    "wooden_sword": {
        "name": "Деревянный меч",
        "emoji": "🪵",
        "attack": 3,
        "price": 20,
        "class": None,
    },
    "iron_sword": {
        "name": "Железный меч",
        "emoji": "⚔️",
        "attack": 8,
        "price": 150,
        "class": "warrior",
    },
    "fire_staff": {
        "name": "Огненный посох",
        "emoji": "🔥",
        "attack": 10,
        "price": 200,
        "class": "mage",
    },
    "dagger": {
        "name": "Кинжал",
        "emoji": "🗡️",
        "attack": 7,
        "price": 100,
        "class": "rogue",
    },
    "holy_sword": {
        "name": "Святой меч",
        "emoji": "⚔️",
        "attack": 12,
        "price": 300,
        "class": "paladin",
    },
    "bow": {
        "name": "Лук",
        "emoji": "🏹",
        "attack": 9,
        "price": 180,
        "class": "ranger",
    },
    "death_staff": {
        "name": "Посох смерти",
        "emoji": "☠️",
        "attack": 15,
        "price": 400,
        "class": "necromancer",
    },
}

ARMOR: Dict[str, Dict[str, Any]] = {
    "leather_armor": {
        "name": "Кожаная броня",
        "emoji": "🧥",
        "defense": 2,
        "health": 10,
        "price": 30,
        "class": None,
    },
    "chainmail": {
        "name": "Кольчуга",
        "emoji": "🛡️",
        "defense": 5,
        "health": 20,
        "price": 100,
        "class": "warrior",
    },
    "mage_robe": {
        "name": "Магическая роба",
        "emoji": "袍",
        "defense": 3,
        "mana": 15,
        "price": 120,
        "class": "mage",
    },
    "leather_vest": {
        "name": "Кожаный жилет",
        "emoji": "👕",
        "defense": 4,
        "health": 15,
        "price": 80,
        "class": "rogue",
    },
    "paladin_plate": {
        "name": "Платы паладина",
        "emoji": "🛡️",
        "defense": 8,
        "health": 30,
        "price": 250,
        "class": "paladin",
    },
    "ranger_leather": {
        "name": "Разведывательная кожа",
        "emoji": "🧥",
        "defense": 6,
        "health": 20,
        "price": 150,
        "class": "ranger",
    },
    "necro_cloak": {
        "name": "Плащ некроманта",
        "emoji": "🧥",
        "defense": 4,
        "mana": 20,
        "price": 200,
        "class": "necromancer",
    },
}

PETS: Dict[str, Dict[str, Any]] = {
    "wolf": {"name": "Волк", "emoji": "🐺", "bonus": 0.05, "type": "damage", "price": 500},
    "cat": {"name": "Кот", "emoji": "🐱", "bonus": 0.03, "type": "xp", "price": 300},
    "owl": {"name": "Сова", "emoji": "🦉", "bonus": 0.07, "type": "mana", "price": 700},
}

# ─────────────────────────────────────────────────────────────────────────────
# 💾 БАЗА ДАННЫХ
# ─────────────────────────────────────────────────────────────────────────────
def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect("runequestrpg.db", timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def safe_db_execute(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"❌ БД Error: {e}")
            return None
    return wrapper


@safe_db_execute
def init_database():
    conn = get_db()
    c = conn.cursor()

    # Таблица игроков
    c.execute("""
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            chat_id INTEGER,
            username TEXT,
            class TEXT NOT NULL,
            level INTEGER DEFAULT 1,
            xp INTEGER DEFAULT 0,
            health INTEGER,
            max_health INTEGER,
            mana INTEGER,
            max_mana INTEGER,
            attack INTEGER,
            defense INTEGER,
            gold INTEGER DEFAULT 0,
            dungeon_rating INTEGER DEFAULT 0,
            equipped_weapon TEXT,
            equipped_armor TEXT,
            equipped_rune TEXT,
            pet_id TEXT DEFAULT 'wolf',
            pet_level INTEGER DEFAULT 1,
            total_kills INTEGER DEFAULT 0,
            total_bosses_killed INTEGER DEFAULT 0,
            total_battles_won INTEGER DEFAULT 0,
            total_battles_lost INTEGER DEFAULT 0,
            pvp_wins INTEGER DEFAULT 0,
            pvp_losses INTEGER DEFAULT 0,
            craft_count INTEGER DEFAULT 0,
            current_location TEXT,
            last_daily_reward TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            crit_chance INTEGER DEFAULT 5,
            spell_power INTEGER DEFAULT 0,
            dodge_chance INTEGER DEFAULT 3,
            element TEXT DEFAULT 'fire',
            UNIQUE(user_id, chat_id)
        )
    """)

    # Таблица инвентаря
    c.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_id INTEGER,
            item_id TEXT NOT NULL,
            item_type TEXT,
            quantity INTEGER DEFAULT 1,
            FOREIGN KEY(user_id) REFERENCES players(user_id),
            UNIQUE(user_id, item_id)
        )
    """)

    # Таблица боев
    c.execute("""
        CREATE TABLE IF NOT EXISTS battles (
            user_id INTEGER PRIMARY KEY,
            chat_id INTEGER,
            location_id TEXT,
            enemy_id TEXT NOT NULL,
            enemy_health INTEGER,
            enemy_max_health INTEGER,
            enemy_damage INTEGER,
            is_boss BOOLEAN DEFAULT 0,
            player_health INTEGER,
            player_max_health INTEGER,
            FOREIGN KEY(user_id) REFERENCES players(user_id)
        )
    """)

    # Таблица ПВП очереди
    c.execute("""
        CREATE TABLE IF NOT EXISTS pvp_queue (
            user_id INTEGER,
            chat_id INTEGER,
            username TEXT,
            level INTEGER,
            confirmed BOOLEAN DEFAULT 0,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, chat_id)
        )
    """)

    # Таблица прогресса подземелья
    c.execute("""
        CREATE TABLE IF NOT EXISTS dungeon_progress (
            user_id INTEGER PRIMARY KEY,
            chat_id INTEGER,
            current_floor INTEGER DEFAULT 1,
            is_active BOOLEAN DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES players(user_id)
        )
    """)

    # Индексы для производительности
    c.execute("CREATE INDEX IF NOT EXISTS idx_players_chat_user ON players(chat_id, user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_battles_user ON battles(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_pvp_confirmed ON pvp_queue(confirmed)")

    conn.commit()
    conn.close()
    logger.info("✅ База данных RuneQuestRPG инициализирована")


# ─────────────────────────────────────────────────────────────────────────────
# 🎒 ИНВЕНТАРЬ И ЭКИПИРОВКА
# ─────────────────────────────────────────────────────────────────────────────
@safe_db_execute
def add_item(chat_id: int, user_id: int, item_id: str, quantity: int = 1):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT quantity FROM inventory WHERE user_id = ? AND chat_id = ? AND item_id = ?", (user_id, chat_id, item_id))
        row = c.fetchone()
        if row:
            c.execute("UPDATE inventory SET quantity = quantity + ? WHERE user_id = ? AND chat_id = ? AND item_id = ?", (quantity, user_id, chat_id, item_id))
        else:
            if item_id in WEAPONS:
                item_type = "weapon"
            elif item_id in ARMOR:
                item_type = "armor"
            elif item_id in RUNES:
                item_type = "rune"
            elif item_id in PETS:
                item_type = "pet"
            elif item_id in MATERIALS:
                item_type = "material"
            else:
                item_type = "other"
            c.execute("INSERT INTO inventory (user_id, chat_id, item_id, quantity, item_type) VALUES (?, ?, ?, ?, ?)", (user_id, chat_id, item_id, quantity, item_type))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка добавления предмета: {e}")
    finally:
        conn.close()


@safe_db_execute
def remove_item(chat_id: int, user_id: int, item_id: str, quantity: int = 1):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("UPDATE inventory SET quantity = quantity - ? WHERE user_id = ? AND chat_id = ? AND item_id = ?", (quantity, user_id, chat_id, item_id))
        c.execute("DELETE FROM inventory WHERE user_id = ? AND chat_id = ? AND item_id = ? AND quantity <= 0", (user_id, chat_id, item_id))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка удаления предмета: {e}")
    finally:
        conn.close()


@safe_db_execute
def get_material(chat_id: int, user_id: int, item_id: str) -> int:
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT quantity FROM inventory WHERE user_id = ? AND chat_id = ? AND item_id = ?", (user_id, chat_id, item_id))
        row = c.fetchone()
        return row[0] if row else 0
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка получения материала: {e}")
        return 0
    finally:
        conn.close()


@safe_db_execute
def get_inventory(chat_id: int, user_id: int) -> List[Dict[str, Any]]:
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT item_id, quantity FROM inventory WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
        rows = c.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка получения инвентаря: {e}")
        return []
    finally:
        conn.close()


@safe_db_execute
def equip_weapon(chat_id: int, user_id: int, item_id: str) -> bool:
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("UPDATE players SET equipped_weapon = ? WHERE user_id = ? AND chat_id = ?", (item_id, user_id, chat_id))
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка экипировки оружия: {e}")
        return False
    finally:
        conn.close()


@safe_db_execute
def equip_armor(chat_id: int, user_id: int, item_id: str) -> bool:
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("UPDATE players SET equipped_armor = ? WHERE user_id = ? AND chat_id = ?", (item_id, user_id, chat_id))
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка экипировки брони: {e}")
        return False
    finally:
        conn.close()


@safe_db_execute
def equip_rune(chat_id: int, user_id: int, item_id: str) -> bool:
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("UPDATE players SET equipped_rune = ? WHERE user_id = ? AND chat_id = ?", (item_id, user_id, chat_id))
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка экипировки руны: {e}")
        return False
    finally:
        conn.close()


@safe_db_execute
def buy_item(chat_id: int, user_id: int, item_id: str) -> bool:
    player = get_player(chat_id, user_id)
    if not player:
        return False

    price = 0
    if item_id in WEAPONS:
        # Проверяем класс
        if not can_use_item(player["class"], item_id):
            return False
        price = WEAPONS[item_id]["price"]
    elif item_id in ARMOR:
        # Проверяем класс
        if not can_use_item(player["class"], item_id):
            return False
        price = ARMOR[item_id]["price"]
    elif item_id in PETS:
        price = PETS[item_id]["price"]
    elif item_id in RUNES:
        price = RUNES[item_id]["price"]
    else:
        return False

    if not subtract_gold(chat_id, user_id, price):
        return False

    add_item(chat_id, user_id, item_id)
    return True


@safe_db_execute
def buy_pet(chat_id: int, user_id: int, pet_id: str) -> bool:
    player = get_player(chat_id, user_id)
    if not player or pet_id not in PETS:
        return False

    pet = PETS[pet_id]
    price = pet["price"]

    if not subtract_gold(chat_id, user_id, price):
        return False

    update_player_stat(chat_id, user_id, "pet_id", pet_id)
    return True


def can_use_item(player_class: str, item_id: str) -> bool:
    if item_id in WEAPONS:
        required_class = WEAPONS[item_id].get("class")
        return required_class is None or required_class == player_class
    if item_id in ARMOR:
        required_class = ARMOR[item_id].get("class")
        return required_class is None or required_class == player_class
    return True


# ─────────────────────────────────────────────────────────────────────────────
# 💰 ЭКОНОМИКА ИГРОКА
# ─────────────────────────────────────────────────────────────────────────────
@safe_db_execute
def add_gold(chat_id: int, user_id: int, amount: int):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("UPDATE players SET gold = gold + ? WHERE user_id = ? AND chat_id = ?", (amount, user_id, chat_id))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка добавления золота: {e}")
    finally:
        conn.close()


@safe_db_execute
def subtract_gold(chat_id: int, user_id: int, amount: int) -> bool:
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT gold FROM players WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
        row = c.fetchone()
        if row and row[0] >= amount:
            c.execute("UPDATE players SET gold = gold - ? WHERE user_id = ? AND chat_id = ?", (amount, user_id, chat_id))
            conn.commit()
            return True
        else:
            return False
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка вычитания золота: {e}")
        return False
    finally:
        conn.close()


@safe_db_execute
def update_player_stat(chat_id: int, user_id: int, stat: str, value: int):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute(f"UPDATE players SET {stat} = ? WHERE user_id = ? AND chat_id = ?", (value, user_id, chat_id))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка обновления статистики: {e}")
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# 👤 СИСТЕМА ИГРОКОВ
# ─────────────────────────────────────────────────────────────────────────────
@safe_db_execute
def init_player(chat_id: int, user_id: int, user_name: str, player_class: str) -> bool:
    conn = get_db()
    c = conn.cursor()
    try:
        class_info = CLASSES.get(player_class, CLASSES["warrior"])
        c.execute("""
            INSERT INTO players (
                chat_id, user_id, username, class, level, xp, health, max_health, mana, max_mana, attack, defense, gold,
                crit_chance, spell_power, dodge_chance, element
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            chat_id, user_id, user_name, player_class,
            1, 0, class_info["health"], class_info["health"],
            class_info["mana"], class_info["mana"],
            class_info["attack"], class_info["defense"],
            class_info["starting_gold"],
            class_info["crit_chance"],  # Добавлено
            class_info["spell_power"],  # Добавлено
            class_info["dodge_chance"], # Добавлено
            class_info["element"]       # Добавлено
        ))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Игрок уже существует
        return False
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка инициализации игрока: {e}")
        return False
    finally:
        conn.close()


@safe_db_execute
def get_player(chat_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM players WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
        row = c.fetchone()
        return dict(row) if row else None
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка получения игрока: {e}")
        return None
    finally:
        conn.close()


@safe_db_execute
def player_exists(chat_id: int, user_id: int) -> bool:
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT 1 FROM players WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
        return c.fetchone() is not None
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка проверки существования игрока: {e}")
        return False
    finally:
        conn.close()


def get_player_battle_stats(player: Dict[str, Any]) -> Dict[str, int]:
    """Возвращает полные боевые характеристики с учётом экипировки и питомца"""
    stats = {
        "attack": player["attack"],
        "defense": player["defense"],
        "crit_chance": CLASSES[player["class"]].get("crit_chance", 5),
        "spell_power": player["spell_power"],
        "dodge_chance": player["dodge_chance"],
    }

    # Учитываем оружие
    if player["equipped_weapon"] and player["equipped_weapon"] in WEAPONS:
        weapon = WEAPONS[player["equipped_weapon"]]
        stats["attack"] += weapon["attack"]
        if "attack_bonus" in weapon:
            stats["attack"] += weapon["attack_bonus"]
        if "crit_bonus" in weapon:
            stats["crit_chance"] += weapon["crit_bonus"]

    # Учитываем броню
    if player["equipped_armor"] and player["equipped_armor"] in ARMOR:
        armor = ARMOR[player["equipped_armor"]]
        stats["defense"] += armor["defense"]
        if "defense_bonus" in armor:
            stats["defense"] += armor["defense_bonus"]

    # Учитываем руну
    if player["equipped_rune"] and player["equipped_rune"] in RUNES:
        rune = RUNES[player["equipped_rune"]]
        stats["attack"] += rune["attack_bonus"]
        stats["defense"] += rune["defense_bonus"]
        stats["crit_chance"] += rune["crit_bonus"]

    # Учитываем питомца
    if player["pet_id"] in PETS:
        pet = PETS[player["pet_id"]]
        if pet["type"] == "damage":
            stats["attack"] = int(stats["attack"] * (1 + pet["bonus"]))
        elif pet["type"] == "defense":
            stats["defense"] = int(stats["defense"] * (1 + pet["bonus"]))
        elif pet["type"] == "crit":
            stats["crit_chance"] = int(stats["crit_chance"] * (1 + pet["bonus"]))

    return stats


def calculate_damage(attacker_attack: int, defender_defense: int, attacker_crit_chance: int = 5, spell_power: int = 0) -> Tuple[int, bool]:
    base_damage = max(1, attacker_attack - defender_defense // 2)
    variation = random.uniform(0.85, 1.15)
    damage = int(base_damage * variation)

    if spell_power > 0:
        spell_damage = int(spell_power * random.uniform(0.8, 1.2))
        damage += spell_damage

    is_crit = random.randint(1, 100) <= attacker_crit_chance
    if is_crit:
        damage = int(damage * 1.5)

    return max(1, damage), is_crit


# ─────────────────────────────────────────────────────────────────────────────
# ⚔️ ПВП СИСТЕМА - ОЧЕРЕДЬ ПОДТВЕРЖДЕНИЯ
# ─────────────────────────────────────────────────────────────────────────────
@safe_db_execute
def add_to_pvp_queue(chat_id: int, user_id: int, username: str, level: int):
    conn = get_db()
    c = conn.cursor()
    try:
        # Удаляем старую запись, если есть
        c.execute("DELETE FROM pvp_queue WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
        # Добавляем в очередь с подтверждением
        c.execute("""
            INSERT OR REPLACE INTO pvp_queue (user_id, chat_id, username, level, confirmed, timestamp)
            VALUES (?, ?, ?, ?, 1, ?)
        """, (user_id, chat_id, username, level, datetime.now()))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка добавления в ПВП очередь: {e}")
    finally:
        conn.close()


@safe_db_execute
def remove_from_pvp_queue(chat_id: int, user_id: int):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM pvp_queue WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка удаления из ПВП очереди: {e}")
    finally:
        conn.close()


@safe_db_execute
def get_pvp_queue_status(chat_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    """Получить статус игрока в очереди"""
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM pvp_queue WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
        row = c.fetchone()
        return dict(row) if row else None
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка получения статуса ПВП очереди: {e}")
        return None
    finally:
        conn.close()


@safe_db_execute
def find_pvp_opponent(chat_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    """Найти противника из подтвердивших людей в очереди в том же чате, исключая себя."""
    conn = get_db()
    c = conn.cursor()
    try:
        # Ищем подтвержденного игрока в той же очереди (чате), кроме текущего пользователя
        c.execute("""
            SELECT * FROM pvp_queue
            WHERE chat_id = ? AND user_id != ? AND confirmed = 1
            ORDER BY RANDOM() LIMIT 1
        """, (chat_id, user_id))
        row = c.fetchone()
        return dict(row) if row else None
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка поиска ПВП оппонента: {e}")
        return None
    finally:
        conn.close()


def pvp_battle_logic(chat_id: int, attacker_id: int, defender_id: int) -> Dict[str, Any]:
    """Симуляция ПВП боя."""
    attacker = get_player(chat_id, attacker_id)
    defender = get_player(chat_id, defender_id)

    if not attacker or not defender:
        return {"success": False, "message": "❌ Один из игроков не найден."}

    # Вычисляем боевые статы
    attacker_stats = get_player_battle_stats(attacker)
    defender_stats = get_player_battle_stats(defender)

    # Логика боя (упрощенная)
    attacker_hp = attacker["health"]
    defender_hp = defender["health"]
    attacker_max_hp = attacker["max_health"]
    defender_max_hp = defender["max_health"]

    attacker_damage, attacker_crit = calculate_damage(attacker_stats["attack"], defender_stats["defense"], attacker_stats["crit_chance"], attacker_stats["spell_power"])
    defender_damage, defender_crit = calculate_damage(defender_stats["attack"], attacker_stats["defense"], defender_stats["crit_chance"], defender_stats["spell_power"])

    # Боевой цикл
    round_num = 0
    while attacker_hp > 0 and defender_hp > 0 and round_num < 100:  # Ограничение на 100 раундов
        round_num += 1
        # Атакующий атакует
        defender_hp -= attacker_damage
        # Защитник атакует
        if defender_hp > 0:
            attacker_hp -= defender_damage

    winner_id = None
    if attacker_hp <= 0 and defender_hp <= 0:
        # Ничья
        winner_id = random.choice([attacker_id, defender_id])
    elif attacker_hp > 0:
        winner_id = attacker_id
    else:
        winner_id = defender_id

    # Награда
    reward_gold = int(defender["gold"] * 0.1)  # 10% от золота проигравшего
    if winner_id == attacker_id:
        add_gold(chat_id, winner_id, reward_gold)
        subtract_gold(chat_id, defender_id, reward_gold)
        # Обновляем статистику
        update_player_stat(chat_id, winner_id, "pvp_wins", attacker["pvp_wins"] + 1)
        update_player_stat(chat_id, defender_id, "pvp_losses", defender["pvp_losses"] + 1)
    else:
        add_gold(chat_id, winner_id, reward_gold)
        subtract_gold(chat_id, attacker_id, reward_gold)
        # Обновляем статистику
        update_player_stat(chat_id, winner_id, "pvp_wins", defender["pvp_wins"] + 1)
        update_player_stat(chat_id, attacker_id, "pvp_losses", attacker["pvp_losses"] + 1)

    return {
        "success": True,
        "winner_id": winner_id,
        "attacker_damage": attacker_damage,
        "defender_damage": defender_damage,
        "attacker_crit": attacker_crit,
        "defender_crit": defender_crit,
        "reward_gold": reward_gold,
        "winner_name": attacker["username"] if winner_id == attacker_id else defender["username"],
        "loser_name": defender["username"] if winner_id == attacker_id else attacker["username"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 🏆 РЕЙТИНГИ
# ─────────────────────────────────────────────────────────────────────────────
@safe_db_execute
def get_level_leaderboard(chat_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT username, level FROM players WHERE chat_id = ? ORDER BY level DESC LIMIT ?", (chat_id, limit))
        rows = c.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка получения рейтинга уровней: {e}")
        return []
    finally:
        conn.close()


@safe_db_execute
def get_dungeon_leaderboard(chat_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT username, level, dungeon_rating, total_bosses_killed FROM players WHERE chat_id = ? ORDER BY dungeon_rating DESC, total_bosses_killed DESC LIMIT ?", (chat_id, limit))
        rows = c.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка получения рейтинга подземелья: {e}")
        return []
    finally:
        conn.close()


@safe_db_execute
def get_pvp_leaderboard(chat_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("""
            SELECT username, level, pvp_wins, pvp_losses,
                   CASE WHEN (pvp_wins + pvp_losses) > 0 THEN
                       CAST(pvp_wins AS REAL) * 100 / (pvp_wins + pvp_losses)
                   ELSE 0 END AS win_rate
            FROM players WHERE chat_id = ? AND (pvp_wins + pvp_losses) > 0
            ORDER BY win_rate DESC, pvp_wins DESC LIMIT ?
        """, (chat_id, limit))
        rows = c.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка получения ПВП рейтинга: {e}")
        return []
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# 🛒 МАГАЗИН
# ─────────────────────────────────────────────────────────────────────────────
async def show_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    player = get_player(chat.id, user.id)

    text = f"""🛍️ МАГАЗИН
Твой класс: {CLASSES[player['class']]['emoji']} {CLASSES[player['class']]['name']}
⚠️ Покупай только предметы для своего класса!
Выбери категорию:"""
    keyboard = [
        [InlineKeyboardButton("⚔️ ОРУЖИЕ", callback_data="shop_weapons"), InlineKeyboardButton("🛡️ БРОНЯ", callback_data="shop_armor")],
        [InlineKeyboardButton("🐾 ПИТОМЦЫ", callback_data="shop_pets"), InlineKeyboardButton("🔮 РУНЫ", callback_data="shop_runes")],
        [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")],
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_weapons_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    player = get_player(chat.id, user.id)

    text = f"🛍️ МАГАЗИН - ОРУЖИЕ ({CLASSES[player['class']]['name']})"
    keyboard = []
    for weapon_id, weapon_info in WEAPONS.items():
        # ✅ ПРОВЕРЯЕМ КЛАСС
        if weapon_info.get("class") and weapon_info["class"] != player["class"]:
            continue  # Пропускаем оружие не для его класса
        text += f"\n{weapon_info['emoji']} {weapon_info['name']} - ⚔️ +{weapon_info['attack']}| 💰 {weapon_info['price']}"
        can_afford = player["gold"] >= weapon_info["price"]
        status = "✅" if can_afford else "❌"
        keyboard.append([InlineKeyboardButton(f"{status} {weapon_info['emoji']} {weapon_info['name']}",
                                              callback_data=f"buy_weapon_{weapon_id}")])

    keyboard.append([InlineKeyboardButton("⬅️ НАЗАД", callback_data="shop")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_armor_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    player = get_player(chat.id, user.id)

    text = f"🛍️ МАГАЗИН - БРОНЯ ({CLASSES[player['class']]['name']})"
    keyboard = []
    for armor_id, armor_info in ARMOR.items():
        # ✅ ПРОВЕРЯЕМ КЛАСС
        if armor_info.get("class") and armor_info["class"] != player["class"]:
            continue  # Пропускаем броню не для его класса
        text += f"\n{armor_info['emoji']} {armor_info['name']} - 🛡️ +{armor_info['defense']}| ❤️ +{armor_info['health']}| 💰 {armor_info['price']}"
        can_afford = player["gold"] >= armor_info["price"]
        status = "✅" if can_afford else "❌"
        keyboard.append([InlineKeyboardButton(f"{status} {armor_info['emoji']} {armor_info['name']}",
                                              callback_data=f"buy_armor_{armor_id}")])

    keyboard.append([InlineKeyboardButton("⬅️ НАЗАД", callback_data="shop")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_pets_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    player = get_player(chat.id, user.id)

    text = f"🛍️ МАГАЗИН - ПИТОМЦЫ ({CLASSES[player['class']]['name']})"
    keyboard = []
    for pet_id, pet_info in PETS.items():
        text += f"\n{pet_info['emoji']} {pet_info['name']} ({pet_info['type']})| 💰 {pet_info['price']}"
        can_afford = player["gold"] >= pet_info["price"]
        status = "✅" if can_afford else "❌"
        keyboard.append([InlineKeyboardButton(f"{status} {pet_info['emoji']} {pet_info['name']}",
                                              callback_data=f"buy_pet_{pet_id}")])

    keyboard.append([InlineKeyboardButton("⬅️ НАЗАД", callback_data="shop")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_runes_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    player = get_player(chat.id, user.id)

    text = f"🛍️ МАГАЗИН - РУНЫ ({CLASSES[player['class']]['name']})"
    keyboard = []
    for rune_id, rune_info in RUNES.items():
        text += f"\n{rune_info['emoji']} {rune_info['name']} ({rune_info['type']})| 💰 {rune_info['price']}"
        can_afford = player["gold"] >= rune_info["price"]
        status = "✅" if can_afford else "❌"
        keyboard.append([InlineKeyboardButton(f"{status} {rune_info['emoji']} {rune_info['name']}",
                                              callback_data=f"buy_rune_{rune_id}")])

    keyboard.append([InlineKeyboardButton("⬅️ НАЗАД", callback_data="shop")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def buy_weapon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    weapon_id = query.data.replace("buy_weapon_", "")

    if weapon_id not in WEAPONS:
        await query.answer("❌ Оружие не найдено", show_alert=True)
        return

    player = get_player(chat.id, user.id)
    if not player:
        await query.answer("❌ Игрок не найден", show_alert=True)
        return

    if not can_use_item(player["class"], weapon_id):
        await query.answer("❌ Это оружие не для вашего класса!", show_alert=True)
        return

    if buy_item(chat.id, user.id, weapon_id):
        weapon = WEAPONS[weapon_id]
        await query.answer(f"✅ Куплено: {weapon['name']}", show_alert=True)
        await show_weapons_shop(update, context)
    else:
        await query.answer("❌ Недостаточно золота", show_alert=True)


async def buy_armor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    armor_id = query.data.replace("buy_armor_", "")

    if armor_id not in ARMOR:
        await query.answer("❌ Броня не найдена", show_alert=True)
        return

    player = get_player(chat.id, user.id)
    if not player:
        await query.answer("❌ Игрок не найден", show_alert=True)
        return

    if not can_use_item(player["class"], armor_id):
        await query.answer("❌ Эта броня не для вашего класса!", show_alert=True)
        return

    if buy_item(chat.id, user.id, armor_id):
        armor = ARMOR[armor_id]
        await query.answer(f"✅ Куплено: {armor['name']}", show_alert=True)
        await show_armor_shop(update, context)
    else:
        await query.answer("❌ Недостаточно золота", show_alert=True)


async def buy_pet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    pet_id = query.data.replace("buy_pet_", "")

    if pet_id not in PETS:
        await query.answer("❌ Питомец не найден", show_alert=True)
        return

    player = get_player(chat.id, user.id)
    if not player:
        await query.answer("❌ Игрок не найден", show_alert=True)
        return

    if buy_pet(chat.id, user.id, pet_id):
        pet = PETS[pet_id]
        await query.answer(f"✅ Питомец куплен: {pet['name']}", show_alert=True)
        await show_pets_shop(update, context)
    else:
        await query.answer("❌ Недостаточно золота", show_alert=True)


async def buy_rune(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    rune_id = query.data.replace("buy_rune_", "")

    if rune_id not in RUNES:
        await query.answer("❌ Руна не найдена", show_alert=True)
        return

    player = get_player(chat.id, user.id)
    if not player:
        await query.answer("❌ Игрок не найден", show_alert=True)
        return

    if buy_item(chat.id, user.id, rune_id):
        rune = RUNES[rune_id]
        await query.answer(f"✅ Куплено: {rune['name']}", show_alert=True)
        await show_runes_shop(update, context)
    else:
        await query.answer("❌ Недостаточно золота", show_alert=True)


# ─────────────────────────────────────────────────────────────────────────────
# ⚙️ ЭКИПИРОВКА
# ─────────────────────────────────────────────────────────────────────────────
async def show_equipment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    player = get_player(chat.id, user.id)

    if not player:
        await query.answer("❌ Игрок не найден", show_alert=True)
        return

    text = f"⚙️ ЭКИПИРОВКА ({CLASSES[player['class']]['name']})\n"

    if player["equipped_weapon"]:
        weapon = WEAPONS[player["equipped_weapon"]]
        text += f"⚔️ Оружие: {weapon['emoji']} {weapon['name']} (+{weapon['attack']})\n"
    else:
        text += "⚔️ Оружие: Не экипировано\n"

    if player["equipped_armor"]:
        armor = ARMOR[player["equipped_armor"]]
        text += f"🛡️ Броня: {armor['emoji']} {armor['name']} (+{armor['defense']})\n"
    else:
        text += "🛡️ Броня: Не экипирована\n"

    if player["equipped_rune"]:
        rune = RUNES[player["equipped_rune"]]
        text += f"🔮 Руна: {rune['emoji']} {rune['name']} ({rune['type']})\n"
    else:
        text += "🔮 Руна: Не экипирована\n"

    text += "\n🐾 Питомец: "
    pet = PETS.get(player["pet_id"])
    text += f"{pet['emoji']} {pet['name']}\n"

    # Показываем доступное оружие в инвентаре
    inventory = get_inventory(chat.id, user.id)
    weapons_in_inv = [item for item in inventory if item["item_id"] in WEAPONS and can_use_item(player["class"], item["item_id"])]
    if weapons_in_inv:
        text += "\n⚔️ ОРУЖИЕ В ИНВЕНТАРЕ:"
        for item in weapons_in_inv:
            w = WEAPONS[item["item_id"]]
            text += f"\n{w['emoji']} {w['name']}"

    # Показываем доступную броню в инвентаре
    armor_in_inv = [item for item in inventory if item["item_id"] in ARMOR and can_use_item(player["class"], item["item_id"])]
    if armor_in_inv:
        text += "\n🛡️ БРОНЯ В ИНВЕНТАРЕ:"
        for item in armor_in_inv:
            a = ARMOR[item["item_id"]]
            text += f"\n{a['emoji']} {a['name']}"

    # Показываем доступные руны в инвентаре
    runes_in_inv = [item for item in inventory if item["item_id"] in RUNES]
    if runes_in_inv:
        text += "\n🔮 РУНЫ В ИНВЕНТАРЕ:"
        for item in runes_in_inv:
            r = RUNES[item["item_id"]]
            text += f"\n{r['emoji']} {r['name']}"

    keyboard = [
        [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def equip_weapon_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    weapon_id = query.data.replace("equip_weapon_", "")

    player = get_player(chat.id, user.id)
    if not player or weapon_id not in WEAPONS:
        await query.answer("❌ Оружие не найдено", show_alert=True)
        return

    if not can_use_item(player["class"], weapon_id):
        await query.answer("❌ Это оружие не для вашего класса!", show_alert=True)
        return

    if equip_weapon(chat.id, user.id, weapon_id):
        weapon = WEAPONS[weapon_id]
        await query.answer(f"✅ Экипировано: {weapon['name']}", show_alert=True)
        await show_equipment(update, context)
    else:
        await query.answer("❌ Не удалось экипировать", show_alert=True)


async def equip_armor_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    armor_id = query.data.replace("equip_armor_", "")

    player = get_player(chat.id, user.id)
    if not player or armor_id not in ARMOR:
        await query.answer("❌ Броня не найдена", show_alert=True)
        return

    if not can_use_item(player["class"], armor_id):
        await query.answer("❌ Эта броня не для вашего класса!", show_alert=True)
        return

    if equip_armor(chat.id, user.id, armor_id):
        armor = ARMOR[armor_id]
        await query.answer(f"✅ Экипировано: {armor['name']}", show_alert=True)
        await show_equipment(update, context)
    else:
        await query.answer("❌ Не удалось экипировать", show_alert=True)


# ─────────────────────────────────────────────────────────────────────────────
# 🔨 КРАФТИНГ
# ─────────────────────────────────────────────────────────────────────────────
async def crafting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    text = "🔨 КРАФТИНГ\nВыбери рецепт:"
    keyboard = []
    for recipe_id, recipe in list(CRAFTING_RECIPES.items()):
        keyboard.append([InlineKeyboardButton(f"{recipe['emoji']} {recipe['name']}", callback_data=f"craft_{recipe_id}")])

    keyboard.append([InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def craft(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    recipe_id = query.data.replace("craft_", "")
    recipe = CRAFTING_RECIPES.get(recipe_id)

    if not recipe:
        await query.answer("❌ Рецепт не найден", show_alert=True)
        return

    player = get_player(chat.id, user.id)
    if not player:
        await query.answer("❌ Игрок не найден", show_alert=True)
        return

    text = f"🔨 СОЗДАНИЕ: {recipe['emoji']} {recipe['name']}\nТребуется:"
    has_all = True
    for material, needed in recipe["materials"].items():
        have = get_material(chat.id, user.id, material)
        material_info = MATERIALS[material]
        status = "✅" if have >= needed else "❌"
        text += f"\n{status} {material_info['emoji']} {material_info['name']} ({have}/{needed})"
        if have < needed:
            has_all = False
    gold_ok = player["gold"] >= recipe["gold"]
    level_ok = player["level"] >= recipe["level"]
    text += f"\n💰 Золото: {'✅' if gold_ok else '❌'} ({player['gold']}/{recipe['gold']})"
    text += f"\n⭐ Уровень: {'✅' if level_ok else '❌'} ({player['level']}/{recipe['level']})"

    if has_all and gold_ok and level_ok:
        keyboard = [
            [InlineKeyboardButton("✅ СОЗДАТЬ", callback_data=f"craft_confirm_{recipe_id}")],
            [InlineKeyboardButton("⬅️ НАЗАД", callback_data="crafting")],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("⬅️ НАЗАД", callback_data="crafting")]
        ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def craft_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    recipe_id = query.data.replace("craft_confirm_", "")

    result = craft_item(chat.id, user.id, recipe_id)
    if not result["success"]:
        await query.answer(result["message"], show_alert=True)
        return

    text = f"✅ СОЗДАНО!\n🎁 {result['name']} добавлен в инвентарь."
    keyboard = [
        [InlineKeyboardButton("🔨 НАЗАД К КРАФТУ", callback_data="crafting")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


def craft_item(chat_id: int, user_id: int, recipe_id: str) -> Dict[str, Any]:
    player = get_player(chat_id, user_id)
    recipe = CRAFTING_RECIPES.get(recipe_id)

    if not player or not recipe:
        return {"success": False, "message": "❌ Рецепт не найден"}

    if player["level"] < recipe["level"]:
        return {"success": False, "message": f'❌ Требуется уровень {recipe["level"]}'}

    if player["gold"] < recipe["gold"]:
        return {"success": False, "message": f'❌ Недостаточно золота ({recipe["gold"]})'}

    for material, needed in recipe["materials"].items():
        have = get_material(chat_id, user.id, material)
        if have < needed:
            material_name = MATERIALS.get(material, {}).get("name", material)
            return {"success": False, "message": f"❌ Недостаточно {material_name}"}

    for material, needed in recipe["materials"].items():
        remove_item(chat_id, user.id, material, needed)

    subtract_gold(chat_id, user.id, recipe["gold"])
    add_item(chat_id, user.id, recipe["result"])

    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE players SET craft_count = craft_count + 1 WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
    conn.commit()
    conn.close()

    return {"success": True, "item": recipe["result"], "name": recipe["name"]}


# ─────────────────────────────────────────────────────────────────────────────
# 🏆 ПОДЗЕМЕЛЬЕ
# ─────────────────────────────────────────────────────────────────────────────
async def show_dungeon_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    player = get_player(chat.id, user.id)

    if not player:
        await query.answer("❌ Игрок не найден", show_alert=True)
        return

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT 1 FROM dungeon_progress WHERE user_id = ? AND chat_id = ?", (user.id, chat.id))
    is_active = c.fetchone() is not None
    conn.close()

    text = f"""🏆 ПОДЗЕМЕЛЬЕ
Твой текущий этаж: {player['dungeon_rating']}
⚠️ Подземелье - испытание для сильнейших!
Ты готов войти?
⚠️ При смерти ты выкинут на первый этаж!
Готов?"""
    if is_active:
        keyboard = [
            [InlineKeyboardButton("⚔️ ПРОДОЛЖИТЬ", callback_data="dungeon_continue")],
            [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("🚪 ВОЙТИ", callback_data="dungeon_start")],
            [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")],
        ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


# ─────────────────────────────────────────────────────────────────────────────
# 📊 ТАБЛИЦЫ ЛИДЕРОВ
# ─────────────────────────────────────────────────────────────────────────────
async def show_ratings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    text = """📊 ТАБЛИЦЫ ЛИДЕРОВ
Выбери таблицу:"""
    keyboard = [
        [InlineKeyboardButton("🏆 Уровень", callback_data="rating_level")],
        [InlineKeyboardButton("🌋 Подземелье", callback_data="rating_dungeon")],
        [InlineKeyboardButton("⚔️ ПВП", callback_data="rating_pvp")],
        [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")],
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_level_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    leaders = get_level_leaderboard(query.message.chat.id, 10)
    text = "🏆 РЕЙТИНГ УРОВНЕЙ 🏆"
    for i, leader in enumerate(leaders, 1):
        if i == 1:
            medal = "👑"
        elif i == 2:
            medal = "🥈"
        elif i == 3:
            medal = "🥉"
        else:
            medal = f"{i}."
        text += f"\n{medal} {leader['username']} (Ур. {leader['level']})"

    keyboard = [
        [InlineKeyboardButton("⬅️ НАЗАД", callback_data="ratings")]
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_dungeon_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    leaders = get_dungeon_leaderboard(query.message.chat.id, 10)
    text = "🌋 РЕЙТИНГ ПОДЗЕМЕЛЬЯ 🌋"
    for i, leader in enumerate(leaders, 1):
        if i == 1:
            medal = "👑"
        elif i == 2:
            medal = "🥈"
        elif i == 3:
            medal = "🥉"
        else:
            medal = f"{i}."
        text += f"\n{medal} {leader['username']} (Ур. {leader['level']}) - Этаж {leader['dungeon_rating']}| Боссов: {leader['total_bosses_killed']}"

    keyboard = [
        [InlineKeyboardButton("⬅️ НАЗАД", callback_data="ratings")]
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_pvp_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    leaders = get_pvp_leaderboard(query.message.chat.id, 10)
    text = "⚔️ РЕЙТИНГ ПВП ⚔️"
    for i, leader in enumerate(leaders, 1):
        if i == 1:
            medal = "👑"
        elif i == 2:
            medal = "🥈"
        elif i == 3:
            medal = "🥉"
        else:
            medal = f"{i}."
        wins = leader['pvp_wins']
        losses = leader['pvp_losses']
        win_rate = leader['win_rate']
        text += f"\n{medal} {leader['username']} (Ур. {leader['level']}) - {wins}W {losses}L ({win_rate:.1f}%)"

    keyboard = [
        [InlineKeyboardButton("⬅️ НАЗАД", callback_data="ratings")]
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


# ─────────────────────────────────────────────────────────────────────────────
# ⚔️ ПВП СИСТЕМА - ОЧЕРЕДЬ ПОДТВЕРЖДЕНИЯ
# ─────────────────────────────────────────────────────────────────────────────
async def show_pvp_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    player = get_player(chat.id, user.id)

    if not player:
        await query.answer("❌ Игрок не найден", show_alert=True)
        return

    queue_status = get_pvp_queue_status(chat.id, user.id)
    if queue_status and queue_status["confirmed"]:
        text = """⚔️ ПВП АРЕНА
⏳ ТЫ УЖЕ В ОЧЕРЕДИ ПОИСКА!
Ищем противника...⏱️ Ожидание...
Нажми "ОТМЕНА" если передумал."""
        keyboard = [
            [InlineKeyboardButton("❌ ОТМЕНА", callback_data="pvp_cancel_search")],
            [InlineKeyboardButton("⏸️ ПРОВЕРИТЬ СНОВА", callback_data="pvp_check_match")],
            [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")],
        ]
    else:
        text = """⚔️ ПВП АРЕНА
Сражайся против других игроков и зарабатывай золото!
⚠️ Перед началом поиска убедись, что:
✅ Ты готов к бою
✅ У тебя полное здоровье
✅ Ты экипирован
Начать поиск противника?"""
        keyboard = [
            [InlineKeyboardButton("🔍 НАЧАТЬ ПОИСК", callback_data="pvp_confirm_search")],
            [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")],
        ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def pvp_confirm_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """✅ НОВОЕ - Игрок подтвердил поиск"""
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    player = get_player(chat.id, user.id)

    if not player:
        await query.answer("❌ Игрок не найден", show_alert=True)
        return

    if player["health"] < player["max_health"]:
        await query.answer("❌ Восстанови здоровье перед боем!", show_alert=True)
        return

    # Добавляем в очередь
    add_to_pvp_queue(chat.id, user.id, user.username or user.first_name, player["level"])
    await query.answer("✅ Поиск противника начат!", show_alert=True)
    await show_pvp_menu(update, context)  # Обновляем меню


async def pvp_check_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """✅ НОВОЕ - Проверяем есть ли противник"""
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    # Проверяем, есть ли противник в той же очереди (чате)
    opponent = find_pvp_opponent(chat.id, user.id)

    if not opponent:
        # Сообщение не изменяется, чтобы избежать ошибки "Message is not modified"
        queue_status = get_pvp_queue_status(chat.id, user.id)
        if queue_status and queue_status["confirmed"]:
            text = """⚔️ ПВП АРЕНА
⏳ ТЫ УЖЕ В ОЧЕРЕДИ ПОИСКА!
Ищем противника...⏱️ Ожидание...
Нажми "ОТМЕНА" если передумал."""
            keyboard = [
                [InlineKeyboardButton("❌ ОТМЕНА", callback_data="pvp_cancel_search")],
                [InlineKeyboardButton("⏸️ ПРОВЕРИТЬ СНОВА", callback_data="pvp_check_match")],
                [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")],
            ]
            try:
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            except Exception as e:
                # Игнорируем ошибку, если сообщение не изменилось
                logger.debug(f"Message not modified during pvp_check_match: {e}")
        else:
            await query.answer("❌ Ты не в очереди.", show_alert=True)
    else:
        # Найден противник
        remove_from_pvp_queue(chat.id, user.id)  # Убираем из очереди
        remove_from_pvp_queue(chat.id, opponent["user_id"])  # Убираем оппонента из очереди

        text = f"""⚔️ ПВП АРЕНА
🎉 ПРОТИВНИК НАЙДЕН!
{CLASSES[get_player(chat.id, opponent['user_id'])['class']]['emoji']} {opponent['username']} - Ур. {opponent['level']}
💰 Призовой фонд: {int(opponent['gold'] * 0.1)} золота
Начинаем бой!"""

        keyboard = [
            [InlineKeyboardButton("⚔️ НАЧАТЬ БОЙ", callback_data=f"pvp_start_fight_{opponent['user_id']}")],
            [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")],
        ]

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def pvp_cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    remove_from_pvp_queue(chat.id, user.id)
    await query.answer("❌ Поиск отменён.", show_alert=True)
    await show_pvp_menu(update, context)


async def pvp_start_fight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """✅ НОВОЕ - Начать ПВП бой"""
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    defender_id = int(query.data.replace("pvp_start_fight_", ""))

    result = pvp_battle_logic(chat.id, user.id, defender_id)
    if not result.get("success"):
        await query.answer(result.get("message", "❌ Ошибка"), show_alert=True)
        return

    attacker = get_player(chat.id, user.id)
    defender = get_player(chat.id, defender_id)

    if result["winner_id"] == user.id:
        text = f"""⚔️ ПВП БОЙ
🎉 ПОБЕДА!
Противник: {defender['username']}
⚔️ Твой урон: {result['attacker_damage']} {('💥 КРИТ!' if result['attacker_crit'] else '')}
Ответный урон врага: {result['defender_damage']} 💰 Награда: +{result['reward_gold']} золота"""
    else:
        text = f"""⚔️ ПВП БОЙ
💀 ПОРАЖЕНИЕ!
Противник: {defender['username']}
⚔️ Урон врага: {result['defender_damage']} {('💥 КРИТ!' if result['defender_crit'] else '')}
Твой урон: {result['attacker_damage']} ❌ Награда: -10% золота"""

    keyboard = [
        [InlineKeyboardButton("🎮 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


# ─────────────────────────────────────────────────────────────────────────────
# 🎮 ОСНОВНОЕ МЕНЮ И ПРОФИЛЬ
# ─────────────────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    user_id = user.id
    chat_id = chat.id

    if player_exists(chat_id, user_id):
        await show_main_menu(update, context)
        return

    text = f"""🎮 Добро пожаловать в RuneQuestRPG, {user.first_name}!
⚔️ ВЫБЕРИ СВОЙ КЛАСС:
🛡️ ВОИН (HP: 120| Атака: 15| Защита: 8)
🔥 МАГ (HP: 70| Атака: 8| Защита: 3| Магия: 25)
🗡️ РАЗБОЙНИК (HP: 85| Атака: 19| Защита: 5| Крит: 22%)
⛪ ПАЛАДИН (HP: 140| Атака: 13| Защита: 15)
🏹 РЕЙНДЖЕР (HP: 95| Атака: 17| Защита: 6)
💀 НЕКРОМАНТ (HP: 80| Атака: 10| Защита: 4| Магия: 30)"""

    keyboard = [
        [InlineKeyboardButton("⚔️ Воин", callback_data="class_warrior"), InlineKeyboardButton("🔥 Маг", callback_data="class_mage")],
        [InlineKeyboardButton("🗡️ Разбойник", callback_data="class_rogue"), InlineKeyboardButton("⛪ Паладин", callback_data="class_paladin")],
        [InlineKeyboardButton("🏹 Рейнджер", callback_data="class_ranger"), InlineKeyboardButton("💀 Некромант", callback_data="class_necromancer")],
    ]

    if update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        query = update.callback_query
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def select_class(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    class_choice = query.data.replace("class_", "")

    if init_player(chat.id, user.id, user.username or user.first_name, class_choice):
        logger.info(f"✅ Игрок создан: {user.first_name} ({user.id}) - {class_choice}")
        await show_main_menu(update, context)
    else:
        await query.answer("❌ Ошибка при создании персонажа", show_alert=True)


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query if update.callback_query else None
    message = query.message if query else update.message
    user = update.effective_user
    chat = update.effective_chat
    player = get_player(chat.id, user.id)

    if not player:
        text = "❌ Игрок не найден. Используй /start для регистрации."
        if query:
            await query.edit_message_text(text)
        else:
            await message.reply_text(text)
        return

    class_info = CLASSES[player["class"]]
    text = f"""🎮 RUNEQUESTRPG - ГЛАВНОЕ МЕНЮ
👤 {user.first_name}
{class_info['emoji']} Класс: {class_info['name']}
📊 Уровень: {player['level']} | ❤️ HP: {player['health']}/{player['max_health']} | ⚡ Mana: {player['mana']}/{player['max_mana']}
💰 Золото: {player['gold']} | 📈 XP: {player['xp']}/{int(LEVEL_UP_BASE * ((player['level'] + 1) ** 1.5))}"""

    keyboard = [
        [InlineKeyboardButton("👤 Профиль", callback_data="profile"), InlineKeyboardButton("🎒 Инвентарь", callback_data="inventory")],
        [InlineKeyboardButton("⚔️ Бой", callback_data="locations_list"), InlineKeyboardButton("🏆 ПВП", callback_data="pvp_menu")],
        [InlineKeyboardButton("🛒 Магазин", callback_data="shop"), InlineKeyboardButton("⚙️ Экипировка", callback_data="equipment")],
        [InlineKeyboardButton("🔨 Крафт", callback_data="crafting"), InlineKeyboardButton("🏆 Подземелье", callback_data="dungeon")],
        [InlineKeyboardButton("⚔️ ПВП", callback_data="pvp_menu"), InlineKeyboardButton("📊 Рейтинги", callback_data="ratings")],
    ]

    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        if message:
            await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    player = get_player(chat.id, user.id)

    if not player:
        await query.answer("❌ Игрок не найден", show_alert=True)
        return

    class_info = CLASSES[player["class"]]
    xp_needed = int(LEVEL_UP_BASE * ((player["level"] + 1) ** 1.5))
    xp_percent = int(player["xp"] / max(xp_needed, 1) * 100)
    bar_filled = "█" * (xp_percent // 10)
    bar_empty = "░" * (10 - xp_percent // 10)
    pet = PETS.get(player["pet_id"])

    # Вычисляем боевые статы
    battle_stats = get_player_battle_stats(player)

    text = f"""👤 ПРОФИЛЬ ГЕРОЯ
{class_info['emoji']} {class_info['name']}
⭐ Уровень: {player['level']}/{MAX_LEVEL}
📊 Опыт: {player['xp']}/{xp_needed} ({xp_percent}%)
{bar_filled}{bar_empty}
❤️ Здоровье: {player['health']}/{player['max_health']}
💙 Мана: {player['mana']}/{player['max_mana']}
⚔️ Атака: {battle_stats['attack']} (база: {player['attack']})
🛡️ Защита: {battle_stats['defense']} (база: {player['defense']})
💥 Крит: {battle_stats['crit_chance']}%
💰 Золото: {player['gold']}
🏆 Рейтинг подземелья: {player['dungeon_rating']}

🐾 ПИТОМЕЦ: {pet['emoji']} {pet['name']}

📈 СТАТИСТИКА:
⚔️ Побед в бою: {player['total_battles_won']}
💀 Поражений в бою: {player['total_battles_lost']}
👹 Убито боссов: {player['total_bosses_killed']}
⚔️ ПВП Побед: {player['pvp_wins']}
📉 ПВП Поражений: {player['pvp_losses']}
🔨 Крафтов: {player['craft_count']}"""

    keyboard = [
        [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


# ─────────────────────────────────────────────────────────────────────────────
# 🎒 ИНВЕНТАРЬ
# ─────────────────────────────────────────────────────────────────────────────
async def show_inventory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    inventory = get_inventory(chat.id, user.id)

    if not inventory:
        text = "🎒 ИНВЕНТАРЬ\n❌ Инвентарь пуст"
    else:
        text = "🎒 ИНВЕНТАРЬ"
        for item in inventory:
            iid = item["item_id"]
            qty = item['quantity']
            if iid in WEAPONS:
                w = WEAPONS[iid]
                text += f"\n⚔️ {w['name']} x{qty}"
            elif iid in ARMOR:
                a = ARMOR[iid]
                text += f"\n🛡️ {a['name']} x{qty}"
            elif iid in MATERIALS:
                m = MATERIALS[iid]
                text += f"\n📦 {m['name']} x{qty}"
            elif iid in PETS:
                p = PETS[iid]
                text += f"\n🐾 {p['emoji']} {p['name']} x{qty}"
            else:
                text += f"\n📦 {iid} x{qty}"

    keyboard = [
        [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


# ─────────────────────────────────────────────────────────────────────────────
# 🏰 ЛОКАЦИИ
# ─────────────────────────────────────────────────────────────────────────────
async def show_locations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """✅ НОВОЕ - Показать локации"""
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    player = get_player(chat.id, user.id)

    if not player:
        await query.answer("❌ Игрок не найден", show_alert=True)
        return

    text = "🏰 ВЫБЕРИ ЛОКАЦИЮ:"
    keyboard = []
    for loc_id, loc in LOCATIONS.items():
        # Показываем статус доступности
        if player["level"] < loc["min_level"]:
            status = "🔒"  # Слишком слабый
        elif player["level"] > loc["max_level"]:
            status = "⚠️"  # Слишком сильный
        else:
            status = "✅"  # Подходит

        text += f"\n{status} {loc['emoji']} {loc['name']} (Ур. {loc['min_level']}-{loc['max_level']})"

    keyboard.append([InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def select_location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """✅ НОВОЕ - Выбрана локация, показываем подтверждение"""
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    location_id = query.data.replace("location_select_", "")
    location = LOCATIONS.get(location_id)

    if not location:
        await query.answer("❌ Локация не найдена", show_alert=True)
        return

    player = get_player(chat.id, user.id)
    if not player:
        await query.answer("❌ Игрок не найден", show_alert=True)
        return

    # ✅ ПРОВЕРЯЕМ УРОВЕНЬ
    if player["level"] < location["min_level"]:
        return {"error": f"❌ Требуется уровень {location['min_level']}-{location['max_level']}! Ты уровня {player['level']}"}
    if player["level"] > location["max_level"]:
        return {"error": f"❌ Эта локация слишком слаба для тебя! Требуется уровень {location['min_level']}-{location['max_level']}"}

    # ✅ ВРАГИ ТОЛЬКО ИЗ ЛОКАЦИИ
    possible_enemies = location["enemies"]
    enemy_id = random.choice(possible_enemies)
    enemy_template = ENEMIES[enemy_id].copy()

    level_diff = max(1, player["level"] - enemy_template["level"])
    scale = 1.0 + level_diff * 0.12
    enemy_template["current_hp"] = int(enemy_template["hp"] * scale)

    # Создаем запись боя
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM battles WHERE user_id = ? AND chat_id = ?", (user.id, chat.id))  # Удаляем старый бой
    c.execute("""
        INSERT INTO battles (user_id, chat_id, location_id, enemy_id, enemy_health, enemy_max_health, enemy_damage, is_boss, player_health, player_max_health)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user.id, chat.id, location_id, enemy_id,
        enemy_template["current_hp"], enemy_template["current_hp"],
        int(enemy_template["damage"] * scale), enemy_template.get("boss", False),
        player["health"], player["max_health"]
    ))
    conn.commit()
    conn.close()

    text = f"""{location['emoji']} {location['name'].upper()}
{location['description']}
Рек. уровень: {location['min_level']}-{location['max_level']}
Твой уровень: {player['level']}
✅ ГОТОВ!
Враги:"""
    for enemy_id in location["enemies"]:
        enemy = ENEMIES[enemy_id]
        text += f"\n{enemy['emoji']} {enemy['name']} (Ур. {enemy['level']})"

    keyboard = [
        [InlineKeyboardButton("⚔️ НАЧАТЬ БОЙ", callback_data=f"fight_{location_id}")],
        [InlineKeyboardButton("⬅️ НАЗАД", callback_data="locations_list")],
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def start_battle_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """✅ НОВОЕ - Начать бой из локации"""
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    location_id = query.data.replace("fight_", "")

    player = get_player(chat.id, user.id)
    if not player:
        await query.answer("❌ Игрок не найден", show_alert=True)
        return

    # Проверяем, не в бою ли уже
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT 1 FROM battles WHERE user_id = ? AND chat_id = ?", (user.id, chat.id))
    in_battle = c.fetchone() is not None
    conn.close()

    if in_battle:
        await query.answer("⚠️ Ты уже в бою!", show_alert=True)
        return

    # ✅ НАЧИНАЕМ БОЙ С ВРАГОМ ИЗ ЛОКАЦИИ
    result = start_battle_logic(chat.id, user.id, location_id)
    if not result.get("success"):
        await query.answer(result.get("error", "❌ Не удалось начать бой"), show_alert=True)
        return

    text = f"""⚔️ БОЙ НАЧАЛСЯ!
Противник: {result['enemy_emoji']} {result['enemy_name']} (Ур. {result['enemy_level']})
❤️ Враг HP: {result['enemy_health']}/{result['enemy_max_health']}
⚔️ Враг урон: {result['enemy_damage']}"""

    keyboard = [
        [InlineKeyboardButton("⚔️ АТАКОВАТЬ", callback_data="attack")],
        [InlineKeyboardButton("🧪 ЗЕЛЬЕ", callback_data="use_potion")],
        [InlineKeyboardButton("🏃 СБЕЖАТЬ", callback_data="escape"), InlineKeyboardButton("❌ СДАТЬСЯ", callback_data="surrender")],
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


def start_battle_logic(chat_id: int, user_id: int, location_id: str) -> Dict[str, Any]:
    player = get_player(chat_id, user_id)
    if not player:
        return {"success": False, "error": "❌ Игрок не найден"}

    location = LOCATIONS.get(location_id)
    if not location:
        return {"success": False, "error": "❌ Локация не найдена"}

    # Проверяем уровень
    if player["level"] < location["min_level"] or player["level"] > location["max_level"]:
        return {"success": False, "error": f"❌ Недопустимый уровень для локации {location['name']}"}

    # Выбираем случайного врага из локации
    possible_enemies = location["enemies"]
    enemy_id = random.choice(possible_enemies)
    enemy_template = ENEMIES[enemy_id].copy()

    # Масштабирование врага
    level_diff = max(1, player["level"] - enemy_template["level"])
    scale = 1.0 + level_diff * 0.12
    scaled_damage = int(enemy_template["damage"] * scale)
    scaled_health = int(enemy_template["hp"] * scale)

    # Создаем запись боя
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM battles WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))  # Удаляем старый бой
    c.execute("""
        INSERT INTO battles (user_id, chat_id, location_id, enemy_id, enemy_health, enemy_max_health, enemy_damage, is_boss, player_health, player_max_health)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, chat_id, location_id, enemy_id,
        scaled_health, scaled_health, scaled_damage, enemy_template.get("boss", False),
        player["health"], player["max_health"]
    ))
    conn.commit()
    conn.close()

    return {
        "success": True,
        "enemy_id": enemy_id,
        "enemy_name": enemy_template["name"],
        "enemy_emoji": enemy_template["emoji"],
        "enemy_level": enemy_template["level"],
        "enemy_health": scaled_health,
        "enemy_max_health": scaled_health,
        "enemy_damage": scaled_damage,
        "is_boss": enemy_template.get("boss", False),
    }


async def get_battle(chat_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM battles WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
        row = c.fetchone()
        return dict(row) if row else None
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка получения боя: {e}")
        return None
    finally:
        conn.close()


async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    player = get_player(chat.id, user.id)
    if not player:
        await query.answer("❌ Игрок не найден", show_alert=True)
        return

    battle = await get_battle(chat.id, user.id)
    if not battle:
        await query.answer("❌ Бой не найден", show_alert=True)
        return

    battle_result = perform_attack_logic(chat.id, user.id, battle)
    if not battle_result.get("success"):
        await query.answer(battle_result.get("message", "❌ Ошибка"), show_alert=True)
        return

    text = f"""⚔️ БОЙ
Твоя атака: {("💥" if battle_result['is_crit'] else "")} {battle_result['damage']} урона{("✨ КРИТ!" if battle_result['is_crit'] else "")}
❤️ Враг HP: {battle_result['enemy_hp']}/{battle_result['enemy_max_hp']}"""

    if battle_result.get("victory"):
        # Вычисляем награду
        enemy_xp = ENEMIES[battle["enemy_id"]]["xp"]
        enemy_gold = ENEMIES[battle["enemy_id"]]["gold"]
        xp_bonus = 1.0
        if player["pet_id"] == "cat":
            xp_bonus = 1.1  # Бонус к XP от питомца
        xp_gained = int(enemy_xp * xp_bonus)
        gold_gained = enemy_gold

        # Обновляем игрока
        add_gold(chat.id, user.id, gold_gained)
        update_player_stat(chat_id, user.id, "xp", player["xp"] + xp_gained)
        # Проверка повышения уровня
        xp_needed = int(LEVEL_UP_BASE * ((player["level"] + 1) ** 1.5))
        if player["xp"] + xp_gained >= xp_needed:
            update_player_stat(chat_id, user.id, "level", player["level"] + 1)
            update_player_stat(chat_id, user.id, "max_health", player["max_health"] + STATS_PER_LEVEL["health"])
            update_player_stat(chat_id, user.id, "max_mana", player["max_mana"] + STATS_PER_LEVEL["mana"])
            update_player_stat(chat_id, user.id, "attack", player["attack"] + STATS_PER_LEVEL["attack"])
            update_player_stat(chat_id, user.id, "defense", player["defense"] + STATS_PER_LEVEL["defense"])
            # Обновляем текущее здоровье и ману до новых максимумов
            update_player_stat(chat_id, user.id, "health", player["max_health"] + STATS_PER_LEVEL["health"])
            update_player_stat(chat_id, user.id, "mana", player["max_mana"] + STATS_PER_LEVEL["mana"])
            # Обновляем статистику
            if battle["is_boss"]:
                update_player_stat(chat_id, user.id, "total_bosses_killed", player["total_bosses_killed"] + 1)
            update_player_stat(chat_id, user.id, "total_kills", player["total_kills"] + 1)
            update_player_stat(chat_id, user.id, "total_battles_won", player["total_battles_won"] + 1)

        # Лут
        loot_text = ""
        if random.random() < 0.3:  # 30% шанс на лут
            loot_item = random.choice(ENEMIES[battle["enemy_id"]]["loot"])
            add_item(chat.id, user.id, loot_item)
            loot_info = MATERIALS.get(loot_item, {})
            loot_text = f"🎁 Лут: {loot_info.get('emoji', '')} {loot_info.get('name', 'Неизвестно')}"

        text += f"""
🎉 ПОБЕДА!
⭐ Опыт: +{xp_gained}
💰 Золото: +{gold_gained}
{loot_text}"""
        # Удаляем запись боя
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM battles WHERE user_id = ? AND chat_id = ?", (user.id, chat.id))
        conn.commit()
        conn.close()
        keyboard = [
            [InlineKeyboardButton("🎮 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]
        ]
    elif battle_result.get("defeat"):
        gold_lost = int(player["gold"] * 0.1)
        subtract_gold(chat.id, user.id, gold_lost)
        # Обновляем статистику
        update_player_stat(chat_id, user.id, "total_battles_lost", player["total_battles_lost"] + 1)
        text += f"""
💀 ПОРАЖЕНИЕ!
Потеряно золота: -{gold_lost}"""
        # Удаляем запись боя
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM battles WHERE user_id = ? AND chat_id = ?", (user.id, chat.id))
        conn.commit()
        conn.close()
        keyboard = [
            [InlineKeyboardButton("🎮 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]
        ]
    else:
        enemy_damage = battle_result.get("enemy_damage", 0)
        player_hp = battle_result.get("player_hp", 0)
        player_max_hp = battle_result.get("player_max_hp", 0)
        text += f"""
👹 Враг атакует: {enemy_damage} урона
❤️ Твой HP: {player_hp}/{player_max_hp}"""
        keyboard = [
            [InlineKeyboardButton("⚔️ АТАКОВАТЬ", callback_data="attack")],
            [InlineKeyboardButton("🧪 ЗЕЛЬЕ", callback_data="use_potion")],
            [InlineKeyboardButton("🏃 СБЕЖАТЬ", callback_data="escape"), InlineKeyboardButton("❌ СДАТЬСЯ", callback_data="surrender")],
        ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


def perform_attack_logic(chat_id: int, user_id: int, battle: Dict[str, Any]) -> Dict[str, Any]:
    player = get_player(chat_id, user_id)
    if not player or not battle:
        return {"success": False, "message": "❌ Бой не найден"}

    # Вычисляем боевые статы
    battle_stats = get_player_battle_stats(player)

    # Атака игрока
    player_damage, is_crit = calculate_damage(battle_stats["attack"], battle["enemy_damage"] // 2, battle_stats["crit_chance"], battle_stats["spell_power"])
    new_enemy_hp = battle["enemy_health"] - player_damage

    # Проверка победы
    if new_enemy_hp <= 0:
        # Игрок победил
        return {
            "success": True, "victory": True, "damage": player_damage, "is_crit": is_crit,
            "enemy_hp": 0, "enemy_max_hp": battle["enemy_max_health"],
        }

    # Атака врага
    enemy_damage, _ = calculate_damage(battle["enemy_damage"], battle_stats["defense"], 5, 0)  # Упрощение: crit = 5, spell = 0
    new_player_hp = player["health"] - enemy_damage

    # Обновляем HP врага и игрока в базе
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE battles SET enemy_health = ? WHERE user_id = ? AND chat_id = ?", (new_enemy_hp, user_id, chat_id))
    c.execute("UPDATE players SET health = ? WHERE user_id = ? AND chat_id = ?", (new_player_hp, user_id, chat_id))
    conn.commit()
    conn.close()

    # Проверка поражения
    if new_player_hp <= 0:
        return {
            "success": True, "defeat": True, "damage": player_damage, "is_crit": is_crit,
            "enemy_hp": new_enemy_hp, "enemy_max_hp": battle["enemy_max_health"],
            "player_hp": 0, "player_max_hp": player["max_health"]
        }

    return {
        "success": True, "damage": player_damage, "is_crit": is_crit,
        "enemy_hp": new_enemy_hp, "enemy_max_hp": battle["enemy_max_health"],
        "enemy_damage": enemy_damage,
        "player_hp": new_player_hp, "player_max_hp": player["max_health"]
    }


async def use_potion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    player = get_player(chat.id, user.id)
    battle = await get_battle(chat.id, user.id)

    if not player or not battle:
        await query.answer("❌ Бой не найден", show_alert=True)
        return

    if get_material(chat.id, user.id, "health_potion") <= 0:
        await query.answer("❌ Нет зелий здоровья", show_alert=True)
        return

    remove_item(chat.id, user.id, "health_potion")
    heal_amount = int(player["max_health"] * 0.5)
    new_hp = min(player["max_health"], player["health"] + heal_amount)

    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE players SET health = ? WHERE user_id = ? AND chat_id = ?", (new_hp, user.id, chat.id))
    conn.commit()
    conn.close()

    # Атака врага после использования зелья
    battle_stats = get_player_battle_stats(player)
    enemy_damage, _ = calculate_damage(battle["enemy_damage"], battle_stats["defense"], 5, 0)
    final_player_hp = new_hp - enemy_damage

    text = f"""🧪 ЗЕЛЬЕ ИСПОЛЬЗОВАНО!
💚 +{heal_amount} HP
❤️ Твой HP: {new_hp}/{player['max_health']}

👹 Враг атакует: {enemy_damage} урона
❤️ Твой HP: {final_player_hp}/{player['max_health']}"""

    keyboard = [
        [InlineKeyboardButton("⚔️ АТАКОВАТЬ", callback_data="attack")],
        [InlineKeyboardButton("🏃 СБЕЖАТЬ", callback_data="escape")],
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def escape(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    player = get_player(chat.id, user.id)
    battle = await get_battle(chat.id, user.id)

    if not player or not battle:
        await query.answer("❌ Бой не найден", show_alert=True)
        return

    # 50% шанс на побег
    if random.random() < 0.5:
        gold_penalty = int(player["gold"] * 0.05)  # Потеря 5% золота
        subtract_gold(chat.id, user.id, gold_penalty)
        # Удаляем запись боя
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM battles WHERE user_id = ? AND chat_id = ?", (user.id, chat.id))
        conn.commit()
        conn.close()
        await query.edit_message_text(f"🏃 ПОБЕГ УДАЛСЯ! Потеряно {gold_penalty} золота.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎮 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]]))
    else:
        # Проваленный побег - враг атакует
        battle_stats = get_player_battle_stats(player)
        enemy_damage, _ = calculate_damage(battle["enemy_damage"], battle_stats["defense"], 5, 0)
        new_player_hp = player["health"] - enemy_damage
        update_player_stat(chat.id, user.id, "health", new_player_hp)

        text = f"""🏃 ПОБЕГ НЕ УДАЛСЯ!
👹 Враг атакует: {enemy_damage} урона
❤️ Твой HP: {new_player_hp}/{player['max_health']}"""

        keyboard = [
            [InlineKeyboardButton("⚔️ АТАКОВАТЬ", callback_data="attack")],
            [InlineKeyboardButton("🧪 ЗЕЛЬЕ", callback_data="use_potion")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def surrender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    player = get_player(chat.id, user.id)

    if not player:
        await query.answer("❌ Игрок не найден", show_alert=True)
        return

    # Потеря 10% золота
    gold_penalty = int(player["gold"] * 0.1)
    subtract_gold(chat.id, user.id, gold_penalty)
    # Удаляем запись боя
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM battles WHERE user_id = ? AND chat_id = ?", (user.id, chat.id))
    conn.commit()
    conn.close()
    await query.edit_message_text(f"❌ СДАЛСЯ! Потеряно {gold_penalty} золота.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎮 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]]))


# ─────────────────────────────────────────────────────────────────────────────
# 🚀 ГЛАВНАЯ ФУНКЦИЯ
# ─────────────────────────────────────────────────────────────────────────────
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"❌ Update {update} вызвала ошибку: {context.error}")
    try:
        if update.callback_query:
            await update.callback_query.answer("❌ Произошла ошибка. Попробуй снова.", show_alert=True)
    except:
        pass


def signal_handler(sig, frame):
    """Обработчик сигналов для graceful shutdown"""
    logger.info("⚠️ Получен сигнал завершения. Закрывается...")
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    init_database()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(30)
        .build()
    )

    # Основные хендлеры
    app.add_handler(CommandHandler("start", start))

    # Выбор класса
    app.add_handler(CallbackQueryHandler(select_class, pattern="^class_"))

    # Главное меню
    app.add_handler(CallbackQueryHandler(show_main_menu, pattern="^main_menu$"))

    # Профиль
    app.add_handler(CallbackQueryHandler(show_profile, pattern="^profile$"))

    # Локации
    app.add_handler(CallbackQueryHandler(show_locations, pattern="^locations_list$"))
    app.add_handler(CallbackQueryHandler(select_location_handler, pattern="^location_select_"))

    # Боевая система
    app.add_handler(CallbackQueryHandler(attack, pattern="^attack$"))
    app.add_handler(CallbackQueryHandler(use_potion, pattern="^use_potion$"))
    app.add_handler(CallbackQueryHandler(escape, pattern="^escape$"))
    app.add_handler(CallbackQueryHandler(surrender, pattern="^surrender$"))

    # Крафтинг
    app.add_handler(CallbackQueryHandler(crafting, pattern="^crafting$"))
    app.add_handler(CallbackQueryHandler(craft, pattern="^craft_[a-z_]+$"))
    app.add_handler(CallbackQueryHandler(craft_confirm, pattern="^craft_confirm_[a-z_]+$"))

    # Подземелье
    app.add_handler(CallbackQueryHandler(show_dungeon_menu, pattern="^dungeon$"))

    # ✅ ПВП - ОЧЕРЕДЬ ПОДТВЕРЖДЕНИЯ
    app.add_handler(CallbackQueryHandler(show_pvp_menu, pattern="^pvp_menu$"))
    app.add_handler(CallbackQueryHandler(pvp_confirm_search, pattern="^pvp_confirm_search$"))
    app.add_handler(CallbackQueryHandler(pvp_check_match, pattern="^pvp_check_match$"))
    app.add_handler(CallbackQueryHandler(pvp_cancel_search, pattern="^pvp_cancel_search$"))
    app.add_handler(CallbackQueryHandler(pvp_start_fight, pattern="^pvp_start_fight_"))

    # Магазин
    app.add_handler(CallbackQueryHandler(show_shop, pattern="^shop$"))
    app.add_handler(CallbackQueryHandler(show_weapons_shop, pattern="^shop_weapons$"))
    app.add_handler(CallbackQueryHandler(buy_weapon, pattern="^buy_weapon_"))
    app.add_handler(CallbackQueryHandler(show_armor_shop, pattern="^shop_armor$"))
    app.add_handler(CallbackQueryHandler(buy_armor, pattern="^buy_armor_"))
    app.add_handler(CallbackQueryHandler(show_pets_shop, pattern="^shop_pets$"))
    app.add_handler(CallbackQueryHandler(buy_pet, pattern="^buy_pet_"))
    app.add_handler(CallbackQueryHandler(show_runes_shop, pattern="^shop_runes$"))
    app.add_handler(CallbackQueryHandler(buy_rune, pattern="^buy_rune_"))

    # Экипировка
    app.add_handler(CallbackQueryHandler(show_equipment, pattern="^equipment$"))
    app.add_handler(CallbackQueryHandler(equip_weapon_handler, pattern="^equip_weapon_"))
    app.add_handler(CallbackQueryHandler(equip_armor_handler, pattern="^equip_armor_"))

    # Рейтинги
    app.add_handler(CallbackQueryHandler(show_ratings, pattern="^ratings$"))
    app.add_handler(CallbackQueryHandler(show_level_rating, pattern="^rating_level$"))
    app.add_handler(CallbackQueryHandler(show_dungeon_rating, pattern="^rating_dungeon$"))
    app.add_handler(CallbackQueryHandler(show_pvp_rating, pattern="^rating_pvp$"))

    # Инвентарь
    app.add_handler(CallbackQueryHandler(show_inventory, pattern="^inventory$"))

    # Обработчик ошибок
    app.add_error_handler(error_handler)

    logger.info("✅ RuneQuestRPG BOT v5.1 ЗАПУЩЕН И ГОТОВ!")

    # Проверка на Render: если WEBHOOK_URL задан, используем webhook, иначе polling
    if os.getenv("WEBHOOK_URL"):
        logger.info(f"🚀 Запуск с вебхуком на {os.getenv('WEBHOOK_URL')}")
        app.run_webhook(
            listen="0.0.0.0",
            port=int(os.getenv("PORT", 10000)),
            url_path=BOT_TOKEN,
            webhook_url=f"{os.getenv('WEBHOOK_URL')}/{BOT_TOKEN}"
        )
    else:
        logger.info("🚀 Запуск с polling")
        app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
