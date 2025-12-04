# -*- coding: utf-8 -*-
"""
RuneQuestRPG v5.3 — RPG Telegram Bot

Изменения по твоим запросам:
- ПВП ПЕРЕДЕЛАНО ПОД ГЛОБАЛЬНЫЙ ПОИСК (игроки в ЛС, не в общем чате)
- ПОДЗЕМЕЛЬЯ СДЕЛАНЫ НОРМАЛЬНО (этажи, сохранение рейтинга, бой через общую систему битв)
- ДОБАВЛЕН PORT BINDING ЧЕРЕЗ FASTAPI ДЛЯ WEB SERVICE НА RENDER.COM

Запуск:
    python bot.py
"""

import os
import sys
import sqlite3
import random
import logging
import signal
import threading
from typing import Optional, Dict, Any, Callable, List, Tuple
from functools import wraps
from enum import Enum

from dotenv import load_dotenv
from fastapi import FastAPI
import uvicorn

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

# ===================== КОНФИГ =====================

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден в .env")

PORT = int(os.getenv("PORT", "10000"))

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

MAX_LEVEL = 100
LEVEL_UP_BASE = 100
STATS_PER_LEVEL = {"health": 20, "mana": 15, "attack": 5, "defense": 2}

# ===================== ДАННЫЕ И КЛАССЫ =====================


class Element(Enum):
    PHYSICAL = "physical"
    FIRE = "fire"
    ICE = "ice"
    SHADOW = "shadow"
    HOLY = "holy"
    POISON = "poison"
    ARCANE = "arcane"


CLASSES: Dict[str, Dict[str, Any]] = {
    "warrior": {
        "name": "Воин",
        "emoji": "🗡️",
        "description": "Классический боец ближнего боя.",
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
        "emoji": "🪄",
        "description": "Слабое тело, но мощная магия.",
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
        "description": "Криты и уклонения.",
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
        "emoji": "✨",
        "description": "Танк со священной силой.",
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
        "description": "Баланс атаки и ловкости.",
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
        "description": "Маг смерти, слаб телом.",
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

ENEMIES: Dict[str, Dict[str, Any]] = {
    "goblin": {
        "name": "Гоблин",
        "emoji": "👺",
        "level": 1,
        "hp": 25,
        "damage": 5,
        "xp": 30,
        "gold": 10,
        "loot": [],
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
        "loot": [],
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
        "loot": [],
        "boss": False,
        "element": Element.SHADOW.value,
    },
    "dragon_boss": {
        "name": "Дракон",
        "emoji": "🐉",
        "level": 10,
        "hp": 250,
        "damage": 40,
        "xp": 600,
        "gold": 300,
        "loot": [],
        "boss": True,
        "element": Element.FIRE.value,
    },
}

PETS: Dict[str, Dict[str, Any]] = {
    "wolf": {
        "name": "Волк",
        "emoji": "🐺",
        "attack_bonus": 10,
        "defense_bonus": 0,
        "xp_bonus": 1.1,
        "price": 500,
        "level": 1,
    },
}

WEAPONS: Dict[str, Dict[str, Any]] = {
    "iron_sword": {
        "name": "Железный меч",
        "emoji": "⚔️",
        "attack": 10,
        "price": 100,
        "level": 1,
        "crit": 0,
        "class": "warrior",
    },
}

ARMOR: Dict[str, Dict[str, Any]] = {
    "iron_armor": {
        "name": "Железная броня",
        "emoji": "🛡️",
        "defense": 8,
        "health": 20,
        "price": 150,
        "level": 1,
        "class": "warrior",
    },
}

MATERIALS: Dict[str, Dict[str, Any]] = {
    "copper_ore": {"name": "Медная руда", "emoji": "⛏️", "value": 10},
}

LOCATIONS: Dict[str, Dict[str, Any]] = {
    "dark_forest": {
        "name": "Тёмный лес",
        "emoji": "🌲",
        "min_level": 1,
        "max_level": 10,
        "description": "Опасный лес, полный гоблинов и волков.",
        "enemies": ["goblin", "wolf", "skeleton"],
    }
}

# ===================== БД =====================


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect("runequestrpg.db", timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def safedb_execute(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"DB error in {func.__name__}: {e}")
            return None

    return wrapper


@safedb_execute
def init_database():
    conn = get_db()
    c = conn.cursor()

    # Игроки
    c.execute(
        """
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
            pet_id TEXT DEFAULT 'wolf',
            pet_level INTEGER DEFAULT 1,
            total_kills INTEGER DEFAULT 0,
            total_bosses_killed INTEGER DEFAULT 0,
            total_battles_won INTEGER DEFAULT 0,
            total_battles_lost INTEGER DEFAULT 0,
            pvp_wins INTEGER DEFAULT 0,
            pvp_losses INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Инвентарь
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_id INTEGER,
            item_id TEXT NOT NULL,
            item_type TEXT,
            quantity INTEGER DEFAULT 1,
            UNIQUE(user_id, item_id),
            FOREIGN KEY(user_id) REFERENCES players(user_id)
        )
        """
    )

    # Обычные/подземельные бои
    c.execute(
        """
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
            is_dungeon BOOLEAN DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES players(user_id)
        )
        """
    )

    # Прогресс подземелья
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS dungeon_progress (
            user_id INTEGER PRIMARY KEY,
            chat_id INTEGER,
            current_floor INTEGER DEFAULT 1,
            is_active BOOLEAN DEFAULT 0,
            enemies_killed INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES players(user_id)
        )
        """
    )

    # Очередь ПВП (ГЛОБАЛЬНАЯ)
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS pvp_queue (
            user_id INTEGER PRIMARY KEY,
            chat_id INTEGER,
            is_waiting BOOLEAN DEFAULT 1,
            confirmed BOOLEAN DEFAULT 0,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES players(user_id)
        )
        """
    )

    # История ПВП боёв
    c.execute(
        """
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
        """
    )

    conn.commit()
    conn.close()
    logger.info("✅ База данных инициализирована")


# ===================== ФУНКЦИИ ДЛЯ ИГРОКОВ =====================


@safedb_execute
def init_player(chat_id: int, user_id: int, username: str, player_class: str) -> bool:
    if player_class not in CLASSES:
        player_class = "warrior"
    class_info = CLASSES[player_class]

    conn = get_db()
    c = conn.cursor()
    try:
        c.execute(
            """
            INSERT INTO players (
                user_id, chat_id, username, class,
                level, xp, health, max_health, mana, max_mana,
                attack, defense, gold, pet_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                chat_id,
                username or "Безымянный",
                player_class,
                1,
                0,
                class_info["health"],
                class_info["health"],
                class_info["mana"],
                class_info["mana"],
                class_info["attack"],
                class_info["defense"],
                class_info["starting_gold"],
                "wolf",
            ),
        )
        # стартовые зелья
        c.execute(
            """
            INSERT OR IGNORE INTO inventory (user_id, chat_id, item_id, item_type, quantity)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, chat_id, "health_potion", "potion", 3),
        )
        conn.commit()
        logger.info(f"✅ Игрок создан: {username} ({user_id}) - {player_class}")
        return True
    except sqlite3.IntegrityError:
        logger.warning(f"Игрок уже существует: {user_id}")
        return False
    finally:
        conn.close()


@safedb_execute
def get_player(chat_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM players WHERE user_id = ? AND chat_id = ?",
        (user_id, chat_id),
    )
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


@safedb_execute
def player_exists(chat_id: int, user_id: int) -> bool:
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT 1 FROM players WHERE user_id = ? AND chat_id = ?",
        (user_id, chat_id),
    )
    exists = c.fetchone() is not None
    conn.close()
    return exists


@safedb_execute
def add_xp(chat_id: int, user_id: int, xp_amount: int) -> int:
    player = get_player(chat_id, user_id)
    if not player:
        return 0
    new_xp = player["xp"] + xp_amount
    level = player["level"]
    level_ups = 0

    while level < MAX_LEVEL:
        xp_needed = int(LEVEL_UP_BASE * (level ** 1.5))
        if new_xp >= xp_needed:
            new_xp -= xp_needed
            level += 1
            level_ups += 1
        else:
            break

    conn = get_db()
    c = conn.cursor()
    if level_ups > 0:
        new_max_hp = player["max_health"] + STATS_PER_LEVEL["health"] * level_ups
        new_max_mana = player["max_mana"] + STATS_PER_LEVEL["mana"] * level_ups
        new_attack = player["attack"] + STATS_PER_LEVEL["attack"] * level_ups
        new_defense = player["defense"] + STATS_PER_LEVEL["defense"] * level_ups
        c.execute(
            """
            UPDATE players
            SET xp = ?, level = ?, max_health = ?, health = ?, max_mana = ?, mana = ?, attack = ?, defense = ?
            WHERE user_id = ? AND chat_id = ?
            """,
            (
                new_xp,
                level,
                new_max_hp,
                new_max_hp,
                new_max_mana,
                new_max_mana,
                new_attack,
                new_defense,
                user_id,
                chat_id,
            ),
        )
    else:
        c.execute(
            "UPDATE players SET xp = ? WHERE user_id = ? AND chat_id = ?",
            (new_xp, user_id, chat_id),
        )

    conn.commit()
    conn.close()
    return level_ups


@safedb_execute
def add_gold(chat_id: int, user_id: int, amount: int):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE players SET gold = gold + ? WHERE user_id = ? AND chat_id = ?",
        (amount, user_id, chat_id),
    )
    conn.commit()
    conn.close()


@safedb_execute
def subtract_gold(chat_id: int, user_id: int, amount: int) -> bool:
    player = get_player(chat_id, user_id)
    if not player or player["gold"] < amount:
        return False
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE players SET gold = gold - ? WHERE user_id = ? AND chat_id = ?",
        (amount, user_id, chat_id),
    )
    conn.commit()
    conn.close()
    return True


# ===================== ИНВЕНТАРЬ =====================


@safedb_execute
def get_inventory(chat_id: int, user_id: int) -> List[Dict[str, Any]]:
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM inventory WHERE user_id = ? AND chat_id = ? ORDER BY item_type, item_id",
        (user_id, chat_id),
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


@safedb_execute
def get_item_quantity(chat_id: int, user_id: int, item_id: str) -> int:
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT quantity FROM inventory WHERE user_id = ? AND chat_id = ? AND item_id = ?",
        (user_id, chat_id, item_id),
    )
    row = c.fetchone()
    conn.close()
    return row["quantity"] if row else 0


@safedb_execute
def add_item(chat_id: int, user_id: int, item_id: str, quantity: int = 1):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT quantity FROM inventory WHERE user_id = ? AND chat_id = ? AND item_id = ?",
        (user_id, chat_id, item_id),
    )
    row = c.fetchone()
    if row:
        c.execute(
            "UPDATE inventory SET quantity = quantity + ? WHERE user_id = ? AND chat_id = ? AND item_id = ?",
            (quantity, user_id, chat_id, item_id),
        )
    else:
        item_type = "misc"
        if item_id in WEAPONS:
            item_type = "weapon"
        elif item_id in ARMOR:
            item_type = "armor"
        elif item_id in MATERIALS:
            item_type = "material"
        elif item_id == "health_potion":
            item_type = "potion"
        c.execute(
            "INSERT INTO inventory (user_id, chat_id, item_id, item_type, quantity) VALUES (?, ?, ?, ?, ?)",
            (user_id, chat_id, item_id, item_type, quantity),
        )
    conn.commit()
    conn.close()


@safedb_execute
def remove_item(chat_id: int, user_id: int, item_id: str, quantity: int = 1) -> bool:
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT quantity FROM inventory WHERE user_id = ? AND chat_id = ? AND item_id = ?",
        (user_id, chat_id, item_id),
    )
    row = c.fetchone()
    if not row or row["quantity"] < quantity:
        conn.close()
        return False
    if row["quantity"] == quantity:
        c.execute(
            "DELETE FROM inventory WHERE user_id = ? AND chat_id = ? AND item_id = ?",
            (user_id, chat_id, item_id),
        )
    else:
        c.execute(
            "UPDATE inventory SET quantity = quantity - ? WHERE user_id = ? AND chat_id = ? AND item_id = ?",
            (quantity, user_id, chat_id, item_id),
        )
    conn.commit()
    conn.close()
    return True


# ===================== БОИ (PVE + ПОДЗЕМЕЛЬЯ) =====================


def calculate_damage(attacker_attack: int, defender_defense: int, crit_chance: int, spell_power: int = 0) -> Tuple[int, bool]:
    base = max(1, attacker_attack - defender_defense // 2)
    variation = random.uniform(0.85, 1.15)
    damage = int(base * variation)

    if spell_power > 0:
        damage += int(spell_power * random.uniform(0.8, 1.2))

    is_crit = random.randint(1, 100) <= crit_chance
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

    # питомец
    pet_id = player.get("pet_id")
    if pet_id and pet_id in PETS:
        pet = PETS[pet_id]
        stats["attack"] += pet["attack_bonus"]
        stats["defense"] += pet["defense_bonus"]

    # TODO: учёт оружия/брони

    return stats


@safedb_execute
def start_battle(
    chat_id: int,
    user_id: int,
    enemy_id: str,
    is_dungeon: bool = False,
    location_id: str = "world",
) -> Optional[Dict[str, Any]]:
    player = get_player(chat_id, user_id)
    if not player:
        return None

    if enemy_id not in ENEMIES:
        return None

    enemy_template = ENEMIES[enemy_id].copy()
    enemy_hp = enemy_template["hp"]
    enemy_damage = enemy_template["damage"]

    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        INSERT OR REPLACE INTO battles
        (user_id, chat_id, location_id, enemy_id, enemy_health, enemy_max_health,
         enemy_damage, is_boss, player_health, player_max_health, is_dungeon)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            chat_id,
            location_id,
            enemy_id,
            enemy_hp,
            enemy_hp,
            enemy_damage,
            int(enemy_template.get("boss", False)),
            player["health"],
            player["max_health"],
            int(is_dungeon),
        ),
    )
    conn.commit()
    conn.close()

    return {
        "enemy_id": enemy_id,
        "enemy_name": enemy_template["name"],
        "enemy_emoji": enemy_template["emoji"],
        "enemy_health": enemy_hp,
        "enemy_max_health": enemy_hp,
        "enemy_damage": enemy_damage,
        "is_boss": enemy_template.get("boss", False),
        "player_health": player["health"],
        "player_max_health": player["max_health"],
        "is_dungeon": is_dungeon,
    }


@safedb_execute
def get_active_battle(chat_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM battles WHERE user_id = ? AND chat_id = ?",
        (user_id, chat_id),
    )
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


@safedb_execute
def end_battle(chat_id: int, user_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "DELETE FROM battles WHERE user_id = ? AND chat_id = ?",
        (user_id, chat_id),
    )
    conn.commit()
    conn.close()


@safedb_execute
def start_dungeon_logic(chat_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    """
    Логика старта подземелья:
      - ставим/обновляем dungeon_progress
      - создаём бой через battles с пометкой is_dungeon = 1
      - враги усиливаются с этажом
    """
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM dungeon_progress WHERE user_id = ? AND chat_id = ?",
        (user_id, chat_id),
    )
    row = c.fetchone()

    if row and row["is_active"]:
        # уже в подземелье
        conn.close()
        return None

    player = get_player(chat_id, user_id)
    if not player:
        conn.close()
        return None

    floor = 1
    if row:
        floor = row["current_floor"]
        c.execute(
            "UPDATE dungeon_progress SET is_active = 1 WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        )
    else:
        c.execute(
            """
            INSERT INTO dungeon_progress (user_id, chat_id, current_floor, is_active, enemies_killed)
            VALUES (?, ?, ?, 1, 0)
            """,
            (user_id, chat_id, floor),
        )

    conn.commit()
    conn.close()

    # Выбираем врага и усиливаем по этажу
    enemy_id = random.choice(list(ENEMIES.keys()))
    enemy_template = ENEMIES[enemy_id].copy()
    scale = 1.0 + (floor - 1) * 0.15
    enemy_hp = int(enemy_template["hp"] * scale)
    enemy_damage = int(enemy_template["damage"] * scale)

    # создаём бой
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        INSERT OR REPLACE INTO battles
        (user_id, chat_id, location_id, enemy_id, enemy_health, enemy_max_health,
         enemy_damage, is_boss, player_health, player_max_health, is_dungeon)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            user_id,
            chat_id,
            f"dungeon_floor_{floor}",
            enemy_id,
            enemy_hp,
            enemy_hp,
            enemy_damage,
            int(enemy_template.get("boss", False)),
            player["health"],
            player["max_health"],
        ),
    )
    conn.commit()
    conn.close()

    return {
        "floor": floor,
        "enemy_id": enemy_id,
        "enemy_name": enemy_template["name"],
        "enemy_emoji": enemy_template["emoji"],
        "enemy_health": enemy_hp,
        "enemy_max_health": enemy_hp,
        "enemy_damage": enemy_damage,
    }


@safedb_execute
def end_dungeon_logic(chat_id: int, user_id: int, victory: bool):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM dungeon_progress WHERE user_id = ? AND chat_id = ?",
        (user_id, chat_id),
    )
    row = c.fetchone()
    if not row:
        conn.close()
        return

    current_floor = row["current_floor"]

    if victory:
        # переход на следующий этаж
        c.execute(
            """
            UPDATE dungeon_progress
            SET current_floor = current_floor + 1,
                enemies_killed = enemies_killed + 1,
                is_active = 1
            WHERE user_id = ? AND chat_id = ?
            """,
            (user_id, chat_id),
        )
        # апдейтим рейтинг если текущий этаж выше
        c.execute(
            "UPDATE players SET dungeon_rating = MAX(dungeon_rating, ?) WHERE user_id = ? AND chat_id = ?",
            (current_floor + 1, user_id, chat_id),
        )
    else:
        # поражение — сбрасываем прогресс, но сохраняем рейтинг
        c.execute(
            """
            UPDATE dungeon_progress
            SET current_floor = 1,
                is_active = 0
            WHERE user_id = ? AND chat_id = ?
            """,
            (user_id, chat_id),
        )

    conn.commit()
    conn.close()


@safedb_execute
def perform_attack(chat_id: int, user_id: int) -> Dict[str, Any]:
    """
    Общая логика атаки (используется и для обычных боёв, и для подземелий).
    """
    player = get_player(chat_id, user_id)
    battle = get_active_battle(chat_id, user_id)
    if not player or not battle:
        return {"success": False, "message": "Нет активного боя."}

    player_stats = get_player_battle_stats(player)
    damage, is_crit = calculate_damage(
        player_stats["attack"], 0, player_stats["crit_chance"], player_stats["spell_power"]
    )

    new_enemy_hp = battle["enemy_health"] - damage
    result: Dict[str, Any] = {
        "success": True,
        "damage": damage,
        "is_crit": is_crit,
        "enemy_hp": max(0, new_enemy_hp),
        "enemy_max_hp": battle["enemy_max_health"],
        "enemy_defeated": new_enemy_hp <= 0,
        "victory": False,
        "defeat": False,
        "xpgained": 0,
        "goldgained": 0,
        "levelup": 0,
        "goldlost": 0,
        "is_dungeon": bool(battle["is_dungeon"]),
    }

    if new_enemy_hp <= 0:
        # победа
        end_battle(chat_id, user_id)
        enemy = ENEMIES.get(battle["enemy_id"], {"xp": 0, "gold": 0})
        xp = enemy.get("xp", 0)
        gold = enemy.get("gold", 0)

        # бонус от питомца
        if player.get("pet_id") in PETS:
            xp = int(xp * PETS[player["pet_id"]]["xp_bonus"])

        add_gold(chat_id, user_id, gold)
        lvl = add_xp(chat_id, user_id, xp)

        # обновляем статистику
        conn = get_db()
        c = conn.cursor()
        c.execute(
            """
            UPDATE players
            SET total_kills = total_kills + 1,
                total_battles_won = total_battles_won + 1
            WHERE user_id = ? AND chat_id = ?
            """,
            (user_id, chat_id),
        )
        if battle["is_boss"]:
            c.execute(
                """
                UPDATE players
                SET total_bosses_killed = total_bosses_killed + 1
                WHERE user_id = ? AND chat_id = ?
                """,
                (user_id, chat_id),
            )
        conn.commit()
        conn.close()

        result.update(
            {
                "xpgained": xp,
                "goldgained": gold,
                "levelup": lvl,
                "victory": True,
            }
        )

        # если это подземелье — двигаем прогресс
        if battle["is_dungeon"]:
            end_dungeon_logic(chat_id, user_id, victory=True)
    else:
        # враг жив — атакует игрока
        conn = get_db()
        c = conn.cursor()
        c.execute(
            "UPDATE battles SET enemy_health = ? WHERE user_id = ? AND chat_id = ?",
            (new_enemy_hp, user_id, chat_id),
        )
        conn.commit()
        conn.close()

        enemy_damage, _ = calculate_damage(
            battle["enemy_damage"], player["defense"], 5, 0
        )
        new_player_hp = player["health"] - enemy_damage

        result["enemy_damage"] = enemy_damage
        result["player_hp"] = max(0, new_player_hp)
        result["player_max_hp"] = player["max_health"]

        if new_player_hp <= 0:
            # поражение
            end_battle(chat_id, user_id)
            gold_lost = int(player["gold"] * 0.1)
            if gold_lost > 0:
                subtract_gold(chat_id, user_id, gold_lost)
            conn = get_db()
            c = conn.cursor()
            c.execute(
                """
                UPDATE players
                SET health = max_health,
                    total_battles_lost = total_battles_lost + 1
                WHERE user_id = ? AND chat_id = ?
                """,
                (user_id, chat_id),
            )
            conn.commit()
            conn.close()
            result["defeat"] = True
            result["goldlost"] = gold_lost
        else:
            # просто обновляем HP игрока
            conn = get_db()
            c = conn.cursor()
            c.execute(
                "UPDATE players SET health = ? WHERE user_id = ? AND chat_id = ?",
                (new_player_hp, user_id, chat_id),
            )
            conn.commit()
            conn.close()

    return result


# ===================== ПВП (ГЛОБАЛЬНОЕ) =====================


@safedb_execute
def add_pvp_queue(chat_id: int, user_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        INSERT OR REPLACE INTO pvp_queue (user_id, chat_id, is_waiting, confirmed, timestamp)
        VALUES (?, ?, 1, 0, CURRENT_TIMESTAMP)
        """,
        (user_id, chat_id),
    )
    conn.commit()
    conn.close()


@safedb_execute
def confirm_pvp_search(chat_id: int, user_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE pvp_queue SET confirmed = 1 WHERE user_id = ? AND chat_id = ?",
        (user_id, chat_id),
    )
    conn.commit()
    conn.close()


@safedb_execute
def cancel_pvp_search(chat_id: int, user_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM pvp_queue WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


@safedb_execute
def get_pvp_queue_status(chat_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM pvp_queue WHERE user_id = ? AND chat_id = ?",
        (user_id, chat_id),
    )
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


@safedb_execute
def find_pvp_opponent(chat_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    """
    Глобальный поиск соперника:
    - НЕ фильтруем по chat_id
    - оба confirmed = 1
    - оба is_waiting = 1
    - уровень ±5
    """
    player = get_player(chat_id, user_id)
    if not player:
        return None

    min_level = max(1, player["level"] - 5)
    max_level = player["level"] + 5

    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT p.user_id,
               p.chat_id,
               p.username,
               p.level,
               p.attack,
               p.defense,
               p.gold,
               p.class
        FROM players p
        JOIN pvp_queue q ON p.user_id = q.user_id
        WHERE p.user_id != ?
          AND p.level BETWEEN ? AND ?
          AND q.confirmed = 1
          AND q.is_waiting = 1
        ORDER BY q.timestamp ASC
        LIMIT 1
        """,
        (user_id, min_level, max_level),
    )
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


@safedb_execute
def pvp_battle(attacker_chat_id: int, attacker_id: int, defender_id: int) -> Dict[str, Any]:
    """
    ПВП бой между игроками из разных чатов.
    """
    attacker = get_player(attacker_chat_id, attacker_id)

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM players WHERE user_id = ?", (defender_id,))
    drow = c.fetchone()
    conn.close()

    if not attacker or not drow:
        return {"success": False, "message": "Один из игроков не найден."}

    defender = dict(drow)
    defender_chat_id = defender["chat_id"]

    attacker_stats = get_player_battle_stats(attacker)
    defender_stats = get_player_battle_stats(defender)

    # удар атакующего
    attacker_damage, attacker_crit = calculate_damage(
        attacker_stats["attack"],
        defender_stats["defense"],
        attacker_stats["crit_chance"],
        attacker_stats["spell_power"],
    )
    defender_new_hp = defender["health"] - attacker_damage

    if defender_new_hp <= 0:
        defender_damage, defender_crit = 0, False
        attacker_new_hp = attacker["health"]
    else:
        defender_damage, defender_crit = calculate_damage(
            defender_stats["attack"],
            attacker_stats["defense"],
            defender_stats["crit_chance"],
            defender_stats["spell_power"],
        )
        attacker_new_hp = attacker["health"] - defender_damage

    if defender_new_hp <= 0:
        winner_id = attacker_id
        reward_gold = int(defender["gold"] * 0.1)
    elif attacker_new_hp <= 0:
        winner_id = defender_id
        reward_gold = int(attacker["gold"] * 0.1)
    else:
        if defender_new_hp < attacker_new_hp:
            winner_id = attacker_id
            reward_gold = int(defender["gold"] * 0.05)
        else:
            winner_id = defender_id
            reward_gold = int(attacker["gold"] * 0.05)

    # обновляем БД
    conn = get_db()
    c = conn.cursor()

    c.execute(
        """
        INSERT INTO pvp_battles (attacker_id, defender_id, chat_id, winner_id, reward_gold)
        VALUES (?, ?, ?, ?, ?)
        """,
        (attacker_id, defender_id, attacker_chat_id, winner_id, reward_gold),
    )

    # победитель
    c.execute(
        "UPDATE players SET pvp_wins = pvp_wins + 1, gold = gold + ? WHERE user_id = ?",
        (reward_gold, winner_id),
    )

    # проигравший
    loser_id = defender_id if winner_id == attacker_id else attacker_id
    c.execute(
        "UPDATE players SET pvp_losses = pvp_losses + 1, health = max_health WHERE user_id = ?",
        (loser_id,),
    )

    # убираем обоих из очереди
    c.execute("DELETE FROM pvp_queue WHERE user_id IN (?, ?)", (attacker_id, defender_id))

    conn.commit()
    conn.close()

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
        "defender_chat_id": defender_chat_id,
    }


# ===================== РЕЙТИНГИ =====================


@safedb_execute
def get_global_leaderboard(chat_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT user_id, username, level, gold, total_kills, total_bosses_killed
        FROM players
        WHERE chat_id = ?
        ORDER BY level DESC, gold DESC, total_kills DESC
        LIMIT ?
        """,
        (chat_id, limit),
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


@safedb_execute
def get_pvp_leaderboard(chat_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT username, level, pvp_wins, pvp_losses,
               CASE WHEN (pvp_wins + pvp_losses) > 0
                    THEN ROUND(100.0 * pvp_wins / (pvp_wins + pvp_losses), 2)
                    ELSE 0 END AS winrate
        FROM players
        WHERE chat_id = ? AND (pvp_wins + pvp_losses) > 0
        ORDER BY pvp_wins DESC, winrate DESC
        LIMIT ?
        """,
        (chat_id, limit),
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


@safedb_execute
def get_dungeon_leaderboard(chat_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT username, level, dungeon_rating, total_bosses_killed
        FROM players
        WHERE chat_id = ? AND dungeon_rating > 0
        ORDER BY dungeon_rating DESC, total_bosses_killed DESC
        LIMIT ?
        """,
        (chat_id, limit),
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


@safedb_execute
def get_player_position(chat_id: int, user_id: int) -> int:
    player = get_player(chat_id, user_id)
    if not player:
        return 0
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT COUNT(*) AS pos
        FROM players
        WHERE chat_id = ?
          AND (level > ? OR (level = ? AND gold > ?))
        """,
        (chat_id, player["level"], player["level"], player["gold"]),
    )
    row = c.fetchone()
    conn.close()
    return int(row["pos"]) + 1 if row else 1


# ===================== ОБРАБОТЧИКИ БОТА =====================


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if player_exists(chat.id, user.id):
        await show_main_menu(update, context)
        return

    text = (
        f"Добро пожаловать в RuneQuestRPG, {user.first_name}!\n\n"
        "Выбери класс:\n"
        "🗡️ Воин — баланс атаки и защиты\n"
        "🪄 Маг — слаб телом, силён магией\n"
        "🗡️ Разбойник — криты и уклонение\n"
        "✨ Паладин — танк со светлой магией\n"
        "🏹 Рейнджер — дальний бой\n"
        "💀 Некромант — магия смерти\n"
    )
    keyboard = [
        [
            InlineKeyboardButton("🗡️ Воин", callback_data="class_warrior"),
            InlineKeyboardButton("🪄 Маг", callback_data="class_mage"),
        ],
        [
            InlineKeyboardButton("🗡️ Разбойник", callback_data="class_rogue"),
            InlineKeyboardButton("✨ Паладин", callback_data="class_paladin"),
        ],
        [
            InlineKeyboardButton("🏹 Рейнджер", callback_data="class_ranger"),
            InlineKeyboardButton("💀 Некромант", callback_data="class_necromancer"),
        ],
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def cb_select_class(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    class_name = query.data.replace("class_", "")
    created = init_player(chat.id, user.id, user.username or user.first_name, class_name)
    if not created:
        await query.answer("Ошибка создания персонажа.", show_alert=True)
        return

    info = CLASSES.get(class_name, CLASSES["warrior"])
    text = (
        f"✅ Класс выбран: {info['emoji']} {info['name']}\n\n"
        f"{info['description']}\n\n"
        f"❤️ HP: {info['health']}\n"
        f"💎 Мана: {info['mana']}\n"
        f"⚔️ Атака: {info['attack']}\n"
        f"🛡️ Защита: {info['defense']}\n"
        f"💰 Золото: {info['starting_gold']}\n\n"
        "Персонаж создан! Переходим в главное меню."
    )
    keyboard = [[InlineKeyboardButton("➡️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query if update.callback_query else None
    message = query.message if query else update.message
    user = update.effective_user
    chat = update.effective_chat

    player = get_player(chat.id, user.id)
    if not player:
        text = "Сначала создай персонажа: /start"
        if query:
            await query.edit_message_text(text)
        else:
            await message.reply_text(text)
        return

    info = CLASSES[player["class"]]
    pet = PETS.get(player["pet_id"], PETS["wolf"])

    text = (
        f"{info['emoji']} RuneQuestRPG — {user.first_name}\n\n"
        f"Класс: {info['name']} (ур. {player['level']}/{MAX_LEVEL})\n"
        f"XP: {player['xp']}\n"
        f"❤️ HP: {player['health']}/{player['max_health']}\n"
        f"💎 Мана: {player['mana']}/{player['max_mana']}\n"
        f"💰 Золото: {player['gold']}\n\n"
        f"🐾 Питомец: {pet['emoji']} {pet['name']} (ур. {player['pet_level']})\n"
        f"🏰 Рейтинг подземелья: {player['dungeon_rating']}\n"
    )
    keyboard = [
        [
            InlineKeyboardButton("👤 Профиль", callback_data="profile"),
            InlineKeyboardButton("🎒 Инвентарь", callback_data="inventory"),
        ],
        [
            InlineKeyboardButton("⚔️ Охота", callback_data="locations"),
            InlineKeyboardButton("🏰 Подземелье", callback_data="dungeon"),
        ],
        [
            InlineKeyboardButton("⚔️ ПВП", callback_data="pvp_menu"),
            InlineKeyboardButton("🏆 Рейтинги", callback_data="ratings"),
        ],
    ]

    if query:
        try:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception:
            await query.answer("Главное меню", show_alert=False)
    else:
        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def cb_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    player = get_player(chat.id, user.id)
    if not player:
        await query.answer("Персонаж не найден.", show_alert=True)
        return

    info = CLASSES[player["class"]]
    pet = PETS.get(player["pet_id"], PETS["wolf"])
    stats = get_player_battle_stats(player)
    text = (
        f"👤 Профиль: {user.first_name}\n\n"
        f"{info['emoji']} Класс: {info['name']} (ур. {player['level']}/{MAX_LEVEL})\n"
        f"XP: {player['xp']}\n"
        f"❤️ HP: {player['health']}/{player['max_health']}\n"
        f"💎 Мана: {player['mana']}/{player['max_mana']}\n"
        f"⚔️ Атака: {stats['attack']} (базовая {player['attack']})\n"
        f"🛡️ Защита: {stats['defense']} (базовая {player['defense']})\n"
        f"💥 Крит: {stats['crit_chance']}%\n"
        f"💰 Золото: {player['gold']}\n\n"
        f"🐾 Питомец: {pet['emoji']} {pet['name']} (ур. {player['pet_level']})\n\n"
        f"⚔️ Победы: {player['total_battles_won']} | Поражения: {player['total_battles_lost']}\n"
        f"💀 Боссы: {player['total_bosses_killed']}\n"
        f"⚔️ ПВП W/L: {player['pvp_wins']}/{player['pvp_losses']}\n"
        f"🏰 Рейтинг подземелий: {player['dungeon_rating']}\n"
    )
    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def cb_inventory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    items = get_inventory(chat.id, user.id)
    if not items:
        text = "🎒 Инвентарь пуст."
    else:
        lines = ["🎒 Инвентарь:\n"]
        for it in items:
            iid = it["item_id"]
            qty = it["quantity"]
            if iid in WEAPONS:
                w = WEAPONS[iid]
                lines.append(f"{w['emoji']} {w['name']} x{qty}")
            elif iid in ARMOR:
                a = ARMOR[iid]
                lines.append(f"{a['emoji']} {a['name']} x{qty}")
            elif iid in MATERIALS:
                m = MATERIALS[iid]
                lines.append(f"{m['emoji']} {m['name']} x{qty}")
            elif iid == "health_potion":
                lines.append(f"🧪 Зелье лечения x{qty}")
            else:
                lines.append(f"{iid} x{qty}")
        text = "\n".join(lines)

    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


# ------ Локации (обычная охота) ------


async def cb_locations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    player = get_player(chat.id, user.id)
    if not player:
        await query.answer("Сначала создай персонажа.", show_alert=True)
        return

    lines = ["🌍 Локации:\n"]
    keyboard: List[List[InlineKeyboardButton]] = []
    for loc_id, loc in LOCATIONS.items():
        if player["level"] < loc["min_level"]:
            status = "🔒"
        elif player["level"] > loc["max_level"]:
            status = "⚠️"
        else:
            status = "✅"
        lines.append(
            f"{status} {loc['emoji']} {loc['name']} "
            f"(ур. {loc['min_level']}-{loc['max_level']})"
        )
        if status != "🔒":
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"{loc['emoji']} {loc['name']}",
                        callback_data=f"loc_{loc_id}",
                    )
                ]
            )

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")])
    await query.edit_message_text(
        "\n".join(lines), reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def cb_select_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    loc_id = query.data.replace("loc_", "")
    loc = LOCATIONS.get(loc_id)
    if not loc:
        await query.answer("Локация не найдена.", show_alert=True)
        return

    player = get_player(chat.id, user.id)
    if not player:
        await query.answer("Персонаж не найден.", show_alert=True)
        return

    if player["level"] < loc["min_level"] or player["level"] > loc["max_level"]:
        await query.answer(
            f"Доступно только для уровней {loc['min_level']}-{loc['max_level']}.",
            show_alert=True,
        )
        return

    # выбираем врага
    enemy_id = random.choice(loc["enemies"])
    battle = start_battle(chat.id, user.id, enemy_id, is_dungeon=False, location_id=loc_id)
    if not battle:
        await query.answer("Не удалось начать бой.", show_alert=True)
        return

    text = (
        f"⚔️ Бой в локации {loc['emoji']} {loc['name']}\n\n"
        f"Противник: {battle['enemy_emoji']} {battle['enemy_name']}\n"
        f"❤️ HP врага: {battle['enemy_health']}/{battle['enemy_max_health']}\n"
        f"⚔️ Урон врага: {battle['enemy_damage']}\n\n"
        "Твои действия?"
    )
    keyboard = [
        [InlineKeyboardButton("⚔️ Атаковать", callback_data="attack")],
        [InlineKeyboardButton("🧪 Зелье", callback_data="use_potion")],
        [InlineKeyboardButton("🏃 Сбежать", callback_data="escape")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


# ------ Атака / зелье / бегство ------


async def cb_attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    player = get_player(chat.id, user.id)
    if not player:
        await query.answer("Персонаж не найден.", show_alert=True)
        return

    battle = get_active_battle(chat.id, user.id)
    if not battle:
        await query.answer("Нет активного боя.", show_alert=True)
        return

    result = perform_attack(chat.id, user.id)
    if not result.get("success"):
        await query.answer(result.get("message", "Ошибка."), show_alert=True)
        return

    # Формируем текст
    lines = ["⚔️ Атака\n"]
    if result["is_crit"]:
        lines.append(f"💥 Критический удар! Ты нанёс {result['damage']} урона.")
    else:
        lines.append(f"Ты нанёс {result['damage']} урона.")

    lines.append(
        f"❤️ HP врага: {result['enemy_hp']}/{result['enemy_max_hp']}"
    )

    if result.get("enemy_damage"):
        lines.append(
            f"Ответный удар врага: {result['enemy_damage']} урона.\n"
            f"Твой HP: {result.get('player_hp', 0)}/{result.get('player_max_hp', 0)}"
        )

    keyboard: List[List[InlineKeyboardButton]] = []

    if result["victory"]:
        lines.append(
            f"\n🏆 Победа!\n+{result['xpgained']} XP, +{result['goldgained']} золота."
        )
        if result["levelup"] > 0:
            lines.append(f"⬆️ Уровень повышен на {result['levelup']}!")

        if result["is_dungeon"]:
            lines.append("\n🏰 Ты прошёл этаж подземелья!")

        keyboard.append([InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")])
    elif result["defeat"]:
        lines.append(
            f"\n💀 Поражение.\nПотеряно золота: {result['goldlost']}."
        )
        keyboard.append([InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")])
    else:
        keyboard.append([InlineKeyboardButton("⚔️ Атаковать", callback_data="attack")])
        keyboard.append([InlineKeyboardButton("🧪 Зелье", callback_data="use_potion")])
        keyboard.append([InlineKeyboardButton("🏃 Сбежать", callback_data="escape")])

    await query.edit_message_text(
        "\n".join(lines), reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def cb_use_potion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    player = get_player(chat.id, user.id)
    battle = get_active_battle(chat.id, user.id)
    if not player or not battle:
        await query.answer("Нет активного боя.", show_alert=True)
        return

    if get_item_quantity(chat.id, user.id, "health_potion") <= 0:
        await query.answer("Нет зелий лечения.", show_alert=True)
        return

    remove_item(chat.id, user.id, "health_potion", 1)
    heal_amount = int(player["max_health"] * 0.5)
    new_hp = min(player["max_health"], player["health"] + heal_amount)

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE players SET health = ? WHERE user_id = ? AND chat_id = ?",
        (new_hp, user.id, chat.id),
    )
    conn.commit()
    conn.close()

    # враг атакует после использования зелья
    enemy_damage, _ = calculate_damage(battle["enemy_damage"], player["defense"], 5)
    new_player_hp = new_hp - enemy_damage

    lines = [
        "🧪 Ты используешь зелье лечения.",
        f"Ты восстанавливаешь {heal_amount} HP (до {new_hp}/{player['max_health']}).",
        f"Враг наносит {enemy_damage} урона.",
    ]

    keyboard: List[List[InlineKeyboardButton]] = []

    if new_player_hp <= 0:
        end_battle(chat.id, user.id)
        gold_lost = int(player["gold"] * 0.1)
        if gold_lost > 0:
            subtract_gold(chat.id, user.id, gold_lost)
        conn = get_db()
        c = conn.cursor()
        c.execute(
            """
            UPDATE players
            SET health = max_health,
                total_battles_lost = total_battles_lost + 1
            WHERE user_id = ? AND chat_id = ?
            """,
            (user.id, chat.id),
        )
        conn.commit()
        conn.close()
        lines.append(
            f"💀 Поражение. Потеряно золота: {gold_lost}."
        )
        keyboard.append([InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")])
    else:
        conn = get_db()
        c = conn.cursor()
        c.execute(
            "UPDATE players SET health = ? WHERE user_id = ? AND chat_id = ?",
            (new_player_hp, user.id, chat.id),
        )
        conn.commit()
        conn.close()
        lines.append(
            f"Твой HP: {new_player_hp}/{player['max_health']}."
        )
        keyboard.append([InlineKeyboardButton("⚔️ Атаковать", callback_data="attack")])
        keyboard.append([InlineKeyboardButton("🏃 Сбежать", callback_data="escape")])

    await query.edit_message_text(
        "\n".join(lines), reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def cb_escape(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    player = get_player(chat.id, user.id)
    battle = get_active_battle(chat.id, user.id)
    if not player or not battle:
        await query.answer("Нет активного боя.", show_alert=True)
        return

    # шанс 50% сбежать без наказания
    if random.randint(1, 100) <= 50:
        end_battle(chat.id, user.id)
        text = "🏃 Ты успешно сбежал из боя."
        keyboard = [[InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")]]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # не удалось сбежать — враг бьёт
    enemy_damage, _ = calculate_damage(battle["enemy_damage"], player["defense"], 5)
    new_player_hp = player["health"] - enemy_damage

    lines = [
        "❌ Не удалось сбежать!",
        f"Враг наносит {enemy_damage} урона.",
    ]
    keyboard: List[List[InlineKeyboardButton]] = []

    if new_player_hp <= 0:
        end_battle(chat.id, user.id)
        gold_lost = int(player["gold"] * 0.1)
        if gold_lost > 0:
            subtract_gold(chat.id, user.id, gold_lost)
        conn = get_db()
        c = conn.cursor()
        c.execute(
            """
            UPDATE players
            SET health = max_health,
                total_battles_lost = total_battles_lost + 1
            WHERE user_id = ? AND chat_id = ?
            """,
            (user.id, chat.id),
        )
        conn.commit()
        conn.close()
        lines.append(
            f"💀 Поражение. Потеряно золота: {gold_lost}."
        )
        keyboard.append([InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")])
    else:
        conn = get_db()
        c = conn.cursor()
        c.execute(
            "UPDATE players SET health = ? WHERE user_id = ? AND chat_id = ?",
            (new_player_hp, user.id, chat.id),
        )
        conn.commit()
        conn.close()
        lines.append(
            f"Твой HP: {new_player_hp}/{player['max_health']}."
        )
        keyboard.append([InlineKeyboardButton("⚔️ Атаковать", callback_data="attack")])
        keyboard.append([InlineKeyboardButton("🏃 Попробовать ещё раз", callback_data="escape")])

    await query.edit_message_text(
        "\n".join(lines), reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ------ Подземелья ------


async def cb_dungeon_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    player = get_player(chat.id, user.id)
    if not player:
        await query.answer("Сначала создай персонажа.", show_alert=True)
        return

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT current_floor, is_active FROM dungeon_progress WHERE user_id = ? AND chat_id = ?",
        (user.id, chat.id),
    )
    row = c.fetchone()
    conn.close()

    floor = row["current_floor"] if row else 1
    is_active = bool(row["is_active"]) if row else False

    text = (
        "🏰 Подземелье\n\n"
        f"Текущий этаж: {floor}\n"
        f"Лучший этаж: {player['dungeon_rating']}\n\n"
        "Побеждай врагов и поднимайся всё выше!"
    )
    if is_active:
        keyboard = [
            [InlineKeyboardButton("⚔️ Продолжить бой", callback_data="dungeon_continue")],
            [InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("🚪 Войти в подземелье", callback_data="dungeon_start")],
            [InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")],
        ]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def cb_dungeon_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    result = start_dungeon_logic(chat.id, user.id)
    if not result:
        await query.answer("Не удалось начать подземелье.", show_alert=True)
        return

    text = (
        f"🏰 Подземелье — этаж {result['floor']}\n\n"
        f"Ты встречаешь {result['enemy_emoji']} {result['enemy_name']}\n"
        f"❤️ HP врага: {result['enemy_health']}/{result['enemy_max_health']}\n"
        f"⚔️ Урон врага: {result['enemy_damage']}\n\n"
        "Твои действия?"
    )
    keyboard = [
        [InlineKeyboardButton("⚔️ Атаковать", callback_data="attack")],
        [InlineKeyboardButton("🧪 Зелье", callback_data="use_potion")],
        [InlineKeyboardButton("🏃 Сбежать", callback_data="escape")],
    ]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def cb_dungeon_continue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    battle = get_active_battle(chat.id, user.id)
    if not battle or not battle["is_dungeon"]:
        await query.answer("Нет активного боя в подземелье.", show_alert=True)
        return

    enemy = ENEMIES.get(battle["enemy_id"], {"name": "Враг", "emoji": "❓"})
    text = (
        "⚔️ Бой в подземелье\n\n"
        f"{enemy['emoji']} {enemy['name']}\n"
        f"❤️ HP врага: {battle['enemy_health']}/{battle['enemy_max_health']}\n"
        f"Твой HP: {battle['player_health']}/{battle['player_max_health']}\n\n"
        "Твои действия?"
    )
    keyboard = [
        [InlineKeyboardButton("⚔️ Атаковать", callback_data="attack")],
        [InlineKeyboardButton("🧪 Зелье", callback_data="use_potion")],
        [InlineKeyboardButton("🏃 Сбежать", callback_data="escape")],
    ]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ------ ПВП (меню и бой) ------


async def cb_pvp_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    player = get_player(chat.id, user.id)
    if not player:
        await query.answer("Сначала создай персонажа.", show_alert=True)
        return

    add_pvp_queue(chat.id, user.id)
    confirm_pvp_search(chat.id, user.id)

    text = (
        "⚔️ ПВП АРЕНА\n\n"
        "🔍 Поиск противника начат.\n\n"
        "Нажимай «⏸️ Проверить снова», пока не будет найден соперник.\n"
        "Противники ищутся глобально среди всех игроков бота."
    )
    keyboard = [
        [InlineKeyboardButton("⏸️ Проверить снова", callback_data="pvp_check")],
        [InlineKeyboardButton("❌ Отмена", callback_data="pvp_cancel")],
        [InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")],
    ]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def cb_pvp_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    opponent = find_pvp_opponent(chat.id, user.id)
    if not opponent:
        text = (
            "⚔️ ПВП АРЕНА\n\n"
            "❌ Пока нет подходящего противника.\n\n"
            "Подожди немного и нажми «⏸️ Проверить снова»."
        )
        keyboard = [
            [InlineKeyboardButton("⏸️ Проверить снова", callback_data="pvp_check")],
            [InlineKeyboardButton("❌ Отмена", callback_data="pvp_cancel")],
            [InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")],
        ]
    else:
        cls = CLASSES.get(opponent["class"], CLASSES["warrior"])
        reward = max(1, int(opponent["gold"] * 0.1))
        text = (
            "⚔️ ПВП АРЕНА\n\n"
            "🎯 Противник найден!\n\n"
            f"{cls['emoji']} {opponent['username']}\n"
            f"🏅 Уровень: {opponent['level']}\n"
            f"⚔️ Атака: {opponent['attack']}\n"
            f"🛡️ Защита: {opponent['defense']}\n"
            f"💰 Примерная награда: {reward}\n\n"
            "Нажми «⚔️ Начать бой», чтобы начать сражение."
        )
        keyboard = [
            [
                InlineKeyboardButton(
                    "⚔️ Начать бой",
                    callback_data=f"pvp_start_{opponent['user_id']}_{opponent['chat_id']}",
                )
            ],
            [InlineKeyboardButton("❌ Отмена", callback_data="pvp_cancel")],
            [InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")],
        ]

        # помечаем обоих как не ожидающих
        conn = get_db()
        c = conn.cursor()
        c.execute(
            "UPDATE pvp_queue SET is_waiting = 0 WHERE user_id IN (?, ?)",
            (user.id, opponent["user_id"]),
        )
        conn.commit()
        conn.close()

    try:
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Ошибка редактирования ПВП сообщения: {e}")
        await query.answer("Статус не изменился.", show_alert=False)


async def cb_pvp_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    cancel_pvp_search(chat.id, user.id)
    text = "❌ Поиск ПВП противника отменён."
    keyboard = [[InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")]]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def cb_pvp_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    data = query.data.replace("pvp_start_", "")
    parts = data.split("_")
    if len(parts) != 2:
        await query.answer("Ошибка данных ПВП.", show_alert=True)
        return

    defender_id = int(parts[0])
    defender_chat_id = int(parts[1])

    result = pvp_battle(chat.id, user.id, defender_id)
    if not result.get("success"):
        await query.answer(result.get("message", "Ошибка ПВП."), show_alert=True)
        return

    attacker = get_player(chat.id, user.id)
    defender = get_player(defender_chat_id, defender_id)

    if result["winner_id"] == user.id:
        text_attacker = (
            "⚔️ ПВП БОЙ\n\n"
            "🎉 ПОБЕДА!\n\n"
            f"Ты победил {defender['username']}!\n"
            f"Твой урон: {result['attacker_damage']}"
            f"{' (крит)' if result['attacker_crit'] else ''}\n"
            f"Получено урона: {result['defender_damage']}"
            f"{' (крит)' if result['defender_crit'] else ''}\n\n"
            f"💰 Награда: +{result['reward_gold']} золота."
        )
        text_defender = (
            "⚔️ ПВП БОЙ\n\n"
            "💀 ПОРАЖЕНИЕ\n\n"
            f"Тебя победил {attacker['username']}.\n"
            f"Твой урон: {result['defender_damage']}"
            f"{' (крит)' if result['defender_crit'] else ''}\n"
            f"Получено урона: {result['attacker_damage']}"
            f"{' (крит)' if result['attacker_crit'] else ''}\n\n"
            f"💸 Потеряно: -{result['reward_gold']} золота."
        )
    else:
        text_attacker = (
            "⚔️ ПВП БОЙ\n\n"
            "💀 ПОРАЖЕНИЕ\n\n"
            f"Тебя победил {defender['username']}.\n"
            f"Твой урон: {result['attacker_damage']}"
            f"{' (крит)' if result['attacker_crit'] else ''}\n"
            f"Получено урона: {result['defender_damage']}"
            f"{' (крит)' if result['defender_crit'] else ''}\n\n"
            f"💸 Потеряно: -{result['reward_gold']} золота."
        )
        text_defender = (
            "⚔️ ПВП БОЙ\n\n"
            "🎉 ПОБЕДА!\n\n"
            f"Ты победил {attacker['username']}!\n"
            f"Твой урон: {result['defender_damage']}"
            f"{' (крит)' if result['defender_crit'] else ''}\n"
            f"Получено урона: {result['attacker_damage']}"
            f"{' (крит)' if result['attacker_crit'] else ''}\n\n"
            f"💰 Награда: +{result['reward_gold']} золота."
        )

    keyboard = [[InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")]]

    await query.edit_message_text(
        text_attacker, reply_markup=InlineKeyboardMarkup(keyboard)
    )

    try:
        await context.bot.send_message(
            chat_id=defender_chat_id,
            text=text_defender,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    except Exception as e:
        logger.error(f"Не удалось отправить ПВП результат противнику: {e}")


# ------ Рейтинги ------


async def cb_ratings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    text = (
        "🏆 Рейтинги\n\n"
        "Выбери таблицу:"
    )
    keyboard = [
        [
            InlineKeyboardButton("🌍 Общий рейтинг", callback_data="rating_global"),
        ],
        [
            InlineKeyboardButton("⚔️ ПВП рейтинг", callback_data="rating_pvp"),
        ],
        [
            InlineKeyboardButton("🏰 Рейтинг подземелий", callback_data="rating_dungeon"),
        ],
        [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")],
    ]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def cb_rating_global(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat

    leaders = get_global_leaderboard(chat.id, 10)
    player = get_player(chat.id, user.id)
    pos = get_player_position(chat.id, user.id)

    if not leaders:
        text = "Пока нет игроков в рейтинге."
    else:
        lines = ["🏆 Глобальный рейтинг\n", "№  Игрок               Ур.   💰Золото"]
        for i, leader in enumerate(leaders, start=1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            name = (leader["username"] or "Безымянный")[:16].ljust(16)
            lvl = str(leader["level"]).rjust(2)
            gold = str(leader["gold"]).rjust(6)
            lines.append(f"{medal} {name}  {lvl}   {gold}")
        if player:
            lines.append("")
            lines.append(
                f"Ты: #{pos} {player['username']} (ур. {player['level']}, золото {player['gold']})"
            )
        text = "\n".join(lines)

    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="ratings")]]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def cb_rating_pvp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat = query.message.chat

    leaders = get_pvp_leaderboard(chat.id, 10)
    if not leaders:
        text = "ПВП рейтинг пока пуст."
    else:
        lines = ["⚔️ ПВП рейтинг\n", "№  Игрок               W   L  WR%"]
        for i, leader in enumerate(leaders, start=1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            name = (leader["username"] or "Безымянный")[:16].ljust(16)
            w = str(leader["pvp_wins"]).rjust(3)
            l = str(leader["pvp_losses"]).rjust(3)
            wr = str(leader["winrate"]).rjust(4)
            lines.append(f"{medal} {name} {w} {l} {wr}")
        text = "\n".join(lines)

    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="ratings")]]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def cb_rating_dungeon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat = query.message.chat

    leaders = get_dungeon_leaderboard(chat.id, 10)
    if not leaders:
        text = "Рейтинг подземелий пока пуст."
    else:
        lines = ["🏰 Рейтинг подземелий\n", "№  Игрок               Этаж  Боссы"]
        for i, leader in enumerate(leaders, start=1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            name = (leader["username"] or "Безымянный")[:16].ljust(16)
            floor = str(leader["dungeon_rating"]).rjust(4)
            bosses = str(leader["total_bosses_killed"]).rjust(3)
            lines.append(f"{medal} {name}  {floor}  {bosses}")
        text = "\n".join(lines)

    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="ratings")]]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ===================== FASTAPI ДЛЯ RENDER (PORT BINDING) =====================

api_app = FastAPI()


@api_app.get("/")
async def root():
    return {"status": "ok", "message": "RuneQuestRPG bot is running"}


@api_app.get("/health")
async def health():
    return {"status": "healthy"}


# ===================== ЗАПУСК БОТА И СЕРВЕРА =====================


def run_fastapi():
    uvicorn.run(api_app, host="0.0.0.0", port=PORT, log_level="info")


def main():
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

    init_database()

    # запускаем FastAPI-сервер в фоне (для Render Web Service port binding)
    threading.Thread(target=run_fastapi, daemon=True).start()
    logger.info(f"📡 FastAPI server started on 0.0.0.0:{PORT}")

    application = Application.builder().token(BOT_TOKEN).build()

    # Команда /start
    application.add_handler(CommandHandler("start", cmd_start))

    # Главное меню и базовые колбеки
    application.add_handler(CallbackQueryHandler(cb_select_class, pattern=r"^class_"))
    application.add_handler(CallbackQueryHandler(show_main_menu, pattern=r"^main_menu$"))
    application.add_handler(CallbackQueryHandler(cb_profile, pattern=r"^profile$"))
    application.add_handler(CallbackQueryHandler(cb_inventory, pattern=r"^inventory$"))

    # Локации и бой
    application.add_handler(CallbackQueryHandler(cb_locations, pattern=r"^locations$"))
    application.add_handler(CallbackQueryHandler(cb_select_location, pattern=r"^loc_"))
    application.add_handler(CallbackQueryHandler(cb_attack, pattern=r"^attack$"))
    application.add_handler(CallbackQueryHandler(cb_use_potion, pattern=r"^use_potion$"))
    application.add_handler(CallbackQueryHandler(cb_escape, pattern=r"^escape$"))

    # Подземелья
    application.add_handler(CallbackQueryHandler(cb_dungeon_menu, pattern=r"^dungeon$"))
    application.add_handler(CallbackQueryHandler(cb_dungeon_start, pattern=r"^dungeon_start$"))
    application.add_handler(CallbackQueryHandler(cb_dungeon_continue, pattern=r"^dungeon_continue$"))

    # ПВП
    application.add_handler(CallbackQueryHandler(cb_pvp_menu, pattern=r"^pvp_menu$"))
    application.add_handler(CallbackQueryHandler(cb_pvp_check, pattern=r"^pvp_check$"))
    application.add_handler(CallbackQueryHandler(cb_pvp_cancel, pattern=r"^pvp_cancel$"))
    application.add_handler(CallbackQueryHandler(cb_pvp_start, pattern=r"^pvp_start_\d+_\d+$"))

    # Рейтинги
    application.add_handler(CallbackQueryHandler(cb_ratings_menu, pattern=r"^ratings$"))
    application.add_handler(CallbackQueryHandler(cb_rating_global, pattern=r"^rating_global$"))
    application.add_handler(CallbackQueryHandler(cb_rating_pvp, pattern=r"^rating_pvp$"))
    application.add_handler(CallbackQueryHandler(cb_rating_dungeon, pattern=r"^rating_dungeon$"))

    logger.info("✅ RuneQuestRPG bot запущен. Ожидаем апдейты...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
