from flask import Flask, request, jsonify
from threading import Thread
import telebot
from telebot import types
import time

app = Flask(__name__)

servers = {}
pending_commands = {}

BOT_TOKEN = "7950194700:AAHeIfO6UwnCXnN8M200L4MfEdAmIhZs6r8"
ADMIN_IDS = [8096475445]

bot = telebot.TeleBot(BOT_TOKEN)

SERVER_TIMEOUT = 15

def is_admin(user_id):
    return user_id in ADMIN_IDS

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
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "Нет доступа")
        return
    
    active = get_active_servers()
    total_players = sum(info['player_count'] for info in active.values())
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔍 Найти игрока", callback_data="search"))
    
    bot.send_message(
        message.chat.id,
        f"🎮 Панель управления Roblox\n\n📡 Серверов: {len(active)}\n👥 Игроков онлайн: {total_players}",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if not is_admin(call.from_user.id):
        return
    
    data = call.data
    
    if data.startswith("plr_"):
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
    if not is_admin(message.from_user.id):
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
