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
    total_bosses_killed INTEGER DEFAULT 0,
    total_raids_completed INTEGER DEFAULT 0,
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

cursor.execute('''
CREATE TABLE IF NOT EXISTS quests (
    chat_id INTEGER, user_id INTEGER, quest_id TEXT,
    quest_type TEXT, completed_at TIMESTAMP,
    PRIMARY KEY (chat_id, user_id, quest_id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS skills (
    chat_id INTEGER, user_id INTEGER, skill_id TEXT,
    skill_level INTEGER DEFAULT 1,
    PRIMARY KEY (chat_id, user_id, skill_id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS guilds (
    guild_id TEXT PRIMARY KEY, guild_name TEXT, leader_id INTEGER,
    gold INTEGER DEFAULT 0, level INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS guild_members (
    guild_id TEXT, user_id INTEGER, chat_id INTEGER,
    role TEXT DEFAULT 'member',
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, user_id, chat_id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS pvp_stats (
    chat_id INTEGER, user_id INTEGER,
    rating INTEGER DEFAULT 1000, wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0,
    PRIMARY KEY (chat_id, user_id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS crafting_materials (
    chat_id INTEGER, user_id INTEGER, material_id TEXT,
    quantity INTEGER DEFAULT 0,
    PRIMARY KEY (chat_id, user_id, material_id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS battles (
    chat_id INTEGER, user_id INTEGER,
    enemy_id TEXT, enemy_health INTEGER, player_health INTEGER,
    PRIMARY KEY (chat_id, user_id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS raids (
    chat_id INTEGER, user_id INTEGER,
    raid_id TEXT, wave INTEGER, wave_progress INTEGER,
    PRIMARY KEY (chat_id, user_id, raid_id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS item_enchantments (
    chat_id INTEGER, user_id INTEGER, item_id TEXT,
    enchantment_level INTEGER DEFAULT 0,
    PRIMARY KEY (chat_id, user_id, item_id)
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
    "ancient_dragon": {"name": "Древний Дракон", "emoji": "👹", "damage_bonus": 40, "defense_bonus": 15, "xp_bonus": 2.0},
    "celestial_phoenix": {"name": "Небесный Феникс", "emoji": "✨", "damage_bonus": 35, "defense_bonus": 12, "xp_bonus": 1.9},
}

# ========== ВРАГИ ==========

ENEMIES = {
    # Обычные враги (1-3 уровня)
    "goblin": {"name": "Гоблин", "emoji": "👹", "level": 1, "health": 15, "damage": 3, "xp": 25, "gold": 10, "loot": ["copper_coin"], "is_boss": False},
    "rat": {"name": "Крыса", "emoji": "🐭", "level": 1, "health": 10, "damage": 2, "xp": 15, "gold": 5, "loot": ["copper_coin"], "is_boss": False},
    "skeleton": {"name": "Скелет", "emoji": "☠️", "level": 2, "health": 25, "damage": 5, "xp": 40, "gold": 20, "loot": ["bone_fragment"], "is_boss": False},
    "zombie": {"name": "Зомби", "emoji": "🧟", "level": 2, "health": 30, "damage": 6, "xp": 50, "gold": 25, "loot": ["rotten_flesh"], "is_boss": False},
    "imp": {"name": "Чертёнок", "emoji": "😈", "level": 2, "health": 20, "damage": 7, "xp": 45, "gold": 15, "loot": ["sulfur"], "is_boss": False},
    
    # Усиленные враги (3-4 уровня)
    "orc": {"name": "Орк", "emoji": "🗡️", "level": 3, "health": 45, "damage": 12, "xp": 100, "gold": 50, "loot": ["iron_ore"], "is_boss": False},
    "troll": {"name": "Тролль", "emoji": "👹", "level": 3, "health": 60, "damage": 11, "xp": 110, "gold": 60, "loot": ["troll_club", "cave_pearl"], "is_boss": False},
    "werewolf": {"name": "Оборотень", "emoji": "🐺", "level": 4, "health": 50, "damage": 15, "xp": 130, "gold": 70, "loot": ["wolf_fur", "silver_coin"], "is_boss": False},
    "shadow_knight": {"name": "Рыцарь Теней", "emoji": "⚔️", "level": 4, "health": 65, "damage": 18, "xp": 150, "gold": 80, "loot": ["dark_crystal", "iron_sword"], "is_boss": False},
    "witch": {"name": "Ведьма", "emoji": "🧙‍♀️", "level": 4, "health": 40, "damage": 20, "xp": 140, "gold": 75, "loot": ["magic_dust", "cursed_potion"], "is_boss": False},
    
    # Редкие враги (5-6 уровня)
    "basilisk": {"name": "Василиск", "emoji": "🐍", "level": 5, "health": 100, "damage": 25, "xp": 200, "gold": 120, "loot": ["basilisk_fang", "poison_vial"], "is_boss": False},
    "ice_mage": {"name": "Ледяной маг", "emoji": "❄️", "level": 5, "health": 55, "damage": 28, "xp": 180, "gold": 110, "loot": ["ice_crystal", "mana_potion"], "is_boss": False},
    "demon": {"name": "Демон", "emoji": "😈", "level": 6, "health": 120, "damage": 32, "xp": 250, "gold": 150, "loot": ["demonic_essence", "soul_fragment"], "is_boss": False},
    "golem": {"name": "Голем", "emoji": "🪨", "level": 6, "health": 150, "damage": 20, "xp": 220, "gold": 140, "loot": ["stone_heart", "magical_core"], "is_boss": False},
    
    # БОССЫ (7-10 уровня)
    "dragon": {"name": "Дракон", "emoji": "🐉", "level": 7, "health": 200, "damage": 40, "xp": 500, "gold": 300, "loot": ["dragon_scale", "dragon_heart"], "is_boss": True},
    "lich": {"name": "Лич", "emoji": "💀", "level": 8, "health": 180, "damage": 45, "xp": 550, "gold": 350, "loot": ["soul_essence", "lich_staff"], "is_boss": True},
    "archidemon": {"name": "Архидемон", "emoji": "😈", "level": 9, "health": 250, "damage": 50, "xp": 700, "gold": 400, "loot": ["demonic_core", "eternal_essence"], "is_boss": True},
    "lich_king": {"name": "Истинный Лич-Король", "emoji": "👿", "level": 10, "health": 300, "damage": 60, "xp": 1000, "gold": 500, "loot": ["king_crown", "eternal_staff"], "is_boss": True},
}

# ========== МАГАЗИН ==========

SHOP_ITEMS = {
    "health_potion": {"name": "Зелье здоровья", "emoji": "❤️", "price": 50, "rarity": "common", "class": None},
    "mana_potion": {"name": "Зелье маны", "emoji": "💙", "price": 50, "rarity": "common", "class": None},
    "strength_potion": {"name": "Зелье силы", "emoji": "💪", "price": 100, "rarity": "uncommon", "class": None},
    "wisdom_elixir": {"name": "Эликсир мудрости", "emoji": "🧠", "price": 200, "rarity": "rare", "class": None},
    
    "iron_sword": {"name": "Железный меч", "emoji": "⚔️", "price": 200, "rarity": "uncommon", "class": "warrior", "attack": 5},
    "steel_armor": {"name": "Стальная броня", "emoji": "🛡️", "price": 250, "rarity": "uncommon", "class": "warrior", "defense": 4},
    "legendary_sword": {"name": "Меч Вечности", "emoji": "⚡", "price": 5000, "rarity": "legendary", "class": "warrior", "attack": 50},
    
    "fireball_staff": {"name": "Посох огня", "emoji": "🔥", "price": 200, "rarity": "rare", "class": "mage", "attack": 8},
    "mage_robe": {"name": "Мантия мага", "emoji": "👗", "price": 150, "rarity": "uncommon", "class": "mage", "mana": 20},
    "archimage_staff": {"name": "Посох Архимага", "emoji": "🔮", "price": 5000, "rarity": "legendary", "class": "mage", "attack": 30, "mana": 100},
    
    "dagger_set": {"name": "Набор кинжалов", "emoji": "🗡️", "price": 180, "rarity": "uncommon", "class": "rogue", "attack": 6},
    "shadow_cloak": {"name": "Плащ теней", "emoji": "⚫", "price": 220, "rarity": "rare", "class": "rogue", "defense": 3, "attack": 2},
    
    "holy_shield": {"name": "Святой щит", "emoji": "⛪", "price": 300, "rarity": "rare", "class": "paladin", "defense": 6},
    "blessed_armor": {"name": "Благословенная брония", "emoji": "✨", "price": 280, "rarity": "rare", "class": "paladin", "defense": 5, "health": 20},
    "titan_shield": {"name": "Щит Титана", "emoji": "🛡️", "price": 5000, "rarity": "legendary", "class": "paladin", "defense": 40},
    
    "longbow": {"name": "Длинный лук", "emoji": "🏹", "price": 220, "rarity": "uncommon", "class": "ranger", "attack": 7},
    "ranger_armor": {"name": "Лёгкая броня рейнджера", "emoji": "🧥", "price": 180, "rarity": "uncommon", "class": "ranger", "defense": 3, "attack": 2},
    "moon_bow": {"name": "Лук Луны", "emoji": "🏹", "price": 5000, "rarity": "legendary", "class": "ranger", "attack": 40},
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
    "demonic_core": {"name": "Демонический ядро", "rarity": "legendary", "emoji": "🔴"},
    "eternal_essence": {"name": "Вечная сущность", "rarity": "legendary", "emoji": "✨"},
    "king_crown": {"name": "Корона Короля", "rarity": "legendary", "emoji": "👑"},
    "eternal_staff": {"name": "Вечный посох", "rarity": "legendary", "emoji": "🔮"},
}

MATERIALS = {
    "copper_ingot": {"name": "Медный слиток", "emoji": "🟠", "rarity": "common"},
    "iron_ingot": {"name": "Железный слиток", "emoji": "⚫", "rarity": "uncommon"},
    "mithril_ingot": {"name": "Мифриловый слиток", "emoji": "💙", "rarity": "rare"},
    "adamantite": {"name": "Адамантит", "emoji": "⚪", "rarity": "rare"},
    "enchanted_dust": {"name": "Чарованная пыль", "emoji": "✨", "rarity": "rare"},
    "void_essence": {"name": "Сущность пустоты", "emoji": "🌌", "rarity": "legendary"},
    "celestial_stone": {"name": "Небесный камень", "emoji": "⭐", "rarity": "legendary"},
}

# ========== УМЕНИЯ ==========

SKILLS = {
    # Маг
    "fireball": {"name": "Огненный шар", "emoji": "🔥", "type": "mage", "damage_multiplier": 1.5, "cost": 15},
    "frost_nova": {"name": "Ледяная nova", "emoji": "❄️", "type": "mage", "damage_multiplier": 1.4, "cost": 15},
    "chain_lightning": {"name": "Цепная молния", "emoji": "⚡", "type": "mage", "damage_multiplier": 1.6, "cost": 20},
    "meteor_shower": {"name": "Метеоритный дождь", "emoji": "☄️", "type": "mage", "damage_multiplier": 2.0, "cost": 30},
    "teleport": {"name": "Телепортация", "emoji": "🌀", "type": "mage", "damage_multiplier": 0.5, "cost": 25},
    "time_vortex": {"name": "Временной вихрь", "emoji": "⏳", "type": "mage", "damage_multiplier": 1.8, "cost": 35},
    
    # Воин
    "power_strike": {"name": "Мощный удар", "emoji": "💥", "type": "warrior", "damage_multiplier": 1.8, "cost": 10},
    "whirlwind": {"name": "Смерч атак", "emoji": "🌪️", "type": "warrior", "damage_multiplier": 1.7, "cost": 15},
    "battle_cry": {"name": "Боевой клич", "emoji": "📣", "type": "warrior", "damage_multiplier": 1.5, "cost": 10},
    "invulnerability": {"name": "Неуязвимость", "emoji": "🛡️", "type": "warrior", "damage_multiplier": 0.3, "cost": 20},
    
    # Разбойник
    "backstab": {"name": "Удар в спину", "emoji": "🗡️", "type": "rogue", "damage_multiplier": 2.0, "cost": 12},
    "invisibility": {"name": "Невидимость", "emoji": "👻", "type": "rogue", "damage_multiplier": 0.0, "cost": 15},
    "trap": {"name": "Ловушки", "emoji": "🪤", "type": "rogue", "damage_multiplier": 1.3, "cost": 10},
    "deadly_strike": {"name": "Смертельный удар", "emoji": "💀", "type": "rogue", "damage_multiplier": 2.5, "cost": 25},
    
    # Паладин
    "shield_bash": {"name": "Удар щитом", "emoji": "🛡️", "type": "paladin", "damage_multiplier": 1.5, "cost": 12},
    "holy_shield": {"name": "Святой щит", "emoji": "⛪", "type": "paladin", "damage_multiplier": 0.5, "cost": 15},
    "resurrection": {"name": "Воскрешение", "emoji": "✨", "type": "paladin", "damage_multiplier": 0.0, "cost": 40},
    "divine_ray": {"name": "Божественный луч", "emoji": "☀️", "type": "paladin", "damage_multiplier": 1.8, "cost": 20},
    
    # Рейнджер
    "multi_shot": {"name": "Множественный выстрел", "emoji": "🏹", "type": "ranger", "damage_multiplier": 1.6, "cost": 14},
    "animal_capture": {"name": "Ловля животных", "emoji": "🦁", "type": "ranger", "damage_multiplier": 0.8, "cost": 10},
    "ice_trap": {"name": "Ловушка льда", "emoji": "❄️", "type": "ranger", "damage_multiplier": 1.2, "cost": 12},
    "pet_summon": {"name": "Призыв питомца", "emoji": "🐾", "type": "ranger", "damage_multiplier": 1.4, "cost": 18},
}

# ========== РЕЦЕПТЫ ==========

RECIPES = {
    "iron_sword_recipe": {
        "name": "Рецепт: Железный меч",
        "emoji": "⚔️",
        "materials": {"iron_ingot": 5},
        "result": "iron_sword",
        "level_required": 5
    },
    "mithril_armor_recipe": {
        "name": "Рецепт: Мифриловая броня",
        "emoji": "🛡️",
        "materials": {"mithril_ingot": 8, "enchanted_dust": 3},
        "result": "mithril_armor",
        "level_required": 15
    },
    "strength_potion_recipe": {
        "name": "Рецепт: Зелье силы",
        "emoji": "💪",
        "materials": {"sulfur": 3, "magical_core": 1},
        "result": "strength_potion",
        "level_required": 10
    },
    "eternal_ring_recipe": {
        "name": "Рецепт: Кольцо Вечности",
        "emoji": "💍",
        "materials": {"eternal_essence": 5, "adamantite": 10},
        "result": "eternal_ring",
        "level_required": 40
    },
}

# ========== РЕЙДЫ ==========

RAIDS = {
    "abandoned_ruins": {
        "name": "Заброшенные развалины",
        "emoji": "🏚️",
        "level": 5,
        "waves": 3,
        "bosses_in_raid": 0,
        "xp_reward": 1000,
        "gold_reward": 500,
        "loot": ["iron_ingot", "enchanted_dust"]
    },
    "werewolf_fortress": {
        "name": "Крепость оборотней",
        "emoji": "🏰",
        "level": 7,
        "waves": 4,
        "bosses_in_raid": 1,
        "xp_reward": 1500,
        "gold_reward": 750,
        "loot": ["mithril_ingot", "dark_crystal", "dragon_scale"]
    },
    "black_palace": {
        "name": "Чёрный дворец",
        "emoji": "👑",
        "level": 9,
        "waves": 5,
        "bosses_in_raid": 2,
        "xp_reward": 2500,
        "gold_reward": 1000,
        "loot": ["adamantite", "soul_essence", "eternal_essence"]
    },
    "abyss": {
        "name": "Абисс",
        "emoji": "🌌",
        "level": 11,
        "waves": 6,
        "bosses_in_raid": 3,
        "xp_reward": 4000,
        "gold_reward": 1500,
        "loot": ["celestial_stone", "void_essence", "king_crown"]
    },
}

# ========== ЕЖЕДНЕВНЫЕ КВЕСТЫ ==========

DAILY_QUESTS = {
    "kill_5_enemies": {"name": "Убить 5 врагов", "emoji": "⚔️", "target": 5, "reward_xp": 200, "reward_gold": 150},
    "kill_10_enemies": {"name": "Убить 10 врагов", "emoji": "⚔️", "target": 10, "reward_xp": 400, "reward_gold": 300},
    "collect_rare_items": {"name": "Собрать 3 редких предмета", "emoji": "💎", "target": 3, "reward_xp": 250, "reward_gold": 200},
    "deal_damage": {"name": "Нанести 500 урона", "emoji": "💥", "target": 500, "reward_xp": 300, "reward_gold": 250},
    "earn_gold": {"name": "Заработать 1000 золота", "emoji": "💰", "target": 1000, "reward_xp": 350, "reward_gold": 200},
}

# ========== ЕЖЕНЕДЕЛЬНЫЕ КВЕСТЫ ==========

WEEKLY_QUESTS = {
    "kill_boss": {"name": "Убить босса", "emoji": "👹", "target": 1, "reward_xp": 1000, "reward_gold": 500},
    "complete_3_raids": {"name": "Пройти 3 рейда", "emoji": "🏰", "target": 3, "reward_xp": 1500, "reward_gold": 750},
    "earn_10000_gold": {"name": "Заработать 10000 золота", "emoji": "💰", "target": 10000, "reward_xp": 1200, "reward_gold": 500},
    "craft_5_items": {"name": "Создать 5 предметов", "emoji": "🔨", "target": 5, "reward_xp": 800, "reward_gold": 400},
}

# ========== ДОСТИЖЕНИЯ ==========

ACHIEVEMENTS = {
    "hunter_10": {"name": "Охотник", "emoji": "⚔️", "description": "Убей 10 врагов", "target": 10, "reward": 100},
    "hunter_50": {"name": "Опытный охотник", "emoji": "⚔️", "description": "Убей 50 врагов", "target": 50, "reward": 500},
    "hunter_100": {"name": "Мастер охоты", "emoji": "⚔️", "description": "Убей 100 врагов", "target": 100, "reward": 1000},
    "hunter_500": {"name": "Легенда охоты", "emoji": "⚔️", "description": "Убей 500 врагов", "target": 500, "reward": 5000},
    
    "rich_1000": {"name": "Богач", "emoji": "💰", "description": "Накопи 1000 золота", "target": 1000, "reward": 200},
    "rich_5000": {"name": "Мультимиллионер", "emoji": "💰", "description": "Накопи 5000 золота", "target": 5000, "reward": 1000},
    "rich_10000": {"name": "Король золота", "emoji": "💰", "description": "Накопи 10000 золота", "target": 10000, "reward": 5000},
    "rich_50000": {"name": "Божество богатства", "emoji": "💰", "description": "Накопи 50000 золота", "target": 50000, "reward": 10000},
    
    "scholar_3": {"name": "Ученик", "emoji": "📚", "description": "Выучи 3 умения", "target": 3, "reward": 150},
    "scholar_7": {"name": "Учёный", "emoji": "📚", "description": "Выучи 7 умений", "target": 7, "reward": 500},
    "scholar_10": {"name": "Мастер магии", "emoji": "📚", "description": "Выучи 10 умений", "target": 10, "reward": 1500},
    
    "collector_5": {"name": "Коллекционер", "emoji": "🎁", "description": "Собери 5 редких предметов", "target": 5, "reward": 200},
    "collector_15": {"name": "Серьёзный коллекционер", "emoji": "🎁", "description": "Собери 15 редких предметов", "target": 15, "reward": 800},
    "collector_30": {"name": "Мастер сбора", "emoji": "🎁", "description": "Собери 30 редких предметов", "target": 30, "reward": 2000},
    
    "boss_slayer_3": {"name": "Убийца боссов", "emoji": "👹", "description": "Убей 3 босса", "target": 3, "reward": 500},
    "boss_slayer_10": {"name": "Опытный убийца", "emoji": "👹", "description": "Убей 10 боссов", "target": 10, "reward": 2000},
    "boss_slayer_30": {"name": "Король боссов", "emoji": "👹", "description": "Убей 30 боссов", "target": 30, "reward": 10000},
    
    "hero_level_10": {"name": "Молодой герой", "emoji": "⭐", "description": "Достигни 10 уровня", "target": 10, "reward": 300},
    "hero_level_20": {"name": "Герой", "emoji": "⭐", "description": "Достигни 20 уровня", "target": 20, "reward": 1000},
    "hero_level_30": {"name": "Великий герой", "emoji": "⭐", "description": "Достигни 30 уровня", "target": 30, "reward": 5000},
    "hero_level_50": {"name": "Легендарный герой", "emoji": "⭐", "description": "Достигни 50 уровня", "target": 50, "reward": 20000},
    
    "crafter_10": {"name": "Крафтер", "emoji": "🔨", "description": "Создай 10 предметов", "target": 10, "reward": 200},
    "crafter_50": {"name": "Мастер крафта", "emoji": "🔨", "description": "Создай 50 предметов", "target": 50, "reward": 1000},
    "crafter_100": {"name": "Легендарный кузнец", "emoji": "🔨", "description": "Создай 100 предметов", "target": 100, "reward": 5000},
    
    "pet_master_50": {"name": "Тренер питомцев", "emoji": "🐾", "description": "Прокачай питомца до 50 уровня", "target": 50, "reward": 1000},
    "pet_master_100": {"name": "Мастер питомцев", "emoji": "🐾", "description": "Прокачай питомца до 100 уровня", "target": 100, "reward": 5000},
}

LEVEL_REQUIREMENTS = {i: i * 300 for i in range(1, 51)}

PVP_RANKS = {
    0: {"name": "Новичок", "emoji": "🥚", "min_rating": 0},
    1: {"name": "Адепт", "emoji": "🥈", "min_rating": 1000},
    2: {"name": "Мастер", "emoji": "🥇", "min_rating": 1500},
    3: {"name": "Чемпион", "emoji": "👑", "min_rating": 2000},
    4: {"name": "Легенда", "emoji": "⭐", "min_rating": 2500},
}

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
            "total_bosses_killed": row[18],
            "total_raids_completed": row[19],
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

    while new_level < 50 and new_xp >= LEVEL_REQUIREMENTS.get(new_level + 1, 99999):
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
def add_boss_kill(chat_id, user_id):
    cursor.execute('SELECT total_bosses_killed FROM players WHERE chat_id=? AND user_id=?', (chat_id, user_id))
    row = cursor.fetchone()
    new_kills = (row[0] if row else 0) + 1
    cursor.execute(
        'UPDATE players SET total_bosses_killed=? WHERE chat_id=? AND user_id=?',
        (new_kills, chat_id, user_id),
    )
    conn.commit()
    return new_kills

@safe_db_execute
def add_raid_completion(chat_id, user_id):
    cursor.execute('SELECT total_raids_completed FROM players WHERE chat_id=? AND user_id=?', (chat_id, user_id))
    row = cursor.fetchone()
    new_raids = (row[0] if row else 0) + 1
    cursor.execute(
        'UPDATE players SET total_raids_completed=? WHERE chat_id=? AND user_id=?',
        (new_raids, chat_id, user_id),
    )
    conn.commit()
    return new_raids

@safe_db_execute
def get_top_players(chat_id, limit=10):
    cursor.execute(
        'SELECT user_name, level, total_kills, gold, class FROM players WHERE chat_id=? ORDER BY level DESC, total_kills DESC LIMIT ?',
        (chat_id, limit)
    )
    return cursor.fetchall()

@safe_db_execute
def add_skill(chat_id, user_id, skill_id):
    cursor.execute(
        'SELECT skill_level FROM skills WHERE chat_id=? AND user_id=? AND skill_id=?',
        (chat_id, user_id, skill_id)
    )
    row = cursor.fetchone()
    if row:
        new_level = min(row[0] + 1, 10)
        cursor.execute(
            'UPDATE skills SET skill_level=? WHERE chat_id=? AND user_id=? AND skill_id=?',
            (new_level, chat_id, user_id, skill_id)
        )
    else:
        cursor.execute(
            'INSERT INTO skills VALUES (?, ?, ?, ?)',
            (chat_id, user_id, skill_id, 1)
        )
    conn.commit()

@safe_db_execute
def get_player_skills(chat_id, user_id):
    cursor.execute(
        'SELECT skill_id, skill_level FROM skills WHERE chat_id=? AND user_id=?',
        (chat_id, user_id)
    )
    return {row[0]: row[1] for row in cursor.fetchall()}

@safe_db_execute
def add_material(chat_id, user_id, material_id, quantity=1):
    cursor.execute(
        'SELECT quantity FROM crafting_materials WHERE chat_id=? AND user_id=? AND material_id=?',
        (chat_id, user_id, material_id)
    )
    row = cursor.fetchone()
    if row:
        cursor.execute(
            'UPDATE crafting_materials SET quantity=? WHERE chat_id=? AND user_id=? AND material_id=?',
            (row[0] + quantity, chat_id, user_id, material_id)
        )
    else:
        cursor.execute(
            'INSERT INTO crafting_materials VALUES (?, ?, ?, ?)',
            (chat_id, user_id, material_id, quantity)
        )
    conn.commit()

@safe_db_execute
def get_materials(chat_id, user_id):
    cursor.execute(
        'SELECT material_id, quantity FROM crafting_materials WHERE chat_id=? AND user_id=?',
        (chat_id, user_id)
    )
    return {row[0]: row[1] for row in cursor.fetchall()}

@safe_db_execute
def get_daily_quest_progress(chat_id, user_id):
    cursor.execute(
        'SELECT quest_id FROM quests WHERE chat_id=? AND user_id=? AND quest_type=\'daily\' AND date(completed_at) = date(\'now\')',
        (chat_id, user_id)
    )
    return [row[0] for row in cursor.fetchall()]

@safe_db_execute
def get_weekly_quest_progress(chat_id, user_id):
    cursor.execute(
        'SELECT quest_id FROM quests WHERE chat_id=? AND user_id=? AND quest_type=\'weekly\' AND strftime(\'%W\', completed_at) = strftime(\'%W\', \'now\')',
        (chat_id, user_id)
    )
    return [row[0] for row in cursor.fetchall()]

@safe_db_execute
def complete_quest(chat_id, user_id, quest_id, quest_type='daily'):
    cursor.execute(
        'INSERT OR IGNORE INTO quests VALUES (?, ?, ?, ?, datetime(\'now\'))',
        (chat_id, user_id, quest_id, quest_type)
    )
    conn.commit()

@safe_db_execute
def get_achievement_progress(chat_id, user_id, achievement_id):
    cursor.execute(
        'SELECT progress FROM achievements WHERE user_id=? AND chat_id=? AND achievement_id=?',
        (user_id, chat_id, achievement_id)
    )
    row = cursor.fetchone()
    return row[0] if row else 0

@safe_db_execute
def update_achievement_progress(chat_id, user_id, achievement_id, progress):
    cursor.execute(
        'SELECT progress FROM achievements WHERE user_id=? AND chat_id=? AND achievement_id=?',
        (user_id, chat_id, achievement_id)
    )
    row = cursor.fetchone()
    if row:
        new_progress = max(row[0], progress)
        cursor.execute(
            'UPDATE achievements SET progress=? WHERE user_id=? AND chat_id=? AND achievement_id=?',
            (new_progress, user_id, chat_id, achievement_id)
        )
    else:
        cursor.execute(
            'INSERT INTO achievements VALUES (?, ?, ?, datetime(\'now\'), ?)',
            (user_id, chat_id, achievement_id, progress)
        )
    conn.commit()

@safe_db_execute
def get_pvp_stats(chat_id, user_id):
    cursor.execute(
        'SELECT rating, wins, losses FROM pvp_stats WHERE chat_id=? AND user_id=?',
        (chat_id, user_id)
    )
    row = cursor.fetchone()
    if row:
        return {"rating": row[0], "wins": row[1], "losses": row[2]}
    cursor.execute(
        'INSERT INTO pvp_stats VALUES (?, ?, ?, ?, ?)',
        (chat_id, user_id, 1000, 0, 0)
    )
    conn.commit()
    return {"rating": 1000, "wins": 0, "losses": 0}

@safe_db_execute
def update_pvp_stats(chat_id, user_id, win=True):
    stats = get_pvp_stats(chat_id, user_id)
    rating_change = 50 if win else -30
    new_rating = max(0, stats["rating"] + rating_change)
    new_wins = stats["wins"] + (1 if win else 0)
    new_losses = stats["losses"] + (0 if win else 1)
    cursor.execute(
        'UPDATE pvp_stats SET rating=?, wins=?, losses=? WHERE chat_id=? AND user_id=?',
        (new_rating, new_wins, new_losses, chat_id, user_id)
    )
    conn.commit()
    return new_rating

@safe_db_execute
def start_battle(chat_id, user_id):
    cursor.execute('DELETE FROM battles WHERE chat_id=? AND user_id=?', (chat_id, user_id))
    
    enemy_id = random.choice(list(ENEMIES.keys()))
    enemy_info = ENEMIES[enemy_id]
    
    cursor.execute(
        'INSERT INTO battles VALUES (?, ?, ?, ?, ?)',
        (chat_id, user_id, enemy_id, enemy_info["health"], 0)
    )
    conn.commit()
    return enemy_id

@safe_db_execute
def get_battle(chat_id, user_id):
    cursor.execute('SELECT enemy_id, enemy_health, player_health FROM battles WHERE chat_id=? AND user_id=?', (chat_id, user_id))
    row = cursor.fetchone()
    if row:
        return {"enemy_id": row[0], "enemy_health": row[1], "player_health": row[2]}
    return None

@safe_db_execute
def update_battle(chat_id, user_id, enemy_health, player_health):
    cursor.execute(
        'UPDATE battles SET enemy_health=?, player_health=? WHERE chat_id=? AND user_id=?',
        (enemy_health, player_health, chat_id, user_id)
    )
    conn.commit()

@safe_db_execute
def end_battle(chat_id, user_id):
    cursor.execute('DELETE FROM battles WHERE chat_id=? AND user_id=?', (chat_id, user_id))
    conn.commit()

@safe_db_execute
def start_raid(chat_id, user_id, raid_id):
    cursor.execute('DELETE FROM raids WHERE chat_id=? AND user_id=? AND raid_id=?', (chat_id, user_id, raid_id))
    cursor.execute(
        'INSERT INTO raids VALUES (?, ?, ?, ?, ?)',
        (chat_id, user_id, raid_id, 1, 0)
    )
    conn.commit()

@safe_db_execute
def get_raid_progress(chat_id, user_id, raid_id):
    cursor.execute('SELECT wave, wave_progress FROM raids WHERE chat_id=? AND user_id=? AND raid_id=?', (chat_id, user_id, raid_id))
    row = cursor.fetchone()
    if row:
        return {"wave": row[0], "wave_progress": row[1]}
    return None

@safe_db_execute
def update_raid_progress(chat_id, user_id, raid_id, wave, wave_progress):
    cursor.execute(
        'UPDATE raids SET wave=?, wave_progress=? WHERE chat_id=? AND user_id=? AND raid_id=?',
        (wave, wave_progress, chat_id, user_id, raid_id)
    )
    conn.commit()

@safe_db_execute
def end_raid(chat_id, user_id, raid_id):
    cursor.execute('DELETE FROM raids WHERE chat_id=? AND user_id=? AND raid_id=?', (chat_id, user_id, raid_id))
    conn.commit()

# ========== КОМАНДЫ ==========

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    player = get_player(chat_id, user.id)
    if not player:
        keyboard = []
        for class_id, class_info in CLASSES.items():
            keyboard.append([InlineKeyboardButton(f"{class_info['emoji']} {class_info['name']}", callback_data=f"class_{class_id}")])
        
        reply_text = (
            "⚔️ QUEST WORLD - RPG ПРИКЛЮЧЕНИЕ ⚔️\n\n"
            "Выбери свой класс для начала приключения!\n\n"
            "Каждый класс имеет свои сильные стороны:"
        )
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(reply_text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.message.reply_text(reply_text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        keyboard = [
            [InlineKeyboardButton("⚔️ БОЙ", callback_data="start_battle"), InlineKeyboardButton("📜 КВЕСТЫ", callback_data="show_quests")],
            [InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data="show_profile"), InlineKeyboardButton("⚡ УМЕНИЯ", callback_data="show_skills")],
            [InlineKeyboardButton("🐾 ПИТОМЕЦ", callback_data="show_pet"), InlineKeyboardButton("📦 ИНВЕНТАРЬ", callback_data="show_inventory")],
            [InlineKeyboardButton("🛒 МАГАЗИН", callback_data="show_shop"), InlineKeyboardButton("⚙️ КРАФТ", callback_data="show_crafting")],
            [InlineKeyboardButton("👑 ТОП ИГРОКОВ", callback_data="show_top"), InlineKeyboardButton("🏟️ PVP", callback_data="show_pvp")],
            [InlineKeyboardButton("🏰 РЕЙДЫ", callback_data="show_raids"), InlineKeyboardButton("🎖️ ДОСТИЖЕНИЯ", callback_data="show_achievements")],
        ]

        reply_text = (
            f"⚔️ QUEST WORLD - RPG ПРИКЛЮЧЕНИЕ ⚔️\n\n"
            f"Добро пожаловать, {CLASSES[player['class']]['emoji']} {CLASSES[player['class']]['name']}!\n\n"
            f"Исследуй подземелья, учи умения и становись легендой!"
        )
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(reply_text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.message.reply_text(reply_text, reply_markup=InlineKeyboardMarkup(keyboard))

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
    
    keyboard = [
        [InlineKeyboardButton("🎮 НАЧАТЬ ИГРУ", callback_data="after_class_select")],
        [InlineKeyboardButton("⬅️ ВЫБРАТЬ ДРУГОЙ КЛАСС", callback_data="restart_class_selection")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def restart_class_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    
    with db_lock:
        cursor.execute('DELETE FROM players WHERE chat_id=? AND user_id=?', (chat_id, user_id))
        conn.commit()
    
    keyboard = []
    for class_id, class_info in CLASSES.items():
        keyboard.append([InlineKeyboardButton(f"{class_info['emoji']} {class_info['name']}", callback_data=f"class_{class_id}")])
    
    text = (
        "⚔️ QUEST WORLD - RPG ПРИКЛЮЧЕНИЕ ⚔️\n\n"
        "Выбери свой класс для начала приключения!\n\n"
        "Каждый класс имеет свои сильные стороны:"
    )
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def after_class_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    player = get_player(chat_id, user.id)
    
    keyboard = [
        [InlineKeyboardButton("⚔️ БОЙ", callback_data="start_battle"), InlineKeyboardButton("📜 КВЕСТЫ", callback_data="show_quests")],
        [InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data="show_profile"), InlineKeyboardButton("⚡ УМЕНИЯ", callback_data="show_skills")],
        [InlineKeyboardButton("🐾 ПИТОМЕЦ", callback_data="show_pet"), InlineKeyboardButton("📦 ИНВЕНТАРЬ", callback_data="show_inventory")],
        [InlineKeyboardButton("🛒 МАГАЗИН", callback_data="show_shop"), InlineKeyboardButton("⚙️ КРАФТ", callback_data="show_crafting")],
        [InlineKeyboardButton("👑 ТОП ИГРОКОВ", callback_data="show_top"), InlineKeyboardButton("🏟️ PVP", callback_data="show_pvp")],
        [InlineKeyboardButton("🏰 РЕЙДЫ", callback_data="show_raids"), InlineKeyboardButton("🎖️ ДОСТИЖЕНИЯ", callback_data="show_achievements")],
    ]

    reply_text = (
        f"⚔️ QUEST WORLD - RPG ПРИКЛЮЧЕНИЕ ⚔️\n\n"
        f"Добро пожаловать, {CLASSES[player['class']]['emoji']} {CLASSES[player['class']]['name']}!\n\n"
        f"Исследуй подземелья, учи умения и становись легендой!"
    )
    
    await query.edit_message_text(reply_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id

    player = get_player(chat_id, user.id)
    pet = get_player_pet(chat_id, user.id)
    pet_info = PETS.get(pet["pet_id"], {})
    class_info = CLASSES[player["class"]]

    xp_percent = int((player["xp"] / LEVEL_REQUIREMENTS.get(player["level"] + 1, 99999)) * 100)

    text = (
        f"👤 {user.first_name}\n"
        f"{'─' * 30}\n\n"
        f"{class_info['emoji']} Класс: {class_info['name']}\n"
        f"⭐ Уровень: {player['level']}/50\n"
        f"📊 XP: {player['xp']}/{LEVEL_REQUIREMENTS.get(player['level'] + 1, 99999)} ({xp_percent}%)\n"
        f"{'█' * (xp_percent // 10)}{'░' * (10 - xp_percent // 10)}\n\n"
        f"❤️ HP: {player['health']}/{player['max_health']}\n"
        f"💙 Мана: {player['mana']}/{player['max_mana']}\n"
        f"⚔️ Атака: {player['attack']}\n"
        f"🛡️ Защита: {player['defense']}\n\n"
        f"💰 Золото: {player['gold']}\n"
        f"🐾 Питомец: {pet_info.get('emoji', '❓')} {pet_info.get('name', 'Нет')} (Ур. {pet['pet_level']})\n"
        f"⚔️ Побед: {player['total_kills']}\n"
        f"👹 Боссов убито: {player['total_bosses_killed']}\n"
        f"🏰 Рейдов пройдено: {player['total_raids_completed']}"
    )

    keyboard = [[InlineKeyboardButton("⬅️ НАЗАД", callback_data="main_menu")]]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

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

async def show_quests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    completed = get_daily_quest_progress(chat_id, user.id)
    
    text = "📜 ЕЖЕДНЕВНЫЕ КВЕСТЫ\n" + f"{'─' * 30}\n\n"
    
    keyboard = []
    for quest_id, quest_info in DAILY_QUESTS.items():
        status = "✅" if quest_id in completed else "⬜"
        text += f"{status} {quest_info['emoji']} {quest_info['name']}\n"
        text += f"   Цель: {quest_info['target']} | Награда: +{quest_info['reward_xp']} XP, +{quest_info['reward_gold']} 💰\n\n"
        
        if quest_id not in completed:
            keyboard.append([InlineKeyboardButton(f"✓ {quest_info['emoji']}", callback_data=f"complete_quest_daily_{quest_id}")])
    
    keyboard.append([InlineKeyboardButton("📋 ЕЖЕНЕДЕЛЬНЫЕ", callback_data="show_weekly_quests")])
    keyboard.append([InlineKeyboardButton("⬅️ НАЗАД", callback_data="main_menu")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_weekly_quests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    completed = get_weekly_quest_progress(chat_id, user.id)
    
    text = "📋 ЕЖЕНЕДЕЛЬНЫЕ КВЕСТЫ\n" + f"{'─' * 30}\n\n"
    
    keyboard = []
    for quest_id, quest_info in WEEKLY_QUESTS.items():
        status = "✅" if quest_id in completed else "⬜"
        text += f"{status} {quest_info['emoji']} {quest_info['name']}\n"
        text += f"   Цель: {quest_info['target']} | Награда: +{quest_info['reward_xp']} XP, +{quest_info['reward_gold']} 💰\n\n"
        
        if quest_id not in completed:
            keyboard.append([InlineKeyboardButton(f"✓ {quest_info['emoji']}", callback_data=f"complete_quest_weekly_{quest_id}")])
    
    keyboard.append([InlineKeyboardButton("📜 ЕЖЕДНЕВНЫЕ", callback_data="show_quests")])
    keyboard.append([InlineKeyboardButton("⬅️ НАЗАД", callback_data="main_menu")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def complete_daily_quest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    parts = query.data.split("_")
    quest_type = parts[2]
    quest_id = parts[3]
    
    if quest_type == "daily" and quest_id in DAILY_QUESTS:
        quest = DAILY_QUESTS[quest_id]
        add_xp(chat_id, user.id, user.first_name, quest["reward_xp"])
        add_gold(chat_id, user.id, quest["reward_gold"])
        complete_quest(chat_id, user.id, quest_id, "daily")
        
        text = f"✅ Квест завершён!\n+{quest['reward_xp']} XP\n+{quest['reward_gold']} 💰"
        keyboard = [[InlineKeyboardButton("📜 КВЕСТЫ", callback_data="show_quests"), InlineKeyboardButton("⬅️ МЕНЮ", callback_data="main_menu")]]
    elif quest_type == "weekly" and quest_id in WEEKLY_QUESTS:
        quest = WEEKLY_QUESTS[quest_id]
        add_xp(chat_id, user.id, user.first_name, quest["reward_xp"])
        add_gold(chat_id, user.id, quest["reward_gold"])
        complete_quest(chat_id, user.id, quest_id, "weekly")
        
        text = f"✅ Квест завершён!\n+{quest['reward_xp']} XP\n+{quest['reward_gold']} 💰"
        keyboard = [[InlineKeyboardButton("📋 КВЕСТЫ", callback_data="show_weekly_quests"), InlineKeyboardButton("⬅️ МЕНЮ", callback_data="main_menu")]]
    else:
        text = "❌ Квест не найден"
        keyboard = [[InlineKeyboardButton("⬅️ МЕНЮ", callback_data="main_menu")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_skills(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    player_skills = get_player_skills(chat_id, user.id)
    player = get_player(chat_id, user.id)
    player_class = player["class"]
    
    text = "⚡ УМЕНИЯ\n" + f"{'─' * 30}\n\n"
    
    keyboard = []
    for skill_id, skill_info in SKILLS.items():
        if skill_info["type"] == player_class:
            level = player_skills.get(skill_id, 0)
            text += f"{skill_info['emoji']} {skill_info['name']} (Ур. {level}/10)\n"
            text += f"   Урон: ×{skill_info['damage_multiplier']} | Мана: {skill_info['cost']}\n\n"
            
            if level < 10:
                keyboard.append([InlineKeyboardButton(f"↑ {skill_info['emoji']}", callback_data=f"learn_skill_{skill_id}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ НАЗАД", callback_data="main_menu")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def learn_skill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    skill_id = query.data.split("_")[2]
    
    player = get_player(chat_id, user.id)
    cost = 500 * (len(get_player_skills(chat_id, user.id)) + 1)
    
    if player["gold"] >= cost:
        subtract_gold(chat_id, user.id, cost)
        add_skill(chat_id, user.id, skill_id)
        
        text = f"✅ Умение улучшено!\n-{cost} 💰"
        keyboard = [[InlineKeyboardButton("⚡ УМЕНИЯ", callback_data="show_skills"), InlineKeyboardButton("⬅️ МЕНЮ", callback_data="main_menu")]]
    else:
        text = f"❌ Недостаточно золота!\nНужно: {cost} 💰\nУ тебя: {player['gold']} 💰"
        keyboard = [[InlineKeyboardButton("⚡ УМЕНИЯ", callback_data="show_skills")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_crafting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    player = get_player(chat_id, user.id)
    materials = get_materials(chat_id, user.id)
    
    text = "⚙️ КРАФТ И УЛУЧШЕНИЯ\n" + f"{'─' * 30}\n\n"
    text += f"⭐ Уровень: {player['level']}\n\n"
    text += f"📦 Ваши материалы:\n"
    
    if materials:
        for material_id, qty in materials.items():
            mat_info = MATERIALS.get(material_id, {})
            text += f"  {mat_info.get('emoji', '?')} {mat_info.get('name', material_id)}: {qty}\n"
    else:
        text += "  ❌ Материалов нет\n"
    
    text += f"\n🔨 Доступные рецепты:\n"
    
    keyboard = []
    has_recipes = False
    for recipe_id, recipe_info in RECIPES.items():
        if player["level"] >= recipe_info["level_required"]:
            text += f"  {recipe_info['emoji']} {recipe_info['name']}\n"
            keyboard.append([InlineKeyboardButton(f"Создать {recipe_info['emoji']}", callback_data=f"craft_{recipe_id}")])
            has_recipes = True
    
    if not has_recipes:
        text += "  ❌ Нет доступных рецептов\n"
    
    keyboard.append([InlineKeyboardButton("⬅️ НАЗАД", callback_data="main_menu")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def craft_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    recipe_id = query.data.split("_")[1]
    
    if recipe_id not in RECIPES:
        await query.answer("❌ Рецепт не найден", show_alert=True)
        return
    
    recipe = RECIPES[recipe_id]
    materials = get_materials(chat_id, user.id)
    
    can_craft = True
    for mat_id, needed_qty in recipe["materials"].items():
        if materials.get(mat_id, 0) < needed_qty:
            can_craft = False
            break
    
    if can_craft:
        for mat_id, needed_qty in recipe["materials"].items():
            add_material(chat_id, user.id, mat_id, -needed_qty)
        
        add_item(chat_id, user.id, recipe["result"])
        text = f"✅ Создано: {recipe['emoji']} {recipe['name']}"
        keyboard = [[InlineKeyboardButton("⚙️ КРАФТ", callback_data="show_crafting"), InlineKeyboardButton("⬅️ МЕНЮ", callback_data="main_menu")]]
    else:
        text = f"❌ Недостаточно материалов!\n\nНужно:\n"
        for mat_id, needed_qty in recipe["materials"].items():
            mat_info = MATERIALS.get(mat_id, {})
            current = materials.get(mat_id, 0)
            text += f"{mat_info.get('emoji', '?')} {mat_info.get('name', mat_id)}: {current}/{needed_qty}\n"
        keyboard = [[InlineKeyboardButton("⚙️ КРАФТ", callback_data="show_crafting")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_raids(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    player = get_player(chat_id, user.id)
    
    text = "🏰 РЕЙДЫ И ПОДЗЕМЕЛЬЯ\n" + f"{'─' * 30}\n\n"
    
    keyboard = []
    for raid_id, raid_info in RAIDS.items():
        if player["level"] >= raid_info["level"]:
            text += f"{raid_info['emoji']} {raid_info['name']} (Ур. {raid_info['level']})\n"
            text += f"   Волн: {raid_info['waves']} | Боссов: {raid_info['bosses_in_raid']}\n"
            text += f"   Награда: +{raid_info['xp_reward']} XP, +{raid_info['gold_reward']} 💰\n\n"
            keyboard.append([InlineKeyboardButton(f"Войти {raid_info['emoji']}", callback_data=f"start_raid_{raid_id}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ НАЗАД", callback_data="main_menu")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_achievements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    player = get_player(chat_id, user.id)
    
    text = "🎖️ ДОСТИЖЕНИЯ\n" + f"{'─' * 30}\n\n"
    
    # Обновляем прогресс достижений
    update_achievement_progress(chat_id, user.id, "hunter_10", player["total_kills"])
    update_achievement_progress(chat_id, user.id, "hunter_50", player["total_kills"])
    update_achievement_progress(chat_id, user.id, "hunter_100", player["total_kills"])
    update_achievement_progress(chat_id, user.id, "hunter_500", player["total_kills"])
    
    update_achievement_progress(chat_id, user.id, "rich_1000", player["gold"])
    update_achievement_progress(chat_id, user.id, "rich_5000", player["gold"])
    update_achievement_progress(chat_id, user.id, "rich_10000", player["gold"])
    update_achievement_progress(chat_id, user.id, "rich_50000", player["gold"])
    
    update_achievement_progress(chat_id, user.id, "scholar_3", len(get_player_skills(chat_id, user.id)))
    update_achievement_progress(chat_id, user.id, "scholar_7", len(get_player_skills(chat_id, user.id)))
    update_achievement_progress(chat_id, user.id, "scholar_10", len(get_player_skills(chat_id, user.id)))
    
    update_achievement_progress(chat_id, user.id, "boss_slayer_3", player["total_bosses_killed"])
    update_achievement_progress(chat_id, user.id, "boss_slayer_10", player["total_bosses_killed"])
    update_achievement_progress(chat_id, user.id, "boss_slayer_30", player["total_bosses_killed"])
    
    update_achievement_progress(chat_id, user.id, "hero_level_10", player["level"])
    update_achievement_progress(chat_id, user.id, "hero_level_20", player["level"])
    update_achievement_progress(chat_id, user.id, "hero_level_30", player["level"])
    update_achievement_progress(chat_id, user.id, "hero_level_50", player["level"])
    
    # Показываем достижения
    achievement_count = 0
    for ach_id, ach_info in ACHIEVEMENTS.items():
        progress = get_achievement_progress(chat_id, user.id, ach_id)
        target = ach_info["target"]
        status = "✅" if progress >= target else "⬜"
        
        text += f"{status} {ach_info['emoji']} {ach_info['name']}\n"
        text += f"   {progress}/{target}\n\n"
        achievement_count += 1
        
        if achievement_count >= 5:
            break
    
    keyboard = [[InlineKeyboardButton("⬅️ НАЗАД", callback_data="main_menu")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def start_battle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    player = get_player(chat_id, user.id)
    
    enemy_id = start_battle(chat_id, user.id)
    enemy_info = ENEMIES[enemy_id]
    pet = get_player_pet(chat_id, user.id)
    pet_info = PETS[pet["pet_id"]]
    
    enemy_health = enemy_info["health"] + (player["level"] - 1) * 5
    
    update_battle(chat_id, user.id, enemy_health, player["health"])
    
    text = (
        f"⚔️ БОЙ НАЧАЛАСЬ!\n\n"
        f"👤 Ты: {player['health']}/{player['max_health']} HP\n"
        f"{enemy_info['emoji']} {enemy_info['name']}: {enemy_health} HP\n\n"
        f"🐾 Питомец: {pet_info['emoji']} {pet_info['name']}"
    )
    
    keyboard = [
        [InlineKeyboardButton("⚔️ АТАКОВАТЬ", callback_data="attack_enemy")],
        [InlineKeyboardButton("🏥 ИСЦЕЛИТЬСЯ", callback_data="heal_self")],
        [InlineKeyboardButton("❌ СБЕЖАТЬ", callback_data="flee_battle")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def attack_enemy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    player = get_player(chat_id, user.id)
    battle = get_battle(chat_id, user.id)
    
    if not battle:
        await query.answer("❌ Боя нет!", show_alert=True)
        return
    
    enemy_info = ENEMIES[battle["enemy_id"]]
    pet = get_player_pet(chat_id, user.id)
    pet_info = PETS[pet["pet_id"]]
    
    player_damage = player["attack"] + pet_info["damage_bonus"] + random.randint(-2, 5)
    enemy_damage = enemy_info["damage"] + random.randint(-1, 3)
    
    new_enemy_health = max(0, battle["enemy_health"] - player_damage)
    new_player_health = max(0, player["health"] - enemy_damage)
    
    update_battle(chat_id, user.id, new_enemy_health, new_player_health)
    
    cursor.execute(
        'UPDATE players SET health=? WHERE chat_id=? AND user_id=?',
        (new_player_health, chat_id, user.id)
    )
    conn.commit()
    
    text = (
        f"⚔️ БОЙ\n\n"
        f"💥 Ты нанёс {player_damage} урона!\n"
        f"💔 Враг нанёс {enemy_damage} урона!\n\n"
        f"👤 Твоё здоровье: {new_player_health}/{player['max_health']} HP\n"
        f"{enemy_info['emoji']} Здоровье врага: {new_enemy_health} HP"
    )
    
    if new_enemy_health <= 0:
        xp_reward = enemy_info["xp"]
        gold_reward = enemy_info["gold"]
        
        add_xp(chat_id, user.id, user.first_name, int(xp_reward * 1.2))
        add_gold(chat_id, user.id, gold_reward)
        add_kill(chat_id, user.id)
        
        if enemy_info.get("is_boss"):
            add_boss_kill(chat_id, user.id)
        
        for loot_item in enemy_info.get("loot", []):
            add_item(chat_id, user.id, loot_item)
        
        end_battle(chat_id, user.id)
        
        text = (
            f"🎉 ПОБЕДА!\n\n"
            f"Ты победил {enemy_info['emoji']} {enemy_info['name']}!\n\n"
            f"+{int(xp_reward * 1.2)} XP\n"
            f"+{gold_reward} 💰\n"
            f"Лут: {', '.join([ITEMS[item]['emoji'] + ' ' + ITEMS[item]['name'] for item in enemy_info.get('loot', [])])}"
        )
        
        keyboard = [
            [InlineKeyboardButton("⚔️ НОВЫЙ БОЙ", callback_data="start_battle")],
            [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]
        ]
    elif new_player_health <= 0:
        end_battle(chat_id, user.id)
        
        cursor.execute(
            'UPDATE players SET health=? WHERE chat_id=? AND user_id=?',
            (player["max_health"], chat_id, user.id)
        )
        conn.commit()
        
        text = (
            f"💀 ПОРАЖЕНИЕ!\n\n"
            f"Ты был побеждён {enemy_info['emoji']} {enemy_info['name']}...\n\n"
            f"Твоё здоровье полностью восстановлено."
        )
        
        keyboard = [
            [InlineKeyboardButton("⚔️ НОВЫЙ БОЙ", callback_data="start_battle")],
            [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("⚔️ АТАКОВАТЬ", callback_data="attack_enemy")],
            [InlineKeyboardButton("🏥 ИСЦЕЛИТЬСЯ", callback_data="heal_self")],
            [InlineKeyboardButton("❌ СБЕЖАТЬ", callback_data="flee_battle")]
        ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def heal_self(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    player = get_player(chat_id, user.id)
    battle = get_battle(chat_id, user.id)
    
    if not battle:
        await query.answer("❌ Боя нет!", show_alert=True)
        return
    
    if player["mana"] < 20:
        text = "❌ Недостаточно маны!"
        keyboard = [
            [InlineKeyboardButton("⚔️ АТАКОВАТЬ", callback_data="attack_enemy")],
            [InlineKeyboardButton("🏥 ИСЦЕЛИТЬСЯ", callback_data="heal_self")],
            [InlineKeyboardButton("❌ СБЕЖАТЬ", callback_data="flee_battle")]
        ]
    else:
        heal_amount = 30
        new_player_health = min(player["max_health"], battle["player_health"] + heal_amount)
        new_mana = max(0, player["mana"] - 20)
        
        enemy_info = ENEMIES[battle["enemy_id"]]
        enemy_damage = enemy_info["damage"] + random.randint(-1, 3)
        new_player_health = max(0, new_player_health - enemy_damage)
        
        update_battle(chat_id, user.id, battle["enemy_health"], new_player_health)
        
        cursor.execute(
            'UPDATE players SET health=?, mana=? WHERE chat_id=? AND user_id=?',
            (new_player_health, new_mana, chat_id, user.id)
        )
        conn.commit()
        
        text = (
            f"🏥 ИСЦЕЛЕНИЕ\n\n"
            f"+{heal_amount} HP (исцеление)\n"
            f"-{enemy_damage} HP (атака врага)\n\n"
            f"👤 Твоё здоровье: {new_player_health}/{player['max_health']} HP\n"
            f"{enemy_info['emoji']} Здоровье врага: {battle['enemy_health']} HP"
        )
        
        if new_player_health <= 0:
            end_battle(chat_id, user.id)
            
            cursor.execute(
                'UPDATE players SET health=? WHERE chat_id=? AND user_id=?',
                (player["max_health"], chat_id, user.id)
            )
            conn.commit()
            
            text = (
                f"💀 ПОРАЖЕНИЕ!\n\n"
                f"Ты был побеждён {enemy_info['emoji']} {enemy_info['name']}...\n\n"
                f"Твоё здоровье полностью восстановлено."
            )
            
            keyboard = [
                [InlineKeyboardButton("⚔️ НОВЫЙ БОЙ", callback_data="start_battle")],
                [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("⚔️ АТАКОВАТЬ", callback_data="attack_enemy")],
                [InlineKeyboardButton("🏥 ИСЦЕЛИТЬСЯ", callback_data="heal_self")],
                [InlineKeyboardButton("❌ СБЕЖАТЬ", callback_data="flee_battle")]
            ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def flee_battle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    end_battle(chat_id, user.id)
    
    text = "🏃 Ты сбежал из боя!"
    keyboard = [
        [InlineKeyboardButton("⚔️ НОВЫЙ БОЙ", callback_data="start_battle")],
        [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_pvp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    stats = get_pvp_stats(chat_id, user.id)
    
    rank_info = None
    for rank_id in sorted(PVP_RANKS.keys(), reverse=True):
        if stats["rating"] >= PVP_RANKS[rank_id]["min_rating"]:
            rank_info = PVP_RANKS[rank_id]
            break
    
    text = (
        f"🏟️ PVP СТАТИСТИКА\n"
        f"{'─' * 30}\n\n"
        f"{rank_info['emoji']} Ранг: {rank_info['name']}\n"
        f"⭐ Рейтинг: {stats['rating']}\n"
        f"✅ Победы: {stats['wins']}\n"
        f"❌ Поражения: {stats['losses']}\n\n"
        f"Процент побед: {int(stats['wins'] * 100 / max(stats['wins'] + stats['losses'], 1))}%"
    )
    
    keyboard = [[InlineKeyboardButton("⬅️ НАЗАД", callback_data="main_menu")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def start_raid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    raid_id = query.data.split("_")[2]
    
    if raid_id not in RAIDS:
        await query.answer("❌ Рейд не найден", show_alert=True)
        return
    
    raid_info = RAIDS[raid_id]
    start_raid(chat_id, user.id, raid_id)
    
    text = (
        f"🏰 {raid_info['name'].upper()}\n\n"
        f"Волна: 1/{raid_info['waves']}\n"
        f"Готовься к боям!\n\n"
        f"Враги готовятся атаковать..."
    )
    
    keyboard = [[InlineKeyboardButton("⚔️ НАЧАТЬ ВОЛНУ", callback_data=f"raid_wave_{raid_id}")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    player = get_player(chat_id, user.id)
    
    if not player:
        await query.answer("❌ Персонаж не найден!", show_alert=True)
        return
    
    keyboard = [
        [InlineKeyboardButton("⚔️ БОЙ", callback_data="start_battle"), InlineKeyboardButton("📜 КВЕСТЫ", callback_data="show_quests")],
        [InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data="show_profile"), InlineKeyboardButton("⚡ УМЕНИЯ", callback_data="show_skills")],
        [InlineKeyboardButton("🐾 ПИТОМЕЦ", callback_data="show_pet"), InlineKeyboardButton("📦 ИНВЕНТАРЬ", callback_data="show_inventory")],
        [InlineKeyboardButton("🛒 МАГАЗИН", callback_data="show_shop"), InlineKeyboardButton("⚙️ КРАФТ", callback_data="show_crafting")],
        [InlineKeyboardButton("👑 ТОП ИГРОКОВ", callback_data="show_top"), InlineKeyboardButton("🏟️ PVP", callback_data="show_pvp")],
        [InlineKeyboardButton("🏰 РЕЙДЫ", callback_data="show_raids"), InlineKeyboardButton("🎖️ ДОСТИЖЕНИЯ", callback_data="show_achievements")],
    ]

    reply_text = (
        f"⚔️ QUEST WORLD - RPG ПРИКЛЮЧЕНИЕ ⚔️\n\n"
        f"Добро пожаловать, {CLASSES[player['class']]['emoji']} {CLASSES[player['class']]['name']}!\n\n"
        f"Исследуй подземелья, учи умения и становись легендой!"
    )
    
    await query.edit_message_text(reply_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("class_"):
        await select_class(update, context)
    elif data == "after_class_select":
        await after_class_select(update, context)
    elif data == "restart_class_selection":
        await restart_class_selection(update, context)
    elif data == "show_profile":
        await show_profile(update, context)
    elif data == "show_pet":
        await show_pet(update, context)
    elif data == "show_inventory":
        await show_inventory(update, context)
    elif data == "show_shop":
        await show_shop(update, context)
    elif data.startswith("buy_"):
        await buy_item(update, context)
    elif data == "show_top":
        await show_top(update, context)
    elif data == "show_quests":
        await show_quests(update, context)
    elif data == "show_weekly_quests":
        await show_weekly_quests(update, context)
    elif data.startswith("complete_quest_"):
        await complete_daily_quest(update, context)
    elif data == "show_skills":
        await show_skills(update, context)
    elif data.startswith("learn_skill_"):
        await learn_skill(update, context)
    elif data == "show_crafting":
        await show_crafting(update, context)
    elif data.startswith("craft_"):
        await craft_item(update, context)
    elif data == "show_raids":
        await show_raids(update, context)
    elif data.startswith("start_raid_"):
        await start_raid(update, context)
    elif data == "show_achievements":
        await show_achievements(update, context)
    elif data == "start_battle":
        await start_battle(update, context)
    elif data == "attack_enemy":
        await attack_enemy(update, context)
    elif data == "heal_self":
        await heal_self(update, context)
    elif data == "flee_battle":
        await flee_battle(update, context)
    elif data == "show_pvp":
        await show_pvp(update, context)
    elif data == "main_menu":
        await main_menu(update, context)

async def webhook_handler(request):
    data = await request.json()
    update = Update.de_json(data, app.bot)
    await app.process_update(update)
    return web.Response(text="OK")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", 8000))

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start_command))
app.add_handler(CallbackQueryHandler(button_handler))

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    
    if WEBHOOK_URL:
        async def main():
            await app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
            
            app_web = web.Application()
            app_web.router.add_post("/webhook", webhook_handler)
            
            runner = web.AppRunner(app_web)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", WEBHOOK_PORT)
            await site.start()
            
            print(f"Бот запущен на вебхуке: {WEBHOOK_URL}")
            
            try:
                await asyncio.Event().wait()
            except KeyboardInterrupt:
                await runner.cleanup()
        
        loop.run_until_complete(main())
    else:
        loop.run_until_complete(app.run_polling())
