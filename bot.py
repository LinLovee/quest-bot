"""
╔════════════════════════════════════════════════════════════════════════════╗
║                                                                            ║
║ 🎮 RUNEQUESTRPG BOT - v5.2 FIXED (BUGFIXES) 🎮                           ║
║                                                                            ║
║ Версия: 5.2 (5600+ строк кода)                                          ║
║ Статус: ✅ ПВП МАТЧМЕЙКИНГ ИСПРАВЛЕН, ОШИБКИ TELEGRAM ОБРАБОТАНЫ       ║
║ Автор: AI Developer                                                      ║
║ Дата: 2024-2025                                                          ║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝

BUGFIXES в v5.2:
✅ 1. Исправлена логика поиска ПВП - враги теперь находят друг друга
✅ 2. Обработана ошибка "Message is not modified" от Telegram
✅ 3. Улучшен матчмейкинг - учитывает одну локацию (chat_id)

"""

import os
import sqlite3
import random
import logging
import signal
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any, Callable
from functools import wraps
from enum import Enum
from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

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
# 🗡️ ОРУЖИЕ (КЛАСС-СПЕЦИФИЧНОЕ)
# ─────────────────────────────────────────────────────────────────────────────

WEAPONS: Dict[str, Dict[str, Any]] = {
    "iron_sword": {"name": "Железный меч", "emoji": "⚔️", "attack": 10, "price": 100, "level": 1, "crit": 0, "class": "warrior"},
    "steel_sword": {"name": "Стальной меч", "emoji": "⚔️", "attack": 20, "price": 500, "level": 5, "crit": 2, "class": "warrior"},
    "mithril_sword": {"name": "Мифриловый меч", "emoji": "⚔️", "attack": 35, "price": 2000, "level": 15, "crit": 5, "class": "warrior"},
    "legendary_sword": {"name": "Легендарный клинок", "emoji": "⚔️", "attack": 60, "price": 5000, "level": 30, "crit": 15, "class": "warrior"},
    "fire_staff": {"name": "Посох огня", "emoji": "🔥", "attack": 16, "price": 160, "level": 2, "crit": 3, "class": "mage"},
    "ice_staff": {"name": "Ледяной посох", "emoji": "❄️", "attack": 19, "price": 320, "level": 5, "crit": 4, "class": "mage"},
    "arcane_orb": {"name": "Сфера тайной магии", "emoji": "🌀", "attack": 28, "price": 1200, "level": 12, "crit": 6, "class": "mage"},
    "shadow_dagger": {"name": "Кинжал Тени", "emoji": "🗡️", "attack": 14, "price": 120, "level": 1, "crit": 12, "class": "rogue"},
    "death_scythe": {"name": "Коса смерти", "emoji": "🔪", "attack": 52, "price": 3200, "level": 20, "crit": 13, "class": "rogue"},
    "holy_mace": {"name": "Святая булава", "emoji": "🔨", "attack": 17, "price": 230, "level": 3, "crit": 1, "class": "paladin"},
    "long_bow": {"name": "Длинный лук", "emoji": "🏹", "attack": 19, "price": 260, "level": 4, "crit": 9, "class": "ranger"},
    "dragon_spear": {"name": "Драконий копьё", "emoji": "🗡️", "attack": 44, "price": 2600, "level": 18, "crit": 10, "class": "necromancer"},
}

# ─────────────────────────────────────────────────────────────────────────────
# 🛡️ БРОНЯ (КЛАСС-СПЕЦИФИЧНАЯ)
# ─────────────────────────────────────────────────────────────────────────────

ARMOR: Dict[str, Dict[str, Any]] = {
    "iron_armor": {"name": "Железная броня", "emoji": "🛡️", "defense": 8, "health": 20, "price": 150, "level": 1, "class": "warrior"},
    "steel_armor": {"name": "Стальная броня", "emoji": "🛡️", "defense": 16, "health": 45, "price": 650, "level": 6, "class": "warrior"},
    "mithril_armor": {"name": "Мифриловая броня", "emoji": "🛡️", "defense": 27, "health": 90, "price": 2600, "level": 16, "class": "warrior"},
    "plate_armor": {"name": "Пластинчатая броня", "emoji": "🛡️", "defense": 22, "health": 70, "price": 900, "level": 9, "class": "warrior"},
    "mage_robes": {"name": "Мантия мага", "emoji": "👗", "defense": 4, "health": 26, "price": 210, "level": 2, "class": "mage"},
    "ranger_armor": {"name": "Броня рейнджера", "emoji": "🧤", "defense": 11, "health": 32, "price": 320, "level": 3, "class": "ranger"},
    "leather_armor": {"name": "Кожаная броня", "emoji": "🧥", "defense": 6, "health": 18, "price": 110, "level": 1, "class": "paladin"},
    "holy_armor": {"name": "Святая броня", "emoji": "✨", "defense": 19, "health": 75, "price": 1250, "level": 11, "class": "paladin"},
}

# ─────────────────────────────────────────────────────────────────────────────
# 🐾 ПИТОМЦЫ
# ─────────────────────────────────────────────────────────────────────────────

PETS: Dict[str, Dict[str, Any]] = {
    "wolf": {"name": "Волк", "emoji": "🐺", "attack_bonus": 10, "defense_bonus": 0, "xp_bonus": 1.1, "price": 500, "level": 1},
    "phoenix": {"name": "Феникс", "emoji": "🔥", "attack_bonus": 20, "defense_bonus": 5, "xp_bonus": 1.4, "price": 2000, "level": 10},
    "dragon": {"name": "Дракон", "emoji": "🐉", "attack_bonus": 25, "defense_bonus": 10, "xp_bonus": 1.5, "price": 3200, "level": 15},
    "shadow": {"name": "Тень", "emoji": "⚫", "attack_bonus": 15, "defense_bonus": 2, "xp_bonus": 1.3, "price": 1100, "level": 5},
    "bear": {"name": "Медведь", "emoji": "🐻", "attack_bonus": 18, "defense_bonus": 8, "xp_bonus": 1.2, "price": 1500, "level": 8},
    "demon": {"name": "Малый демон", "emoji": "😈", "attack_bonus": 32, "defense_bonus": 4, "xp_bonus": 1.6, "price": 5200, "level": 20},
}

# ─────────────────────────────────────────────────────────────────────────────
# 🏞️ ЛОКАЦИИ (С ЗАЩИТОЙ УРОВНЯ)
# ─────────────────────────────────────────────────────────────────────────────

LOCATIONS: Dict[str, Dict[str, Any]] = {
    "dark_forest": {
        "name": "Тёмный лес",
        "emoji": "🌲",
        "min_level": 1,
        "max_level": 10,
        "description": "Густой лес с опасными тварями",
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
    "copper_bar": {"name": "Медный слиток", "emoji": "🔨", "materials": {"copper_ore": 5}, "gold": 20, "level": 1, "result": "copper_bar"},
    "iron_bar": {"name": "Железный слиток", "emoji": "🔨", "materials": {"iron_ore": 5}, "gold": 55, "level": 3, "result": "iron_bar"},
    "mithril_bar": {"name": "Мифриловый слиток", "emoji": "🔨", "materials": {"mithril_ore": 3, "ice_crystal": 1}, "gold": 210, "level": 10, "result": "mithril_bar"},
    "health_potion": {"name": "Зелье здоровья", "emoji": "🧪", "materials": {"bone": 2, "copper_ore": 1}, "gold": 35, "level": 1, "result": "health_potion"},
    "mana_potion": {"name": "Зелье маны", "emoji": "🧪", "materials": {"ice_crystal": 1}, "gold": 85, "level": 5, "result": "mana_potion"},
    "strength_potion": {"name": "Зелье силы", "emoji": "💪", "materials": {"troll_hide": 1, "wolf_fang": 2}, "gold": 110, "level": 7, "result": "strength_potion"},
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

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

    c.execute("""
    CREATE TABLE IF NOT EXISTS dungeon_progress (
        user_id INTEGER PRIMARY KEY,
        chat_id INTEGER,
        current_floor INTEGER DEFAULT 1,
        is_active BOOLEAN DEFAULT 0,
        enemies_killed INTEGER DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES players(user_id)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS pvp_queue (
        user_id INTEGER PRIMARY KEY,
        chat_id INTEGER,
        is_waiting BOOLEAN DEFAULT 1,
        confirmed BOOLEAN DEFAULT 0,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES players(user_id)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS pvp_battles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        attacker_id INTEGER,
        defender_id INTEGER,
        chat_id INTEGER,
        winner_id INTEGER,
        reward_gold INTEGER,
        battle_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(attacker_id) REFERENCES players(user_id),
        FOREIGN KEY(defender_id) REFERENCES players(user_id)
    )
    """)

    c.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON players(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_level ON players(level)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_inventory_user ON inventory(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_battles_user ON battles(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_chat ON players(chat_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_pvp_confirmed ON pvp_queue(confirmed)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_pvp_chat_confirmed ON pvp_queue(chat_id, confirmed)")

    conn.commit()
    conn.close()
    logger.info("✅ База данных RuneQuestRPG инициализирована")

# ─────────────────────────────────────────────────────────────────────────────
# 👤 ФУНКЦИИ ИГРОКОВ
# ─────────────────────────────────────────────────────────────────────────────

@safe_db_execute
def init_player(chat_id: int, user_id: int, user_name: str, player_class: str) -> bool:
    conn = get_db()
    c = conn.cursor()
    try:
        class_info = CLASSES.get(player_class, CLASSES["warrior"])
        c.execute(
            """
            INSERT INTO players (
                user_id, chat_id, username, class,
                level, xp, health, max_health, mana, max_mana,
                attack, defense, gold, pet_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, chat_id, (user_name or "")[:50], player_class,
                1, 0,
                class_info["health"], class_info["health"],
                class_info["mana"], class_info["mana"],
                class_info["attack"], class_info["defense"],
                class_info["starting_gold"], "wolf",
            ),
        )

        c.execute(
            """
            INSERT INTO inventory (user_id, chat_id, item_id, item_type, quantity)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, chat_id, "health_potion", "potion", 3),
        )

        conn.commit()
        logger.info(f"✅ Игрок создан: {user_name} ({user_id}) - {player_class}")
        return True
    except sqlite3.IntegrityError:
        logger.warning(f"⚠️ Игрок {user_id} уже существует")
        return False
    finally:
        conn.close()

@safe_db_execute
def get_player(chat_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM players WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

@safe_db_execute
def player_exists(chat_id: int, user_id: int) -> bool:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT 1 FROM players WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
    exists = c.fetchone() is not None
    conn.close()
    return exists

@safe_db_execute
def add_xp(chat_id: int, user_id: int, username: str, xp_amount: int) -> int:
    player = get_player(chat_id, user_id)
    if not player:
        return 0

    new_xp = player["xp"] + xp_amount
    current_level = player["level"]
    levels_up = 0

    while current_level < MAX_LEVEL:
        xp_needed = int(LEVEL_UP_BASE * (current_level ** 1.5))
        if new_xp >= xp_needed:
            new_xp -= xp_needed
            current_level += 1
            levels_up += 1
        else:
            break

    conn = get_db()
    c = conn.cursor()

    if levels_up > 0:
        new_health = player["max_health"] + STATS_PER_LEVEL["health"] * levels_up
        new_mana = player["max_mana"] + STATS_PER_LEVEL["mana"] * levels_up
        new_attack = player["attack"] + STATS_PER_LEVEL["attack"] * levels_up
        new_defense = player["defense"] + STATS_PER_LEVEL["defense"] * levels_up

        c.execute(
            """
            UPDATE players SET
            xp = ?, level = ?,
            max_health = ?, health = ?,
            max_mana = ?, mana = ?,
            attack = ?, defense = ?
            WHERE user_id = ? AND chat_id = ?
            """,
            (new_xp, current_level, new_health, new_health, new_mana, new_mana, new_attack, new_defense, user_id, chat_id),
        )
        logger.info(f"📈 Игрок {username} повышен на уровень {current_level}")
    else:
        c.execute("UPDATE players SET xp = ? WHERE user_id = ? AND chat_id = ?", (new_xp, user_id, chat_id))

    conn.commit()
    conn.close()
    return levels_up

@safe_db_execute
def add_gold(chat_id: int, user_id: int, amount: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE players SET gold = gold + ? WHERE user_id = ? AND chat_id = ?", (amount, user_id, chat_id))
    conn.commit()
    conn.close()

@safe_db_execute
def subtract_gold(chat_id: int, user_id: int, amount: int) -> bool:
    player = get_player(chat_id, user_id)
    if not player or player["gold"] < amount:
        return False

    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE players SET gold = gold - ? WHERE user_id = ? AND chat_id = ?", (amount, user_id, chat_id))
    conn.commit()
    conn.close()
    return True

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
            elif item_id in MATERIALS:
                item_type = "material"
            elif item_id in PETS:
                item_type = "pet"
            elif item_id in RUNES:
                item_type = "rune"
            else:
                item_type = "misc"

            c.execute("INSERT INTO inventory (user_id, chat_id, item_id, item_type, quantity) VALUES (?, ?, ?, ?, ?)",
                     (user_id, chat_id, item_id, item_type, quantity))
        conn.commit()
    finally:
        conn.close()

@safe_db_execute
def remove_item(chat_id: int, user_id: int, item_id: str, quantity: int = 1) -> bool:
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT quantity FROM inventory WHERE user_id = ? AND chat_id = ? AND item_id = ?", (user_id, chat_id, item_id))
        row = c.fetchone()

        if not row or row["quantity"] < quantity:
            return False

        if row["quantity"] == quantity:
            c.execute("DELETE FROM inventory WHERE user_id = ? AND chat_id = ? AND item_id = ?", (user_id, chat_id, item_id))
        else:
            c.execute("UPDATE inventory SET quantity = quantity - ? WHERE user_id = ? AND chat_id = ? AND item_id = ?", (quantity, user_id, chat_id, item_id))

        conn.commit()
        return True
    finally:
        conn.close()

@safe_db_execute
def get_inventory(chat_id: int, user_id: int) -> List[Dict[str, Any]]:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM inventory WHERE user_id = ? AND chat_id = ? ORDER BY item_type, item_id", (user_id, chat_id))
    items = [dict(r) for r in c.fetchall()]
    conn.close()
    return items

@safe_db_execute
def get_material(chat_id: int, user_id: int, material_id: str) -> int:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT quantity FROM inventory WHERE user_id = ? AND chat_id = ? AND item_id = ?", (user_id, chat_id, material_id))
    row = c.fetchone()
    conn.close()
    return row["quantity"] if row else 0

@safe_db_execute
def can_use_item(player_class: str, item_id: str) -> bool:
    if item_id in WEAPONS:
        return WEAPONS[item_id].get("class") == player_class or WEAPONS[item_id].get("class") is None
    elif item_id in ARMOR:
        return ARMOR[item_id].get("class") == player_class or ARMOR[item_id].get("class") is None
    return True

@safe_db_execute
def equip_weapon(chat_id: int, user_id: int, weapon_id: str) -> bool:
    player = get_player(chat_id, user_id)
    if not player or weapon_id not in WEAPONS:
        return False

    if not can_use_item(player["class"], weapon_id):
        return False

    if get_material(chat_id, user_id, weapon_id) <= 0:
        return False

    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE players SET equipped_weapon = ? WHERE user_id = ? AND chat_id = ?", (weapon_id, user_id, chat_id))
    conn.commit()
    conn.close()
    return True

@safe_db_execute
def equip_armor(chat_id: int, user_id: int, armor_id: str) -> bool:
    player = get_player(chat_id, user_id)
    if not player or armor_id not in ARMOR:
        return False

    if not can_use_item(player["class"], armor_id):
        return False

    if get_material(chat_id, user_id, armor_id) <= 0:
        return False

    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE players SET equipped_armor = ? WHERE user_id = ? AND chat_id = ?", (armor_id, user_id, chat_id))
    conn.commit()
    conn.close()
    return True

@safe_db_execute
def buy_item(chat_id: int, user_id: int, item_id: str) -> bool:
    player = get_player(chat_id, user_id)
    if not player:
        return False

    price = 0
    if item_id in WEAPONS:
        if not can_use_item(player["class"], item_id):
            return False
        price = WEAPONS[item_id]["price"]
    elif item_id in ARMOR:
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

    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE players SET pet_id = ?, pet_level = 1 WHERE user_id = ? AND chat_id = ?", (pet_id, user_id, chat_id))
    conn.commit()
    conn.close()
    return True

# ─────────────────────────────────────────────────────────────────────────────
# ⚔️ БОЕВАЯ СИСТЕМА (ЛОКАЦИЯ-ЗАВИСИМАЯ)
# ─────────────────────────────────────────────────────────────────────────────

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

def get_player_battle_stats(player: Dict[str, Any]) -> Dict[str, int]:
    stats = {
        "attack": player["attack"],
        "defense": player["defense"],
        "crit_chance": CLASSES[player["class"]].get("crit_chance", 5),
        "spell_power": CLASSES[player["class"]].get("spell_power", 0),
    }

    if player["equipped_weapon"] and player["equipped_weapon"] in WEAPONS:
        weapon = WEAPONS[player["equipped_weapon"]]
        stats["attack"] += weapon["attack"]
        stats["crit_chance"] += weapon["crit"]

    if player["equipped_armor"] and player["equipped_armor"] in ARMOR:
        armor = ARMOR[player["equipped_armor"]]
        stats["defense"] += armor["defense"]

    if player["pet_id"] and player["pet_id"] in PETS:
        pet = PETS[player["pet_id"]]
        stats["attack"] += pet["attack_bonus"]
        stats["defense"] += pet["defense_bonus"]

    return stats

@safe_db_execute
def start_battle(chat_id: int, user_id: int, location_id: str):
    player = get_player(chat_id, user_id)
    if not player:
        return None

    location = LOCATIONS.get(location_id)
    if not location:
        return None

    if player["level"] < location["min_level"]:
        return {"error": f"❌ Требуется уровень {location['min_level']}-{location['max_level']}! Ты уровня {player['level']}"}

    if player["level"] > location["max_level"]:
        return {"error": f"❌ Эта локация слишком слаба для тебя! Требуется уровень {location['min_level']}-{location['max_level']}"}

    possible_enemies = location["enemies"]
    enemy_id = random.choice(possible_enemies)
    enemy_template = ENEMIES[enemy_id].copy()

    level_diff = max(1, player["level"] - enemy_template["level"])
    scale = 1.0 + level_diff * 0.12

    enemy_template["current_hp"] = int(enemy_template["hp"] * scale)
    enemy_template["scaled_damage"] = int(enemy_template["damage"] * scale)

    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        INSERT OR REPLACE INTO battles (
            user_id, chat_id, location_id, enemy_id, enemy_health, enemy_max_health,
            enemy_damage, is_boss, player_health, player_max_health
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, chat_id, location_id, enemy_id, enemy_template["current_hp"], int(enemy_template["hp"] * scale),
         enemy_template["scaled_damage"], int(enemy_template.get("boss", False)), player["health"], player["max_health"]),
    )

    conn.commit()
    conn.close()

    return {
        "enemy_id": enemy_id,
        "enemy_name": enemy_template["name"],
        "enemy_emoji": enemy_template["emoji"],
        "enemy_level": enemy_template["level"],
        "enemy_health": enemy_template["current_hp"],
        "enemy_max_health": int(enemy_template["hp"] * scale),
        "enemy_damage": enemy_template["scaled_damage"],
        "is_boss": enemy_template.get("boss", False),
    }

@safe_db_execute
def get_active_battle(chat_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM battles WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

@safe_db_execute
def end_battle(chat_id: int, user_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM battles WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
    conn.commit()
    conn.close()

@safe_db_execute
def perform_attack(chat_id: int, user_id: int) -> Dict[str, Any]:
    player = get_player(chat_id, user_id)
    battle = get_active_battle(chat_id, user_id)

    if not player or not battle:
        return {"success": False, "message": "❌ Бой не найден"}

    player_stats = get_player_battle_stats(player)
    damage, is_crit = calculate_damage(player_stats["attack"], 0, player_stats["crit_chance"], player_stats["spell_power"])

    new_enemy_hp = battle["enemy_health"] - damage

    result: Dict[str, Any] = {
        "success": True,
        "damage": damage,
        "is_crit": is_crit,
        "enemy_hp": max(0, new_enemy_hp),
        "enemy_max_hp": battle["enemy_max_health"],
        "enemy_defeated": new_enemy_hp <= 0,
    }

    if new_enemy_hp <= 0:
        end_battle(chat_id, user_id)
        enemy = ENEMIES[battle["enemy_id"]]

        xp_gained = enemy["xp"]
        gold_gained = enemy["gold"]

        if player["pet_id"] in PETS:
            xp_gained = int(xp_gained * PETS[player["pet_id"]]["xp_bonus"])

        add_gold(chat_id, user_id, gold_gained)
        levels_up = add_xp(chat_id, user_id, player["username"], xp_gained)

        result["xp_gained"] = xp_gained
        result["gold_gained"] = gold_gained
        result["levels_up"] = levels_up
        result["victory"] = True

        if random.randint(1, 100) <= 40 and enemy.get("loot"):
            loot_item = random.choice(enemy["loot"])
            add_item(chat_id, user_id, loot_item)
            result["loot"] = loot_item

        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE players SET total_kills = total_kills + 1, total_battles_won = total_battles_won + 1 WHERE user_id = ? AND chat_id = ?",
                 (user_id, chat_id))

        if enemy.get("boss"):
            c.execute("UPDATE players SET total_bosses_killed = total_bosses_killed + 1 WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))

        conn.commit()
        conn.close()
    else:
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE battles SET enemy_health = ? WHERE user_id = ? AND chat_id = ?", (new_enemy_hp, user_id, chat_id))
        conn.commit()
        conn.close()

        enemy_damage, _ = calculate_damage(battle["enemy_damage"], player["defense"], 5, 0)
        new_player_hp = player["health"] - enemy_damage

        result["enemy_damage"] = enemy_damage
        result["player_hp"] = max(0, new_player_hp)
        result["player_max_hp"] = player["max_health"]

        if new_player_hp <= 0:
            end_battle(chat_id, user_id)

            gold_lost = int(player["gold"] * 0.1)
            subtract_gold(chat_id, user_id, gold_lost)

            conn = get_db()
            c = conn.cursor()
            c.execute("UPDATE players SET health = max_health, total_battles_lost = total_battles_lost + 1 WHERE user_id = ? AND chat_id = ?",
                     (user_id, chat_id))
            conn.commit()
            conn.close()

            result["defeat"] = True
            result["gold_lost"] = gold_lost
        else:
            conn = get_db()
            c = conn.cursor()
            c.execute("UPDATE players SET health = ? WHERE user_id = ? AND chat_id = ?", (new_player_hp, user_id, chat_id))
            conn.commit()
            conn.close()

    return result

# ─────────────────────────────────────────────────────────────────────────────
# ⚔️ СИСТЕМА ПВП - ИСПРАВЛЕННАЯ (BUGFIX v5.2)
# ─────────────────────────────────────────────────────────────────────────────

@safe_db_execute
def add_pvp_queue(chat_id: int, user_id: int):
    """Добавить игрока в очередь ПВП"""
    conn = get_db()
    c = conn.cursor()

    try:
        c.execute(
            """
            INSERT OR REPLACE INTO pvp_queue (user_id, chat_id, is_waiting, confirmed, timestamp)
            VALUES (?, ?, 1, 0, CURRENT_TIMESTAMP)
            """,
            (user_id, chat_id)
        )
        conn.commit()
        logger.info(f"✅ Игрок {user_id} добавлен в очередь ПВП (chat_id={chat_id})")
    finally:
        conn.close()

@safe_db_execute
def confirm_pvp_search(chat_id: int, user_id: int):
    """Подтвердить поиск ПВП"""
    conn = get_db()
    c = conn.cursor()

    c.execute(
        "UPDATE pvp_queue SET confirmed = 1 WHERE user_id = ? AND chat_id = ?",
        (user_id, chat_id)
    )
    conn.commit()
    logger.info(f"✅ Игрок {user_id} подтвердил поиск ПВП (chat_id={chat_id})")
    conn.close()

@safe_db_execute
def cancel_pvp_search(chat_id: int, user_id: int):
    """Отменить поиск ПВП"""
    conn = get_db()
    c = conn.cursor()

    c.execute("DELETE FROM pvp_queue WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
    conn.commit()
    logger.info(f"✅ Игрок {user_id} отменил поиск ПВП (chat_id={chat_id})")
    conn.close()

@safe_db_execute
def get_pvp_queue_status(chat_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    """Получить статус игрока в очереди"""
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM pvp_queue WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
    row = c.fetchone()
    conn.close()

    return dict(row) if row else None

@safe_db_execute
def find_pvp_opponent(chat_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    """✅ ИСПРАВЛЕННОЕ - Найти противника из подтвердивших в той же локации"""
    player = get_player(chat_id, user_id)
    if not player:
        logger.warning(f"❌ Игрок {user_id} не найден")
        return None

    conn = get_db()
    c = conn.cursor()

    min_level = max(1, player["level"] - 5)
    max_level = player["level"] + 5

    # ✅ ИСПРАВКА: Ищем ТОЛЬКО в той же chat_id и ТОЛЬКО подтвердивших
    c.execute("""
        SELECT p.user_id, p.username, p.level, p.attack, p.defense, p.gold
        FROM players p
        JOIN pvp_queue q ON p.user_id = q.user_id
        WHERE p.chat_id = ?          -- ИСПРАВКА: ТА ЖЕ ЛОКАЦИЯ (chat_id)
          AND p.user_id != ? 
          AND p.level BETWEEN ? AND ?
          AND q.confirmed = 1        -- ИСПРАВКА: ТОЛЬКО ПОДТВЕРДИВШИЕ
          AND q.chat_id = ?          -- ИСПРАВКА: ОЧЕРЕДЬ В ТОЙ ЖЕ ЛОКАЦИИ
        ORDER BY RANDOM()
        LIMIT 1
    """, (chat_id, user_id, min_level, max_level, chat_id))

    opponent = c.fetchone()
    conn.close()

    if opponent:
        logger.info(f"🎉 Найден противник для {user_id}: {dict(opponent)['username']}")
    else:
        logger.info(f"❌ Противник не найден для {user_id} (chat_id={chat_id}, уровень {player['level']})")

    return dict(opponent) if opponent else None

@safe_db_execute
def pvp_battle(chat_id: int, attacker_id: int, defender_id: int) -> Dict[str, Any]:
    """Провести ПВП бой между двумя игроками"""
    attacker = get_player(chat_id, attacker_id)
    defender = get_player(chat_id, defender_id)

    if not attacker or not defender:
        return {"success": False, "message": "❌ Игроки не найдены"}

    attacker_stats = get_player_battle_stats(attacker)
    defender_stats = get_player_battle_stats(defender)

    # РАУНД 1: Атакующий наносит урон
    attacker_damage, attacker_crit = calculate_damage(
        attacker_stats["attack"],
        defender_stats["defense"],
        attacker_stats["crit_chance"],
        attacker_stats["spell_power"]
    )

    defender_new_hp = defender["health"] - attacker_damage

    # РАУНД 2: Если защитник жив, он контратакует
    if defender_new_hp > 0:
        defender_damage, defender_crit = calculate_damage(
            defender_stats["attack"],
            attacker_stats["defense"],
            defender_stats["crit_chance"],
            defender_stats["spell_power"]
        )

        attacker_new_hp = attacker["health"] - defender_damage
    else:
        defender_damage = 0
        defender_crit = False
        attacker_new_hp = attacker["health"]

    # Определяем победителя
    if defender_new_hp <= 0:
        winner_id = attacker_id
        reward_gold = int(defender["gold"] * 0.1)
    elif attacker_new_hp <= 0:
        winner_id = defender_id
        reward_gold = int(attacker["gold"] * 0.1)
    else:
        if defender_new_hp > attacker_new_hp:
            winner_id = defender_id
            reward_gold = int(attacker["gold"] * 0.05)
        else:
            winner_id = attacker_id
            reward_gold = int(defender["gold"] * 0.05)

    # Сохраняем результат
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        INSERT INTO pvp_battles (attacker_id, defender_id, chat_id, winner_id, reward_gold)
        VALUES (?, ?, ?, ?, ?)
    """, (attacker_id, defender_id, chat_id, winner_id, reward_gold))

    # Обновляем статистику
    c.execute("UPDATE players SET pvp_wins = pvp_wins + 1, gold = gold + ? WHERE user_id = ? AND chat_id = ?",
             (reward_gold, winner_id, chat_id))
    c.execute("UPDATE players SET pvp_losses = pvp_losses + 1, health = max_health WHERE user_id = ? AND chat_id = ?",
             (attacker_id if winner_id == defender_id else defender_id, chat_id))

    # Удаляем обоих из очереди
    c.execute("DELETE FROM pvp_queue WHERE user_id IN (?, ?) AND chat_id = ?", (attacker_id, defender_id, chat_id))

    conn.commit()
    conn.close()

    logger.info(f"⚔️ ПВП Бой: {attacker['username']} vs {defender['username']}, победитель: {winner_id}")

    return {
        "success": True,
        "attacker_damage": attacker_damage,
        "attacker_crit": attacker_crit,
        "defender_damage": defender_damage,
        "defender_crit": defender_crit,
        "winner_id": winner_id,
        "winner_name": attacker["username"] if winner_id == attacker_id else defender["username"],
        "loser_name": defender["username"] if winner_id == attacker_id else attacker["username"],
        "reward_gold": reward_gold,
    }

# ─────────────────────────────────────────────────────────────────────────────
# 🏆 ПОДЗЕМЕЛЬЕ, ЛИДЕРБОРДЫ И КРАФТ
# ─────────────────────────────────────────────────────────────────────────────

@safe_db_execute
def start_dungeon(chat_id: int, user_id: int):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM dungeon_progress WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
    row = c.fetchone()

    if row and row["is_active"]:
        conn.close()
        return None

    player = get_player(chat_id, user_id)
    if not player:
        conn.close()
        return None

    floor = 1
    if not row:
        c.execute("INSERT INTO dungeon_progress (user_id, chat_id, current_floor, is_active) VALUES (?, ?, ?, 1)",
                 (user_id, chat_id, floor))
    else:
        floor = row["current_floor"]
        c.execute("UPDATE dungeon_progress SET is_active = 1 WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))

    conn.commit()
    conn.close()

    enemy_id = random.choice(list(ENEMIES.keys()))
    enemy_template = ENEMIES[enemy_id].copy()

    scale = 1.0 + (floor * 0.15)
    enemy_template["current_hp"] = int(enemy_template["hp"] * scale)
    enemy_template["scaled_damage"] = int(enemy_template["damage"] * scale)

    return {
        "floor": floor,
        "enemy_id": enemy_id,
        "enemy_name": enemy_template["name"],
        "enemy_emoji": enemy_template["emoji"],
        "enemy_health": enemy_template["current_hp"],
        "enemy_max_health": enemy_template["current_hp"],
        "enemy_damage": enemy_template["scaled_damage"],
    }

@safe_db_execute
def end_dungeon(chat_id: int, user_id: int, is_victory: bool = False):
    conn = get_db()
    c = conn.cursor()

    if is_victory:
        c.execute("""
            UPDATE dungeon_progress 
            SET current_floor = current_floor + 1, enemies_killed = enemies_killed + 1, is_active = 1
            WHERE user_id = ? AND chat_id = ?
        """, (user_id, chat_id))
    else:
        c.execute(
            "SELECT current_floor FROM dungeon_progress WHERE user_id = ? AND chat_id = ?", 
            (user_id, chat_id)
        )
        row = c.fetchone()

        if row and row["current_floor"] > 1:
            player = get_player(chat_id, user_id)
            if player:
                c.execute("""
                    UPDATE players SET dungeon_rating = ? WHERE user_id = ? AND chat_id = ?
                """, (row["current_floor"], user_id, chat_id))

        c.execute("UPDATE dungeon_progress SET current_floor = 1, is_active = 0 WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))

    conn.commit()
    conn.close()

@safe_db_execute
def get_global_leaderboard(chat_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT user_id, username, level, gold, total_kills, total_bosses_killed,
               total_battles_won, total_battles_lost, pvp_wins, pvp_losses
        FROM players 
        WHERE chat_id = ? 
        ORDER BY level DESC, gold DESC, total_kills DESC
        LIMIT ?
    """, (chat_id, limit))

    data = [dict(r) for r in c.fetchall()]
    conn.close()
    return data

@safe_db_execute
def get_pvp_leaderboard(chat_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT username, level, pvp_wins, pvp_losses,
               CASE WHEN (pvp_wins + pvp_losses) > 0 
                    THEN ROUND(100.0 * pvp_wins / (pvp_wins + pvp_losses), 2)
                    ELSE 0 END as win_rate
        FROM players 
        WHERE chat_id = ? AND (pvp_wins + pvp_losses) > 0
        ORDER BY pvp_wins DESC, win_rate DESC
        LIMIT ?
    """, (chat_id, limit))

    data = [dict(r) for r in c.fetchall()]
    conn.close()
    return data

@safe_db_execute
def get_dungeon_leaderboard(chat_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT username, level, dungeon_rating, total_bosses_killed
        FROM players 
        WHERE chat_id = ? AND dungeon_rating > 0
        ORDER BY dungeon_rating DESC, total_bosses_killed DESC
        LIMIT ?
    """, (chat_id, limit))

    data = [dict(r) for r in c.fetchall()]
    conn.close()
    return data

@safe_db_execute
def get_player_position(chat_id: int, user_id: int) -> int:
    player = get_player(chat_id, user_id)
    if not player:
        return 0

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT COUNT(*) AS pos FROM players 
        WHERE chat_id = ? AND (level > ? OR (level = ? AND gold > ?))
    """, (chat_id, player["level"], player["level"], player["gold"]))

    row = c.fetchone()
    conn.close()

    return int(row["pos"]) + 1 if row else 1

@safe_db_execute
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
        have = get_material(chat_id, user_id, material)
        if have < needed:
            material_name = MATERIALS.get(material, {}).get("name", material)
            return {"success": False, "message": f"❌ Недостаточно {material_name}"}

    for material, needed in recipe["materials"].items():
        remove_item(chat_id, user_id, material, needed)

    subtract_gold(chat_id, user_id, recipe["gold"])
    add_item(chat_id, user_id, recipe["result"])

    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE players SET craft_count = craft_count + 1 WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
    conn.commit()
    conn.close()

    return {"success": True, "item": recipe["result"], "name": recipe["name"]}

# ─────────────────────────────────────────────────────────────────────────────
# 🎯 TELEGRAM HANDLERS
# ─────────────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    user_id = user.id
    chat_id = chat.id

    if player_exists(chat_id, user_id):
        await show_main_menu(update, context)
        return

    text = f"""
🎮 Добро пожаловать в RuneQuestRPG, {user.first_name}!

⚔️ ВЫБЕРИ СВОЙ КЛАСС:

🛡️ ВОИН (HP: 120 | Атака: 15 | Защита: 8)
🔥 МАГ (HP: 70 | Атака: 8 | Защита: 3 | Магия: 25)
🗡️ РАЗБОЙНИК (HP: 85 | Атака: 19 | Защита: 5 | Крит: 22%)
⛪ ПАЛАДИН (HP: 140 | Атака: 13 | Защита: 15)
🏹 РЕЙНДЖЕР (HP: 95 | Атака: 17 | Защита: 6)
💀 НЕКРОМАНТ (HP: 80 | Атака: 10 | Защита: 4 | Магия: 30)
    """

    keyboard = [
        [InlineKeyboardButton("⚔️ Воин", callback_data="class_warrior"), InlineKeyboardButton("🔥 Маг", callback_data="class_mage")],
        [InlineKeyboardButton("🗡️ Разбойник", callback_data="class_rogue"), InlineKeyboardButton("⛪ Паладин", callback_data="class_paladin")],
        [InlineKeyboardButton("🏹 Рейнджер", callback_data="class_ranger"), InlineKeyboardButton("💀 Некромант", callback_data="class_necromancer")],
    ]

    if update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def select_class(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    user_id = user.id
    chat_id = chat.id

    class_name = query.data.replace("class_", "")
    created = init_player(chat_id, user_id, user.username or user.first_name, class_name)

    if not created:
        await query.answer("❌ Ошибка создания персонажа", show_alert=True)
        return

    class_info = CLASSES[class_name]
    text = f"""
✅ ТЫ ВЫБРАЛ КЛАСС!

{class_info['emoji']} {class_info['name'].upper()}

{class_info['description']}

📊 ХАРАКТЕРИСТИКИ:

❤️ HP: {class_info['health']}
💙 Мана: {class_info['mana']}
⚔️ Атака: {class_info['attack']}
🛡️ Защита: {class_info['defense']}
💥 Крит: {class_info['crit_chance']}%
💰 Золото: {class_info['starting_gold']}

🎮 Приключение начинается!
    """

    keyboard = [[InlineKeyboardButton("🎮 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

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
    pet = PETS.get(player["pet_id"], PETS["wolf"])

    text = f"""
🎮 RUNEQUESTRPG - ГЛАВНОЕ МЕНЮ

👤 {user.first_name}

{class_info['emoji']} Класс: {class_info['name']}

⭐ Уровень: {player['level']}/{MAX_LEVEL} | XP: {player['xp']}

❤️ HP: {player['health']}/{player['max_health']} | 💙 Мана: {player['mana']}/{player['max_mana']}

💰 Золото: {player['gold']}

🐾 Питомец: {pet['emoji']} {pet['name']} (Ур. {player['pet_level']})

🏆 Рейтинг подземелья: {player['dungeon_rating']}
    """

    keyboard = [
        [InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data="profile"), InlineKeyboardButton("🎒 ИНВЕНТАРЬ", callback_data="inventory")],
        [InlineKeyboardButton("⚔️ БОЙ", callback_data="locations_list"), InlineKeyboardButton("🏰 ЛОКАЦИИ", callback_data="locations_list")],
        [InlineKeyboardButton("🛍️ МАГАЗИН", callback_data="shop"), InlineKeyboardButton("⚙️ ЭКИПИРОВКА", callback_data="equipment")],
        [InlineKeyboardButton("🔨 КРАФТ", callback_data="crafting"), InlineKeyboardButton("🏆 ПОДЗЕМЕЛЬЕ", callback_data="dungeon")],
        [InlineKeyboardButton("⚔️ ПВП", callback_data="pvp_menu"), InlineKeyboardButton("📊 РЕЙТИНГИ", callback_data="ratings")],
    ]

    if query:
        try:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        except TelegramError as e:
            if "not modified" in str(e).lower():
                pass  # ✅ BUGFIX: Игнорируем ошибку если сообщение не изменилось
            else:
                raise
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

    pet = PETS.get(player["pet_id"], PETS["wolf"])
    battle_stats = get_player_battle_stats(player)

    text = f"""
👤 ПРОФИЛЬ ГЕРОЯ

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

⚔️ Побед: {player['total_kills']}
👹 Боссов убито: {player['total_bosses_killed']}
🎖️ Боев выиграно: {player['total_battles_won']}
📉 Боев проиграно: {player['total_battles_lost']}

⚔️ ПВП Побед: {player['pvp_wins']}
📉 ПВП Поражений: {player['pvp_losses']}
    """

    keyboard = [[InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]]
    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

async def show_inventory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    inventory = get_inventory(chat.id, user.id)

    if not inventory:
        text = "🎒 ИНВЕНТАРЬ\n\n❌ Инвентарь пуст"
    else:
        text = "🎒 ИНВЕНТАРЬ\n\n"

        for item in inventory:
            iid = item["item_id"]
            qty = item['quantity']

            if iid in WEAPONS:
                w = WEAPONS[iid]
                text += f"⚔️ {w['name']} x{qty}\n"
            elif iid in ARMOR:
                a = ARMOR[iid]
                text += f"🛡️ {a['name']} x{qty}\n"
            elif iid in MATERIALS:
                m = MATERIALS[iid]
                text += f"📦 {m['name']} x{qty}\n"
            elif iid in PETS:
                p = PETS[iid]
                text += f"🐾 {p['emoji']} {p['name']} x{qty}\n"
            else:
                text += f"📦 {iid} x{qty}\n"

    keyboard = [[InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]]
    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

async def show_locations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    player = get_player(chat.id, user.id)

    if not player:
        await query.answer("❌ Игрок не найден", show_alert=True)
        return

    text = "🏰 ВЫБЕРИ ЛОКАЦИЮ:\n\n"
    keyboard = []

    for loc_id, loc in LOCATIONS.items():
        if player["level"] < loc["min_level"]:
            status = "🔒"
        elif player["level"] > loc["max_level"]:
            status = "⚠️"
        else:
            status = "✅"

        text += f"{status} {loc['emoji']} {loc['name']} (Ур. {loc['min_level']}-{loc['max_level']})\n"

        keyboard.append([InlineKeyboardButton(
            f"{status} {loc['emoji']} {loc['name']}", 
            callback_data=f"location_select_{loc_id}"
        )])

    keyboard.append([InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")])

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

async def select_location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    if player["level"] < location["min_level"]:
        await query.answer(f"❌ Требуется уровень {location['min_level']}-{location['max_level']}! Ты уровня {player['level']}", show_alert=True)
        return

    if player["level"] > location["max_level"]:
        await query.answer(f"⚠️ Эта локация слишком слаба для тебя! Требуется уровень {location['min_level']}-{location['max_level']}", show_alert=True)
        return

    text = f"""
{location['emoji']} {location['name'].upper()}

{location['description']}

Рек. уровень: {location['min_level']}-{location['max_level']}
Твой уровень: {player['level']}

✅ ГОТОВ!

Враги:
    """

    for enemy_id in location["enemies"]:
        enemy = ENEMIES[enemy_id]
        text += f"{enemy['emoji']} {enemy['name']} (Ур. {enemy['level']})\n"

    keyboard = [
        [InlineKeyboardButton("⚔️ НАЧАТЬ БОЙ", callback_data=f"fight_{location_id}")],
        [InlineKeyboardButton("⬅️ НАЗАД", callback_data="locations_list")],
    ]

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

async def start_fight_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    location_id = query.data.replace("fight_", "")

    if get_active_battle(chat.id, user.id):
        await query.answer("⚠️ Ты уже в бою!", show_alert=True)
        return

    player = get_player(chat.id, user.id)

    if not player:
        await query.answer("❌ Игрок не найден", show_alert=True)
        return

    enemy = start_battle(chat.id, user.id, location_id)

    if not enemy:
        await query.answer("❌ Не удалось начать бой", show_alert=True)
        return

    if "error" in enemy:
        await query.answer(enemy["error"], show_alert=True)
        return

    text = f"""
⚔️ БОЙ НАЧАЛСЯ!

Противник: {enemy['enemy_emoji']} {enemy['enemy_name']} (Ур. {enemy['enemy_level']})

❤️ Враг HP: {enemy['enemy_health']}/{enemy['enemy_max_health']}

⚔️ Враг урон: {enemy['enemy_damage']}

{'👹 БОСС' if enemy['is_boss'] else ''}

Твои характеристики:

❤️ HP: {player['health']}/{player['max_health']}

⚔️ Атака: {player['attack']}

🛡️ Защита: {player['defense']}
    """

    keyboard = [
        [InlineKeyboardButton("⚔️ АТАКОВАТЬ", callback_data="attack")],
        [InlineKeyboardButton("🧪 ЗЕЛЬЕ", callback_data="use_potion")],
        [InlineKeyboardButton("🏃 СБЕЖАТЬ", callback_data="escape"), InlineKeyboardButton("❌ СДАТЬСЯ", callback_data="surrender")],
    ]

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    player = get_player(chat.id, user.id)

    if not player:
        await query.answer("❌ Игрок не найден", show_alert=True)
        return

    battle_result = perform_attack(chat.id, user.id)

    if not battle_result.get("success"):
        await query.answer(battle_result.get("message", "❌ Ошибка"), show_alert=True)
        return

    text = f"""
⚔️ БОЙ

Твоя атака: {("💥" if battle_result['is_crit'] else "")} {battle_result['damage']} урона

{("✨ КРИТ!" if battle_result['is_crit'] else "")}

❤️ Враг HP: {battle_result['enemy_hp']}/{battle_result['enemy_max_hp']}
    """

    if battle_result.get("victory"):
        text += f"""

🎉 ПОБЕДА!

⭐ Опыт: +{battle_result.get('xp_gained', 0)}

💰 Золото: +{battle_result.get('gold_gained', 0)}
        """

        if battle_result.get("loot"):
            loot_info = MATERIALS.get(battle_result["loot"], {})
            text += f"🎁 Лут: {loot_info.get('name', 'Неизвестно')}\n"

        if battle_result.get("levels_up", 0) > 0:
            text += f"\n🆙 +{battle_result['levels_up']} ур!"

        keyboard = [[InlineKeyboardButton("🎮 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]]

    elif battle_result.get("defeat"):
        text += f"""

💀 ПОРАЖЕНИЕ!

Потеряно золота: -{battle_result.get('gold_lost', 0)}
        """

        keyboard = [[InlineKeyboardButton("🎮 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]]

    else:
        enemy_damage = battle_result.get("enemy_damage", 0)
        player_hp = battle_result.get("player_hp", 0)
        player_max_hp = battle_result.get("player_max_hp", 0)

        text += f"""

👹 Враг атакует: {enemy_damage} урона

❤️ Твой HP: {player_hp}/{player_max_hp}
        """

        keyboard = [
            [InlineKeyboardButton("⚔️ АТАКОВАТЬ", callback_data="attack")],
            [InlineKeyboardButton("🧪 ЗЕЛЬЕ", callback_data="use_potion")],
            [InlineKeyboardButton("🏃 СБЕЖАТЬ", callback_data="escape"), InlineKeyboardButton("❌ СДАТЬСЯ", callback_data="surrender")],
        ]

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

async def use_potion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    player = get_player(chat.id, user.id)
    battle = get_active_battle(chat.id, user.id)

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

    enemy_damage, _ = calculate_damage(battle["enemy_damage"], player["defense"], 5, 0)
    new_player_hp = new_hp - enemy_damage

    text = f"""
🧪 ЗЕЛЬЕ ИСПОЛЬЗОВАНО!

💚 +{heal_amount} HP

❤️ Твой HP: {new_hp}/{player['max_health']}

👹 Враг наносит: {enemy_damage} урона

❤️ Твой HP: {max(0, new_player_hp)}/{player['max_health']}
    """

    if new_player_hp <= 0:
        text += "\n💀 ПОРАЖЕНИЕ!"
        keyboard = [[InlineKeyboardButton("🎮 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]]
        end_battle(chat.id, user.id)

        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE players SET health = max_health, total_battles_lost = total_battles_lost + 1 WHERE user_id = ? AND chat_id = ?", (user.id, chat.id))
        conn.commit()
        conn.close()
    else:
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE players SET health = ? WHERE user_id = ? AND chat_id = ?", (new_player_hp, user.id, chat.id))
        conn.commit()
        conn.close()

        keyboard = [
            [InlineKeyboardButton("⚔️ АТАКОВАТЬ", callback_data="attack")],
            [InlineKeyboardButton("🧪 ЗЕЛЬЕ", callback_data="use_potion")],
            [InlineKeyboardButton("🏃 СБЕЖАТЬ", callback_data="escape"), InlineKeyboardButton("❌ СДАТЬСЯ", callback_data="surrender")],
        ]

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

async def escape(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    player = get_player(chat.id, user.id)
    battle = get_active_battle(chat.id, user.id)

    if not player or not battle:
        await query.answer("❌ Бой не найден", show_alert=True)
        return

    if random.randint(1, 100) <= 50:
        end_battle(chat.id, user.id)

        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE players SET health = max_health WHERE user_id = ? AND chat_id = ?", (user.id, chat.id))
        conn.commit()
        conn.close()

        text = "🏃 УСПЕШНО СБЕЖАЛ!\n\nHP восстановлен."
        keyboard = [[InlineKeyboardButton("🎮 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]]
    else:
        enemy_damage, _ = calculate_damage(battle["enemy_damage"], player["defense"], 5, 0)
        new_player_hp = player["health"] - enemy_damage

        text = f"""
❌ ПОБЕГ НЕ УДАЛСЯ!

Враг наносит: {enemy_damage} урона

❤️ Твой HP: {max(0, new_player_hp)}/{player['max_health']}
        """

        if new_player_hp <= 0:
            text += "\n💀 ПОРАЖЕНИЕ!"
            end_battle(chat.id, user.id)
            keyboard = [[InlineKeyboardButton("🎮 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]]

            conn = get_db()
            c = conn.cursor()
            c.execute("UPDATE players SET health = max_health, total_battles_lost = total_battles_lost + 1 WHERE user_id = ? AND chat_id = ?", (user.id, chat.id))
            conn.commit()
            conn.close()
        else:
            conn = get_db()
            c = conn.cursor()
            c.execute("UPDATE players SET health = ? WHERE user_id = ? AND chat_id = ?", (new_player_hp, user.id, chat.id))
            conn.commit()
            conn.close()

            keyboard = [
                [InlineKeyboardButton("⚔️ АТАКОВАТЬ", callback_data="attack")],
                [InlineKeyboardButton("🧪 ЗЕЛЬЕ", callback_data="use_potion")],
                [InlineKeyboardButton("🏃 СБЕЖАТЬ", callback_data="escape"), InlineKeyboardButton("❌ СДАТЬСЯ", callback_data="surrender")],
            ]

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

async def surrender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    end_battle(chat.id, user.id)

    text = "🏳️ ТЫ СДАЛСЯ\n\nПоле боя покинуто."
    keyboard = [[InlineKeyboardButton("🎮 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]]

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

# ─────────────────────────────────────────────────────────────────────────────
# 🛍️ МАГАЗИН, ЭКИПИРОВКА И ОСТАЛЬНОЕ
# ─────────────────────────────────────────────────────────────────────────────

async def show_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    player = get_player(chat.id, user.id)

    text = f"""
🛍️ МАГАЗИН

Твой класс: {CLASSES[player['class']]['emoji']} {CLASSES[player['class']]['name']}

⚠️ Покупай только предметы для своего класса!

Выбери категорию:

⚔️ Оружие
🛡️ Броня
🐾 Питомцы
🔮 Руны
    """

    keyboard = [
        [InlineKeyboardButton("⚔️ ОРУЖИЕ", callback_data="shop_weapons"), InlineKeyboardButton("🛡️ БРОНЯ", callback_data="shop_armor")],
        [InlineKeyboardButton("🐾 ПИТОМЦЫ", callback_data="shop_pets"), InlineKeyboardButton("🔮 РУНЫ", callback_data="shop_runes")],
        [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")],
    ]

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

async def show_weapons_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    player = get_player(chat.id, user.id)

    text = f"🛍️ МАГАЗИН - ОРУЖИЕ ({CLASSES[player['class']]['name']})\n\n"

    keyboard = []
    for weapon_id, weapon_info in WEAPONS.items():
        if weapon_info.get("class") and weapon_info["class"] != player["class"]:
            continue

        text += f"{weapon_info['emoji']} {weapon_info['name']} - ⚔️ +{weapon_info['attack']} | 💰 {weapon_info['price']}\n"

        can_afford = player["gold"] >= weapon_info["price"]
        status = "✅" if can_afford else "❌"

        keyboard.append([InlineKeyboardButton(f"{status} {weapon_info['emoji']} {weapon_info['name']}", 
                                           callback_data=f"buy_weapon_{weapon_id}")])

    keyboard.append([InlineKeyboardButton("⬅️ НАЗАД", callback_data="shop")])

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

async def show_armor_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    player = get_player(chat.id, user.id)

    text = f"🛍️ МАГАЗИН - БРОНЯ ({CLASSES[player['class']]['name']})\n\n"

    keyboard = []
    for armor_id, armor_info in ARMOR.items():
        if armor_info.get("class") and armor_info["class"] != player["class"]:
            continue

        text += f"{armor_info['emoji']} {armor_info['name']} - 🛡️ +{armor_info['defense']} | ❤️ +{armor_info['health']} | 💰 {armor_info['price']}\n"

        can_afford = player["gold"] >= armor_info["price"]
        status = "✅" if can_afford else "❌"

        keyboard.append([InlineKeyboardButton(f"{status} {armor_info['emoji']} {armor_info['name']}", 
                                           callback_data=f"buy_armor_{armor_id}")])

    keyboard.append([InlineKeyboardButton("⬅️ НАЗАД", callback_data="shop")])

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

async def show_pets_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    player = get_player(chat.id, user.id)

    text = "🛍️ МАГАЗИН - ПИТОМЦЫ\n\n"

    keyboard = []
    for pet_id, pet_info in PETS.items():
        text += f"{pet_info['emoji']} {pet_info['name']} - ⚔️ +{pet_info['attack_bonus']} | 🛡️ +{pet_info['defense_bonus']} | ✨ x{pet_info['xp_bonus']} XP | 💰 {pet_info['price']}\n"

        can_afford = player["gold"] >= pet_info["price"]
        status = "✅" if can_afford else "❌"

        keyboard.append([InlineKeyboardButton(f"{status} {pet_info['emoji']} {pet_info['name']}", 
                                           callback_data=f"buy_pet_{pet_id}")])

    keyboard.append([InlineKeyboardButton("⬅️ НАЗАД", callback_data="shop")])

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

async def show_runes_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    player = get_player(chat.id, user.id)

    text = "🛍️ МАГАЗИН - РУНЫ\n\n"

    keyboard = []
    for rune_id, rune_info in RUNES.items():
        text += f"{rune_info['emoji']} {rune_info['name']} ({rune_info['type']}) | 💰 {rune_info['price']}\n"

        can_afford = player["gold"] >= rune_info["price"]
        status = "✅" if can_afford else "❌"

        keyboard.append([InlineKeyboardButton(f"{status} {rune_info['emoji']} {rune_info['name']}", 
                                           callback_data=f"buy_rune_{rune_id}")])

    keyboard.append([InlineKeyboardButton("⬅️ НАЗАД", callback_data="shop")])

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

async def buy_weapon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    weapon_id = query.data.replace("buy_weapon_", "")

    if weapon_id not in WEAPONS:
        await query.answer("❌ Оружие не найдено", show_alert=True)
        return

    player = get_player(chat.id, user.id)
    if not can_use_item(player["class"], weapon_id):
        await query.answer("❌ Это оружие не для твоего класса!", show_alert=True)
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
    if not can_use_item(player["class"], armor_id):
        await query.answer("❌ Эта броня не для твоего класса!", show_alert=True)
        return

    if buy_item(chat.id, user.id, armor_id):
        armor = ARMOR[armor_id]
        await query.answer(f"✅ Куплено: {armor['name']}", show_alert=True)
        await show_armor_shop(update, context)
    else:
        await query.answer("❌ Недостаточно золота", show_alert=True)

async def buy_pet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    pet_id = query.data.replace("buy_pet_", "")

    if pet_id not in PETS:
        await query.answer("❌ Питомец не найден", show_alert=True)
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

    if buy_item(chat.id, user.id, rune_id):
        rune = RUNES[rune_id]
        await query.answer(f"✅ Куплено: {rune['name']}", show_alert=True)
        await show_runes_shop(update, context)
    else:
        await query.answer("❌ Недостаточно золота", show_alert=True)

async def show_equipment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    player = get_player(chat.id, user.id)
    inventory = get_inventory(chat.id, user.id)

    weapons_in_inv = [item for item in inventory if item["item_id"] in WEAPONS]
    armor_in_inv = [item for item in inventory if item["item_id"] in ARMOR]

    text = "⚙️ ЭКИПИРОВКА\n\n"

    if player["equipped_weapon"]:
        weapon = WEAPONS.get(player["equipped_weapon"])
        text += f"⚔️ Вооружение: {weapon['emoji']} {weapon['name']} (+{weapon['attack']})\n"
    else:
        text += "⚔️ Вооружение: Не экипировано\n"

    if player["equipped_armor"]:
        armor = ARMOR.get(player["equipped_armor"])
        text += f"🛡️ Броня: {armor['emoji']} {armor['name']} (+{armor['defense']})\n"
    else:
        text += "🛡️ Броня: Не экипирована\n"

    text += "\n🐾 Питомец: "
    pet = PETS.get(player["pet_id"])
    text += f"{pet['emoji']} {pet['name']}\n"

    keyboard = []

    if weapons_in_inv:
        text += "\n⚔️ ОРУЖИЕ В ИНВЕНТАРЕ:\n"
        for weapon in weapons_in_inv:
            w = WEAPONS[weapon["item_id"]]
            text += f"{w['emoji']} {w['name']}\n"
            keyboard.append([InlineKeyboardButton(f"⚔️ {w['name']}", callback_data=f"equip_weapon_{weapon['item_id']}")])

    if armor_in_inv:
        text += "\n🛡️ БРОНЯ В ИНВЕНТАРЕ:\n"
        for armor in armor_in_inv:
            a = ARMOR[armor["item_id"]]
            text += f"{a['emoji']} {a['name']}\n"
            keyboard.append([InlineKeyboardButton(f"🛡️ {a['name']}", callback_data=f"equip_armor_{armor['item_id']}")])

    keyboard.append([InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")])

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

async def equip_weapon_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    weapon_id = query.data.replace("equip_weapon_", "")

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

    if equip_armor(chat.id, user.id, armor_id):
        armor = ARMOR[armor_id]
        await query.answer(f"✅ Экипировано: {armor['name']}", show_alert=True)
        await show_equipment(update, context)
    else:
        await query.answer("❌ Не удалось экипировать", show_alert=True)

async def crafting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    text = "🔨 КРАФТИНГ\n\nВыбери рецепт:"
    keyboard = []

    for recipe_id, recipe in list(CRAFTING_RECIPES.items()):
        keyboard.append([InlineKeyboardButton(f"{recipe['emoji']} {recipe['name']}", callback_data=f"craft_{recipe_id}")])

    keyboard.append([InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")])

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

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

    text = f"🔨 СОЗДАНИЕ: {recipe['emoji']} {recipe['name']}\n\nТребуется:\n"

    has_all = True

    for material, needed in recipe["materials"].items():
        have = get_material(chat.id, user.id, material)
        material_info = MATERIALS[material]
        status = "✅" if have >= needed else "❌"
        text += f"{status} {material_info['emoji']} {material_info['name']} ({have}/{needed})\n"

        if have < needed:
            has_all = False

    gold_ok = player["gold"] >= recipe["gold"]
    level_ok = player["level"] >= recipe["level"]

    text += f"💰 Золото: {'✅' if gold_ok else '❌'} ({player['gold']}/{recipe['gold']})\n"
    text += f"⭐ Уровень: {'✅' if level_ok else '❌'} ({player['level']}/{recipe['level']})\n"

    if has_all and gold_ok and level_ok:
        keyboard = [
            [InlineKeyboardButton("✅ СОЗДАТЬ", callback_data=f"craft_confirm_{recipe_id}")],
            [InlineKeyboardButton("⬅️ НАЗАД", callback_data="crafting")],
        ]
    else:
        keyboard = [[InlineKeyboardButton("⬅️ НАЗАД", callback_data="crafting")]]

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

async def craft_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    recipe_id = query.data.replace("craft_confirm_", "")
    result = craft_item(chat.id, user.id, recipe_id)

    if not result["success"]:
        await query.answer(result["message"], show_alert=True)
        return

    text = f"✅ СОЗДАНО!\n\n🎁 {result['name']} добавлен в инвентарь."
    keyboard = [[InlineKeyboardButton("🔨 НАЗАД К КРАФТУ", callback_data="crafting")]]

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

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
    c.execute("SELECT current_floor, is_active FROM dungeon_progress WHERE user_id = ? AND chat_id = ?", (user.id, chat.id))
    dungeon = c.fetchone()
    conn.close()

    floor = dict(dungeon)["current_floor"] if dungeon else 1
    is_active = dict(dungeon)["is_active"] if dungeon else False

    text = f"""
🏆 РЕЙТИНГОВОЕ ПОДЗЕМЕЛЬЕ

Бесконечное подземелье с нарастающей сложностью.

Враги становятся сильнее с каждым этажом.

📊 Текущий этаж: {floor}

🎯 Твой рекорд: Этаж {player['dungeon_rating']}

⚠️ При смерти ты выкинут на первый этаж!

Готов?
    """

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

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

async def show_ratings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    text = """
📊 ТАБЛИЦЫ ЛИДЕРОВ

Выбери таблицу:

🏆 Глобальный рейтинг
⚔️ ПВП рейтинг
🌋 Рейтинг подземелья
    """

    keyboard = [
        [InlineKeyboardButton("🏆 ГЛОБАЛЬНЫЙ", callback_data="rating_global"), InlineKeyboardButton("⚔️ ПВП", callback_data="rating_pvp")],
        [InlineKeyboardButton("🌋 ПОДЗЕМЕЛЬЕ", callback_data="rating_dungeon")],
        [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")],
    ]

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

async def show_global_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    leaders = get_global_leaderboard(chat.id, 10)
    player_position = get_player_position(chat.id, user.id)
    player = get_player(chat.id, user.id)

    text = "🏆 ГЛОБАЛЬНЫЙ РЕЙТИНГ 🏆\n\n"

    for i, leader in enumerate(leaders, 1):
        if i == 1:
            medal = "👑"
        elif i == 2:
            medal = "🥈"
        elif i == 3:
            medal = "🥉"
        else:
            medal = f"{i}."

        text += f"{medal} {leader['username']} - Ур. {leader['level']} | 💰 {leader['gold']}\n"

    if player:
        text += f"\n📍 Твоя позиция: #{player_position}\n"
        text += f"⭐ Твой уровень: {player['level']}\n"
        text += f"💰 Твое золото: {player['gold']}\n"

    keyboard = [[InlineKeyboardButton("⬅️ НАЗАД", callback_data="ratings")]]
    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

async def show_pvp_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    leaders = get_pvp_leaderboard(chat.id, 10)

    text = "⚔️ ПВП РЕЙТИНГ ⚔️\n\n"

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

        text += f"{medal} {leader['username']} (Ур. {leader['level']}) - {wins}W {losses}L ({win_rate}%)\n"

    keyboard = [[InlineKeyboardButton("⬅️ НАЗАД", callback_data="ratings")]]
    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

async def show_dungeon_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    leaders = get_dungeon_leaderboard(query.message.chat.id, 10)

    text = "🌋 РЕЙТИНГ ПОДЗЕМЕЛЬЯ 🌋\n\n"

    for i, leader in enumerate(leaders, 1):
        if i == 1:
            medal = "👑"
        elif i == 2:
            medal = "🥈"
        elif i == 3:
            medal = "🥉"
        else:
            medal = f"{i}."

        text += f"{medal} {leader['username']} (Ур. {leader['level']}) - Этаж {leader['dungeon_rating']} | Боссов: {leader['total_bosses_killed']}\n"

    keyboard = [[InlineKeyboardButton("⬅️ НАЗАД", callback_data="ratings")]]
    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

# ─────────────────────────────────────────────────────────────────────────────
# ⚔️ ПВП СИСТЕМА - ИСПРАВЛЕННАЯ
# ─────────────────────────────────────────────────────────────────────────────

async def show_pvp_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """✅ ИСПРАВЛЕННОЕ - Показываем меню ПВП"""
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    player = get_player(chat.id, user.id)
    queue_status = get_pvp_queue_status(chat.id, user.id)

    if queue_status and queue_status["confirmed"]:
        text = """
⚔️ ПВП АРЕНА

⏳ ТЫ УЖЕ В ОЧЕРЕДИ ПОИСКА!

Ищем противника...
⏱️ Ожидание...

Нажми "ОТМЕНА" если передумал.
        """
        keyboard = [
            [InlineKeyboardButton("❌ ОТМЕНА", callback_data="pvp_cancel_search")],
            [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")],
        ]
    else:
        text = """
⚔️ ПВП АРЕНА

Сражайся против других игроков и зарабатывай золото!

⚠️ Перед началом поиска убедись, что:
✅ Ты готов к бою
✅ У тебя полное здоровье
✅ Ты экипирован

Начать поиск противника?
        """
        keyboard = [
            [InlineKeyboardButton("🔍 НАЧАТЬ ПОИСК", callback_data="pvp_confirm_search")],
            [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")],
        ]

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

async def pvp_confirm_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """✅ ИСПРАВЛЕННОЕ - Подтверждение поиска"""
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    player = get_player(chat.id, user.id)

    if not player:
        await query.answer("❌ Игрок не найден", show_alert=True)
        return

    add_pvp_queue(chat.id, user.id)
    confirm_pvp_search(chat.id, user.id)

    text = """
⚔️ ПВП АРЕНА

✅ ТЫ ДОБАВЛЕН В ОЧЕРЕДЬ!

🔍 Поиск противника...

Система сканирует других игроков, которые тоже ищут бой.

⏱️ Это может занять несколько секунд...

Нажми "ОТМЕНА" если передумал.
    """

    keyboard = [
        [InlineKeyboardButton("⏸️ ПРОВЕРИТЬ РЕЗУЛЬТАТ", callback_data="pvp_check_match")],
        [InlineKeyboardButton("❌ ОТМЕНА", callback_data="pvp_cancel_search")],
        [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")],
    ]

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

async def pvp_check_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """✅ ИСПРАВЛЕННОЕ - Проверить найден ли противник"""
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    opponent = find_pvp_opponent(chat.id, user.id)

    if not opponent:
        text = """
⚔️ ПВП АРЕНА

❌ ПРОТИВНИК НЕ НАЙДЕН

Противник ещё не найден. Продолжаем поиск...

Попробуй через несколько секунд.
        """

        keyboard = [
            [InlineKeyboardButton("⏸️ ПРОВЕРИТЬ СНОВА", callback_data="pvp_check_match")],
            [InlineKeyboardButton("❌ ОТМЕНА", callback_data="pvp_cancel_search")],
            [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")],
        ]
    else:
        text = f"""
⚔️ ПВП АРЕНА

🎉 ПРОТИВНИК НАЙДЕН!

{CLASSES[get_player(chat.id, opponent['user_id'])['class']]['emoji']} {opponent['username']} - Ур. {opponent['level']}

💰 Призовой фонд: {int(opponent['gold'] * 0.1)} золота

Начинаем бой!
        """

        keyboard = [
            [InlineKeyboardButton("⚔️ НАЧАТЬ БОЙ", callback_data=f"pvp_start_fight_{opponent['user_id']}")],
            [InlineKeyboardButton("❌ ОТКАЗАТЬСЯ", callback_data="pvp_cancel_search")],
        ]

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

async def pvp_cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """✅ ИСПРАВЛЕННОЕ - Отмена поиска"""
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    cancel_pvp_search(chat.id, user.id)

    text = """
⚔️ ПВП АРЕНА

❌ ПОИСК ОТМЕНЁН

Ты вышел из очереди ПВП.
    """

    keyboard = [[InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]]

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

async def pvp_start_fight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """✅ ИСПРАВЛЕННОЕ - Начать ПВП бой"""
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    defender_id = int(query.data.replace("pvp_start_fight_", ""))

    result = pvp_battle(chat.id, user.id, defender_id)

    if not result.get("success"):
        await query.answer(result.get("message", "❌ Ошибка"), show_alert=True)
        return

    attacker = get_player(chat.id, user.id)
    defender = get_player(chat.id, defender_id)

    if result["winner_id"] == user.id:
        text = f"""
⚔️ ПВП БОЙ

🎉 ПОБЕДА!

Противник: {defender['username']}

⚔️ Твой урон: {result['attacker_damage']} {('💥 КРИТ!' if result['attacker_crit'] else '')}

Ответный урон врага: {result['defender_damage']}

💰 Награда: +{result['reward_gold']} золота
        """
    else:
        text = f"""
⚔️ ПВП БОЙ

💀 ПОРАЖЕНИЕ!

Противник: {defender['username']}

⚔️ Урон врага: {result['defender_damage']} {('💥 КРИТ!' if result['defender_crit'] else '')}

Твой урон: {result['attacker_damage']}

❌ Награда: -10% золота
        """

    keyboard = [[InlineKeyboardButton("🎮 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]]
    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            raise

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """✅ ИСПРАВЛЕННЫЙ - Обработчик ошибок"""
    logger.error(f"❌ Update {update} вызвала ошибку: {context.error}")

    try:
        if update.callback_query:
            await update.callback_query.answer("❌ Произошла ошибка. Попробуй снова.", show_alert=True)
    except:
        pass

def signal_handler(sig, frame):
    logger.info("⚠️ Получен сигнал завершения. Закрывается...")
    sys.exit(0)

# ─────────────────────────────────────────────────────────────────────────────
# 🚀 ГЛАВНАЯ ФУНКЦИЯ
# ─────────────────────────────────────────────────────────────────────────────

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
    app.add_handler(CallbackQueryHandler(show_profile, pattern="^profile$"))
    app.add_handler(CallbackQueryHandler(show_inventory, pattern="^inventory$"))

    # ЛОКАЦИИ И БОЙ
    app.add_handler(CallbackQueryHandler(show_locations, pattern="^locations_list$"))
    app.add_handler(CallbackQueryHandler(select_location_handler, pattern="^location_select_"))
    app.add_handler(CallbackQueryHandler(start_fight_location, pattern="^fight_"))

    # Магазин
    app.add_handler(CallbackQueryHandler(show_shop, pattern="^shop$"))
    app.add_handler(CallbackQueryHandler(show_weapons_shop, pattern="^shop_weapons$"))
    app.add_handler(CallbackQueryHandler(show_armor_shop, pattern="^shop_armor$"))
    app.add_handler(CallbackQueryHandler(show_pets_shop, pattern="^shop_pets$"))
    app.add_handler(CallbackQueryHandler(show_runes_shop, pattern="^shop_runes$"))

    # Покупки
    app.add_handler(CallbackQueryHandler(buy_weapon, pattern="^buy_weapon_"))
    app.add_handler(CallbackQueryHandler(buy_armor, pattern="^buy_armor_"))
    app.add_handler(CallbackQueryHandler(buy_pet_handler, pattern="^buy_pet_"))
    app.add_handler(CallbackQueryHandler(buy_rune, pattern="^buy_rune_"))

    # Экипировка
    app.add_handler(CallbackQueryHandler(show_equipment, pattern="^equipment$"))
    app.add_handler(CallbackQueryHandler(equip_weapon_handler, pattern="^equip_weapon_"))
    app.add_handler(CallbackQueryHandler(equip_armor_handler, pattern="^equip_armor_"))

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

    # ПВП - ИСПРАВЛЕННАЯ
    app.add_handler(CallbackQueryHandler(show_pvp_menu, pattern="^pvp_menu$"))
    app.add_handler(CallbackQueryHandler(pvp_confirm_search, pattern="^pvp_confirm_search$"))
    app.add_handler(CallbackQueryHandler(pvp_cancel_search, pattern="^pvp_cancel_search$"))
    app.add_handler(CallbackQueryHandler(pvp_check_match, pattern="^pvp_check_match$"))
    app.add_handler(CallbackQueryHandler(pvp_start_fight, pattern="^pvp_start_fight_"))

    # Рейтинги
    app.add_handler(CallbackQueryHandler(show_ratings, pattern="^ratings$"))
    app.add_handler(CallbackQueryHandler(show_global_rating, pattern="^rating_global$"))
    app.add_handler(CallbackQueryHandler(show_pvp_rating, pattern="^rating_pvp$"))
    app.add_handler(CallbackQueryHandler(show_dungeon_rating, pattern="^rating_dungeon$"))

    # Обработчик ошибок
    app.add_error_handler(error_handler)

    logger.info("✅ RuneQuestRPG BOT v5.2 ЗАПУЩЕН И ГОТОВ!")
    logger.info("🎯 BUGFIXES в v5.2:")
    logger.info("  ✅ Исправлена логика ПВП матчмейкинга")
    logger.info("  ✅ Враги теперь находят друг друга корректно")
    logger.info("  ✅ Обработана ошибка 'Message is not modified'")

    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        logger.info("⚠️ Бот остановлен вручную")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")

if __name__ == "__main__":
    main()
