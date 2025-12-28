from flask import Flask
from threading import Thread
import telebot
from telebot import types
import time
import json
import os
import random
import re

app = Flask(__name__)

BOT_TOKEN = "7950194700:AAHeIfO6UwnCXnN8M200L4MfEdAmIhZs6r8"
OWNER_IDS = [8096475445, 8220513089]

DATA_FILE = "brain.json"
ADMINS_FILE = "admins.json"
SETTINGS_FILE = "settings.json"

def load_brain():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('chains', {}), data.get('replies', {}), data.get('words', [])
        except:
            pass
    return {}, {}, []

def save_brain():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'chains': chains,
            'replies': replies,
            'words': list(all_words)[-10000:]
        }, f, ensure_ascii=False)

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

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {'reply_chance': 15, 'learn': True, 'min_words': 2}

def save_settings():
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f)

chains, replies, words_list = load_brain()
all_words = set(words_list)
admin_ids = load_admins()
settings = load_settings()

for oid in OWNER_IDS:
    admin_ids.add(oid)

bot = telebot.TeleBot(BOT_TOKEN)
last_save = time.time()

def is_admin(user_id):
    return user_id in admin_ids

def is_owner(user_id):
    return user_id in OWNER_IDS

def clean_text(text):
    text = re.sub(r'http\S+', '', text)
    text = re.sub(r'@\w+', '', text)
    text = text.lower().strip()
    return text

def tokenize(text):
    text = clean_text(text)
    words = re.findall(r'[а-яёa-z0-9]+|[.!?]', text)
    return words

def learn_message(text):
    if not settings.get('learn', True):
        return
    
    words = tokenize(text)
    if len(words) < settings.get('min_words', 2):
        return
    
    for word in words:
        all_words.add(word)
    
    for i in range(len(words) - 1):
        word = words[i]
        next_word = words[i + 1]
        
        if word not in chains:
            chains[word] = {}
        
        if next_word not in chains[word]:
            chains[word][next_word] = 0
        
        chains[word][next_word] += 1
    
    if len(words) >= 2:
        first_word = words[0]
        if '_start' not in chains:
            chains['_start'] = {}
        if first_word not in chains['_start']:
            chains['_start'][first_word] = 0
        chains['_start'][first_word] += 1

def learn_reply(trigger_text, reply_text):
    if not settings.get('learn', True):
        return
    
    trigger_words = tokenize(trigger_text)
    if not trigger_words:
        return
    
    key = ' '.join(trigger_words[:3])
    
    if key not in replies:
        replies[key] = []
    
    if reply_text not in replies[key]:
        replies[key].append(reply_text)
        if len(replies[key]) > 20:
            replies[key] = replies[key][-20:]

def generate_response(seed_text=None):
    if not chains:
        return None
    
    if seed_text:
        seed_words = tokenize(seed_text)
        for word in seed_words:
            if word in chains and chains[word]:
                start_word = word
                break
        else:
            if '_start' in chains and chains['_start']:
                start_word = weighted_choice(chains['_start'])
            else:
                return None
    else:
        if '_start' in chains and chains['_start']:
            start_word = weighted_choice(chains['_start'])
        else:
            start_word = random.choice(list(chains.keys()))
            if start_word == '_start':
                return None
    
    result = [start_word]
    current = start_word
    
    max_len = random.randint(3, 15)
    
    for _ in range(max_len):
        if current not in chains or not chains[current]:
            break
        
        next_word = weighted_choice(chains[current])
        
        if next_word in '.!?':
            result.append(next_word)
            if random.random() < 0.7:
                break
        else:
            result.append(next_word)
        
        current = next_word
    
    if len(result) < 2:
        return None
    
    text = ' '.join(result)
    text = re.sub(r' ([.!?])', r'\1', text)
    text = text.strip()
    
    if text and text[0].isalpha():
        text = text[0].upper() + text[1:]
    
    return text

def weighted_choice(choices_dict):
    total = sum(choices_dict.values())
    r = random.uniform(0, total)
    cumsum = 0
    for choice, weight in choices_dict.items():
        cumsum += weight
        if r <= cumsum:
            return choice
    return random.choice(list(choices_dict.keys()))

def find_reply(text):
    words = tokenize(text)
    if not words:
        return None
    
    key = ' '.join(words[:3])
    if key in replies and replies[key]:
        return random.choice(replies[key])
    
    for k, v in replies.items():
        k_words = k.split()
        for word in words:
            if word in k_words and v:
                if random.random() < 0.3:
                    return random.choice(v)
    
    return None

def maybe_save():
    global last_save
    if time.time() - last_save > 60:
        save_brain()
        last_save = time.time()

@app.route('/')
def home():
    return f"Sglipa Bot Online! Words: {len(all_words)}, Chains: {len(chains)}"

@app.route('/ping')
def ping():
    return "pong"

@app.route('/health')
def health():
    return "OK"

@bot.message_handler(commands=['start'])
def cmd_start(message):
    if message.chat.type != 'private':
        return
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📊 Статистика", callback_data="stats"))
    
    if is_admin(message.from_user.id):
        markup.add(types.InlineKeyboardButton("⚙️ Настройки", callback_data="settings"))
    
    bot.send_message(
        message.chat.id,
        f"🧠 Привет! Я учусь на сообщениях в чатах и иногда отвечаю.\n\n"
        f"📝 Выучено слов: {len(all_words)}\n"
        f"🔗 Связей: {len(chains)}\n"
        f"💬 Шаблонов ответов: {len(replies)}",
        reply_markup=markup
    )

@bot.message_handler(commands=['stats'])
def cmd_stats(message):
    bot.send_message(
        message.chat.id,
        f"📊 Статистика:\n\n"
        f"📝 Слов: {len(all_words)}\n"
        f"🔗 Связей: {len(chains)}\n"
        f"💬 Шаблонов: {len(replies)}\n"
        f"🎲 Шанс ответа: {settings.get('reply_chance', 15)}%"
    )

@bot.message_handler(commands=['say'])
def cmd_say(message):
    text = message.text.replace('/say', '').strip()
    response = generate_response(text if text else None)
    if response:
        bot.send_message(message.chat.id, response)
    else:
        bot.send_message(message.chat.id, "🤷 Ещё не научился говорить...")

@bot.message_handler(commands=['chance'])
def cmd_chance(message):
    if not is_admin(message.from_user.id):
        return
    
    parts = message.text.split()
    if len(parts) > 1:
        try:
            new_chance = int(parts[1])
            new_chance = max(0, min(100, new_chance))
            settings['reply_chance'] = new_chance
            save_settings()
            bot.send_message(message.chat.id, f"✅ Шанс ответа: {new_chance}%")
        except:
            bot.send_message(message.chat.id, f"🎲 Текущий шанс: {settings.get('reply_chance', 15)}%\n\nИспользуй: /chance 20")
    else:
        bot.send_message(message.chat.id, f"🎲 Текущий шанс: {settings.get('reply_chance', 15)}%\n\nИспользуй: /chance 20")

@bot.message_handler(commands=['learn'])
def cmd_learn(message):
    if not is_admin(message.from_user.id):
        return
    
    settings['learn'] = not settings.get('learn', True)
    save_settings()
    
    status = "включено" if settings['learn'] else "выключено"
    bot.send_message(message.chat.id, f"📚 Обучение {status}")

@bot.message_handler(commands=['reset'])
def cmd_reset(message):
    if not is_owner(message.from_user.id):
        return
    
    global chains, replies, all_words
    chains = {}
    replies = {}
    all_words = set()
    save_brain()
    bot.send_message(message.chat.id, "🗑 Память очищена")

@bot.message_handler(func=lambda m: m.text and not m.text.startswith('/'), content_types=['text'])
def handle_message(message):
    text = message.text
    chat_id = message.chat.id
    
    learn_message(text)
    
    if message.reply_to_message and message.reply_to_message.text:
        learn_reply(message.reply_to_message.text, text)
    
    should_reply = False
    
    bot_info = bot.get_me()
    bot_username = bot_info.username.lower() if bot_info.username else ""
    
    if bot_username and bot_username in text.lower():
        should_reply = True
    
    if message.reply_to_message:
        if message.reply_to_message.from_user and message.reply_to_message.from_user.id == bot_info.id:
            should_reply = True
    
    if not should_reply:
        chance = settings.get('reply_chance', 15)
        if random.randint(1, 100) <= chance:
            should_reply = True
    
    if should_reply and chains:
        reply_from_memory = find_reply(text)
        
        if reply_from_memory and random.random() < 0.4:
            response = reply_from_memory
        else:
            response = generate_response(text)
        
        if response:
            time.sleep(random.uniform(0.5, 2))
            bot.send_message(chat_id, response)
    
    maybe_save()

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    data = call.data
    
    if data == "stats":
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            f"📊 Статистика:\n\n"
            f"📝 Слов: {len(all_words)}\n"
            f"🔗 Связей: {len(chains)}\n"
            f"💬 Шаблонов: {len(replies)}\n"
            f"🎲 Шанс ответа: {settings.get('reply_chance', 15)}%\n"
            f"📚 Обучение: {'✅' if settings.get('learn', True) else '❌'}",
            call.message.chat.id,
            call.message.message_id
        )
    
    elif data == "settings":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Нет доступа")
            return
        
        markup = types.InlineKeyboardMarkup()
        
        learn_status = "✅" if settings.get('learn', True) else "❌"
        markup.add(types.InlineKeyboardButton(f"📚 Обучение: {learn_status}", callback_data="toggle_learn"))
        
        markup.add(types.InlineKeyboardButton(f"🎲 Шанс: {settings.get('reply_chance', 15)}%", callback_data="show_chance"))
        
        if is_owner(user_id):
            markup.add(types.InlineKeyboardButton("🗑 Очистить память", callback_data="confirm_reset"))
        
        markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back_main"))
        
        bot.edit_message_text(
            "⚙️ Настройки",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif data == "toggle_learn":
        if not is_admin(user_id):
            return
        
        settings['learn'] = not settings.get('learn', True)
        save_settings()
        
        markup = types.InlineKeyboardMarkup()
        learn_status = "✅" if settings.get('learn', True) else "❌"
        markup.add(types.InlineKeyboardButton(f"📚 Обучение: {learn_status}", callback_data="toggle_learn"))
        markup.add(types.InlineKeyboardButton(f"🎲 Шанс: {settings.get('reply_chance', 15)}%", callback_data="show_chance"))
        
        if is_owner(user_id):
            markup.add(types.InlineKeyboardButton("🗑 Очистить память", callback_data="confirm_reset"))
        
        markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back_main"))
        
        bot.edit_message_text(
            "⚙️ Настройки",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif data == "show_chance":
        bot.answer_callback_query(call.id, "Используй /chance 20 чтобы изменить")
    
    elif data == "confirm_reset":
        if not is_owner(user_id):
            return
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Да, очистить", callback_data="do_reset"))
        markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="settings"))
        
        bot.edit_message_text(
            "⚠️ Точно очистить всю память?",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif data == "do_reset":
        if not is_owner(user_id):
            return
        
        global chains, replies, all_words
        chains = {}
        replies = {}
        all_words = set()
        save_brain()
        
        bot.answer_callback_query(call.id, "🗑 Память очищена")
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="settings"))
        
        bot.edit_message_text(
            "🗑 Память очищена!",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif data == "back_main":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📊 Статистика", callback_data="stats"))
        
        if is_admin(user_id):
            markup.add(types.InlineKeyboardButton("⚙️ Настройки", callback_data="settings"))
        
        bot.edit_message_text(
            f"🧠 Я учусь на сообщениях в чатах и иногда отвечаю.\n\n"
            f"📝 Выучено слов: {len(all_words)}\n"
            f"🔗 Связей: {len(chains)}\n"
            f"💬 Шаблонов ответов: {len(replies)}",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

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
