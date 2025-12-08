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

def is_admin(user_id):
    return user_id in ADMIN_IDS

@app.route('/')
def home():
    return f"Online. Servers: {len(servers)}"

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    data = request.json
    job_id = data['job_id']
    servers[job_id] = {
        "players": data['players'],
        "player_count": data['player_count'],
        "max_players": data['max_players']
    }
    commands = pending_commands.pop(job_id, [])
    return jsonify({"commands": commands})

@app.route('/player_joined', methods=['POST'])
def player_joined():
    data = request.json
    job_id = data['job_id']
    if job_id in servers:
        servers[job_id]['players'][str(data['user_id'])] = data['username']
    return jsonify({"status": "ok"})

@app.route('/player_left', methods=['POST'])
def player_left():
    data = request.json
    job_id = data['job_id']
    if job_id in servers:
        servers[job_id]['players'].pop(str(data['user_id']), None)
    return jsonify({"status": "ok"})

@bot.message_handler(commands=['start', 'panel'])
def start(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "Нет доступа")
        return
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Список серверов", callback_data="servers"))
    markup.add(types.InlineKeyboardButton("Найти игрока", callback_data="search"))
    
    bot.send_message(message.chat.id, "Панель управления Roblox", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if not is_admin(call.from_user.id):
        return
    
    data = call.data
    
    if data == "servers":
        if not servers:
            bot.edit_message_text("Нет активных серверов", call.message.chat.id, call.message.message_id)
            return
        
        markup = types.InlineKeyboardMarkup()
        for job_id, info in servers.items():
            text = f"{job_id[:8]}... ({info['player_count']}/{info['max_players']})"
            markup.add(types.InlineKeyboardButton(text, callback_data=f"srv_{job_id}"))
        
        markup.add(types.InlineKeyboardButton("Обновить", callback_data="servers"))
        markup.add(types.InlineKeyboardButton("Назад", callback_data="menu"))
        
        bot.edit_message_text(f"Серверов: {len(servers)}", call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    elif data.startswith("srv_"):
        job_id = data[4:]
        
        if job_id not in servers:
            bot.answer_callback_query(call.id, "Сервер не найден")
            return
        
        info = servers[job_id]
        markup = types.InlineKeyboardMarkup()
        
        for user_id, username in info['players'].items():
            markup.add(types.InlineKeyboardButton(username, callback_data=f"plr_{job_id}_{user_id}"))
        
        markup.add(types.InlineKeyboardButton("Обновить", callback_data=f"srv_{job_id}"))
        markup.add(types.InlineKeyboardButton("К серверам", callback_data="servers"))
        
        bot.edit_message_text(f"Сервер: {job_id[:16]}...\nИгроков: {len(info['players'])}", call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    elif data.startswith("plr_"):
        parts = data.split("_")
        job_id = parts[1]
        user_id = parts[2]
        
        username = servers.get(job_id, {}).get('players', {}).get(user_id, "Unknown")
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Кикнуть", callback_data=f"kick_{job_id}_{user_id}"))
        markup.add(types.InlineKeyboardButton("Бан навсегда", callback_data=f"ban_{job_id}_{user_id}_0"))
        markup.add(types.InlineKeyboardButton("Бан 1 день", callback_data=f"ban_{job_id}_{user_id}_1"))
        markup.add(types.InlineKeyboardButton("Бан 7 дней", callback_data=f"ban_{job_id}_{user_id}_7"))
        markup.add(types.InlineKeyboardButton("Разбанить", callback_data=f"unban_{job_id}_{user_id}"))
        markup.add(types.InlineKeyboardButton("Убить", callback_data=f"kill_{job_id}_{user_id}"))
        markup.add(types.InlineKeyboardButton("Дать веревку", callback_data=f"rope_{job_id}_{user_id}"))
        markup.add(types.InlineKeyboardButton("Назад", callback_data=f"srv_{job_id}"))
        
        bot.edit_message_text(f"Игрок: {username}\nID: {user_id}", call.message.chat.id, call.message.message_id, reply_markup=markup)
    
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
        
        username = servers.get(job_id, {}).get('players', {}).get(user_id, "Unknown")
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("К серверам", callback_data="servers"))
        
        bot.edit_message_text(f"{username} будет кикнут", call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    elif data.startswith("ban_"):
        parts = data.split("_")
        job_id = parts[1]
        user_id = parts[2]
        duration = int(parts[3])
        
        for jid in servers.keys():
            if jid not in pending_commands:
                pending_commands[jid] = []
            pending_commands[jid].append({
                "action": "ban",
                "user_id": int(user_id),
                "duration": duration,
                "reason": "Забанен администратором"
            })
        
        username = servers.get(job_id, {}).get('players', {}).get(user_id, "Unknown")
        
        if duration == 0:
            ban_text = "навсегда"
        else:
            ban_text = f"на {duration} дн."
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("К серверам", callback_data="servers"))
        
        bot.edit_message_text(f"{username} забанен {ban_text}", call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    elif data.startswith("unban_"):
        parts = data.split("_")
        job_id = parts[1]
        user_id = parts[2]
        
        for jid in servers.keys():
            if jid not in pending_commands:
                pending_commands[jid] = []
            pending_commands[jid].append({
                "action": "unban",
                "user_id": int(user_id)
            })
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("К серверам", callback_data="servers"))
        
        bot.edit_message_text("Игрок разбанен", call.message.chat.id, call.message.message_id, reply_markup=markup)
    
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
        
        username = servers.get(job_id, {}).get('players', {}).get(user_id, "Unknown")
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("К серверам", callback_data="servers"))
        
        bot.edit_message_text(f"{username} будет убит", call.message.chat.id, call.message.message_id, reply_markup=markup)
    
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
        
        username = servers.get(job_id, {}).get('players', {}).get(user_id, "Unknown")
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("К серверам", callback_data="servers"))
        
        bot.edit_message_text(f"{username} получит веревку", call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    elif data == "menu":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Список серверов", callback_data="servers"))
        markup.add(types.InlineKeyboardButton("Найти игрока", callback_data="search"))
        
        bot.edit_message_text("Панель управления Roblox", call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    elif data == "search":
        msg = bot.edit_message_text("Введите ник игрока:", call.message.chat.id, call.message.message_id)
        bot.register_next_step_handler(msg, search_player)

def search_player(message):
    if not is_admin(message.from_user.id):
        return
    
    search_name = message.text.lower()
    results = []
    
    for job_id, info in servers.items():
        for user_id, username in info['players'].items():
            if search_name in username.lower():
                results.append((job_id, user_id, username))
    
    if not results:
        bot.reply_to(message, "Игрок не найден")
        return
    
    markup = types.InlineKeyboardMarkup()
    for job_id, user_id, username in results:
        markup.add(types.InlineKeyboardButton(f"{username} ({job_id[:8]}...)", callback_data=f"plr_{job_id}_{user_id}"))
    markup.add(types.InlineKeyboardButton("Меню", callback_data="menu"))
    
    bot.send_message(message.chat.id, f"Найдено: {len(results)}", reply_markup=markup)

def run_bot():
    print("Telegram bot started")
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"Bot error: {e}")
            time.sleep(3)

if __name__ == '__main__':
    bot_thread = Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    print("Flask server started")
    app.run(host='0.0.0.0', port=10000)
