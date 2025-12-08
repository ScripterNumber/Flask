from flask import Flask, request, jsonify
from threading import Thread
import telebot
from telebot import types
import time

# ============ FLASK СЕРВЕР ============
app = Flask(__name__)

# Хранилище данных
servers = {}
pending_commands = {}

# ============ НАСТРОЙКИ ============
BOT_TOKEN = "7950194700:AAHeIfO6UwnCXnN8M200L4MfEdAmIhZs6r8"
ADMIN_IDS = [8096475445]  # Замени на свой Telegram ID

bot = telebot.TeleBot(BOT_TOKEN)

def is_admin(user_id):
    return user_id in ADMIN_IDS

# ============ API ДЛЯ ROBLOX ============
@app.route('/')
def home():
    return f"✅ Bot is alive! Servers: {len(servers)}"

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

# ============ TELEGRAM БОТ ============
@bot.message_handler(commands=['start', 'panel'])
def start(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Нет доступа")
        return
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📋 Список серверов", callback_data="servers"))
    markup.add(types.InlineKeyboardButton("🔍 Найти игрока", callback_data="search"))
    
    bot.send_message(message.chat.id, "🎮 **Панель управления Roblox**", 
                     reply_markup=markup, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if not is_admin(call.from_user.id):
        return
    
    data = call.data
    
    # --- Список серверов ---
    if data == "servers":
        if not servers:
            bot.edit_message_text("❌ Нет активных серверов", 
                                  call.message.chat.id, call.message.message_id)
            return
        
        markup = types.InlineKeyboardMarkup()
        for job_id, info in servers.items():
            text = f"🖥 {job_id[:8]}... ({info['player_count']}/{info['max_players']})"
            markup.add(types.InlineKeyboardButton(text, callback_data=f"srv_{job_id}"))
        
        markup.add(types.InlineKeyboardButton("🔄 Обновить", callback_data="servers"))
        markup.add(types.InlineKeyboardButton("◀️ Меню", callback_data="menu"))
        
        bot.edit_message_text(f"📋 **Серверов: {len(servers)}**",
                              call.message.chat.id, call.message.message_id,
                              reply_markup=markup, parse_mode='Markdown')
    
    # --- Выбран сервер ---
    elif data.startswith("srv_"):
        job_id = data[4:]
        
        if job_id not in servers:
            bot.answer_callback_query(call.id, "❌ Сервер не найден")
            return
        
        info = servers[job_id]
        markup = types.InlineKeyboardMarkup()
        
        for user_id, username in info['players'].items():
            markup.add(types.InlineKeyboardButton(
                f"👤 {username}", callback_data=f"plr_{job_id}_{user_id}"
            ))
        
        markup.add(types.InlineKeyboardButton("🔄 Обновить", callback_data=f"srv_{job_id}"))
        markup.add(types.InlineKeyboardButton("◀️ К серверам", callback_data="servers"))
        
        bot.edit_message_text(
            f"🖥 **Сервер:** `{job_id[:16]}...`\n👥 **Игроков:** {len(info['players'])}",
            call.message.chat.id, call.message.message_id,
            reply_markup=markup, parse_mode='Markdown'
        )
    
    # --- Выбран игрок ---
    elif data.startswith("plr_"):
        parts = data.split("_")
        job_id = parts[1]
        user_id = parts[2]
        
        username = servers.get(job_id, {}).get('players', {}).get(user_id, "Unknown")
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("👢 Кикнуть", callback_data=f"kick_{job_id}_{user_id}"))
        markup.add(types.InlineKeyboardButton("🔨 Забанить", callback_data=f"ban_{job_id}_{user_id}"))
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"srv_{job_id}"))
        
        bot.edit_message_text(
            f"👤 **Игрок:** {username}\n🆔 **ID:** `{user_id}`",
            call.message.chat.id, call.message.message_id,
            reply_markup=markup, parse_mode='Markdown'
        )
    
    # --- Кик ---
    elif data.startswith("kick_"):
        parts = data.split("_")
        job_id = parts[1]
        user_id = parts[2]
        
        if job_id not in pending_commands:
            pending_commands[job_id] = []
        
        pending_commands[job_id].append({
            "action": "kick",
            "user_id": int(user_id),
            "reason": "Kicked by admin"
        })
        
        username = servers.get(job_id, {}).get('players', {}).get(user_id, "Unknown")
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("◀️ К серверам", callback_data="servers"))
        
        bot.edit_message_text(f"✅ **{username} будет кикнут!**",
                              call.message.chat.id, call.message.message_id,
                              reply_markup=markup, parse_mode='Markdown')
    
    # --- Бан ---
    elif data.startswith("ban_"):
        parts = data.split("_")
        job_id = parts[1]
        user_id = parts[2]
        
        for jid in servers.keys():
            if jid not in pending_commands:
                pending_commands[jid] = []
            pending_commands[jid].append({
                "action": "ban",
                "user_id": int(user_id),
                "reason": "Banned by admin"
            })
        
        username = servers.get(job_id, {}).get('players', {}).get(user_id, "Unknown")
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("◀️ К серверам", callback_data="servers"))
        
        bot.edit_message_text(f"🔨 **{username} забанен везде!**",
                              call.message.chat.id, call.message.message_id,
                              reply_markup=markup, parse_mode='Markdown')
    
    # --- Меню ---
    elif data == "menu":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📋 Список серверов", callback_data="servers"))
        markup.add(types.InlineKeyboardButton("🔍 Найти игрока", callback_data="search"))
        
        bot.edit_message_text("🎮 **Панель управления Roblox**",
                              call.message.chat.id, call.message.message_id,
                              reply_markup=markup, parse_mode='Markdown')
    
    # --- Поиск ---
    elif data == "search":
        msg = bot.edit_message_text("🔍 **Введите ник игрока:**",
                                    call.message.chat.id, call.message.message_id,
                                    parse_mode='Markdown')
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
        bot.reply_to(message, "❌ Игрок не найден")
        return
    
    markup = types.InlineKeyboardMarkup()
    for job_id, user_id, username in results:
        markup.add(types.InlineKeyboardButton(
            f"👤 {username} ({job_id[:8]}...)",
            callback_data=f"plr_{job_id}_{user_id}"
        ))
    markup.add(types.InlineKeyboardButton("◀️ Меню", callback_data="menu"))
    
    bot.send_message(message.chat.id, f"🔍 **Найдено: {len(results)}**",
                     reply_markup=markup, parse_mode='Markdown')

# ============ ЗАПУСК ============
def run_bot():
    print("🤖 Telegram бот запущен!")
    while True:
        try:
            bot.polling(none_stop=True, interval=0)
        except Exception as e:
            print(f"Ошибка бота: {e}")
            time.sleep(5)

if __name__ == '__main__':
    # Запускаем бота в отдельном потоке
    bot_thread = Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Запускаем Flask сервер
    print("🌐 Flask сервер запущен!")
    app.run(host='0.0.0.0', port=10000)
