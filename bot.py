import os
import random
import logging
import sqlite3
import threading
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.FileHandler("quest_bot.log", encoding="utf-8"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

db_lock = threading.RLock()
conn = sqlite3.connect('quest_bot.db', check_same_thread=False, timeout=30.0)
cursor = conn.cursor()

# ========== СИСТЕМА ПВП - ОЧЕРЕДЬ ОЖИДАЮЩИХ ИГРОКОВ ==========
pvp_queue = {}

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
    equipped_weapon TEXT, equipped_armor TEXT,
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
CREATE TABLE IF NOT EXISTS equipment (
    chat_id INTEGER, user_id INTEGER, item_id TEXT,
    attack INTEGER DEFAULT 0, defense INTEGER DEFAULT 0,
    health INTEGER DEFAULT 0, mana INTEGER DEFAULT 0,
    class_req TEXT,
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

cursor.execute('''
CREATE TABLE IF NOT EXISTS pvp_battles (
    chat_id INTEGER, user_id_1 INTEGER, user_id_2 INTEGER,
    player_1_health INTEGER, player_2_health INTEGER,
    active INTEGER DEFAULT 1,
    PRIMARY KEY (chat_id, user_id_1, user_id_2)
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

PETS = {
    "wolf": {"name": "Волк", "emoji": "🐺", "damage_bonus": 10, "defense_bonus": 3, "xp_bonus": 1.1, "price": 1000},
    "dragon": {"name": "Дракон", "emoji": "🐉", "damage_bonus": 25, "defense_bonus": 8, "xp_bonus": 1.5, "price": 5000},
    "phoenix": {"name": "Феникс", "emoji": "🔥", "damage_bonus": 20, "defense_bonus": 5, "xp_bonus": 1.4, "price": 4000},
    "shadow": {"name": "Тень", "emoji": "⚫", "damage_bonus": 15, "defense_bonus": 4, "xp_bonus": 1.3, "price": 2500},
    "bear": {"name": "Медведь", "emoji": "🐻", "damage_bonus": 18, "defense_bonus": 10, "xp_bonus": 1.2, "price": 2000},
    "ancient_dragon": {"name": "Древний Дракон", "emoji": "👹", "damage_bonus": 40, "defense_bonus": 15, "xp_bonus": 2.0, "price": 15000},
    "celestial_phoenix": {"name": "Небесный Феникс", "emoji": "✨", "damage_bonus": 35, "defense_bonus": 12, "xp_bonus": 1.9, "price": 12000},
}

ENEMIES = {
    "goblin": {"name": "Гоблин", "emoji": "👹", "level": 1, "health": 15, "damage": 3, "xp": 25, "gold": 10, "loot": ["copper_coin"], "is_boss": False},
    "rat": {"name": "Крыса", "emoji": "🐭", "level": 1, "health": 10, "damage": 2, "xp": 15, "gold": 5, "loot": ["copper_coin"], "is_boss": False},
    "skeleton": {"name": "Скелет", "emoji": "☠️", "level": 2, "health": 25, "damage": 5, "xp": 40, "gold": 20, "loot": ["bone_fragment"], "is_boss": False},
    "zombie": {"name": "Зомби", "emoji": "🧟", "level": 2, "health": 30, "damage": 6, "xp": 50, "gold": 25, "loot": ["rotten_flesh"], "is_boss": False},
    "imp": {"name": "Чертёнок", "emoji": "😈", "level": 2, "health": 20, "damage": 7, "xp": 45, "gold": 15, "loot": ["sulfur"], "is_boss": False},
    "orc": {"name": "Орк", "emoji": "🗡️", "level": 3, "health": 45, "damage": 12, "xp": 100, "gold": 50, "loot": ["iron_ore"], "is_boss": False},
    "troll": {"name": "Тролль", "emoji": "👹", "level": 3, "health": 60, "damage": 11, "xp": 110, "gold": 60, "loot": ["troll_club", "cave_pearl"], "is_boss": False},
    "werewolf": {"name": "Оборотень", "emoji": "🐺", "level": 4, "health": 50, "damage": 15, "xp": 130, "gold": 70, "loot": ["wolf_fur", "silver_coin"], "is_boss": False},
    "shadow_knight": {"name": "Рыцарь Теней", "emoji": "⚔️", "level": 4, "health": 65, "damage": 18, "xp": 150, "gold": 80, "loot": ["dark_crystal", "iron_sword"], "is_boss": False},
    "witch": {"name": "Ведьма", "emoji": "🧙‍♀️", "level": 4, "health": 40, "damage": 20, "xp": 140, "gold": 75, "loot": ["magic_dust", "cursed_potion"], "is_boss": False},
    "basilisk": {"name": "Василиск", "emoji": "🐍", "level": 5, "health": 100, "damage": 25, "xp": 200, "gold": 120, "loot": ["basilisk_fang", "poison_vial"], "is_boss": False},
    "ice_mage": {"name": "Ледяной маг", "emoji": "❄️", "level": 5, "health": 55, "damage": 28, "xp": 180, "gold": 110, "loot": ["ice_crystal", "mana_potion"], "is_boss": False},
    "demon": {"name": "Демон", "emoji": "😈", "level": 6, "health": 120, "damage": 32, "xp": 250, "gold": 150, "loot": ["demonic_essence", "soul_fragment"], "is_boss": False},
    "golem": {"name": "Голем", "emoji": "🪨", "level": 6, "health": 150, "damage": 20, "xp": 220, "gold": 140, "loot": ["stone_heart", "magical_core"], "is_boss": False},
    "dragon": {"name": "Дракон", "emoji": "🐉", "level": 7, "health": 200, "damage": 40, "xp": 500, "gold": 300, "loot": ["dragon_scale", "dragon_heart"], "is_boss": True},
    "lich": {"name": "Лич", "emoji": "💀", "level": 8, "health": 180, "damage": 45, "xp": 550, "gold": 350, "loot": ["soul_essence", "lich_staff"], "is_boss": True},
    "archidemon": {"name": "Архидемон", "emoji": "😈", "level": 9, "health": 250, "damage": 50, "xp": 700, "gold": 400, "loot": ["demonic_core", "eternal_essence"], "is_boss": True},
    "lich_king": {"name": "Истинный Лич-Король", "emoji": "👿", "level": 10, "health": 300, "damage": 60, "xp": 1000, "gold": 500, "loot": ["king_crown", "eternal_staff"], "is_boss": True},
}

EQUIPMENT_ITEMS = {
    "iron_sword": {"name": "Железный меч", "emoji": "⚔️", "type": "weapon", "attack": 5, "price": 200, "class": "warrior"},
    "steel_sword": {"name": "Стальной меч", "emoji": "🗡️", "type": "weapon", "attack": 10, "price": 500, "class": "warrior"},
    "legendary_sword": {"name": "Меч Вечности", "emoji": "⚡", "type": "weapon", "attack": 50, "price": 5000, "class": "warrior"},
    "iron_armor": {"name": "Железная броня", "emoji": "🛡️", "type": "armor", "defense": 4, "price": 250, "class": "warrior"},
    "steel_armor": {"name": "Стальная броня", "emoji": "🛡️", "type": "armor", "defense": 8, "price": 600, "class": "warrior"},
    "legendary_armor": {"name": "Легендарная броня", "emoji": "👑", "type": "armor", "defense": 40, "price": 5000, "class": "warrior"},
    "fireball_staff": {"name": "Посох огня", "emoji": "🔥", "type": "weapon", "attack": 8, "price": 200, "class": "mage"},
    "archimage_staff": {"name": "Посох Архимага", "emoji": "🔮", "type": "weapon", "attack": 30, "price": 5000, "class": "mage"},
    "mage_robe": {"name": "Мантия мага", "emoji": "👗", "type": "armor", "defense": 2, "mana": 20, "price": 150, "class": "mage"},
    "celestial_robe": {"name": "Небесная мантия", "emoji": "✨", "type": "armor", "defense": 5, "mana": 50, "price": 3000, "class": "mage"},
    "dagger": {"name": "Кинжал", "emoji": "🗡️", "type": "weapon", "attack": 6, "price": 180, "class": "rogue"},
    "shadow_dagger": {"name": "Теневой кинжал", "emoji": "⚫", "type": "weapon", "attack": 15, "price": 1000, "class": "rogue"},
    "shadow_cloak": {"name": "Плащ теней", "emoji": "⚫", "type": "armor", "defense": 3, "price": 220, "class": "rogue"},
    "assassin_armor": {"name": "Броня ассасина", "emoji": "🖤", "type": "armor", "defense": 6, "price": 1500, "class": "rogue"},
    "holy_shield": {"name": "Святой щит", "emoji": "⛪", "type": "armor", "defense": 6, "price": 300, "class": "paladin"},
    "titan_shield": {"name": "Щит Титана", "emoji": "🛡️", "type": "armor", "defense": 40, "price": 5000, "class": "paladin"},
    "blessed_mace": {"name": "Святая булава", "emoji": "⛪", "type": "weapon", "attack": 12, "price": 600, "class": "paladin"},
    "longbow": {"name": "Длинный лук", "emoji": "🏹", "type": "weapon", "attack": 7, "price": 220, "class": "ranger"},
    "moon_bow": {"name": "Лук Луны", "emoji": "🏹", "type": "weapon", "attack": 40, "price": 5000, "class": "ranger"},
}

SHOP_ITEMS = {
    "health_potion": {"name": "Зелье здоровья", "emoji": "❤️", "price": 50, "rarity": "common", "class": None},
    "mana_potion": {"name": "Зелье маны", "emoji": "💙", "price": 50, "rarity": "common", "class": None},
    "strength_potion": {"name": "Зелье силы", "emoji": "💪", "price": 100, "rarity": "uncommon", "class": None},
    "wisdom_elixir": {"name": "Эликсир мудрости", "emoji": "🧠", "price": 200, "rarity": "rare", "class": None},
}

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
    "iron_sword": {"name": "Железный меч", "rarity": "uncommon", "emoji": "⚔️"},
    "mana_potion": {"name": "Зелье маны", "rarity": "common", "emoji": "💙"},
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

SKILLS = {
    "fireball": {"name": "Огненный шар", "emoji": "🔥", "type": "mage", "damage_multiplier": 1.5, "cost": 15},
    "frost_nova": {"name": "Ледяная nova", "emoji": "❄️", "type": "mage", "damage_multiplier": 1.4, "cost": 15},
    "chain_lightning": {"name": "Цепная молния", "emoji": "⚡", "type": "mage", "damage_multiplier": 1.6, "cost": 20},
    "meteor_shower": {"name": "Метеоритный дождь", "emoji": "☄️", "type": "mage", "damage_multiplier": 2.0, "cost": 30},
    "power_strike": {"name": "Мощный удар", "emoji": "💥", "type": "warrior", "damage_multiplier": 1.8, "cost": 10},
    "whirlwind": {"name": "Смерч атак", "emoji": "🌪️", "type": "warrior", "damage_multiplier": 1.7, "cost": 15},
    "backstab": {"name": "Удар в спину", "emoji": "🗡️", "type": "rogue", "damage_multiplier": 2.0, "cost": 12},
    "deadly_strike": {"name": "Смертельный удар", "emoji": "💀", "type": "rogue", "damage_multiplier": 2.5, "cost": 25},
    "shield_bash": {"name": "Удар щитом", "emoji": "🛡️", "type": "paladin", "damage_multiplier": 1.5, "cost": 12},
    "divine_ray": {"name": "Божественный луч", "emoji": "☀️", "type": "paladin", "damage_multiplier": 1.8, "cost": 20},
    "multi_shot": {"name": "Множественный выстрел", "emoji": "🏹", "type": "ranger", "damage_multiplier": 1.6, "cost": 14},
    "pet_summon": {"name": "Призыв питомца", "emoji": "🐾", "type": "ranger", "damage_multiplier": 1.4, "cost": 18},
}

RECIPES = {
    "iron_ingot_recipe": {
        "name": "Плавить железную руду",
        "emoji": "⛏️",
        "materials": {"iron_ore": 5},
        "result_material": "iron_ingot",
        "quantity": 1,
        "level_required": 5
    },
    "copper_ingot_recipe": {
        "name": "Плавить медь",
        "emoji": "🟠",
        "materials": {"copper_coin": 10},
        "result_material": "copper_ingot",
        "quantity": 1,
        "level_required": 1
    },
}

RAIDS = {
    "abandoned_ruins": {
        "name": "Заброшенные развалины",
        "emoji": "🏚️",
        "level": 5,
        "waves": 3,
        "enemies_per_wave": 3,
        "bosses_in_raid": 0,
        "xp_reward": 1000,
        "gold_reward": 500,
        "loot": ["iron_ore", "iron_ore", "sulfur"]
    },
    "werewolf_fortress": {
        "name": "Крепость оборотней",
        "emoji": "🏰",
        "level": 7,
        "waves": 4,
        "enemies_per_wave": 4,
        "bosses_in_raid": 1,
        "xp_reward": 1500,
        "gold_reward": 750,
        "loot": ["dark_crystal", "dragon_scale", "soul_fragment"]
    },
    "black_palace": {
        "name": "Чёрный дворец",
        "emoji": "👑",
        "level": 9,
        "waves": 5,
        "enemies_per_wave": 5,
        "bosses_in_raid": 2,
        "xp_reward": 2500,
        "gold_reward": 1000,
        "loot": ["soul_essence", "eternal_essence", "eternal_essence"]
    },
    "abyss": {
        "name": "Абисс",
        "emoji": "🌌",
        "level": 11,
        "waves": 6,
        "enemies_per_wave": 6,
        "bosses_in_raid": 3,
        "xp_reward": 4000,
        "gold_reward": 1500,
        "loot": ["king_crown", "void_essence", "celestial_stone"]
    },
}

DAILY_QUESTS = {
    "kill_5_enemies": {"name": "Убить 5 врагов", "emoji": "⚔️", "target": 5, "reward_xp": 200, "reward_gold": 150},
    "kill_10_enemies": {"name": "Убить 10 врагов", "emoji": "⚔️", "target": 10, "reward_xp": 400, "reward_gold": 300},
    "collect_rare_items": {"name": "Собрать 3 редких предмета", "emoji": "💎", "target": 3, "reward_xp": 250, "reward_gold": 200},
}

WEEKLY_QUESTS = {
    "kill_boss": {"name": "Убить босса", "emoji": "👹", "target": 1, "reward_xp": 1000, "reward_gold": 500},
    "complete_3_raids": {"name": "Пройти 3 рейда", "emoji": "🏰", "target": 3, "reward_xp": 1500, "reward_gold": 750},
}

ACHIEVEMENTS = {
    "hunter_10": {"name": "Охотник", "emoji": "⚔️", "description": "Убей 10 врагов", "target": 10, "reward": 100},
    "hunter_50": {"name": "Опытный охотник", "emoji": "⚔️", "description": "Убей 50 врагов", "target": 50, "reward": 500},
    "boss_slayer_3": {"name": "Убийца боссов", "emoji": "👹", "description": "Убей 3 босса", "target": 3, "reward": 500},
    "hero_level_10": {"name": "Молодой герой", "emoji": "⭐", "description": "Достигни 10 уровня", "target": 10, "reward": 300},
    "hero_level_20": {"name": "Герой", "emoji": "⭐", "description": "Достигни 20 уровня", "target": 20, "reward": 1000},
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
            "equipped_weapon": row[20],
            "equipped_armor": row[21],
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
def subtract_material(chat_id, user_id, material_id, quantity):
    cursor.execute(
        'SELECT quantity FROM crafting_materials WHERE chat_id=? AND user_id=? AND material_id=?',
        (chat_id, user_id, material_id)
    )
    row = cursor.fetchone()
    if row and row[0] >= quantity:
        new_qty = row[0] - quantity
        cursor.execute(
            'UPDATE crafting_materials SET quantity=? WHERE chat_id=? AND user_id=? AND material_id=?',
            (new_qty, chat_id, user_id, material_id)
        )
        conn.commit()
        return True
    return False

@safe_db_execute
def get_player_pet(chat_id, user_id):
    cursor.execute('SELECT pet_id, pet_level FROM players WHERE chat_id=? AND user_id=?', (chat_id, user_id))
    row = cursor.fetchone()
    if row:
        return {"pet_id": row[0], "pet_level": row[1]}
    return None

@safe_db_execute
def set_pet(chat_id, user_id, pet_id):
    cursor.execute(
        'UPDATE players SET pet_id=?, pet_level=? WHERE chat_id=? AND user_id=?',
        (pet_id, 1, chat_id, user_id)
    )
    conn.commit()

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
def equip_item(chat_id, user_id, item_id):
    item_info = EQUIPMENT_ITEMS.get(item_id)
    if not item_info:
        return False
    
    if item_info["type"] == "weapon":
        cursor.execute(
            'UPDATE players SET equipped_weapon=? WHERE chat_id=? AND user_id=?',
            (item_id, chat_id, user_id)
        )
    elif item_info["type"] == "armor":
        cursor.execute(
            'UPDATE players SET equipped_armor=? WHERE chat_id=? AND user_id=?',
            (item_id, chat_id, user_id)
        )
    conn.commit()
    return True

@safe_db_execute
def get_equipment_bonus(chat_id, user_id):
    cursor.execute(
        'SELECT equipped_weapon, equipped_armor FROM players WHERE chat_id=? AND user_id=?',
        (chat_id, user_id)
    )
    row = cursor.fetchone()
    bonus = {"attack": 0, "defense": 0}
    if row:
        if row[0]:
            weapon = EQUIPMENT_ITEMS.get(row[0], {})
            bonus["attack"] += weapon.get("attack", 0)
        if row[1]:
            armor = EQUIPMENT_ITEMS.get(row[1], {})
            bonus["defense"] += armor.get("defense", 0)
    return bonus

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
def get_daily_quest_progress(chat_id, user_id):
    cursor.execute(
        'SELECT quest_id FROM quests WHERE chat_id=? AND user_id=? AND quest_type=? AND date(completed_at) = date("now")',
        (chat_id, user_id, 'daily')
    )
    return [row[0] for row in cursor.fetchall()]

@safe_db_execute
def get_weekly_quest_progress(chat_id, user_id):
    cursor.execute(
        'SELECT quest_id FROM quests WHERE chat_id=? AND user_id=? AND quest_type=? AND strftime("%W", completed_at) = strftime("%W", "now")',
        (chat_id, user_id, 'weekly')
    )
    return [row[0] for row in cursor.fetchall()]

@safe_db_execute
def complete_quest(chat_id, user_id, quest_id, quest_type='daily'):
    cursor.execute(
        'INSERT OR IGNORE INTO quests VALUES (?, ?, ?, ?, datetime("now"))',
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
            'INSERT INTO achievements VALUES (?, ?, ?, datetime("now"), ?)',
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
def start_battle_db(chat_id, user_id):
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
            [InlineKeyboardButton("🛡️ ЭКИПИРОВКА", callback_data="show_equipment"), InlineKeyboardButton("🛒 МАГАЗИН", callback_data="show_shop")],
            [InlineKeyboardButton("⚙️ КРАФТ", callback_data="show_crafting"), InlineKeyboardButton("👑 ТОП ИГРОКОВ", callback_data="show_top")],
            [InlineKeyboardButton("🏟️ PVP", callback_data="show_pvp"), InlineKeyboardButton("🏰 РЕЙДЫ", callback_data="show_raids")],
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
        [InlineKeyboardButton("🛡️ ЭКИПИРОВКА", callback_data="show_equipment"), InlineKeyboardButton("🛒 МАГАЗИН", callback_data="show_shop")],
        [InlineKeyboardButton("⚙️ КРАФТ", callback_data="show_crafting"), InlineKeyboardButton("👑 ТОП ИГРОКОВ", callback_data="show_top")],
        [InlineKeyboardButton("🏟️ PVP", callback_data="show_pvp"), InlineKeyboardButton("🏰 РЕЙДЫ", callback_data="show_raids")],
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
    bonus = get_equipment_bonus(chat_id, user.id)

    xp_percent = int((player["xp"] / LEVEL_REQUIREMENTS.get(player["level"] + 1, 99999)) * 100)

    equipped_weapon = ""
    equipped_armor = ""
    if player["equipped_weapon"]:
        w = EQUIPMENT_ITEMS.get(player["equipped_weapon"], {})
        equipped_weapon = f"⚔️ {w.get('name', 'Неизвестно')}"
    if player["equipped_armor"]:
        a = EQUIPMENT_ITEMS.get(player["equipped_armor"], {})
        equipped_armor = f"🛡️ {a.get('name', 'Неизвестно')}"

    text = (
        f"👤 ПРОФИЛЬ: {user.first_name}\n"
        f"{'─' * 35}\n\n"
        f"{class_info['emoji']} Класс: {class_info['name']}\n"
        f"⭐ Уровень: {player['level']}/50\n"
        f"📊 XP: {player['xp']}/{LEVEL_REQUIREMENTS.get(player['level'] + 1, 99999)} ({xp_percent}%)\n"
        f"{'█' * (xp_percent // 10)}{'░' * (10 - xp_percent // 10)}\n\n"
        f"❤️ HP: {player['health']}/{player['max_health']}\n"
        f"💙 Мана: {player['mana']}/{player['max_mana']}\n"
        f"⚔️ Атака: {player['attack']} (+{bonus['attack']})\n"
        f"🛡️ Защита: {player['defense']} (+{bonus['defense']})\n\n"
        f"💰 Золото: {player['gold']}\n"
        f"🐾 Питомец: {pet_info.get('emoji', '❓')} {pet_info.get('name', 'Нет')} (Ур. {pet['pet_level']})\n\n"
        f"🎖️ СТАТИСТИКА:\n"
        f"⚔️ Побед: {player['total_kills']}\n"
        f"👹 Боссов убито: {player['total_bosses_killed']}\n"
        f"🏰 Рейдов пройдено: {player['total_raids_completed']}"
    )
    
    if equipped_weapon:
        text += f"\n\n🛡️ ЭКИПИРОВКА:\n{equipped_weapon}"
    if equipped_armor:
        text += f"\n{equipped_armor}"

    keyboard = [[InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_pet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id

    pet = get_player_pet(chat_id, user.id)
    pet_info = PETS[pet["pet_id"]]
    player = get_player(chat_id, user.id)

    text = (
        f"🐾 ВАША ПИТОМЕЦ\n"
        f"{'─' * 35}\n\n"
        f"{pet_info['emoji']} {pet_info['name'].upper()}\n"
        f"⭐ Уровень: {pet['pet_level']}/100\n\n"
        f"📊 СПОСОБНОСТИ:\n"
        f"⚔️ Бонус атаки: +{pet_info['damage_bonus']}\n"
        f"🛡️ Бонус защиты: +{pet_info['defense_bonus']}\n"
        f"📈 Бонус XP: ×{pet_info['xp_bonus']}\n\n"
        f"💰 Цена: {pet_info['price']} золота\n\n"
        f"💡 СОВЕТ: Заработай больше золота и купи нового питомца,\n"
        f"чтобы получить лучшие бонусы!"
    )

    keyboard = [
        [InlineKeyboardButton("🐾 КУПИТЬ ПИТОМЦА", callback_data="buy_pet_menu")],
        [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def buy_pet_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    player = get_player(chat_id, user.id)
    current_pet = get_player_pet(chat_id, user.id)

    text = "🐾 МАГАЗИН ПИТОМЦЕВ\n" + f"{'─' * 35}\n\n"
    text += f"💰 Твоё золото: {player['gold']}\n\n"
    text += f"Текущий питомец: {PETS[current_pet['pet_id']]['emoji']} {PETS[current_pet['pet_id']]['name']}\n\n"
    
    keyboard = []
    for pet_id, pet_info in PETS.items():
        if pet_id != current_pet['pet_id']:
            affordable = "✅" if player['gold'] >= pet_info['price'] else "❌"
            keyboard.append([InlineKeyboardButton(
                f"{pet_info['emoji']} {pet_info['name']} - {pet_info['price']}💰 {affordable}",
                callback_data=f"buy_pet_{pet_id}"
            )])

    keyboard.append([InlineKeyboardButton("⬅️ НАЗАД", callback_data="show_pet")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def buy_pet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    pet_id = query.data.split("_")[2]
    pet_info = PETS.get(pet_id)
    
    if not pet_info:
        await query.answer("❌ Питомец не найден!", show_alert=True)
        return
    
    player = get_player(chat_id, user.id)
    
    if player["gold"] >= pet_info["price"]:
        subtract_gold(chat_id, user.id, pet_info["price"])
        set_pet(chat_id, user.id, pet_id)
        text = f"✅ Ты получил: {pet_info['emoji']} {pet_info['name']}\n\n-{pet_info['price']} 💰"
        keyboard = [
            [InlineKeyboardButton("🐾 ПИТОМЕЦ", callback_data="show_pet")],
            [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")],
        ]
    else:
        text = f"❌ Недостаточно золота!\nНужно: {pet_info['price']} 💰\nУ тебя: {player['gold']} 💰"
        keyboard = [[InlineKeyboardButton("🐾 МАГАЗИН", callback_data="buy_pet_menu")]]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_equipment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    player = get_player(chat_id, user.id)
    class_info = CLASSES[player["class"]]
    
    equipped_weapon = None
    equipped_armor = None
    
    if player["equipped_weapon"]:
        equipped_weapon = EQUIPMENT_ITEMS.get(player["equipped_weapon"])
    if player["equipped_armor"]:
        equipped_armor = EQUIPMENT_ITEMS.get(player["equipped_armor"])
    
    text = (
        f"🛡️ ЭКИПИРОВКА ({class_info['emoji']} {class_info['name']})\n"
        f"{'─' * 35}\n\n"
        f"⚔️ ОРУЖИЕ:\n"
    )
    
    if equipped_weapon:
        text += f"  ✅ {equipped_weapon['name']} (+{equipped_weapon.get('attack', 0)} атаки)\n"
    else:
        text += "  ❌ Нет оружия\n"
    
    text += f"\n🛡️ БРОНЯ:\n"
    
    if equipped_armor:
        text += f"  ✅ {equipped_armor['name']} (+{equipped_armor.get('defense', 0)} защиты)\n"
    else:
        text += "  ❌ Нет брони\n"
    
    text += f"\n📊 СТАТЫ:\n⚔️ Атака: {player['attack']}\n🛡️ Защита: {player['defense']}\n\n"
    text += f"💡 СОВЕТ: Нажми на оружие или броню ниже,\nчтобы экипировать их!"

    keyboard = [
        [InlineKeyboardButton("⚔️ ОРУЖИЕ", callback_data="equipment_weapons"), InlineKeyboardButton("🛡️ БРОНЯ", callback_data="equipment_armor")],
        [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")],
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def equipment_weapons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    player = get_player(chat_id, user.id)

    text = "⚔️ ВЫБЕРИТЕ ОРУЖИЕ\n" + f"{'─' * 35}\n\n"
    
    keyboard = []
    has_weapons = False
    
    for item_id, item_info in EQUIPMENT_ITEMS.items():
        if item_info["type"] == "weapon" and item_info.get("class") == player["class"]:
            text += f"{item_info['emoji']} {item_info['name']} (+{item_info.get('attack', 0)} атаки)\n"
            keyboard.append([InlineKeyboardButton(f"Экипировать {item_info['emoji']}", callback_data=f"equip_{item_id}")])
            has_weapons = True
    
    if not has_weapons:
        text += "❌ Нет доступного оружия для вашего класса"

    keyboard.append([InlineKeyboardButton("⬅️ НАЗАД", callback_data="show_equipment")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def equipment_armor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    player = get_player(chat_id, user.id)

    text = "🛡️ ВЫБЕРИТЕ БРОНЮ\n" + f"{'─' * 35}\n\n"
    
    keyboard = []
    has_armor = False
    
    for item_id, item_info in EQUIPMENT_ITEMS.items():
        if item_info["type"] == "armor" and item_info.get("class") == player["class"]:
            text += f"{item_info['emoji']} {item_info['name']} (+{item_info.get('defense', 0)} защиты)\n"
            keyboard.append([InlineKeyboardButton(f"Экипировать {item_info['emoji']}", callback_data=f"equip_{item_id}")])
            has_armor = True
    
    if not has_armor:
        text += "❌ Нет доступной брони для вашего класса"

    keyboard.append([InlineKeyboardButton("⬅️ НАЗАД", callback_data="show_equipment")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def equip_item_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id

    item_id = query.data.split("_")[1]
    item_info = EQUIPMENT_ITEMS.get(item_id)

    if not item_info:
        await query.answer("❌ Предмет не найден!", show_alert=True)
        return

    if equip_item(chat_id, user.id, item_id):
        # Успешно экипировано
        stat_type = "атаки" if item_info["type"] == "weapon" else "защиты"
        stat_value = item_info.get("attack", 0) if item_info["type"] == "weapon" else item_info.get("defense", 0)

        text = (
            f"✅ УСПЕШНО ЭКИПИРОВАНО!\n\n"
            f"{item_info['emoji']} {item_info['name']}\n\n"
            f"Получен бонус:\n"
            f"+{stat_value} {stat_type}\n\n"
            f"🛡️ ЭКИПИРОВКА\n"
            f"{'─' * 35}\n\n"
        )

        player = get_player(chat_id, user.id)
        class_info = CLASSES[player["class"]]

        equipped_weapon = None
        equipped_armor = None

        if player["equipped_weapon"]:
            equipped_weapon = EQUIPMENT_ITEMS.get(player["equipped_weapon"])
        if player["equipped_armor"]:
            equipped_armor = EQUIPMENT_ITEMS.get(player["equipped_armor"])

        text += f"⚔️ ОРУЖИЕ:\n"
        if equipped_weapon:
            text += f" ✅ {equipped_weapon['name']} (+{equipped_weapon.get('attack', 0)} атаки)\n"
        else:
            text += " ❌ Нет оружия\n"

        text += f"\n🛡️ БРОНЯ:\n"
        if equipped_armor:
            text += f" ✅ {equipped_armor['name']} (+{equipped_armor.get('defense', 0)} защиты)\n"
        else:
            text += " ❌ Нет брони\n"

        text += f"\n📊 СТАТЫ:\n⚔️ Атака: {player['attack']}\n🛡️ Защита: {player['defense']}"

        keyboard = [
            [InlineKeyboardButton("⚔️ ОРУЖИЕ", callback_data="equipment_weapons"), InlineKeyboardButton("🛡️ БРОНЯ", callback_data="equipment_armor")],
            [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")],
        ]
    else:
        text = "❌ Не удалось экипировать предмет"
        keyboard = [[InlineKeyboardButton("⬅️ НАЗАД", callback_data="show_equipment")]]

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
        text = "📦 ИНВЕНТАРЬ\n" + f"{'─' * 35}\n\n"
        for item_id, qty, rarity in items:
            item_info = ITEMS.get(item_id, {})
            rarity_emoji = {"common": "⚪", "uncommon": "🟢", "rare": "🔵", "legendary": "🟡"}.get(rarity, "⚪")
            text += f"{item_info.get('emoji', '?')} {item_info.get('name', item_id)}\n  x{qty} {rarity_emoji}\n"

    keyboard = [[InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    player = get_player(chat_id, user.id)
    player_class = player["class"]
    
    text = "🛒 МАГАЗИН\n" + f"{'─' * 35}\n\n"
    text += f"💰 Твоё золото: {player['gold']}\n\n"
    text += f"📦 ЗЕЛЬЯ:\n"
    
    keyboard = []
    for item_id, item_info in SHOP_ITEMS.items():
        if item_info["class"] is None:
            affordable = "✅" if player['gold'] >= item_info['price'] else "❌"
            text += f"{item_info['emoji']} {item_info['name']} - {item_info['price']}💰 {affordable}\n"
            keyboard.append([InlineKeyboardButton(
                f"Купить {item_info['emoji']}",
                callback_data=f"buy_{item_id}"
            )])

    text += f"\n⚔️ ОРУЖИЕ И БРОНЯ:\n"
    text += f"Нажми '🛡️ ЭКИПИРОВКА' и купи в магазине!\n"

    keyboard.append([InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def buy_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    item_id = query.data.split("_")[1]
    item_info = SHOP_ITEMS.get(item_id)
    
    if not item_info:
        await query.answer("❌ Предмет не найден!", show_alert=True)
        return
    
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
    
    text = "👑 ТОП 10 ИГРОКОВ\n" + f"{'─' * 35}\n\n"
    
    for i, (name, level, kills, gold, player_class) in enumerate(top_players, 1):
        class_emoji = CLASSES[player_class]["emoji"]
        text += f"{i}. {class_emoji} {name}\n"
        text += f"   ⭐ Ур. {level} | ⚔️ {kills} | 💰 {gold}\n"
    
    if not top_players:
        text = "👑 ТОП 10 ИГРОКОВ\n\n❌ Данных нет"
    
    keyboard = [[InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_quests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    completed = get_daily_quest_progress(chat_id, user.id)
    
    text = "📜 ЕЖЕДНЕВНЫЕ КВЕСТЫ\n" + f"{'─' * 35}\n\n"
    
    keyboard = []
    for quest_id, quest_info in DAILY_QUESTS.items():
        status = "✅" if quest_id in completed else "⬜"
        text += f"{status} {quest_info['emoji']} {quest_info['name']}\n"
        text += f"   Цель: {quest_info['target']} | +{quest_info['reward_xp']}XP, +{quest_info['reward_gold']}💰\n\n"
        
        if quest_id not in completed:
            keyboard.append([InlineKeyboardButton(f"✓ {quest_info['emoji']}", callback_data=f"complete_quest_daily_{quest_id}")])
    
    keyboard.append([InlineKeyboardButton("📋 ЕЖЕНЕДЕЛЬНЫЕ", callback_data="show_weekly_quests")])
    keyboard.append([InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_weekly_quests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    completed = get_weekly_quest_progress(chat_id, user.id)
    
    text = "📋 ЕЖЕНЕДЕЛЬНЫЕ КВЕСТЫ\n" + f"{'─' * 35}\n\n"
    
    keyboard = []
    for quest_id, quest_info in WEEKLY_QUESTS.items():
        status = "✅" if quest_id in completed else "⬜"
        text += f"{status} {quest_info['emoji']} {quest_info['name']}\n"
        text += f"   Цель: {quest_info['target']} | +{quest_info['reward_xp']}XP, +{quest_info['reward_gold']}💰\n\n"
        
        if quest_id not in completed:
            keyboard.append([InlineKeyboardButton(f"✓ {quest_info['emoji']}", callback_data=f"complete_quest_weekly_{quest_id}")])
    
    keyboard.append([InlineKeyboardButton("📜 ЕЖЕДНЕВНЫЕ", callback_data="show_quests")])
    keyboard.append([InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")])
    
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
    
    text = "⚡ УМЕНИЯ\n" + f"{'─' * 35}\n\n"
    
    keyboard = []
    for skill_id, skill_info in SKILLS.items():
        if skill_info["type"] == player_class:
            level = player_skills.get(skill_id, 0)
            text += f"{skill_info['emoji']} {skill_info['name']} (Ур. {level}/10)\n"
            text += f"   Мана: {skill_info['cost']} | Урон: ×{skill_info['damage_multiplier']}\n\n"
            
            if level < 10:
                keyboard.append([InlineKeyboardButton(f"↑ {skill_info['emoji']}", callback_data=f"learn_skill_{skill_id}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")])
    
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
    
    text = "⚙️ КРАФТ\n" + f"{'─' * 35}\n\n"
    text += f"⭐ Уровень: {player['level']}\n\n"
    text += f"📦 ВАШ МАТЕРИАЛЫ:\n"
    
    if materials:
        for material_id, qty in materials.items():
            mat_info = MATERIALS.get(material_id, {})
            text += f"  {mat_info.get('emoji', '?')} {mat_info.get('name', material_id)}: {qty}\n"
    else:
        text += "  ❌ Материалов нет\n  (убивайте мобов для получения материалов)\n"
    
    text += f"\n🔨 ДОСТУПНЫЕ РЕЦЕПТЫ:\n"
    
    keyboard = []
    has_recipes = False
    for recipe_id, recipe_info in RECIPES.items():
        if player["level"] >= recipe_info["level_required"]:
            can_craft = True
            needs = ""
            for mat_id, needed_qty in recipe_info["materials"].items():
                current = materials.get(mat_id, 0)
                mat_info = MATERIALS.get(mat_id, {})
                needs += f"{current}/{needed_qty} {mat_info.get('emoji', '?')} "
                if current < needed_qty:
                    can_craft = False
            
            status = "✅" if can_craft else "❌"
            text += f"  {status} {recipe_info['emoji']} {recipe_info['name']}\n"
            text += f"     Нужно: {needs}\n"
            keyboard.append([InlineKeyboardButton(f"Создать {recipe_info['emoji']}", callback_data=f"craft_{recipe_id}")])
            has_recipes = True
    
    if not has_recipes:
        text += "  ❌ Нет доступных рецептов\n"
    
    keyboard.append([InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")])
    
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
            subtract_material(chat_id, user.id, mat_id, needed_qty)
        
        add_material(chat_id, user.id, recipe["result_material"], recipe["quantity"])
        text = f"✅ Создано: {recipe['emoji']} {recipe['name']}\n+{recipe['quantity']} {MATERIALS[recipe['result_material']]['name']}"
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
    
    text = "🏰 РЕЙДЫ\n" + f"{'─' * 35}\n\n"
    
    keyboard = []
    for raid_id, raid_info in RAIDS.items():
        if player["level"] >= raid_info["level"]:
            text += f"{raid_info['emoji']} {raid_info['name']} (Ур. {raid_info['level']})\n"
            text += f"   Волн: {raid_info['waves']} | Боссов: {raid_info['bosses_in_raid']}\n"
            text += f"   +{raid_info['xp_reward']}XP, +{raid_info['gold_reward']}💰\n\n"
            keyboard.append([InlineKeyboardButton(f"Войти {raid_info['emoji']}", callback_data=f"start_raid_{raid_id}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")])
    
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
        f"🏟️ PVP\n"
        f"{'─' * 35}\n\n"
        f"{rank_info['emoji']} Ранг: {rank_info['name']}\n"
        f"⭐ Рейтинг: {stats['rating']}\n"
        f"✅ Победы: {stats['wins']}\n"
        f"❌ Поражения: {stats['losses']}\n\n"
        f"📊 Процент побед: {int(stats['wins'] * 100 / max(stats['wins'] + stats['losses'], 1))}%\n\n"
        f"💡 Система поиска:\n"
        f"Нажимай кнопку и ждёшь, пока найдётся\n"
        f"соперник примерно твоего уровня!"
    )
    
    keyboard = [
        [InlineKeyboardButton("⚔️ НАЙТИ СОПЕРНИКА", callback_data="pvp_find_opponent")],
        [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def pvp_find_opponent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    player = get_player(chat_id, user.id)
    
    if chat_id not in pvp_queue:
        pvp_queue[chat_id] = {}
    
    for waiting_user_id, waiting_player in pvp_queue[chat_id].items():
        if waiting_user_id != user.id:
            if abs(waiting_player["level"] - player["level"]) <= 3:
                pvp_queue[chat_id].pop(waiting_user_id)
                text = f"⚔️ НАЙДЕН СОПЕРНИК!\n\n{waiting_player['name']} (Ур. {waiting_player['level']})\n\nБой начинается..."
                keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data=f"pvp_battle_{user.id}_{waiting_user_id}")]]
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
                return
    
    pvp_queue[chat_id][user.id] = {
        "name": user.first_name,
        "level": player["level"],
        "user_id": user.id,
        "message_id": query.message.message_id
    }
    
    text = (
        f"🔄 ПОИСК СОПЕРНИКА...\n\n"
        f"Уровень: {player['level']}\n"
        f"Рейтинг: {get_pvp_stats(chat_id, user.id)['rating']}\n\n"
        f"Ожидаем противника примерно вашего уровня...\n"
        f"(разница не более 3 уровней)"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔄 ОБНОВИТЬ", callback_data="pvp_find_opponent")],
        [InlineKeyboardButton("❌ ОТМЕНИТЬ", callback_data="pvp_cancel")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def pvp_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    if chat_id in pvp_queue and user.id in pvp_queue[chat_id]:
        pvp_queue[chat_id].pop(user.id)
    
    text = "❌ Поиск отменён"
    keyboard = [[InlineKeyboardButton("🏟️ PVP", callback_data="show_pvp")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def start_battle_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    player = get_player(chat_id, user.id)
    
    enemy_id = start_battle_db(chat_id, user.id)
    if not enemy_id:
        await query.answer("❌ Ошибка при начале боя", show_alert=True)
        return
    enemy_info = ENEMIES[enemy_id]
    pet = get_player_pet(chat_id, user.id)
    pet_info = PETS[pet["pet_id"]]
    
    enemy_health = enemy_info["health"] + (player["level"] - 1) * 5
    
    update_battle(chat_id, user.id, enemy_health, player["health"])
    
    text = (
        f"⚔️ БОЙ\n"
        f"{'─' * 35}\n\n"
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
        f"⚔️ БОЙ\n"
        f"{'─' * 35}\n\n"
        f"💥 Ты нанёс {player_damage} урона!\n"
        f"💔 Враг нанёс {enemy_damage} урона!\n\n"
        f"👤 Твоё здоровье: {new_player_health}/{player['max_health']} HP\n"
        f"{enemy_info['emoji']} Здоровье врага: {new_enemy_health} HP"
    )
    
    if new_enemy_health <= 0:
        xp_reward = int(enemy_info["xp"] * 1.2)
        gold_reward = enemy_info["gold"]
        
        add_xp(chat_id, user.id, user.first_name, xp_reward)
        add_gold(chat_id, user.id, gold_reward)
        add_kill(chat_id, user.id)
        
        if enemy_info.get("is_boss"):
            add_boss_kill(chat_id, user.id)
        
        for loot_item in enemy_info.get("loot", []):
            add_item(chat_id, user.id, loot_item)
            if loot_item in MATERIALS:
                add_material(chat_id, user.id, loot_item)
        
        end_battle(chat_id, user.id)
        
        loot_text = ""
        for item in enemy_info.get("loot", []):
            loot_text += f"{ITEMS.get(item, {}).get('emoji', '?')} {ITEMS.get(item, {}).get('name', item)}\n"
        
        text = (
            f"🎉 ПОБЕДА!\n"
            f"{'─' * 35}\n\n"
            f"Ты победил {enemy_info['emoji']} {enemy_info['name']}!\n\n"
            f"📊 НАГРАДА:\n"
            f"+{xp_reward} XP\n"
            f"+{gold_reward} 💰\n\n"
            f"📦 ЛУТ:\n{loot_text}"
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
            f"💀 ПОРАЖЕНИЕ\n"
            f"{'─' * 35}\n\n"
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
            f"🏥 ИСЦЕЛЕНИЕ\n"
            f"{'─' * 35}\n\n"
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
                f"💀 ПОРАЖЕНИЕ\n"
                f"{'─' * 35}\n\n"
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

async def start_raid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        f"🏰 {raid_info['name'].upper()}\n"
        f"{'─' * 35}\n\n"
        f"Волна: 1/{raid_info['waves']}\n"
        f"Враги: {raid_info['enemies_per_wave']}\n\n"
        f"Готовься к боям!"
    )
    
    keyboard = [[InlineKeyboardButton("⚔️ НАЧАТЬ", callback_data=f"raid_wave_{raid_id}")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def raid_wave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    raid_id = query.data.split("_")[2]
    raid_info = RAIDS[raid_id]
    
    progress = get_raid_progress(chat_id, user.id, raid_id)
    if not progress:
        await query.answer("❌ Рейд не найден", show_alert=True)
        return
    
    wave = progress["wave"]
    
    if wave > raid_info["waves"]:
        add_raid_completion(chat_id, user.id)
        add_xp(chat_id, user.id, user.first_name, raid_info["xp_reward"])
        add_gold(chat_id, user.id, raid_info["gold_reward"])
        
        for loot_item in raid_info["loot"]:
            if loot_item in MATERIALS:
                add_material(chat_id, user.id, loot_item)
            else:
                add_item(chat_id, user.id, loot_item)
        
        end_raid(chat_id, user.id, raid_id)
        
        loot_text = ""
        for item in raid_info["loot"]:
            if item in MATERIALS:
                mat = MATERIALS[item]
                loot_text += f"{mat['emoji']} {mat['name']}\n"
            else:
                it = ITEMS.get(item, {})
                loot_text += f"{it.get('emoji', '?')} {it.get('name', item)}\n"
        
        text = (
            f"🎉 РЕЙД ЗАВЕРШЁН!\n"
            f"{'─' * 35}\n\n"
            f"{raid_info['emoji']} {raid_info['name']}\n\n"
            f"📊 НАГРАДА:\n"
            f"+{raid_info['xp_reward']} XP\n"
            f"+{raid_info['gold_reward']} 💰\n\n"
            f"📦 ЛУТ:\n{loot_text}"
        )
        
        keyboard = [
            [InlineKeyboardButton("🏰 НОВЫЙ РЕЙД", callback_data="show_raids")],
            [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]
        ]
    else:
        enemies_in_wave = []
        for _ in range(raid_info["enemies_per_wave"]):
            enemy_id = random.choice(list(ENEMIES.keys()))
            enemies_in_wave.append(enemy_id)
        
        current_enemy_id = enemies_in_wave[0]
        current_enemy = ENEMIES[current_enemy_id]
        
        update_raid_progress(chat_id, user.id, raid_id, wave, 0)
        
        context.user_data[f"raid_{raid_id}_enemies"] = enemies_in_wave
        context.user_data[f"raid_{raid_id}_current"] = 0
        
        text = (
            f"🏰 {raid_info['name']}\n"
            f"{'─' * 35}\n\n"
            f"Волна {wave}/{raid_info['waves']}\n"
            f"Враг 1/{raid_info['enemies_per_wave']}\n\n"
            f"{current_enemy['emoji']} {current_enemy['name']}\n"
            f"HP: {current_enemy['health']}"
        )
        
        keyboard = [[InlineKeyboardButton("⚔️ АТАКОВАТЬ", callback_data=f"raid_attack_{raid_id}")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def raid_attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    raid_id = query.data.split("_")[2]
    raid_info = RAIDS[raid_id]
    player = get_player(chat_id, user.id)
    
    progress = get_raid_progress(chat_id, user.id, raid_id)
    enemies_list = context.user_data.get(f"raid_{raid_id}_enemies", [])
    current_idx = context.user_data.get(f"raid_{raid_id}_current", 0)
    
    if not enemies_list or current_idx >= len(enemies_list):
        new_wave = progress["wave"] + 1
        update_raid_progress(chat_id, user.id, raid_id, new_wave, 0)
        await raid_wave(update, context)
        return
    
    current_enemy_id = enemies_list[current_idx]
    current_enemy = ENEMIES[current_enemy_id]
    
    enemy_health = current_enemy["health"]
    player_damage = player["attack"] + random.randint(-2, 5)
    enemy_health -= player_damage
    
    if enemy_health <= 0:
        add_kill(chat_id, user.id)
        if current_enemy.get("is_boss"):
            add_boss_kill(chat_id, user.id)
        
        current_idx += 1
        context.user_data[f"raid_{raid_id}_current"] = current_idx
        
        if current_idx >= len(enemies_list):
            new_wave = progress["wave"] + 1
            update_raid_progress(chat_id, user.id, raid_id, new_wave, 0)
            await raid_wave(update, context)
            return
        
        next_enemy_id = enemies_list[current_idx]
        next_enemy = ENEMIES[next_enemy_id]
        
        text = (
            f"✅ Враг побежден!\n\n"
            f"Враг {current_idx + 1}/{raid_info['enemies_per_wave']}\n\n"
            f"{next_enemy['emoji']} {next_enemy['name']}\n"
            f"HP: {next_enemy['health']}"
        )
        
        keyboard = [[InlineKeyboardButton("⚔️ АТАКОВАТЬ", callback_data=f"raid_attack_{raid_id}")]]
    else:
        text = (
            f"⚔️ БОЙ В РЕЙДЕ\n"
            f"{'─' * 35}\n\n"
            f"Волна {progress['wave']}/{raid_info['waves']}\n"
            f"Враг {current_idx + 1}/{raid_info['enemies_per_wave']}\n\n"
            f"💥 Ты нанёс {player_damage} урона!\n\n"
            f"{current_enemy['emoji']} {current_enemy['name']}\n"
            f"HP: {enemy_health}"
        )
        
        keyboard = [[InlineKeyboardButton("⚔️ АТАКОВАТЬ", callback_data=f"raid_attack_{raid_id}")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def start_battle_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id

    player = get_player(chat_id, user.id)
    enemy_id = start_battle_db(chat_id, user.id)

    if not enemy_id:
        await query.answer("❌ Не удалось начать бой!", show_alert=True)
        return

    enemy_info = ENEMIES[enemy_id]
    pet = get_player_pet(chat_id, user.id)
    pet_info = PETS[pet["pet_id"]]

    enemy_health = enemy_info["health"] + player["level"] - 1 * 5
    player_health = player["health"]

    update_battle(chat_id, user.id, enemy_health, player_health)

    text = (
        f"⚔️ БОЙ\n"
        f"{'─' * 35}\n\n"
        f"👤 Твоё здоровье: {player_health}/{player['max_health']} HP\n"
        f"{pet_info['emoji']} Питомец: {pet_info['name']}\n\n"
        f"{enemy_info['emoji']} {enemy_info['name']}\n"
        f"HP: {enemy_health} HP\n"
        f"⚔️ Атака: {enemy_info['damage']}\n\n"
        f"Выбери действие!"
    )

    keyboard = [
        [InlineKeyboardButton("⚔️ АТАКОВАТЬ", callback_data="attack_enemy"), InlineKeyboardButton("🏥 ИСЦЕЛИТЬСЯ", callback_data="heal_self")],
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
        f"⚔️ АТАКА\n"
        f"{'─' * 35}\n\n"
        f"💥 Ты нанёс {player_damage} урона!\n"
        f"-{enemy_damage} HP (атака врага)\n\n"
        f"👤 Твоё здоровье: {new_player_health}/{player['max_health']} HP\n"
        f"{enemy_info['emoji']} Здоровье врага: {new_enemy_health} HP"
    )

    if new_enemy_health <= 0:
        xp_reward = int(enemy_info["xp"] * 1.2)
        gold_reward = enemy_info["gold"]

        add_xp(chat_id, user.id, user.first_name, xp_reward)
        add_gold(chat_id, user.id, gold_reward)
        add_kill(chat_id, user.id)

        if enemy_info.get("is_boss"):
            add_boss_kill(chat_id, user.id)

        for loot_item in enemy_info.get("loot", []):
            add_item(chat_id, user.id, loot_item)
            if loot_item in MATERIALS:
                add_material(chat_id, user.id, loot_item)

        end_battle(chat_id, user.id)

        loot_text = ""
        for item in enemy_info.get("loot", []):
            loot_text += f"{ITEMS.get(item, {}).get('emoji', '?')} {ITEMS.get(item, {}).get('name', item)}\n"

        text = (
            f"🎉 ПОБЕДА!\n"
            f"{'─' * 35}\n\n"
            f"{enemy_info['emoji']} {enemy_info['name']} побеждён!\n\n"
            f"📊 НАГРАДА:\n"
            f"+{xp_reward} XP\n"
            f"+{gold_reward} 💰\n\n"
            f"📦 ЛУТ:\n{loot_text}"
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
            f"💀 ПОРАЖЕНИЕ\n"
            f"{'─' * 35}\n\n"
            f"Ты был побеждён {enemy_info['emoji']} {enemy_info['name']}...\n\n"
            f"Твоё здоровье полностью восстановлено."
        )

        keyboard = [
            [InlineKeyboardButton("⚔️ НОВЫЙ БОЙ", callback_data="start_battle")],
            [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("⚔️ АТАКОВАТЬ", callback_data="attack_enemy"), InlineKeyboardButton("🏥 ИСЦЕЛИТЬСЯ", callback_data="heal_self")],
            [InlineKeyboardButton("❌ СБЕЖАТЬ", callback_data="flee_battle")]
        ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def pvp_find_opponent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id

    player = get_player(chat_id, user.id)

    if chat_id not in pvp_queue:
        pvp_queue[chat_id] = {}

    for waiting_user_id, waiting_player in pvp_queue[chat_id].items():
        if waiting_user_id != user.id:
            if abs(waiting_player["level"] - player["level"]) <= 3:
                pvp_queue[chat_id].pop(waiting_user_id)

                text = f"✅ Найден противник: {waiting_player['name']} (Ур. {waiting_player['level']})...\n\nБой начинается!"

                keyboard = [[InlineKeyboardButton("⚔️ НАЧАТЬ ПВП", callback_data=f"pvp_battle_{user.id}_{waiting_user_id}")]]

                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
                return

    pvp_queue[chat_id][user.id] = {
        "name": user.first_name,
        "level": player["level"],
        "user_id": user.id,
        "message_id": query.message.message_id
    }

    text = f"🔍 Поиск противника...\n\n⭐ Уровень: {player['level']}\n📊 Рейтинг: {get_pvp_stats(chat_id, user.id)['rating']}\n\n⏳ Жди до 3 минут..."

    keyboard = [
        [InlineKeyboardButton("🔍 ИСКАТЬ", callback_data="pvp_find_opponent")],
        [InlineKeyboardButton("❌ ОТМЕНА", callback_data="pvp_cancel")]
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def pvp_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id

    if chat_id in pvp_queue and user.id in pvp_queue[chat_id]:
        pvp_queue[chat_id].pop(user.id)

    text = "❌ Поиск отменён"

    keyboard = [[InlineKeyboardButton("🏟️ PVP", callback_data="show_pvp")]]

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
        [InlineKeyboardButton("🛡️ ЭКИПИРОВКА", callback_data="show_equipment"), InlineKeyboardButton("🛒 МАГАЗИН", callback_data="show_shop")],
        [InlineKeyboardButton("⚙️ КРАФТ", callback_data="show_crafting"), InlineKeyboardButton("👑 ТОП ИГРОКОВ", callback_data="show_top")],
        [InlineKeyboardButton("🏟️ PVP", callback_data="show_pvp"), InlineKeyboardButton("🏰 РЕЙДЫ", callback_data="show_raids")],
    ]

    reply_text = (
        f"⚔️ QUEST WORLD - RPG ПРИКЛЮЧЕНИЕ ⚔️\n\n"
        f"Добро пожаловать, {CLASSES[player['class']]['emoji']} {CLASSES[player['class']]['name']}!\n\n"
        f"Исследуй подземелья, учи умения и становись легендой!"
    )
    
    await query.edit_message_text(reply_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def pvp_battle_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Заглушка для функции ПВП боя - может быть расширена в будущем"""
    query = update.callback_query
    await query.answer("🏟️ ПВП боя: функция в разработке!", show_alert=False)


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
    elif data == "buy_pet_menu":
        await buy_pet_menu(update, context)
    elif data.startswith("buy_pet_"):
        await buy_pet(update, context)
    elif data == "show_equipment":
        await show_equipment(update, context)
    elif data == "equipment_weapons":
        await equipment_weapons(update, context)
    elif data == "equipment_armor":
        await equipment_armor(update, context)
    elif data.startswith("equip_"):
        await equip_item_handler(update, context)
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
        await start_raid_cmd(update, context)
    elif data.startswith("raid_wave_"):
        await raid_wave(update, context)
    elif data.startswith("raid_attack_"):
        await raid_attack(update, context)
    elif data == "start_battle":
        await start_battle_cmd(update, context)
    elif data == "attack_enemy":
        await attack_enemy(update, context)
    elif data == "heal_self":
        await heal_self(update, context)
    elif data == "flee_battle":
        await flee_battle(update, context)
    elif data == "show_pvp":
        await show_pvp(update, context)
    elif data == "pvp_find_opponent":
        await pvp_find_opponent(update, context)
    elif data == "pvp_cancel":
        await pvp_cancel(update, context)
    elif data == "main_menu":
        await main_menu(update, context)

# ========== СИСТЕМА ЛУТА И КРАФТОВ ==========

LOOT_TABLE = {
    # mob_level: [(item_id, quantity_range, rarity), ...]
    1: [("copper_ore", (1, 3), "common"), ("cloth_scrap", (1, 2), "common")],
    2: [("copper_ore", (2, 4), "common"), ("iron_ore", (1, 1), "common"), ("cloth_scrap", (1, 3), "common")],
    3: [("iron_ore", (1, 3), "common"), ("leather_scrap", (1, 2), "common"), ("herb_green", (1, 2), "common")],
    4: [("iron_ore", (2, 4), "common"), ("leather_scrap", (2, 3), "common"), ("herb_green", (1, 3), "common"), ("steel_ore", (1, 1), "uncommon")],
    5: [("steel_ore", (1, 3), "uncommon"), ("leather_scrap", (2, 4), "uncommon"), ("herb_blue", (1, 2), "uncommon"), ("crystal_shard", (1, 1), "rare")],
}

CRAFT_RECIPES = {
    "iron_sword": {
        "name": "🗡️ Железный меч",
        "materials": {"iron_ore": 5, "copper_ore": 2},
        "result": "iron_sword",
        "quantity": 1,
        "description": "Базовое железное оружие. Урон: +15",
        "type": "weapon"
    },
    "leather_armor": {
        "name": "🛡️ Кожаная броня",
        "materials": {"leather_scrap": 8, "cloth_scrap": 3},
        "result": "leather_armor",
        "quantity": 1,
        "description": "Простая защита. Броня: +5",
        "type": "armor"
    },
    "health_potion": {
        "name": "🧪 Зелье здоровья",
        "materials": {"herb_green": 3, "cloth_scrap": 1},
        "result": "health_potion",
        "quantity": 3,
        "description": "Восстанавливает 50 HP",
        "type": "consumable"
    },
    "steel_sword": {
        "name": "⚔️ Стальной меч",
        "materials": {"steel_ore": 5, "iron_ore": 3, "crystal_shard": 1},
        "result": "steel_sword",
        "quantity": 1,
        "description": "Улучшенное оружие. Урон: +25",
        "type": "weapon"
    },
    "mana_potion": {
        "name": "💙 Зелье маны",
        "materials": {"herb_blue": 5, "crystal_shard": 1},
        "result": "mana_potion",
        "quantity": 2,
        "description": "Восстанавливает 30 MP",
        "type": "consumable"
    },
}

SHOP_ITEMS = {
    "iron_sword": {"name": "🗡️ Железный меч", "price": 100, "attack": 15, "type": "weapon"},
    "leather_armor": {"name": "🛡️ Кожаная броня", "price": 80, "defense": 5, "type": "armor"},
    "steel_sword": {"name": "⚔️ Стальной меч", "price": 250, "attack": 25, "type": "weapon"},
    "steel_armor": {"name": "🛡️ Стальная броня", "price": 200, "defense": 10, "type": "armor"},
    "health_potion": {"name": "🧪 Зелье здоровья", "price": 20, "type": "potion"},
    "mana_potion": {"name": "💙 Зелье маны", "price": 30, "type": "potion"},
}

ITEM_NAMES = {
    "copper_ore": "🪨 Медная руда",
    "iron_ore": "🪨 Железная руда",
    "steel_ore": "🪨 Стальная руда",
    "cloth_scrap": "🧵 Клочок ткани",
    "leather_scrap": "🎒 Кусок кожи",
    "herb_green": "🌿 Зелёная трава",
    "herb_blue": "💎 Синяя трава",
    "crystal_shard": "✨ Осколок кристалла",
    "health_potion": "🧪 Зелье здоровья",
    "mana_potion": "💙 Зелье маны",
    "iron_sword": "🗡️ Железный меч",
    "leather_armor": "🛡️ Кожаная броня",
    "steel_sword": "⚔️ Стальной меч",
    "steel_armor": "🛡️ Стальная броня",
}

def get_recommended_mobs(player_level):
    """Возвращает уровни мобов для игрока"""
    return {
        "easy": max(1, player_level - 2),
        "normal": player_level,
        "hard": min(5, player_level + 2),
    }

def generate_loot(mob_level):
    """Сгенерировать лут от мобов"""
    loot = {}
    if mob_level not in LOOT_TABLE:
        mob_level = 5

    for item_id, qty_range, rarity in LOOT_TABLE[mob_level]:
        quantity = random.randint(qty_range[0], qty_range[1])
        loot[item_id] = quantity

    return loot

def can_craft(user_id, chat_id, recipe_id):
    """Проверить может ли игрок скрафтить рецепт"""
    if recipe_id not in CRAFT_RECIPES:
        return False, "❌ Рецепт не найден"

    recipe = CRAFT_RECIPES[recipe_id]

    for item_id, needed_qty in recipe["materials"].items():
        cursor.execute(
            'SELECT quantity FROM inventory WHERE user_id = ? AND chat_id = ? AND item_id = ?',
            (user_id, chat_id, item_id)
        )
        result = cursor.fetchone()
        have_qty = result[0] if result else 0

        if have_qty < needed_qty:
            item_name = ITEM_NAMES.get(item_id, item_id)
            return False, f"❌ Не хватает {item_name}. Нужно: {needed_qty}, есть: {have_qty}"

    return True, "✅ Можно крафтить"

async def craft_item(update, context, recipe_id):
    """Выполнить крафт"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    can_do, msg = can_craft(user_id, chat_id, recipe_id)

    if not can_do:
        await update.callback_query.answer(msg, show_alert=True)
        return

    recipe = CRAFT_RECIPES[recipe_id]

    # Убираем материалы
    for item_id, qty in recipe["materials"].items():
        cursor.execute(
            'UPDATE inventory SET quantity = quantity - ? WHERE user_id = ? AND chat_id = ? AND item_id = ?',
            (qty, user_id, chat_id, item_id)
        )
        cursor.execute('DELETE FROM inventory WHERE quantity <= 0 AND user_id = ? AND chat_id = ?',
                      (user_id, chat_id))

    # Добавляем результат
    cursor.execute(
        'INSERT INTO inventory (user_id, chat_id, item_id, quantity) VALUES (?, ?, ?, ?) '
        'ON CONFLICT(user_id, chat_id, item_id) DO UPDATE SET quantity = quantity + ?',
        (user_id, chat_id, recipe["result"], recipe["quantity"], recipe["quantity"])
    )

    conn.commit()

    result_name = ITEM_NAMES.get(recipe["result"], recipe["result"])
    text = f"✅ **Крафт завершён!**\n\n{recipe['name']}\n{recipe['description']}\n\n+{recipe['quantity']} {result_name}"

    await update.callback_query.edit_text(text, parse_mode="Markdown")
    await update.callback_query.answer("Крафт успешен!", show_alert=False)

async def buy_item(update, context, item_id):
    """Купить предмет в магазине"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if item_id not in SHOP_ITEMS:
        await update.callback_query.answer("❌ Предмет не найден", show_alert=True)
        return

    item = SHOP_ITEMS[item_id]
    price = item["price"]

    # Проверяем золото
    cursor.execute('SELECT gold FROM players WHERE user_id = ? AND chat_id = ?', (user_id, chat_id))
    result = cursor.fetchone()

    if not result or result[0] < price:
        current_gold = result[0] if result else 0
        await update.callback_query.answer(f"❌ Не хватает золота!\nЕсть: {current_gold}💰, нужно: {price}💰", show_alert=True)
        return

    # Снимаем золото
    cursor.execute('UPDATE players SET gold = gold - ? WHERE user_id = ? AND chat_id = ?',
                  (price, user_id, chat_id))

    # Добавляем предмет
    if item["type"] in ["weapon", "armor"]:
        cursor.execute(
            'INSERT INTO equipment (user_id, chat_id, item_id, attack, defense) VALUES (?, ?, ?, ?, ?) '
            'ON CONFLICT(user_id, chat_id, item_id) DO UPDATE SET attack = attack + ?, defense = defense + ?',
            (user_id, chat_id, item_id, item.get("attack", 0), item.get("defense", 0),
             item.get("attack", 0), item.get("defense", 0))
        )
    else:
        cursor.execute(
            'INSERT INTO inventory (user_id, chat_id, item_id, quantity) VALUES (?, ?, ?, 1) '
            'ON CONFLICT(user_id, chat_id, item_id) DO UPDATE SET quantity = quantity + 1',
            (user_id, chat_id, item_id)
        )

    conn.commit()

    text = f"✅ **Покупка успешна!**\n\n{item['name']}\n💰 Заплачено: {price}\n\nПредмет добавлен в инвентарь!"
    await update.callback_query.edit_text(text, parse_mode="Markdown")
    await update.callback_query.answer("Покупка выполнена!", show_alert=False)
def get_token():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token.strip() == "":
        logger.error("❌ ОШИБКА: Токен не найден в переменных окружения!")
        raise ValueError("TELEGRAM_BOT_TOKEN не установлена!")
    if len(token.strip()) < 10:
        logger.error(f"❌ ОШИБКА: Токен слишком короткий: {token[:5]}...")
        raise ValueError("Токен некорректный!")
    logger.info(f"✅ Токен загружен успешно: {token[:20]}...")
    return token.strip()

TOKEN = get_token()

try:
    app = ApplicationBuilder().token(TOKEN).build()
    logger.info("✅ Приложение успешно создано!")
except Exception as e:
    logger.error(f"❌ Ошибка при создании приложения: {e}")
    raise

