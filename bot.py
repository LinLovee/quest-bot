import os
import random
import logging
import sqlite3
import threading
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
from flask import Flask

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.FileHandler("quest_bot.log", encoding="utf-8"), logging.StreamHandler()]
)

logger = logging.getLogger(__name__)
db_lock = threading.RLock()
conn = sqlite3.connect('quest_bot.db', check_same_thread=False, timeout=30.0)
cursor = conn.cursor()

# ========== FLASK ДЛЯ WEB SERVICE ==========
app_flask = Flask(__name__)

@app_flask.route('/', methods=['GET'])
def health():
    return {'status': 'ok'}, 200

@app_flask.route('/webhook', methods=['POST'])
def webhook():
    return {'status': 'ok'}, 200

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
)''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS inventory (
    chat_id INTEGER, user_id INTEGER, item_id TEXT,
    quantity INTEGER, rarity TEXT, class_req TEXT,
    PRIMARY KEY (chat_id, user_id, item_id)
)''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS battles (
    chat_id INTEGER, user_id INTEGER,
    enemy_id TEXT, enemy_health INTEGER, player_health INTEGER,
    PRIMARY KEY (chat_id, user_id)
)''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS pvp_stats (
    chat_id INTEGER, user_id INTEGER,
    rating INTEGER DEFAULT 1000, wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0,
    PRIMARY KEY (chat_id, user_id)
)''')

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
    "wolf": {"name": "Волк", "emoji": "🐺", "damage_bonus": 10, "defense_bonus": 3, "xp_bonus": 1.1, "price": 1000},
    "dragon": {"name": "Дракон", "emoji": "🐉", "damage_bonus": 25, "defense_bonus": 8, "xp_bonus": 1.5, "price": 5000},
    "phoenix": {"name": "Феникс", "emoji": "🔥", "damage_bonus": 20, "defense_bonus": 5, "xp_bonus": 1.4, "price": 4000},
    "shadow": {"name": "Тень", "emoji": "⚫", "damage_bonus": 15, "defense_bonus": 4, "xp_bonus": 1.3, "price": 2500},
    "bear": {"name": "Медведь", "emoji": "🐻", "damage_bonus": 18, "defense_bonus": 10, "xp_bonus": 1.2, "price": 2000},
    "ancient_dragon": {"name": "Древний Дракон", "emoji": "👹", "damage_bonus": 40, "defense_bonus": 15, "xp_bonus": 2.0, "price": 15000},
    "celestial_phoenix": {"name": "Небесный Феникс", "emoji": "✨", "damage_bonus": 35, "defense_bonus": 12, "xp_bonus": 1.9, "price": 12000},
}

# ========== ВРАГИ ==========
ENEMIES = {
    "goblin": {"name": "Гоблин", "emoji": "👹", "level": 1, "health": 15, "damage": 3, "xp": 25, "gold": 10, "loot": ["copper_coin"], "is_boss": False},
    "rat": {"name": "Крыса", "emoji": "🐭", "level": 1, "health": 10, "damage": 2, "xp": 15, "gold": 5, "loot": ["copper_coin"], "is_boss": False},
    "skeleton": {"name": "Скелет", "emoji": "☠️", "level": 2, "health": 25, "damage": 5, "xp": 40, "gold": 20, "loot": ["bone_fragment"], "is_boss": False},
    "zombie": {"name": "Зомби", "emoji": "🧟", "level": 2, "health": 30, "damage": 6, "xp": 50, "gold": 25, "loot": ["rotten_flesh"], "is_boss": False},
    "imp": {"name": "Чертёнок", "emoji": "😈", "level": 2, "health": 20, "damage": 7, "xp": 45, "gold": 15, "loot": ["sulfur"], "is_boss": False},
    "orc": {"name": "Орк", "emoji": "🗡️", "level": 3, "health": 45, "damage": 12, "xp": 100, "gold": 50, "is_boss": False},
    "troll": {"name": "Тролль", "emoji": "👹", "level": 3, "health": 60, "damage": 11, "xp": 110, "gold": 60, "is_boss": False},
    "werewolf": {"name": "Оборотень", "emoji": "🐺", "level": 4, "health": 50, "damage": 15, "xp": 130, "gold": 70, "is_boss": False},
    "shadow_knight": {"name": "Рыцарь Теней", "emoji": "⚔️", "level": 4, "health": 65, "damage": 18, "xp": 150, "gold": 80, "is_boss": False},
    "witch": {"name": "Ведьма", "emoji": "🧙♀️", "level": 4, "health": 40, "damage": 20, "xp": 140, "gold": 75, "is_boss": False},
    "basilisk": {"name": "Василиск", "emoji": "🐍", "level": 5, "health": 100, "damage": 25, "xp": 200, "gold": 120, "is_boss": False},
    "ice_mage": {"name": "Ледяной маг", "emoji": "❄️", "level": 5, "health": 55, "damage": 28, "xp": 180, "gold": 110, "is_boss": False},
    "demon": {"name": "Демон", "emoji": "😈", "level": 6, "health": 120, "damage": 32, "xp": 250, "gold": 150, "is_boss": False},
    "golem": {"name": "Голем", "emoji": "🪨", "level": 6, "health": 150, "damage": 20, "xp": 220, "gold": 140, "is_boss": False},
    "dragon": {"name": "Дракон", "emoji": "🐉", "level": 7, "health": 200, "damage": 40, "xp": 500, "gold": 300, "is_boss": True},
    "lich": {"name": "Лич", "emoji": "💀", "level": 8, "health": 180, "damage": 45, "xp": 550, "gold": 350, "is_boss": True},
    "archidemon": {"name": "Архидемон", "emoji": "😈", "level": 9, "health": 250, "damage": 50, "xp": 700, "gold": 400, "is_boss": True},
    "lich_king": {"name": "Лич-Король", "emoji": "👿", "level": 10, "health": 300, "damage": 60, "xp": 1000, "gold": 500, "is_boss": True},
}

# ========== ЭКИПИРОВКА ==========
EQUIPMENT_ITEMS = {
    "iron_sword": {"name": "Железный меч", "emoji": "⚔️", "type": "weapon", "attack": 5, "price": 200, "class": "warrior"},
    "steel_sword": {"name": "Стальной меч", "emoji": "🗡️", "type": "weapon", "attack": 10, "price": 500, "class": "warrior"},
    "legendary_sword": {"name": "Меч Вечности", "emoji": "⚡", "type": "weapon", "attack": 50, "price": 5000, "class": "warrior"},
    "iron_armor": {"name": "Железная броня", "emoji": "🛡️", "type": "armor", "defense": 4, "price": 250, "class": "warrior"},
    "steel_armor": {"name": "Стальная броня", "emoji": "🛡️", "type": "armor", "defense": 8, "price": 600, "class": "warrior"},
    "fireball_staff": {"name": "Посох огня", "emoji": "🔥", "type": "weapon", "attack": 8, "price": 200, "class": "mage"},
    "archimage_staff": {"name": "Посох Архимага", "emoji": "🔮", "type": "weapon", "attack": 30, "price": 5000, "class": "mage"},
    "mage_robe": {"name": "Мантия мага", "emoji": "👗", "type": "armor", "defense": 2, "price": 150, "class": "mage"},
    "dagger": {"name": "Кинжал", "emoji": "🗡️", "type": "weapon", "attack": 6, "price": 180, "class": "rogue"},
    "shadow_dagger": {"name": "Теневой кинжал", "emoji": "⚫", "type": "weapon", "attack": 15, "price": 1000, "class": "rogue"},
    "holy_shield": {"name": "Святой щит", "emoji": "⛪", "type": "armor", "defense": 6, "price": 300, "class": "paladin"},
    "longbow": {"name": "Длинный лук", "emoji": "🏹", "type": "weapon", "attack": 7, "price": 220, "class": "ranger"},
}

# ========== МАГАЗИН ==========
SHOP_ITEMS = {
    "health_potion": {"name": "Зелье здоровья", "emoji": "❤️", "price": 50, "rarity": "common"},
    "mana_potion": {"name": "Зелье маны", "emoji": "💙", "price": 50, "rarity": "common"},
    "strength_potion": {"name": "Зелье силы", "emoji": "💪", "price": 100, "rarity": "uncommon"},
}

# ========== ПРЕДМЕТЫ ==========
ITEMS = {
    "copper_coin": {"name": "Медная монета", "rarity": "common", "emoji": "🪙"},
    "bone_fragment": {"name": "Фрагмент кости", "rarity": "common", "emoji": "🦴"},
    "rotten_flesh": {"name": "Гнилое мясо", "rarity": "common", "emoji": "🥩"},
    "iron_ore": {"name": "Железная руда", "rarity": "uncommon", "emoji": "⛏️"},
    "dragon_scale": {"name": "Чешуя дракона", "rarity": "legendary", "emoji": "🐉"},
    "dragon_heart": {"name": "Сердце дракона", "rarity": "legendary", "emoji": "❤️"},
}

LEVEL_REQUIREMENTS = {i: i * 300 for i in range(1, 51)}

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
            "pet_id": row[14],
            "pet_level": row[15],
            "gold": row[16],
            "total_kills": row[17],
            "total_bosses_killed": row[18],
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
    bonus = {"attack": 0, "defense": 0, "mana": 0, "health": 0}
    
    if row:
        if row[0]:
            weapon = EQUIPMENT_ITEMS.get(row[0], {})
            bonus["attack"] += weapon.get("attack", 0)
        if row[1]:
            armor = EQUIPMENT_ITEMS.get(row[1], {})
            bonus["defense"] += armor.get("defense", 0)
            bonus["mana"] += armor.get("mana", 0)
            bonus["health"] += armor.get("health", 0)
    
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
def get_top_players(chat_id, limit=10):
    cursor.execute(
        'SELECT user_name, level, total_kills, gold, class FROM players WHERE chat_id=? ORDER BY level DESC, total_kills DESC LIMIT ?',
        (chat_id, limit)
    )
    return cursor.fetchall()

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
        await main_menu(update, context)

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
        "Выбери свой класс для начала приключения!"
    )
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def after_class_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await main_menu(update, context)

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    player = get_player(chat_id, user.id)
    if not player:
        await start_command(update, context)
        return
    
    class_info = CLASSES[player['class']]
    
    keyboard = [
        [InlineKeyboardButton("⚔️ БОЙ", callback_data="start_battle"), 
         InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data="show_profile")],
        [InlineKeyboardButton("🐾 ПИТОМЕЦ", callback_data="show_pet"), 
         InlineKeyboardButton("📦 ИНВЕНТАРЬ", callback_data="show_inventory")],
        [InlineKeyboardButton("🛡️ ЭКИПИРОВКА", callback_data="show_equipment"), 
         InlineKeyboardButton("🛒 МАГАЗИН", callback_data="show_shop")],
        [InlineKeyboardButton("👑 ТОП ИГРОКОВ", callback_data="show_top")],
    ]
    
    reply_text = (
        f"⚔️ QUEST WORLD - RPG ПРИКЛЮЧЕНИЕ ⚔️\n\n"
        f"Добро пожаловать, {class_info['emoji']} {class_info['name']}!\n\n"
        f"Исследуй подземелья и становись легендой!"
    )
    
    try:
        await query.edit_message_text(reply_text, reply_markup=InlineKeyboardMarkup(keyboard))
    except:
        pass

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
        text += f" ✅ {equipped_weapon['name']} (+{equipped_weapon.get('attack', 0)} атаки)\n"
    else:
        text += " ❌ Нет оружия\n"
    
    text += f"\n🛡️ БРОНЯ:\n"
    
    if equipped_armor:
        text += f" ✅ {equipped_armor['name']} (+{equipped_armor.get('defense', 0)} защиты)\n"
    else:
        text += " ❌ Нет брони\n"
    
    text += f"\n📊 СТАТЫ:\n⚔️ Атака: {player['attack']}\n🛡️ Защита: {player['defense']}\n\n"
    text += f"💡 СОВЕТ: Нажми на оружие или броню ниже!"
    
    keyboard = [
        [InlineKeyboardButton("⚔️ ОРУЖИЕ", callback_data="equipment_weapons"), 
         InlineKeyboardButton("🛡️ БРОНЯ", callback_data="equipment_armor")],
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
    
    if item_info.get("class") and item_info["class"] != get_player(chat_id, user.id)["class"]:
        await query.answer(f"❌ Предмет не подходит для вашего класса!", show_alert=True)
        return
    
    if equip_item(chat_id, user.id, item_id):
        player = get_player(chat_id, user.id)
        class_info = CLASSES[player["class"]]
        
        text = f"✅ Экипировано: {item_info['emoji']} {item_info['name']}\n\n🛡️ ЭКИПИРОВКА\n{'─' * 35}\n\n"
        
        equipped_weapon = EQUIPMENT_ITEMS.get(player["equipped_weapon"]) if player["equipped_weapon"] else None
        equipped_armor = EQUIPMENT_ITEMS.get(player["equipped_armor"]) if player["equipped_armor"] else None
        
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
            [InlineKeyboardButton("⚔️ ОРУЖИЕ", callback_data="equipment_weapons"), 
             InlineKeyboardButton("🛡️ БРОНЯ", callback_data="equipment_armor")],
            [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")],
        ]
    else:
        text = "❌ Не удалось экипировать предмет"
        keyboard = [[InlineKeyboardButton("⬅️ НАЗАД", callback_data="show_equipment")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_pet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    pet = get_player_pet(chat_id, user.id)
    pet_info = PETS[pet["pet_id"]]
    
    text = (
        f"🐾 ВАШ ПИТОМЕЦ\n"
        f"{'─' * 35}\n\n"
        f"{pet_info['emoji']} {pet_info['name'].upper()}\n"
        f"⭐ Уровень: {pet['pet_level']}/100\n\n"
        f"📊 СПОСОБНОСТИ:\n"
        f"⚔️ Бонус атаки: +{pet_info['damage_bonus']}\n"
        f"🛡️ Бонус защиты: +{pet_info['defense_bonus']}\n"
        f"📈 Бонус XP: ×{pet_info['xp_bonus']}\n\n"
        f"💰 Цена: {pet_info['price']} золота"
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
            text += f"{item_info.get('emoji', '?')} {item_info.get('name', item_id)}\n x{qty} {rarity_emoji}\n"
    
    keyboard = [[InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    player = get_player(chat_id, user.id)
    
    text = "🛒 МАГАЗИН\n" + f"{'─' * 35}\n\n"
    text += f"💰 Твоё золото: {player['gold']}\n\n"
    text += f"📦 ЗЕЛЬЯ:\n"
    
    keyboard = []
    for item_id, item_info in SHOP_ITEMS.items():
        affordable = "✅" if player['gold'] >= item_info['price'] else "❌"
        text += f"{item_info['emoji']} {item_info['name']} - {item_info['price']}💰 {affordable}\n"
        keyboard.append([InlineKeyboardButton(
            f"Купить {item_info['emoji']}",
            callback_data=f"buy_{item_id}"
        )])
    
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
        text += f" ⭐ Ур. {level} | ⚔️ {kills} | 💰 {gold}\n"
    
    if not top_players:
        text = "👑 ТОП 10 ИГРОКОВ\n\n❌ Данных нет"
    
    keyboard = [[InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def start_battle_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    enemy_id = start_battle_db(chat_id, user.id)
    enemy_info = ENEMIES[enemy_id]
    player = get_player(chat_id, user.id)
    
    text = (
        f"⚔️ БОЙ НАЧАЛСЯ!\n\n"
        f"Противник: {enemy_info['emoji']} {enemy_info['name']} (Ур. {enemy_info['level']})\n"
        f"❤️ HP врага: {enemy_info['health']}\n"
        f"❤️ Твой HP: {player['health']}/{player['max_health']}"
    )
    
    keyboard = [
        [InlineKeyboardButton("⚔️ АТАКОВАТЬ", callback_data="attack_enemy")],
        [InlineKeyboardButton("🏃 БЕЖАТЬ", callback_data="flee_battle")],
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def attack_enemy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    battle = get_battle(chat_id, user.id)
    if not battle:
        await query.answer("❌ Боя нет!", show_alert=True)
        return
    
    player = get_player(chat_id, user.id)
    enemy_info = ENEMIES[battle["enemy_id"]]
    pet = get_player_pet(chat_id, user.id)
    pet_info = PETS[pet["pet_id"]]
    bonus = get_equipment_bonus(chat_id, user.id)
    
    player_attack = player['attack'] + bonus['attack'] + pet_info['damage_bonus']
    damage = random.randint(max(1, player_attack - 2), player_attack + 5)
    enemy_health = battle["enemy_health"] - damage
    player_damage = random.randint(enemy_info['damage'] - 1, enemy_info['damage'] + 3)
    player_defense = player['defense'] + bonus['defense'] + pet_info['defense_bonus']
    player_damage = max(1, player_damage - player_defense // 3)
    player_health = max(0, player["health"] - player_damage)
    
    update_battle(chat_id, user.id, enemy_health, player_health)
    cursor.execute(
        'UPDATE players SET health=? WHERE chat_id=? AND user_id=?',
        (player_health, chat_id, user.id)
    )
    conn.commit()
    
    text = (
        f"⚔️ БОЙ\n\n"
        f"Ты нанёс {damage} урона!\n"
        f"{enemy_info['emoji']} Враг нанёс {player_damage} урона в ответ!\n\n"
        f"❤️ HP врага: {max(0, enemy_health)}\n"
        f"❤️ Твой HP: {max(0, player_health)}/{player['max_health']}"
    )
    
    keyboard = []
    
    if enemy_health <= 0:
        xp_reward = int(enemy_info['xp'] * 1.2)
        gold_reward = enemy_info['gold']
        add_xp(chat_id, user.id, user.first_name, xp_reward)
        add_gold(chat_id, user.id, gold_reward)
        add_kill(chat_id, user.id)
        
        if enemy_info.get('is_boss'):
            add_boss_kill(chat_id, user.id)
        
        for loot_item in enemy_info.get('loot', []):
            add_item(chat_id, user.id, loot_item)
            if loot_item in MATERIALS:
                add_material(chat_id, user.id, loot_item)
        
        end_battle(chat_id, user.id)
        loot_text = ""
        for item in enemy_info.get('loot', []):
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
            [InlineKeyboardButton("⚔️ ЕЩЕ БОЙ", callback_data="start_battle")],
            [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")],
        ]
    elif player_health <= 0:
        end_battle(chat_id, user.id)
        text = (
            f"❌ ТЫ ПРОИГРАЛ!\n\n"
            f"{enemy_info['emoji']} {enemy_info['name']} одолел тебя...\n\n"
            f"Вернись когда окрепнешь!"
        )
        keyboard = [
            [InlineKeyboardButton("⚔️ ЕЩЕ БОЙ", callback_data="start_battle")],
            [InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")],
        ]
    else:
        update_battle(chat_id, user.id, enemy_health, player_health)
        keyboard = [
            [InlineKeyboardButton("⚔️ АТАКОВАТЬ", callback_data="attack_enemy")],
            [InlineKeyboardButton("🏃 БЕЖАТЬ", callback_data="flee_battle")],
        ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def flee_battle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    
    end_battle(chat_id, user.id)
    
    text = "🏃 Ты убежал из боя!"
    keyboard = [[InlineKeyboardButton("⬅️ ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ========== ГЛАВНАЯ ФУНКЦИЯ ДЛЯ WEB SERVICE ==========

async def main_telegram():
    """Главная функция для запуска бота"""
    port = int(os.getenv("PORT", 8000))
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not token:
        logger.error("❌ TELEGRAM_BOT_TOKEN не установлен!")
        return
    
    logger.info(f"🚀 Запуск бота на порту {port}...")
    
    # Создаём приложение
    app = ApplicationBuilder().token(token).build()
    
    # Регистрируем команды
    app.add_handler(CommandHandler("start", start_command))
    
    # Callback handlers
    app.add_handler(CallbackQueryHandler(select_class, pattern="^class_"))
    app.add_handler(CallbackQueryHandler(restart_class_selection, pattern="^restart_class_selection$"))
    app.add_handler(CallbackQueryHandler(after_class_select, pattern="^after_class_select$"))
    
    app.add_handler(CallbackQueryHandler(show_profile, pattern="^show_profile$"))
    app.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))
    
    app.add_handler(CallbackQueryHandler(show_pet, pattern="^show_pet$"))
    app.add_handler(CallbackQueryHandler(buy_pet_menu, pattern="^buy_pet_menu$"))
    app.add_handler(CallbackQueryHandler(buy_pet, pattern="^buy_pet_"))
    
    app.add_handler(CallbackQueryHandler(show_equipment, pattern="^show_equipment$"))
    app.add_handler(CallbackQueryHandler(equipment_weapons, pattern="^equipment_weapons$"))
    app.add_handler(CallbackQueryHandler(equipment_armor, pattern="^equipment_armor$"))
    app.add_handler(CallbackQueryHandler(equip_item_handler, pattern="^equip_"))
    
    app.add_handler(CallbackQueryHandler(show_inventory, pattern="^show_inventory$"))
    app.add_handler(CallbackQueryHandler(show_shop, pattern="^show_shop$"))
    app.add_handler(CallbackQueryHandler(buy_item, pattern="^buy_"))
    
    app.add_handler(CallbackQueryHandler(show_top, pattern="^show_top$"))
    
    app.add_handler(CallbackQueryHandler(start_battle_cmd, pattern="^start_battle$"))
    app.add_handler(CallbackQueryHandler(attack_enemy, pattern="^attack_enemy$"))
    app.add_handler(CallbackQueryHandler(flee_battle, pattern="^flee_battle$"))
    
    # ✅ ЗАПУСК БОТА В POLLING РЕЖИМЕ
    await app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    import asyncio
    
    # Запускаем Flask в отдельном потоке для Web Service
    import threading
    def run_flask():
        port = int(os.getenv("PORT", 8000))
        app_flask.run(host="0.0.0.0", port=port)
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info("✅ Flask запущен для Web Service")
    
    # Запускаем Telegram бота
    asyncio.run(main_telegram())
