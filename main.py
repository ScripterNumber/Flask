from flask import Flask, request, jsonify
from threading import Thread
import telebot
from telebot import types
import time
import json
import os

app = Flask(__name__)

servers = {}
pending_commands = {}
user_states = {}

BOT_TOKEN = "7950194700:AAHeIfO6UwnCXnN8M200L4MfEdAmIhZs6r8"

OWNER_IDS = [8096475445, 8220513089]

ADMINS_FILE = "admins.json"

def load_admins():
    if os.path.exists(ADMINS_FILE):
        try:
            with open(ADMINS_FILE, 'r') as f:
                data = json.load(f)
                return set(data.get('ids', [])), set(data.get('usernames', []))
        except:
            pass
    return set(OWNER_IDS), set()

def save_admins(admin_ids, admin_usernames):
    with open(ADMINS_FILE, 'w') as f:
        json.dump({
            'ids': list(admin_ids),
            'usernames': list(admin_usernames)
        }, f)

admin_ids, admin_usernames = load_admins()
for owner_id in OWNER_IDS:
    admin_ids.add(owner_id)

bot = telebot.TeleBot(BOT_TOKEN)

SERVER_TIMEOUT = 15

def is_admin(user_id, username=None):
    if user_id in admin_ids:
        return True
    if username and username.lower() in [u.lower() for u in admin_usernames]:
        admin_ids.add(user_id)
        save_admins(admin_ids, admin_usernames)
        return True
    return False

def is_owner(user_id):
    return user_id in OWNER_IDS

def cleanup_servers():
    current_time = time.time()
    dead_servers = []
    for job_id, info in servers.items():
        if current_time - info.get('last_heartbeat', 0) > SERVER_TIMEOUT:
            dead_servers.append(job_id)
        elif info.get('player_count', 0) == 0:
            dead_servers.append(job_id)
    for job_id in dead_servers:
        servers.pop(job_id, None)
        pending_commands.pop(job_id, None)

def get_active_servers():
    cleanup_servers()
    return servers

@app.route('/')
def home():
    active = get_active_servers()
    return f"Online. Servers: {len(active)}"

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    data = request.json
    job_id = data['job_id']
    player_count = data.get('player_count', 0)
    
    if player_count == 0:
        servers.pop(job_id, None)
        pending_commands.pop(job_id, None)
        return jsonify({"commands": []})
    
    servers[job_id] = {
        "players": data['players'],
        "player_count": player_count,
        "max_players": data['max_players'],
        "last_heartbeat": time.time()
    }
    
    commands = pending_commands.pop(job_id, [])
    return jsonify({"commands": commands})

@app.route('/player_joined', methods=['POST'])
def player_joined():
    data = request.json
    job_id = data['job_id']
    if job_id in servers:
        servers[job_id]['players'][str(data['user_id'])] = {
            "name": data['username'],
            "display_name": data.get('display_name', data['username'])
        }
        servers[job_id]['player_count'] = len(servers[job_id]['players'])
        servers[job_id]['last_heartbeat'] = time.time()
    return jsonify({"status": "ok"})

@app.route('/player_left', methods=['POST'])
def player_left():
    data = request.json
    job_id = data['job_id']
    if job_id in servers:
        servers[job_id]['players'].pop(str(data['user_id']), None)
        servers[job_id]['player_count'] = len(servers[job_id]['players'])
        servers[job_id]['last_heartbeat'] = time.time()
        
        if servers[job_id]['player_count'] == 0:
            servers.pop(job_id, None)
            pending_commands.pop(job_id, None)
    
    return jsonify({"status": "ok"})

def get_server_name(job_id):
    return f"Сервер {job_id[:6]}"

@bot.message_handler(commands=['start', 'panel'])
def start(message):
    username = message.from_user.username
    if not is_admin(message.from_user.id, username):
        bot.reply_to(message, "❌ Нет доступа")
        return
    
    active = get_active_servers()
    total_players = sum(info['player_count'] for info in active.values())
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔍 Найти игрока", callback_data="search"))
    
    if is_owner(message.from_user.id):
        markup.add(types.InlineKeyboardButton("👑 Управление админами", callback_data="admin_manage"))
    
    bot.send_message(
        message.chat.id,
        f"🎮 Панель управления Roblox\n\n📡 Серверов: {len(active)}\n👥 Игроков онлайн: {total_players}",
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: message.from_user.id in user_states)
def handle_input(message):
    username = message.from_user.username
    if not is_admin(message.from_user.id, username):
        return
    
    state = user_states.pop(message.from_user.id, None)
    if not state:
        return
    
    action = state.get('action')
    job_id = state.get('job_id')
    user_id = state.get('user_id')
    
    if action == 'give_item':
        item_name = message.text.strip()
        
        if job_id not in pending_commands:
            pending_commands[job_id] = []
        
        pending_commands[job_id].append({
            "action": "give_item",
            "user_id": int(user_id),
            "item_name": item_name
        })
        
        display_name = get_player_display_name(job_id, user_id)
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ К игроку", callback_data=f"plrp2_{job_id}_{user_id}"))
        markup.add(types.InlineKeyboardButton("🏠 Меню", callback_data="menu"))
        
        bot.send_message(
            message.chat.id,
            f"🎁 {display_name} получит предмет: {item_name}",
            reply_markup=markup
        )
    
    elif action == 'set_deaths':
        try:
            deaths = int(message.text.strip())
        except ValueError:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("⬅️ К игроку", callback_data=f"plrp2_{job_id}_{user_id}"))
            bot.send_message(message.chat.id, "❌ Введите число!", reply_markup=markup)
            return
        
        if job_id not in pending_commands:
            pending_commands[job_id] = []
        
        pending_commands[job_id].append({
            "action": "set_deaths",
            "user_id": int(user_id),
            "value": deaths
        })
        
        display_name = get_player_display_name(job_id, user_id)
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ К игроку", callback_data=f"plrp2_{job_id}_{user_id}"))
        markup.add(types.InlineKeyboardButton("🏠 Меню", callback_data="menu"))
        
        bot.send_message(
            message.chat.id,
            f"💀 {display_name} теперь имеет {deaths} смертей",
            reply_markup=markup
        )
    
    elif action == 'set_coins':
        try:
            coins = int(message.text.strip())
        except ValueError:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("⬅️ К игроку", callback_data=f"plrp2_{job_id}_{user_id}"))
            bot.send_message(message.chat.id, "❌ Введите число!", reply_markup=markup)
            return
        
        if job_id not in pending_commands:
            pending_commands[job_id] = []
        
        pending_commands[job_id].append({
            "action": "set_coins",
            "user_id": int(user_id),
            "value": coins
        })
        
        display_name = get_player_display_name(job_id, user_id)
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ К игроку", callback_data=f"plrp2_{job_id}_{user_id}"))
        markup.add(types.InlineKeyboardButton("🏠 Меню", callback_data="menu"))
        
        bot.send_message(
            message.chat.id,
            f"🪙 {display_name} теперь имеет {coins} монет",
            reply_markup=markup
        )
    
    elif action == 'add_admin':
        text = message.text.strip()
        
        if text.startswith('@'):
            new_username = text[1:]
            admin_usernames.add(new_username.lower())
            save_admins(admin_ids, admin_usernames)
            result_text = f"✅ Админ @{new_username} добавлен"
        else:
            try:
                new_id = int(text)
                admin_ids.add(new_id)
                save_admins(admin_ids, admin_usernames)
                result_text = f"✅ Админ с ID {new_id} добавлен"
            except ValueError:
                admin_usernames.add(text.lower())
                save_admins(admin_ids, admin_usernames)
                result_text = f"✅ Админ @{text} добавлен"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ К админам", callback_data="admin_manage"))
        markup.add(types.InlineKeyboardButton("🏠 Меню", callback_data="menu"))
        
        bot.send_message(message.chat.id, result_text, reply_markup=markup)
    
    elif action == 'remove_admin':
        text = message.text.strip()
        removed = False
        
        if text.startswith('@'):
            username_to_remove = text[1:].lower()
            if username_to_remove in [u.lower() for u in admin_usernames]:
                admin_usernames.discard(username_to_remove)
                save_admins(admin_ids, admin_usernames)
                removed = True
                result_text = f"✅ Админ @{username_to_remove} удалён"
        else:
            try:
                id_to_remove = int(text)
                if id_to_remove in OWNER_IDS:
                    result_text = "❌ Нельзя удалить владельца!"
                elif id_to_remove in admin_ids:
                    admin_ids.discard(id_to_remove)
                    save_admins(admin_ids, admin_usernames)
                    removed = True
                    result_text = f"✅ Админ с ID {id_to_remove} удалён"
                else:
                    result_text = "❌ Админ не найден"
            except ValueError:
                username_to_remove = text.lower()
                if username_to_remove in [u.lower() for u in admin_usernames]:
                    admin_usernames.discard(username_to_remove)
                    save_admins(admin_ids, admin_usernames)
                    removed = True
                    result_text = f"✅ Админ @{username_to_remove} удалён"
                else:
                    result_text = "❌ Админ не найден"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ К админам", callback_data="admin_manage"))
        markup.add(types.InlineKeyboardButton("🏠 Меню", callback_data="menu"))
        
        bot.send_message(message.chat.id, result_text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    username = call.from_user.username
    if not is_admin(call.from_user.id, username):
        return
    
    user_states.pop(call.from_user.id, None)
    
    data = call.data
    
    if data == "admin_manage":
        if not is_owner(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только для владельцев!")
            return
        
        show_admin_management(call)
    
    elif data == "admin_add":
        if not is_owner(call.from_user.id):
            return
        
        user_states[call.from_user.id] = {'action': 'add_admin'}
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="admin_manage"))
        
        bot.edit_message_text(
            "➕ Введите @username или ID нового админа:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif data == "admin_remove":
        if not is_owner(call.from_user.id):
            return
        
        user_states[call.from_user.id] = {'action': 'remove_admin'}
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="admin_manage"))
        
        bot.edit_message_text(
            "➖ Введите @username или ID админа для удаления:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif data == "admin_list":
        if not is_owner(call.from_user.id):
            return
        
        text = "👑 Список администраторов:\n\n"
        text += "🔒 Владельцы (нельзя удалить):\n"
        for oid in OWNER_IDS:
            text += f"  • ID: {oid}\n"
        
        non_owner_ids = [aid for aid in admin_ids if aid not in OWNER_IDS]
        if non_owner_ids:
            text += "\n👤 Админы по ID:\n"
            for aid in non_owner_ids:
                text += f"  • {aid}\n"
        
        if admin_usernames:
            text += "\n👤 Админы по username:\n"
            for uname in admin_usernames:
                text += f"  • @{uname}\n"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="admin_manage"))
        
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif data.startswith("plr_"):
        parts = data.split("_")
        job_id = parts[1]
        user_id = parts[2]
        show_player_page1(call, job_id, user_id)
    
    elif data.startswith("plrp2_"):
        parts = data.split("_")
        job_id = parts[1]
        user_id = parts[2]
        show_player_page2(call, job_id, user_id)
    
    elif data.startswith("srvact_"):
        parts = data.split("_")
        job_id = parts[1]
        user_id = parts[2]
        show_server_actions(call, job_id, user_id)
    
    elif data.startswith("killall_"):
        parts = data.split("_")
        job_id = parts[1]
        user_id = parts[2]
        
        if job_id not in pending_commands:
            pending_commands[job_id] = []
        
        pending_commands[job_id].append({
            "action": "kill_all"
        })
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"srvact_{job_id}_{user_id}"))
        markup.add(types.InlineKeyboardButton("🏠 Меню", callback_data="menu"))
        
        bot.edit_message_text(
            "💀 Все игроки на сервере будут убиты",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif data.startswith("giveitem_"):
        parts = data.split("_")
        job_id = parts[1]
        user_id = parts[2]
        
        user_states[call.from_user.id] = {
            'action': 'give_item',
            'job_id': job_id,
            'user_id': user_id
        }
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data=f"plrp2_{job_id}_{user_id}"))
        
        bot.edit_message_text(
            "🎁 Введите название предмета из ServerStorage._items:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif data.startswith("setdeaths_"):
        parts = data.split("_")
        job_id = parts[1]
        user_id = parts[2]
        
        user_states[call.from_user.id] = {
            'action': 'set_deaths',
            'job_id': job_id,
            'user_id': user_id
        }
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data=f"plrp2_{job_id}_{user_id}"))
        
        bot.edit_message_text(
            "💀 Введите количество смертей:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif data.startswith("setcoins_"):
        parts = data.split("_")
        job_id = parts[1]
        user_id = parts[2]
        
        user_states[call.from_user.id] = {
            'action': 'set_coins',
            'job_id': job_id,
            'user_id': user_id
        }
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data=f"plrp2_{job_id}_{user_id}"))
        
        bot.edit_message_text(
            "🪙 Введите количество монет:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif data.startswith("kick_"):
        parts = data.split("_")
        job_id = parts[1]
        user_id = parts[2]
        
        if job_id not in pending_commands:
            pending_commands[job_id] = []
        
        pending_commands[job_id].append({
            "action": "kick",
            "user_id": int(user_id),
            "reason": "Кикнут администратором"
        })
        
        display_name = get_player_display_name(job_id, user_id)
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ К игроку", callback_data=f"plr_{job_id}_{user_id}"))
        markup.add(types.InlineKeyboardButton("🏠 Меню", callback_data="menu"))
        
        bot.edit_message_text(
            f"👢 {display_name} будет кикнут",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif data.startswith("ban_"):
        parts = data.split("_")
        job_id = parts[1]
        user_id = parts[2]
        duration = int(parts[3])
        
        for jid in get_active_servers().keys():
            if jid not in pending_commands:
                pending_commands[jid] = []
            pending_commands[jid].append({
                "action": "ban",
                "user_id": int(user_id),
                "duration": duration,
                "reason": "Забанен администратором"
            })
        
        display_name = get_player_display_name(job_id, user_id)
        ban_text = "навсегда" if duration == 0 else f"на {duration} дн."
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ К игроку", callback_data=f"plr_{job_id}_{user_id}"))
        markup.add(types.InlineKeyboardButton("🏠 Меню", callback_data="menu"))
        
        bot.edit_message_text(
            f"🔨 {display_name} забанен {ban_text}",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif data.startswith("unban_"):
        parts = data.split("_")
        job_id = parts[1]
        user_id = parts[2]
        
        for jid in get_active_servers().keys():
            if jid not in pending_commands:
                pending_commands[jid] = []
            pending_commands[jid].append({
                "action": "unban",
                "user_id": int(user_id)
            })
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ К игроку", callback_data=f"plr_{job_id}_{user_id}"))
        markup.add(types.InlineKeyboardButton("🏠 Меню", callback_data="menu"))
        
        bot.edit_message_text(
            "✅ Игрок разбанен",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif data.startswith("kill_"):
        parts = data.split("_")
        job_id = parts[1]
        user_id = parts[2]
        
        if job_id not in pending_commands:
            pending_commands[job_id] = []
        
        pending_commands[job_id].append({
            "action": "kill",
            "user_id": int(user_id)
        })
        
        display_name = get_player_display_name(job_id, user_id)
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ К игроку", callback_data=f"plr_{job_id}_{user_id}"))
        markup.add(types.InlineKeyboardButton("🏠 Меню", callback_data="menu"))
        
        bot.edit_message_text(
            f"💀 {display_name} будет убит",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif data.startswith("rope_"):
        parts = data.split("_")
        job_id = parts[1]
        user_id = parts[2]
        
        if job_id not in pending_commands:
            pending_commands[job_id] = []
        
        pending_commands[job_id].append({
            "action": "rope",
            "user_id": int(user_id)
        })
        
        display_name = get_player_display_name(job_id, user_id)
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ К игроку", callback_data=f"plr_{job_id}_{user_id}"))
        markup.add(types.InlineKeyboardButton("🏠 Меню", callback_data="menu"))
        
        bot.edit_message_text(
            f"🪢 {display_name} получит верёвку",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif data.startswith("amogus_"):
        parts = data.split("_")
        job_id = parts[1]
        user_id = parts[2]
        
        if job_id not in pending_commands:
            pending_commands[job_id] = []
        
        pending_commands[job_id].append({
            "action": "amogus",
            "user_id": int(user_id)
        })
        
        display_name = get_player_display_name(job_id, user_id)
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ К игроку", callback_data=f"plrp2_{job_id}_{user_id}"))
        markup.add(types.InlineKeyboardButton("🏠 Меню", callback_data="menu"))
        
        bot.edit_message_text(
            f"📮 {display_name} станет амогусом",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif data == "menu":
        active = get_active_servers()
        total_players = sum(info['player_count'] for info in active.values())
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔍 Найти игрока", callback_data="search"))
        
        if is_owner(call.from_user.id):
            markup.add(types.InlineKeyboardButton("👑 Управление админами", callback_data="admin_manage"))
        
        bot.edit_message_text(
            f"🎮 Панель управления Roblox\n\n📡 Серверов: {len(active)}\n👥 Игроков онлайн: {total_players}",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif data == "search":
        msg = bot.edit_message_text(
            "🔍 Введите ник или DisplayName игрока:",
            call.message.chat.id,
            call.message.message_id
        )
        bot.register_next_step_handler(msg, search_player)

def show_admin_management(call):
    admin_count = len(admin_ids) + len(admin_usernames) - len([u for u in admin_usernames if any(is_admin(aid, u) for aid in admin_ids)])
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("➕ Добавить админа", callback_data="admin_add"))
    markup.add(types.InlineKeyboardButton("➖ Удалить админа", callback_data="admin_remove"))
    markup.add(types.InlineKeyboardButton("📋 Список админов", callback_data="admin_list"))
    markup.add(types.InlineKeyboardButton("🏠 Меню", callback_data="menu"))
    
    bot.edit_message_text(
        f"👑 Управление администраторами\n\n"
        f"📊 Всего админов по ID: {len(admin_ids)}\n"
        f"📊 Всего админов по username: {len(admin_usernames)}",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

def get_player_display_name(job_id, user_id):
    active = get_active_servers()
    player_info = active.get(job_id, {}).get('players', {}).get(user_id, {})
    if isinstance(player_info, dict):
        return player_info.get('display_name', player_info.get('name', 'Unknown'))
    return player_info if player_info else 'Unknown'

def show_player_page1(call, job_id, user_id):
    active = get_active_servers()
    player_info = active.get(job_id, {}).get('players', {}).get(user_id, {})
    
    if isinstance(player_info, dict):
        username = player_info.get('name', 'Unknown')
        display_name = player_info.get('display_name', username)
    else:
        username = player_info if player_info else 'Unknown'
        display_name = username
    
    server_name = get_server_name(job_id)
    
    markup = types.InlineKeyboardMarkup()
    
    if job_id in active:
        markup.add(types.InlineKeyboardButton(f"🖥 Действия на сервере", callback_data=f"srvact_{job_id}_{user_id}"))
    
    markup.add(types.InlineKeyboardButton("👢 Кикнуть", callback_data=f"kick_{job_id}_{user_id}"))
    markup.add(types.InlineKeyboardButton("🔨 Бан навсегда", callback_data=f"ban_{job_id}_{user_id}_0"))
    markup.add(
        types.InlineKeyboardButton("📅 Бан 1 день", callback_data=f"ban_{job_id}_{user_id}_1"),
        types.InlineKeyboardButton("📅 Бан 7 дней", callback_data=f"ban_{job_id}_{user_id}_7")
    )
    markup.add(types.InlineKeyboardButton("✅ Разбанить", callback_data=f"unban_{job_id}_{user_id}"))
    markup.add(types.InlineKeyboardButton("💀 Убить", callback_data=f"kill_{job_id}_{user_id}"))
    markup.add(types.InlineKeyboardButton("🪢 Дать верёвку", callback_data=f"rope_{job_id}_{user_id}"))
    markup.add(types.InlineKeyboardButton("🏠 Меню", callback_data="menu"))
    markup.add(types.InlineKeyboardButton("➡️", callback_data=f"plrp2_{job_id}_{user_id}"))
    
    text = f"👤 Игрок: {display_name}\n🏷 Ник: {username}\n🆔 ID: {user_id}\n📡 {server_name}"
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

def show_player_page2(call, job_id, user_id):
    active = get_active_servers()
    player_info = active.get(job_id, {}).get('players', {}).get(user_id, {})
    
    if isinstance(player_info, dict):
        username = player_info.get('name', 'Unknown')
        display_name = player_info.get('display_name', username)
    else:
        username = player_info if player_info else 'Unknown'
        display_name = username
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📮 Превратить в амогуса", callback_data=f"amogus_{job_id}_{user_id}"))
    markup.add(types.InlineKeyboardButton("🎁 Выдать предмет", callback_data=f"giveitem_{job_id}_{user_id}"))
    markup.add(types.InlineKeyboardButton("💀 Установить смерти", callback_data=f"setdeaths_{job_id}_{user_id}"))
    markup.add(types.InlineKeyboardButton("🪙 Выдать монеты", callback_data=f"setcoins_{job_id}_{user_id}"))
    markup.add(types.InlineKeyboardButton("🏠 Меню", callback_data="menu"))
    markup.add(types.InlineKeyboardButton("⬅️", callback_data=f"plr_{job_id}_{user_id}"))
    
    text = f"👤 Игрок: {display_name}\n🏷 Ник: {username}\n🆔 ID: {user_id}\n\n📄 Страница 2"
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

def show_server_actions(call, job_id, user_id):
    active = get_active_servers()
    server_info = active.get(job_id, {})
    server_name = get_server_name(job_id)
    player_count = server_info.get('player_count', 0)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f"💀 Убить всех [{server_name}]", callback_data=f"killall_{job_id}_{user_id}"))
    markup.add(types.InlineKeyboardButton("⬅️ Назад к игроку", callback_data=f"plr_{job_id}_{user_id}"))
    markup.add(types.InlineKeyboardButton("🏠 Меню", callback_data="menu"))
    
    text = f"🖥 {server_name}\n👥 Игроков: {player_count}\n\nВыберите действие:"
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

def search_player(message):
    username = message.from_user.username
    if not is_admin(message.from_user.id, username):
        return
    
    search_text = message.text.lower()
    results = []
    active = get_active_servers()
    
    for job_id, info in active.items():
        for user_id, player_info in info['players'].items():
            if isinstance(player_info, dict):
                name = player_info.get('name', '').lower()
                display_name = player_info.get('display_name', '').lower()
                show_name = player_info.get('display_name', player_info.get('name', 'Unknown'))
            else:
                name = player_info.lower() if player_info else ''
                display_name = name
                show_name = player_info if player_info else 'Unknown'
            
            if search_text in name or search_text in display_name:
                results.append((job_id, user_id, show_name))
    
    if not results:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🏠 Меню", callback_data="menu"))
        bot.send_message(message.chat.id, "❌ Игрок не найден", reply_markup=markup)
        return
    
    markup = types.InlineKeyboardMarkup()
    for job_id, user_id, show_name in results:
        markup.add(types.InlineKeyboardButton(f"👤 {show_name}", callback_data=f"plr_{job_id}_{user_id}"))
    markup.add(types.InlineKeyboardButton("🏠 Меню", callback_data="menu"))
    
    bot.send_message(message.chat.id, f"🔍 Найдено: {len(results)}", reply_markup=markup)

def run_bot():
    print("Telegram bot starting...")
    time.sleep(5)
    bot.remove_webhook()
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"Bot error: {e}")
            time.sleep(10)

if __name__ == '__main__':
    bot_thread = Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    print("Flask server started")
    app.run(host='0.0.0.0', port=10000)
