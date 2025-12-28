from flask import Flask
from threading import Thread
import telebot
from telebot import types
import time
import json
import os
import re

app = Flask(__name__)

BOT_TOKEN = "7950194700:AAHeIfO6UwnCXnN8M200L4MfEdAmIhZs6r8"
OWNER_IDS = [8096475445, 8220513089]
TRIGGERS_FILE = "triggers.json"
ADMINS_FILE = "admins.json"

last_messages = {}
user_states = {}

def load_triggers():
    if os.path.exists(TRIGGERS_FILE):
        try:
            with open(TRIGGERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {
        "привет": "Поприветствовал %user%! 👋",
        "пока": "Попрощался с %user%! 👋",
        "люблю": "Признался в любви %user%! ❤️",
        "ненавижу": "Выразил ненависть к %user%! 😤",
        "обнял": "Обнял %user%! 🤗",
        "ударил": "Ударил %user%! 👊",
        "поцеловал": "Поцеловал %user%! 😘",
        "укусил": "Укусил %user%! 🦷",
        "пнул": "Пнул %user%! 🦶",
        "убил": "Убил %user%! ☠️",
        "воскресил": "Воскресил %user%! ✨",
        "погладил": "Погладил %user%! 🥰",
        "шлёпнул": "Шлёпнул %user%! 👏",
        "выебать": "выебал %user% жестка",
        "витеб": "ты витеб %user%",
        "хуем": "хуем тя %user%",
        "усыканик": "ты бля усыкуха %user%",
        "шлёпнул": "Шлёпнул %user%",
        "ебать": "тя чё ебу или ебать %user%",
        "анус": "у тя анус воняет %user%",
        "урон": "урон в анус те %user%",
        "азартный": "азартный анус ебливый",
        "внатуре": "слыш ты внатуре или чё %user%! 🙏"
    }

def save_triggers():
    with open(TRIGGERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(triggers, f, ensure_ascii=False, indent=2)

def load_admins():
    if os.path.exists(ADMINS_FILE):
        try:
            with open(ADMINS_FILE, 'r') as f:
                data = json.load(f)
                return set(data.get('ids', OWNER_IDS))
        except:
            pass
    return set(OWNER_IDS)

def save_admins():
    with open(ADMINS_FILE, 'w') as f:
        json.dump({'ids': list(admin_ids)}, f)

triggers = load_triggers()
admin_ids = load_admins()
for oid in OWNER_IDS:
    admin_ids.add(oid)

bot = telebot.TeleBot(BOT_TOKEN)

def is_admin(user_id):
    return user_id in admin_ids

def is_owner(user_id):
    return user_id in OWNER_IDS

def get_user_mention(user):
    if user.username:
        return f"@{user.username}"
    return user.first_name

def find_target_user(message):
    chat_id = message.chat.id
    text = message.text
    
    mention_match = re.search(r'@(\w+)', text)
    if mention_match:
        return f"@{mention_match.group(1)}"
    
    if message.reply_to_message:
        reply_user = message.reply_to_message.from_user
        return get_user_mention(reply_user)
    
    if chat_id in last_messages:
        last_info = last_messages[chat_id]
        if last_info.get('username'):
            return f"@{last_info['username']}"
        return last_info.get('first_name', None)
    
    return None

@app.route('/')
def home():
    return f"Trigger Bot Online! Triggers: {len(triggers)}"

@app.route('/ping')
def ping():
    return "pong"

@app.route('/health')
def health():
    return "OK"

@bot.message_handler(commands=['start'])
def cmd_start(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📋 Список триггеров", callback_data="triggers_list"))
    markup.add(types.InlineKeyboardButton("❓ Как пользоваться", callback_data="help"))
    
    if is_admin(message.from_user.id):
        markup.add(types.InlineKeyboardButton("⚙️ Управление", callback_data="admin_panel"))
    
    bot.send_message(
        message.chat.id,
        f"👋 Привет, {message.from_user.first_name}!\n\nЯ бот с триггерами для RP действий.\n\n📊 Активных триггеров: {len(triggers)}",
        reply_markup=markup
    )

@bot.message_handler(commands=['triggers', 'list'])
def cmd_triggers(message):
    show_triggers_list(message.chat.id, None, is_callback=False)

@bot.message_handler(commands=['help'])
def cmd_help(message):
    help_text = """❓ Как пользоваться:

1. Ответ на сообщение:
Ответьте на чьё-то сообщение триггером

2. Упоминание:
обнял @username

3. Последний в чате:
Просто напишите триггер — цель будет последний писавший

Команды:
/triggers — список триггеров
/help — эта справка"""
    bot.send_message(message.chat.id, help_text)

@bot.message_handler(func=lambda m: m.from_user.id in user_states and m.text and not m.text.startswith('/'))
def handle_state_input(message):
    user_id = message.from_user.id
    state = user_states.get(user_id)
    
    if not state:
        return
    
    action = state.get('action')
    
    if action == 'add_trigger_word':
        trigger_word = message.text.strip().lower()
        user_states[user_id] = {
            'action': 'add_trigger_response',
            'word': trigger_word
        }
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="admin_panel"))
        
        bot.send_message(
            message.chat.id,
            f"Слово: {trigger_word}\n\nТеперь введите ответ. Используйте %user% для упоминания цели.\n\nПример: Обнял %user%! 🤗",
            reply_markup=markup
        )
    
    elif action == 'add_trigger_response':
        trigger_word = state.get('word')
        response = message.text.strip()
        
        triggers[trigger_word] = response
        save_triggers()
        
        del user_states[user_id]
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ К управлению", callback_data="admin_panel"))
        
        bot.send_message(
            message.chat.id,
            f"✅ Триггер добавлен!\n\nСлово: {trigger_word}\nОтвет: {response}",
            reply_markup=markup
        )
    
    elif action == 'add_admin':
        del user_states[user_id]
        
        if message.forward_from:
            new_admin_id = message.forward_from.id
        else:
            try:
                new_admin_id = int(message.text.strip())
            except ValueError:
                bot.send_message(message.chat.id, "❌ Неверный формат ID")
                return
        
        admin_ids.add(new_admin_id)
        save_admins()
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="admins"))
        
        bot.send_message(message.chat.id, f"✅ Админ {new_admin_id} добавлен!", reply_markup=markup)
    
    elif action == 'remove_admin':
        del user_states[user_id]
        
        try:
            admin_to_remove = int(message.text.strip())
        except ValueError:
            bot.send_message(message.chat.id, "❌ Неверный формат ID")
            return
        
        if admin_to_remove in OWNER_IDS:
            result = "❌ Нельзя удалить владельца!"
        elif admin_to_remove in admin_ids:
            admin_ids.discard(admin_to_remove)
            save_admins()
            result = f"✅ Админ {admin_to_remove} удалён!"
        else:
            result = "❌ Админ не найден"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="admins"))
        
        bot.send_message(message.chat.id, result, reply_markup=markup)

@bot.message_handler(func=lambda m: m.text and not m.text.startswith('/'), content_types=['text'])
def handle_message(message):
    chat_id = message.chat.id
    text = message.text.lower().strip()
    sender = message.from_user
    
    triggered_word = None
    response_template = None
    
    for trigger, template in triggers.items():
        trigger_lower = trigger.lower()
        if re.search(rf'\b{re.escape(trigger_lower)}\b', text) or text.startswith(trigger_lower):
            triggered_word = trigger
            response_template = template
            break
    
    if triggered_word:
        target = find_target_user(message)
        if target:
            response = response_template.replace("%user%", target)
            bot.send_message(chat_id, response)
    
    last_messages[chat_id] = {
        "user_id": sender.id,
        "username": sender.username,
        "first_name": sender.first_name,
        "time": time.time()
    }

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    data = call.data
    
    if data == "triggers_list":
        show_triggers_list(call.message.chat.id, call.message.message_id, is_callback=True)
    
    elif data == "help":
        help_text = """❓ Как пользоваться:

1. Ответ на сообщение — ответьте триггером
2. Упоминание — обнял @username
3. Последний в чате — просто триггер"""
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="menu"))
        
        bot.edit_message_text(help_text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    elif data == "menu":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📋 Список триггеров", callback_data="triggers_list"))
        markup.add(types.InlineKeyboardButton("❓ Как пользоваться", callback_data="help"))
        
        if is_admin(user_id):
            markup.add(types.InlineKeyboardButton("⚙️ Управление", callback_data="admin_panel"))
        
        bot.edit_message_text(
            f"🤖 Trigger Bot\n\n📊 Активных триггеров: {len(triggers)}",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif data == "admin_panel":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Нет доступа!")
            return
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("➕ Добавить триггер", callback_data="add_trigger"))
        markup.add(types.InlineKeyboardButton("➖ Удалить триггер", callback_data="del_trigger"))
        markup.add(types.InlineKeyboardButton("📋 Все триггеры", callback_data="triggers_list"))
        
        if is_owner(user_id):
            markup.add(types.InlineKeyboardButton("👑 Управление админами", callback_data="admins"))
        
        markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="menu"))
        
        bot.edit_message_text(
            f"⚙️ Панель управления\n\n📊 Триггеров: {len(triggers)}\n👥 Админов: {len(admin_ids)}",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif data == "add_trigger":
        if not is_admin(user_id):
            return
        
        user_states[user_id] = {'action': 'add_trigger_word'}
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="admin_panel"))
        
        bot.edit_message_text(
            "➕ Введите слово-триггер:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif data == "del_trigger":
        if not is_admin(user_id):
            return
        
        markup = types.InlineKeyboardMarkup()
        
        for trigger in sorted(triggers.keys()):
            markup.add(types.InlineKeyboardButton(f"❌ {trigger}", callback_data=f"deltrig_{trigger}"))
        
        markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel"))
        
        bot.edit_message_text(
            "➖ Выберите триггер для удаления:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif data.startswith("deltrig_"):
        if not is_admin(user_id):
            return
        
        trigger_to_del = data[8:]
        
        if trigger_to_del in triggers:
            del triggers[trigger_to_del]
            save_triggers()
            result = f"✅ Триггер «{trigger_to_del}» удалён!"
        else:
            result = "❌ Триггер не найден"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel"))
        
        bot.edit_message_text(result, call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    elif data == "admins":
        if not is_owner(user_id):
            return
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("➕ Добавить админа", callback_data="add_admin"))
        markup.add(types.InlineKeyboardButton("➖ Удалить админа", callback_data="remove_admin"))
        markup.add(types.InlineKeyboardButton("📋 Список", callback_data="list_admins"))
        markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel"))
        
        bot.edit_message_text(
            f"👑 Управление админами\n\nВсего: {len(admin_ids)}",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif data == "add_admin":
        if not is_owner(user_id):
            return
        
        user_states[user_id] = {'action': 'add_admin'}
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="admins"))
        
        bot.edit_message_text(
            "➕ Перешлите сообщение от нового админа или введите его ID:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif data == "remove_admin":
        if not is_owner(user_id):
            return
        
        user_states[user_id] = {'action': 'remove_admin'}
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="admins"))
        
        bot.edit_message_text(
            "➖ Введите ID админа для удаления:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif data == "list_admins":
        if not is_owner(user_id):
            return
        
        text = "👑 Администраторы:\n\n🔒 Владельцы:\n"
        for oid in OWNER_IDS:
            text += f"  • {oid}\n"
        
        other_admins = [a for a in admin_ids if a not in OWNER_IDS]
        if other_admins:
            text += "\n👤 Админы:\n"
            for aid in other_admins:
                text += f"  • {aid}\n"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="admins"))
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

def show_triggers_list(chat_id, message_id, is_callback=True):
    if not triggers:
        text = "📋 Список триггеров пуст"
    else:
        text = "📋 Список триггеров:\n\n"
        for trigger, response in sorted(triggers.items()):
            text += f"• {trigger} → {response}\n"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="menu"))
    
    if is_callback and message_id:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    else:
        bot.send_message(chat_id, text, reply_markup=markup)

def run_bot():
    print("Bot starting...")
    time.sleep(3)
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
    
    app.run(host='0.0.0.0', port=10000)
