import json
import logging
import os
import re
import time
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler

# Loglarni yoqish (xatoliklarni ko'rish uchun DEBUG darajasiga o'zgartiring)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# JSON fayllar
USERS_FILE = "users.json"
RIDES_FILE = "rides.json"
STATS_FILE = "stats.json"
CONFIG_FILE = "config.json"
OFFERS_FILE = "offers.json"  # Yangi: takliflar uchun fayl

# Ovozli xabarlarni kutish uchun lug'at
waiting_for_phone = {}  # {user_id: (message_id, chat_id, timestamp, voice_file_id)}

# Admin holatlari
ADMIN_MAIN, ADMIN_STATS, ADMIN_MESSAGE, ADMIN_GIFT, ADMIN_SETTINGS = range(5)
GIFT_ALL, GIFT_ONE, GIFT_AMOUNT = range(5, 8)
MESSAGE_TEXT, MESSAGE_CONFIRM = range(8, 10)

# Admin ID'lari
ADMIN_IDS = [7578618626, 100799638, 37846745] 

# Telefon raqam uchun regex
PHONE_PATTERN = re.compile(r'(?:\+998|998)?([0-9]{9})')

# JSON fayllarni tekshirish va yaratish
def ensure_json_files():
    files = {
        USERS_FILE: {},
        RIDES_FILE: {},
        STATS_FILE: {"total_rides": 0, "total_coins": 0, "users_count": 0, "last_reset": None},
        CONFIG_FILE: {"initial_coins": 5, "welcome_message": "Botga xush kelibsiz!"},
        OFFERS_FILE: {}  # Yangi: takliflar uchun bo'sh lug'at
    }
    
    for file, default_data in files.items():
        if not os.path.exists(file):
            with open(file, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, ensure_ascii=False, indent=4)

# Foydalanuvchilarni yuklash
def load_users():
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

# Foydalanuvchilarni saqlash
def save_users(users):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=4)

# Takliflarni yuklash
def load_rides():
    try:
        with open(RIDES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

# Takliflarni saqlash
def save_rides(rides):
    with open(RIDES_FILE, 'w', encoding='utf-8') as f:
        json.dump(rides, f, ensure_ascii=False, indent=4)

# Statistikani yuklash
def load_stats():
    try:
        with open(STATS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        stats = {"total_rides": 0, "total_coins": 0, "users_count": 0, "last_reset": None}
        save_stats(stats)
        return stats

# Statistikani saqlash
def save_stats(stats):
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=4)

# Konfiguratsiyani yuklash
def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        config = {"initial_coins": 5, "welcome_message": "Botga xush kelibsiz!"}
        save_config(config)
        return config

# Konfiguratsiyani saqlash
def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

# Takliflarni yuklash
def load_offers():
    try:
        with open(OFFERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

# Takliflarni saqlash
def save_offers(offers):
    with open(OFFERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(offers, f, ensure_ascii=False, indent=4)

# Foydalanuvchi tangalarini o'zgartirish
def update_user_coins(user_id, amount):
    users = load_users()
    user_id_str = str(user_id)
    
    if user_id_str in users:
        users[user_id_str]["coins"] += amount
        save_users(users)
        
        # Statistikani yangilash
        stats = load_stats()
        stats["total_coins"] += amount
        save_stats(stats)
        
        return users[user_id_str]["coins"]
    return None

# Start buyrug'i
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    users = load_users()
    config = load_config()
    
    if str(user_id) not in users:
        # Yangi foydalanuvchi
        keyboard = [[KeyboardButton(text="Telefon raqamni yuborish", request_contact=True)]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            config["welcome_message"] + "\n\nBotdan foydalanish uchun telefon raqamingizni yuboring:",
            reply_markup=reply_markup
        )
    else:
        # Mavjud foydalanuvchi
        user_data = users[str(user_id)]
        await update.message.reply_text(
            f"Salom, {user_data['name']}! Sizning hisobingizda {user_data['coins']} tanga bor."
        )

# Telefon raqamni qabul qilish
async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    contact = update.message.contact
    
    if contact.user_id != user.id:
        await update.message.reply_text("Iltimos, o'z telefon raqamingizni yuboring.")
        return
    
    users = load_users()
    config = load_config()
    
    # Yangi foydalanuvchini qo'shish
    users[str(user.id)] = {
        "name": user.first_name,
        "username": user.username if user.username else "",
        "phone": contact.phone_number,
        "coins": config["initial_coins"],  # Konfiguratsiyadan boshlang'ich tangalar
        "joined_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    save_users(users)
    
    # Statistikani yangilash
    stats = load_stats()
    stats["users_count"] += 1
    stats["total_coins"] += config["initial_coins"]
    save_stats(stats)
    
    await update.message.reply_text(
        f"Ro'yxatdan o'tish muvaffaqiyatli yakunlandi! Sizga {config['initial_coins']} ta tanga berildi.\n"
        f"Hozirgi hisobingiz: {config['initial_coins']} tanga",
        reply_markup=ReplyKeyboardRemove()
    )

# Ovozli xabarni qayta ishlash
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Agar bu javob bo'lsa, javob handlerga o'tkazamiz
    if update.message.reply_to_message:
        await handle_voice_reply(update, context)
        return
    
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    message_id = update.message.message_id
    
    # Guruhda yoki superguruhda tekshirish
    if update.message.chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("Bu buyruq faqat guruhlarda ishlaydi.")
        return
    
    # Foydalanuvchi ro'yxatdan o'tganligini tekshirish
    users = load_users()
    if str(user_id) not in users:
        await update.message.reply_text(
            "Iltimos, avval botga / start buyrug'ini yuborib ro'yxatdan o'ting.  bot linki: @taxi_coin_maxsus_bot"
        )
        return
    
    # Ovozli xabar ma'lumotlarini saqlash va telefon raqam kutish
    waiting_for_phone[user_id] = (
        message_id, 
        chat_id, 
        time.time(), 
        update.message.voice.file_id
    )
    
    # JobQueue o'rniga oddiy xabar yuborish
    logger.info(f"Foydalanuvchi {user_id} ovozli xabar yubordi, telefon raqam kutilmoqda")

# Ovozli javoblarni qayta ishlash
async def handle_voice_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    replied_msg = update.message.reply_to_message
    
    # Bot yuborgan ovozli xabarga javob berilganini tekshirish
    if replied_msg.from_user.id == context.bot.id and replied_msg.voice:
        replied_msg_id = replied_msg.message_id
        
        # Takliflar ma'lumotlarini yuklash
        offers = load_offers()
        
        # Agar bu xabar bizning ovozli xabarlarimizdan biri bo'lsa va hali olinmagan bo'lsa
        if str(replied_msg_id) in offers and offers[str(replied_msg_id)]["status"] == "active":
            # Taklifni olish jarayonini boshlash
            await process_claim(update, context, replied_msg_id)

# Matnli xabarlarni qayta ishlash
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    username = update.message.from_user.username if update.message.from_user.username else None
    text = update.message.text
    
    # Telefon raqamni tekshirish
    phone_match = PHONE_PATTERN.search(text)
    if phone_match and user_id in waiting_for_phone:
        message_id, chat_id, timestamp, voice_file_id = waiting_for_phone[user_id]
        
        #180 soniya o'tganligini tekshirish
        current_time = time.time()
        if current_time - timestamp > 180:
            #180 soniyadan ko'p vaqt o'tgan
            del waiting_for_phone[user_id]
            await update.message.reply_text("Ovozli xabar yuborilganidan keyin 3 daqiqa o'tdi. Iltimos, qayta urinib ko'ring.")
            return
        
        # Telefon raqamni olish
        phone_number = phone_match.group(0)
        if not phone_number.startswith("+"):
            if phone_number.startswith("998"):
                phone_number = "+" + phone_number
            else:
                phone_number = "+998" + phone_number
        
        # Asl xabarlarni o'chirish
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            await context.bot.delete_message(chat_id=update.message.chat_id, message_id=update.message.message_id)
        except Exception as e:
            logger.error(f"Xabarlarni o'chirishda xatolik: {e}")
        
        # O'chirish tugmasi bilan ovozli xabarni yuborish
        keyboard = [
            [InlineKeyboardButton("O'chirish", callback_data=f"delete_offer")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        sent_message = await context.bot.send_voice(
            chat_id=chat_id,
            voice=voice_file_id,
            caption=f"Yangi yo'lovchilar taklifi\nsoni: aniq emas\nqayerdan: aniq emas\nKim yubordi: {user_name} {('@' + username) if username else ''}\n\nushbu yo'lovchini olish uchun yuqoridagi ovozli habarga reply qilib \"olaman\" deb yozing yoki ovozli habar yuboring",
            reply_markup=reply_markup
        )
        
        # Taklifni JSON faylga saqlash
        offers = load_offers()
        offer_id = str(sent_message.message_id)
        
        offers[offer_id] = {
            "chat_id": chat_id,
            "message_id": sent_message.message_id,
            "voice_file_id": voice_file_id,
            "phone_number": phone_number,
            "sender_name": user_name,
            "sender_id": user_id,
            "sender_username": username,
            "status": "active",
            "created_at": datetime.now().isoformat()
        }
        
        save_offers(offers)
        
        # 5 daqiqadan keyin tekshirish uchun task yaratish
        context.application.create_task(check_offer_timeout(context, sent_message.message_id))
        
        # Kutish ro'yxatidan o'chirish
        del waiting_for_phone[user_id]
        
        # Statistikani yangilash
        stats = load_stats()
        stats["total_rides"] += 1
        save_stats(stats)
    
    # Javoblarni tekshirish
    elif update.message.reply_to_message:
        replied_msg = update.message.reply_to_message
        
        # Bot yuborgan ovozli xabarga javob berilganini tekshirish
        if replied_msg.from_user.id == context.bot.id and replied_msg.voice:
            replied_msg_id = replied_msg.message_id
            
            # Takliflar ma'lumotlarini yuklash
            offers = load_offers()
            
            # Agar bu xabar bizning ovozli xabarlarimizdan biri bo'lsa va "olaman" deb yozilgan bo'lsa
            if str(replied_msg_id) in offers and offers[str(replied_msg_id)]["status"] == "active":
                # Agar "olaman" deb yozilgan bo'lsa
                if text.lower() == "olaman":
                    await process_claim(update, context, replied_msg_id)

# 5 daqiqa kutish va taklif o'chirilishi
async def check_offer_timeout(context, message_id):
    await asyncio.sleep(300)  # 5 daqiqa (300 soniya) kutish
    
    # Takliflar ma'lumotlarini yuklash
    offers = load_offers()
    offer_id = str(message_id)
    
    # Agar taklif hali ham mavjud va olinmagan bo'lsa
    if offer_id in offers and offers[offer_id]["status"] == "active":
        offer = offers[offer_id]
        
        # Xabarni o'chirish
        try:
            await context.bot.delete_message(chat_id=offer["chat_id"], message_id=message_id)
        except Exception as e:
            logger.error(f"Xabarni o'chirishda xatolik: {e}")
        
        # Taklifni avtomatik qayta yuborish
        try:
            # O'chirish tugmasi bilan ovozli xabarni qayta yuborish
            keyboard = [
                [InlineKeyboardButton("O'chirish", callback_data=f"delete_offer")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            sent_message = await context.bot.send_voice(
                chat_id=offer["chat_id"],
                voice=offer["voice_file_id"],
                caption=f"Yangi yo'lovchilar taklifi\nsoni: aniq emas\nqayerdan: aniq emas\nKim yubordi: {offer['sender_name']} {('@' + offer['sender_username']) if offer['sender_username'] else ''}\n\nushbu yo'lovchini olish uchun yuqoridagi ovozli habarga reply qilib \"olaman\" deb yozing yoki ovozli habar yuboring",
                reply_markup=reply_markup
            )
            
            # Yangi taklifni saqlash
            new_offer_id = str(sent_message.message_id)
            offers[new_offer_id] = {
                "chat_id": offer["chat_id"],
                "message_id": sent_message.message_id,
                "voice_file_id": offer["voice_file_id"],
                "phone_number": offer["phone_number"],
                "sender_name": offer["sender_name"],
                "sender_id": offer["sender_id"],
                "sender_username": offer["sender_username"],
                "status": "active",
                "created_at": datetime.now().isoformat()
            }
            
            # Eski taklifni o'chirish
            del offers[offer_id]
            save_offers(offers)
            
            # 5 daqiqadan keyin tekshirish uchun task yaratish
            context.application.create_task(check_offer_timeout(context, sent_message.message_id))
            
            # Taklif beruvchiga xabar yuborish
            await context.bot.send_message(
                chat_id=offer["sender_id"],
                text=f"Sizning taklifingiz 5 daqiqa ichida hech kim olmadi. Taklif avtomatik ravishda qayta yuborildi."
            )
            
        except Exception as e:
            logger.error(f"Taklifni qayta yuborishda xatolik: {e}")
            # Xatolik bo'lsa, taklifni o'chirib tashlash
            del offers[offer_id]
            save_offers(offers)

# Taklifni olish jarayoni
async def process_claim(update: Update, context: ContextTypes.DEFAULT_TYPE, replied_msg_id: int) -> None:
    claimer_id = update.message.from_user.id
    claimer_name = update.message.from_user.first_name
    claimer_username = update.message.from_user.username
    
    # Foydalanuvchi ro'yxatdan o'tganligini tekshirish
    users = load_users()
    if str(claimer_id) not in users:
        await update.message.reply_text(
            "Iltimos, avval botga / start buyrug'ini yuborib ro'yxatdan o'ting.  bot linki: @taxi_coin_maxsus_bot"
        )
        return
    
    # Foydalanuvchining balansini tekshirish - manfiy bo'lsa, yangi taklif ololmaydi
    user_coins = users[str(claimer_id)]["coins"]
    if user_coins < 0:
        await update.message.reply_text(
            f"Sizning hisobingizda {user_coins} tanga bor (manfiy balans). Yangi takliflarni olish uchun avval hisobingizni ijobiy holatga keltiring."
        )
        return
    
    # Takliflar ma'lumotlarini yuklash
    offers = load_offers()
    offer_id = str(replied_msg_id)
    
    if offer_id in offers and offers[offer_id]["status"] == "active":
        # Taklifni "kutilmoqda" statusiga o'zgartirish
        offers[offer_id]["status"] = "waiting"
        offers[offer_id]["claimer_id"] = claimer_id
        offers[offer_id]["claimer_name"] = claimer_name
        offers[offer_id]["claimer_username"] = claimer_username
        save_offers(offers)
        
        # Xabar matnini yangilash
        offer = offers[offer_id]
        
        await context.bot.edit_message_caption(
            chat_id=offer["chat_id"],
            message_id=replied_msg_id,
            caption=f"Yangi yo'lovchilar taklifi\nsoni: aniq emas\nqayerdan: aniq emas\nKim yubordi: {offer['sender_name']} {('@' + offer['sender_username']) if offer['sender_username'] else ''}\n\nKutilmoqda: {claimer_name} {('@' + claimer_username) if claimer_username else ''}",
            reply_markup=None  # O'chirish tugmasini olib tashlash
        )
        
        # Olgan foydalanuvchiga shaxsiy xabar yuborish
        keyboard = [
            [
                InlineKeyboardButton("Oldim", callback_data=f"take_{replied_msg_id}"),
                InlineKeyboardButton("Olmadim", callback_data=f"reject_{replied_msg_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=claimer_id,
            text=f"Siz yo'lovchi taklifini oldingiz\n\nsoni: aniq emas\nqayerdan: aniq emas\nkim yubordi: {('@' + offer['sender_username']) if offer['sender_username'] else offer['sender_name']}\ntelefon raqam: {offer['phone_number']}",
            reply_markup=reply_markup
        )

# Foydalanuvchilarni ko'rsatish funksiyasi (sahifalash bilan)
async def show_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE, action_type: str, page: int = 0) -> int:
    query = update.callback_query
    if query:
        await query.answer()
    
    users = load_users()
    
    # Foydalanuvchilarni saralash (eng yangilarini oldin ko'rsatish)
    sorted_users = sorted(
        users.items(),
        key=lambda x: x[1].get("joined_date", ""),
        reverse=True
    )
    
    # Sahifalash parametrlari
    users_per_page = 10  # Har bir sahifada 10 ta foydalanuvchi
    total_users = len(sorted_users)
    total_pages = (total_users + users_per_page - 1) // users_per_page  # Yuqoriga yaxlitlash
    
    # Sahifa raqamini tekshirish
    if page < 0:
        page = 0
    if page >= total_pages and total_pages > 0:
        page = total_pages - 1
    
    # Joriy sahifadagi foydalanuvchilar
    start_idx = page * users_per_page
    end_idx = min(start_idx + users_per_page, total_users)
    current_page_users = sorted_users[start_idx:end_idx]
    
    # Sahifa raqamini saqlash
    context.user_data["current_page"] = page
    context.user_data["action_type"] = action_type
    
    # Foydalanuvchilar ro'yxatini yaratish
    keyboard = []
    
    for user_id, user_data in current_page_users:
        name = user_data.get("name", "Noma'lum")
        username = user_data.get("username", "")
        display_name = f"{name} (@{username})" if username else name
        
        # Callback data formatini yaratish: action_type_user_ID
        callback_data = f"{action_type}_user_{user_id}"
        
        # Har bir foydalanuvchi uchun alohida qator
        keyboard.append([InlineKeyboardButton(display_name, callback_data=callback_data)])
    
    # Navigatsiya tugmalarini qo'shish
    nav_buttons = []
    
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"page_{action_type}_{page-1}"))
    
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"page_{action_type}_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Sahifa ma'lumotini ko'rsatish
    page_info = f"Sahifa {page+1}/{total_pages}" if total_pages > 0 else "Bo'sh ro'yxat"
    keyboard.append([InlineKeyboardButton(page_info, callback_data="page_info")])
    
    # Orqaga tugmasini qo'shish
    keyboard.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = f"Foydalanuvchini tanlang ({start_idx+1}-{end_idx} / {total_users}):"
    
    if query:
        await query.edit_message_text(
            text=message_text,
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            text=message_text,
            reply_markup=reply_markup
        )
    
    # Xabar yuborish yoki sovg'a qilish uchun holat qaytarish
    if action_type == "msg":
        return MESSAGE_TEXT
    else:  # gift
        return GIFT_AMOUNT

# Admin statistikasini ko'rsatish
async def show_admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
    
    stats = load_stats()
    users = load_users()
    
    # Qo'shimcha statistikalar
    active_users = 0
    negative_balance_users = 0
    
    for user_id, user_data in users.items():
        coins = user_data.get("coins", 0)
        if coins > 0:
            active_users += 1
        if coins < 0:
            negative_balance_users += 1
    
    stats_text = (
        f"📊 Bot statistikasi:\n\n"
        f"👥 Jami foydalanuvchilar: {stats['users_count']}\n"
        f"👤 Faol foydalanuvchilar: {active_users}\n"
        f"👤 Manfiy balansli foydalanuvchilar: {negative_balance_users}\n"
        f"🚕 Jami takliflar: {stats['total_rides']}\n"
        f"💰 Jami tangalar: {stats['total_coins']}\n"
    )
    
    if query:
        await query.edit_message_text(
            text=stats_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")]
            ])
        )
    else:
        await update.message.reply_text(stats_text)
    
    return ADMIN_STATS

# Admin panelni ko'rsatish
async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton("✉️ Xabar yuborish", callback_data="admin_message")],
        [InlineKeyboardButton("🎁 Tanga sovg'a qilish", callback_data="admin_gift")],
        [InlineKeyboardButton("⚙️ Sozlamalar", callback_data="admin_settings")],
        [InlineKeyboardButton("❌ Chiqish", callback_data="admin_exit")]
    ]
    
    if query:
        await query.edit_message_text(
            text="Admin panel. Kerakli bo'limni tanlang:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            text="Admin panel. Kerakli bo'limni tanlang:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    return ADMIN_MAIN

# Admin paneldan chiqish
async def admin_exit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("Admin paneldan chiqildi.")
    else:
        await update.message.reply_text(
            "Admin paneldan chiqildi.",
            reply_markup=ReplyKeyboardRemove()
        )
    
    return ConversationHandler.END

# Admin xabarini yuborish
async def send_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    users = load_users()
    message_text = context.user_data.get("message_text", "")
    msg_target = context.user_data.get("msg_target")
    
    sent_count = 0
    failed_count = 0
    
    if msg_target == "all":
        # Barcha foydalanuvchilarga yuborish
        for user_id in users:
            try:
                await context.bot.send_message(
                    chat_id=int(user_id),
                    text=f"📢 Admin xabari:\n\n{message_text}"
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Xabar yuborishda xatolik: {e}")
                failed_count += 1
        
        await query.edit_message_text(
            f"Xabar {sent_count} ta foydalanuvchiga yuborildi. {failed_count} ta yuborishda xatolik.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")]
            ])
        )
    else:
        # Bitta foydalanuvchiga yuborish
        target_id = context.user_data.get("target_id")
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"📢 Admin xabari:\n\n{message_text}"
            )
            await query.edit_message_text(
                f"Xabar foydalanuvchi {target_id} ga muvaffaqiyatli yuborildi.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")]
                ])
            )
        except Exception as e:
            logger.error(f"Xabar yuborishda xatolik: {e}")
            await query.edit_message_text(
                f"Xabar yuborishda xatolik yuz berdi: {str(e)}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")]
                ])
            )
    
    return ADMIN_MAIN

# Tanga sovg'a qilishni tasdiqlash
async def confirm_gift(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    users = load_users()
    gift_target = context.user_data.get("gift_target")
    amount = context.user_data.get("gift_amount", 0)
    
    if gift_target == "all":
        # Barcha foydalanuvchilarga sovg'a qilish
        for user_id in users:
            users[user_id]["coins"] += amount
        
        save_users(users)
        
        # Statistikani yangilash
        stats = load_stats()
        stats["total_coins"] += amount * len(users)
        save_stats(stats)
        
        # Xabar yuborish
        for user_id in users:
            try:
                await context.bot.send_message(
                    chat_id=int(user_id),
                    text=f"🎁 Tabriklaymiz! Admin sizga {amount} tanga sovg'a qildi.\n"
                         f"Yangi hisobingiz: {users[user_id]['coins']} tanga."
                )
            except Exception as e:
                logger.error(f"Xabar yuborishda xatolik: {e}")
        
        await query.edit_message_text(
            f"Barcha foydalanuvchilarga {amount} tanga sovg'a qilindi.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")]
            ])
        )
    else:
        # Bitta foydalanuvchiga sovg'a qilish
        user_id = context.user_data.get("gift_user_id")
        user_id_str = str(user_id)
        
        if user_id_str in users:
            users[user_id_str]["coins"] += amount
            save_users(users)
            
            # Statistikani yangilash
            stats = load_stats()
            stats["total_coins"] += amount
            save_stats(stats)
            
            # Xabar yuborish
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🎁 Tabriklaymiz! Admin sizga {amount} tanga sovg'a qildi.\n"
                         f"Yangi hisobingiz: {users[user_id_str]['coins']} tanga."
                )
            except Exception as e:
                logger.error(f"Xabar yuborishda xatolik: {e}")
            
            await query.edit_message_text(
                f"Foydalanuvchi {users[user_id_str]['name']} ga {amount} tanga sovg'a qilindi.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")]
                ])
            )
        else:
            await query.edit_message_text(
                "Foydalanuvchi topilmadi.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")]
                ])
            )
    
    return ADMIN_MAIN

# Callback query'larni qayta ishlash
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    # Taklifni o'chirish uchun callback'ni tekshirish
    if data == "delete_offer":
        # Xabar ID'sini olish
        message_id = query.message.message_id
        chat_id = query.message.chat.id

        # Takliflar ma'lumotlarini yuklash
        offers = load_offers()
        offer_id = str(message_id)

        # Agar taklif mavjud bo'lsa
        if offer_id in offers:
            offer = offers[offer_id]

            # Faqat taklif egasi yoki adminlar o'chira oladi
            if user_id == offer["sender_id"] or user_id in ADMIN_IDS:
                try:
                    # Xabarni o'chirish
                    await context.bot.delete_message(chat_id=chat_id, message_id=message_id)

                    # Taklifni o'chirish
                    del offers[offer_id]
                    save_offers(offers)

                    # Taklif egasiga xabar yuborish
                    if user_id == offer["sender_id"]:
                        await context.bot.send_message(
                            chat_id=user_id,
                            text="Sizning taklifingiz o'chirildi."
                        )
                    else:
                        # Admin tomonidan o'chirilgan
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"Siz {offer['sender_name']} ning taklifini o'chirdingiz."
                        )

                        # Taklif egasiga xabar yuborish
                        await context.bot.send_message(
                            chat_id=offer["sender_id"],
                            text="Sizning taklifingiz admin tomonidan o'chirildi."
                        )
                except Exception as e:
                    logger.error(f"Taklifni o'chirishda xatolik: {e}")
                    await query.answer("Taklifni o'chirishda xatolik yuz berdi.", show_alert=True)
            else:
                # Ruxsat yo'q
                await query.answer("Siz faqat o'zingizning takliflaringizni o'chira olasiz!", show_alert=True)
        else:
            await query.answer("Taklif topilmadi.", show_alert=True)

    # Sahifalash uchun callback'larni tekshirish
    elif data.startswith("page_"):
        parts = data.split("_")
        if len(parts) >= 3 and parts[2].isdigit():
            action_type = parts[1]  # msg yoki gift
            page = int(parts[2])
            return await show_users_list(update, context, action_type, page)
        elif data == "page_info":
            # Sahifa ma'lumoti tugmasi bosilganda hech narsa qilmaslik
            return

    # Foydalanuvchi tanlash uchun callback'larni tekshirish
    elif data.startswith("msg_user_"):
        # Xabar yuborish uchun foydalanuvchi tanlandi
        target_id = int(data.split("_")[2])
        context.user_data["msg_target"] = "one"
        context.user_data["target_id"] = target_id

        users = load_users()
        user_name = users[str(target_id)]["name"] if str(target_id) in users else "Noma'lum"

        await query.edit_message_text(
            text=f"Foydalanuvchi {user_name} ga yuboriladigan xabarni kiriting:"
        )
        return MESSAGE_TEXT

    elif data.startswith("gift_user_"):
        # Sovg'a qilish uchun foydalanuvchi tanlandi
        target_id = int(data.split("_")[2])
        context.user_data["gift_target"] = "one"
        context.user_data["gift_user_id"] = target_id

        users = load_users()
        user_name = users[str(target_id)]["name"] if str(target_id) in users else "Noma'lum"

        await query.edit_message_text(
            text=f"Foydalanuvchi {user_name} ga qancha tanga sovg'a qilmoqchisiz?"
        )
        return GIFT_AMOUNT

    elif data.startswith("take_"):
        # Taklifni olish
        msg_id = int(data.split("_")[1])

        # Takliflar ma'lumotlarini yuklash
        offers = load_offers()
        offer_id = str(msg_id)

        if offer_id in offers and offers[offer_id]["status"] == "waiting":
            # Yo'lovchilar sonini so'rash
            keyboard = [
                [
                    InlineKeyboardButton("1", callback_data=f"count_{msg_id}_1"),
                    InlineKeyboardButton("2", callback_data=f"count_{msg_id}_2"),
                    InlineKeyboardButton("3", callback_data=f"count_{msg_id}_3"),
                    InlineKeyboardButton("4", callback_data=f"count_{msg_id}_4")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                text="Nechta odam ekan?",
                reply_markup=reply_markup
            )

    elif data.startswith("reject_"):
        # Taklifni rad etish
        msg_id = int(data.split("_")[1])

        # Takliflar ma'lumotlarini yuklash
        offers = load_offers()
        offer_id = str(msg_id)

        if offer_id in offers and offers[offer_id]["status"] == "waiting":
            offer = offers[offer_id]

            # Guruhda xabarni o'chirish
            try:
                await context.bot.delete_message(chat_id=offer["chat_id"], message_id=msg_id)
            except Exception as e:
                logger.error(f"Xabarni o'chirishda xatolik: {e}")

            # Taklifni avtomatik qayta yuborish
            try:
                # O'chirish tugmasi bilan ovozli xabarni qayta yuborish
                keyboard = [
                    [InlineKeyboardButton("O'chirish", callback_data=f"delete_offer")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                sent_message = await context.bot.send_voice(
                    chat_id=offer["chat_id"],
                    voice=offer["voice_file_id"],
                    caption=f"Yangi yo'lovchilar taklifi\nsoni: aniq emas\nqayerdan: aniq emas\nKim yubordi: {offer['sender_name']} {('@' + offer['sender_username']) if offer['sender_username'] else ''}\n\nushbu yo'lovchini olish uchun yuqoridagi ovozli habarga reply qilib \"olaman\" deb yozing yoki ovozli habar yuboring",
                    reply_markup=reply_markup
                )

                # Yangi taklifni saqlash
                new_offer_id = str(sent_message.message_id)
                offers[new_offer_id] = {
                    "chat_id": offer["chat_id"],
                    "message_id": sent_message.message_id,
                    "voice_file_id": offer["voice_file_id"],
                    "phone_number": offer["phone_number"],
                    "sender_name": offer["sender_name"],
                    "sender_id": offer["sender_id"],
                    "sender_username": offer["sender_username"],
                    "status": "active",
                    "created_at": datetime.now().isoformat()
                }

                # Eski taklifni o'chirish
                del offers[offer_id]
                save_offers(offers)

                # 5 daqiqadan keyin tekshirish uchun task yaratish
                context.application.create_task(check_offer_timeout(context, sent_message.message_id))

                # Oluvchiga xabar
                await query.edit_message_text(
                    text="Siz taklifni rad etdingiz."
                )

                # Taklif beruvchiga xabar yuborish
                await context.bot.send_message(
                    chat_id=offer["sender_id"],
                    text=f"Siz bergan foydalanuvchi taklifini {('@' + offer['claimer_username']) if offer['claimer_username'] else offer['claimer_name']} olmadi. Taklif avtomatik ravishda qayta yuborildi."
                )

            except Exception as e:
                logger.error(f"Taklifni qayta yuborishda xatolik: {e}")
                # Xatolik bo'lsa, taklifni o'chirib tashlash
                del offers[offer_id]
                save_offers(offers)

                await query.edit_message_text(
                    text="Taklifni qayta yuborishda xatolik yuz berdi."
                )

    elif data.startswith("count_"):
        # Yo'lovchilar sonini qayta ishlash
        parts = data.split("_")
        msg_id = int(parts[1])
        count = int(parts[2])
        
        # Takliflar ma'lumotlarini yuklash
        offers = load_offers()
        offer_id = str(msg_id)
        
        if offer_id in offers and offers[offer_id]["status"] == "waiting":
            offer = offers[offer_id]
            
            # Tangalarni o'tkazish
            users = load_users()
            claimer_id_str = str(user_id)
            sender_id_str = str(offer["sender_id"])
            
            if claimer_id_str in users and sender_id_str in users:
                # Oluvchidan tangalarni yechib olish - hatto manfiy balansga tushsa ham
                users[claimer_id_str]["coins"] -= count
                users[sender_id_str]["coins"] += count
                
                save_users(users)
                
                # Oluvchiga xabar
                current_balance = users[claimer_id_str]["coins"]
                balance_message = f"Qolgan tangalaringiz: {current_balance}"
                
                if current_balance < 0:
                    balance_message += "\n⚠️ Sizning hisobingiz manfiy holatga tushdi. Yangi takliflarni olish uchun avval hisobingizni to'ldiring."
                
                await query.edit_message_text(
                    text=f"Siz {count} ta yo'lovchini oldingiz va {count} tanga to'ladingiz.\n{balance_message}"
                )
                
                # Beruvchiga xabar
                await context.bot.send_message(
                    chat_id=offer["sender_id"],
                    text=f"Sizning taklifingiz qabul qilindi! {count} tanga qabul qildingiz.\nHisobingiz: {users[sender_id_str]['coins']} tanga"
                )
                
                # Guruhda xabarni yangilash - "olindi" statusiga o'zgartirish
                try:
                    # Statusni yangilash
                    offers[offer_id]["status"] = "completed"
                    offers[offer_id]["passengers_count"] = count
                    offers[offer_id]["completed_at"] = datetime.now().isoformat()
                    save_offers(offers)
                    
                    # Guruhda xabarni yangilash
                    await context.bot.edit_message_caption(
                        chat_id=offer["chat_id"],
                        message_id=msg_id,
                        caption=f"Yangi yo'lovchilar taklifi\nsoni: {count}\nqayerdan: aniq emas\nKim yubordi: {offer['sender_name']} {('@' + offer['sender_username']) if offer['sender_username'] else ''}\n\nOlindi: {offer['claimer_name']} {('@' + offer['claimer_username']) if offer['claimer_username'] else ''}",
                        reply_markup=None  # O'chirish tugmasini olib tashlash
                    )
                except Exception as e:
                    logger.error(f"Xabarni yangilashda xatolik: {e}")
            else:
                await query.edit_message_text(
                    text="Xatolik yuz berdi. Iltimos, qayta urinib ko'ring."
                )

    # Admin panel uchun callback'lar
    elif data == "admin_stats":
        await show_admin_stats(update, context)

    elif data == "admin_message":
        await query.edit_message_text(
            text="Foydalanuvchilarga xabar yuborish. Kimga yubormoqchisiz?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Barcha foydalanuvchilarga", callback_data="msg_all")],
                [InlineKeyboardButton("Bitta foydalanuvchiga", callback_data="msg_one")],
                [InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")]
            ])
        )
        return ADMIN_MESSAGE

    elif data == "msg_all":
        context.user_data["msg_target"] = "all"
        await query.edit_message_text(
            text="Barcha foydalanuvchilarga yuboriladigan xabarni kiriting:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_message")]
            ])
        )
        return MESSAGE_TEXT

    elif data == "msg_one":
        # Foydalanuvchilar ro'yxatini ko'rsatish
        return await show_users_list(update, context, "msg")

    elif data == "admin_gift":
        await query.edit_message_text(
            text="Tanga sovg'a qilish. Kimga sovg'a qilmoqchisiz?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Barcha foydalanuvchilarga", callback_data="gift_all")],
                [InlineKeyboardButton("Bitta foydalanuvchiga", callback_data="gift_one")],
                [InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")]
            ])
        )
        return ADMIN_GIFT

    elif data == "gift_all":
        context.user_data["gift_target"] = "all"
        await query.edit_message_text(
            text="Barcha foydalanuvchilarga qancha tanga sovg'a qilmoqchisiz?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_gift")]
            ])
        )
        return GIFT_AMOUNT

    elif data == "gift_one":
        # Foydalanuvchilar ro'yxatini ko'rsatish
        return await show_users_list(update, context, "gift")

    elif data == "admin_settings":
        config = load_config()
        await query.edit_message_text(
            text=f"Sozlamalar:\n\n"
                 f"Boshlang'ich tangalar: {config['initial_coins']}\n"
                 f"Salomlashish xabari: {config['welcome_message']}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Boshlang'ich tangalarni o'zgartirish", callback_data="set_coins")],
                [InlineKeyboardButton("Salomlashish xabarini o'zgartirish", callback_data="set_welcome")],
                [InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")]
            ])
        )
        return ADMIN_SETTINGS

    elif data == "admin_back":
        await show_admin_panel(update, context)
        return ADMIN_MAIN

# Hisobni ko'rish
async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    users = load_users()

    if str(user_id) not in users:
        await update.message.reply_text(
            "Siz ro'yxatdan o'tmagansiz. /start buyrug'ini yuborib ro'yxatdan o'ting."
        )
        return

    user_data = users[str(user_id)]
    coins = user_data["coins"]

    # Manfiy balans bo'lsa, qo'shimcha xabar ko'rsatish
    additional_message = ""
    if coins < 0:
        additional_message = "\n\n⚠️ Sizning hisobingiz manfiy holatda. Yangi takliflarni olish uchun avval hisobingizni ijobiy holatga keltiring."

    await update.message.reply_text(
        f"Sizning hisobingizda {coins} tanga bor.{additional_message}"
    )

# Admin panel
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Bu buyruq faqat adminlar uchun.")
        return ConversationHandler.END
    
    # Oddiy tugmalar bilan admin panelni ko'rsatish
    keyboard = [
        ["📊 Statistika", "✉️ Xabar yuborish"],
        ["🎁 Tanga sovg'a qilish", "⚙️ Sozlamalar"],
        ["❌ Chiqish"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "Admin panel. Kerakli bo'limni tanlang:",
        reply_markup=reply_markup
    )
    return ADMIN_MAIN

# Admin panelni qayta ishlash
async def handle_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    
    if text == "📊 Statistika":
        stats = load_stats()
        users = load_users()
        
        # Qo'shimcha statistikalar
        active_users = 0
        
        for user_id, user_data in users.items():
            if user_data.get("coins", 0) > 0:
                active_users += 1
        
        stats_text = (
            f"📊 Bot statistikasi:\n\n"
            f"👥 Jami foydalanuvchilar: {stats['users_count']}\n"
            f"👤 Faol foydalanuvchilar: {active_users}\n"
            f"🚕 Jami takliflar: {stats['total_rides']}\n"
            f"💰 Jami tangalar: {stats['total_coins']}\n"
        )
        
        await update.message.reply_text(stats_text)
        return ADMIN_MAIN
    
    elif text == "✉️ Xabar yuborish":
        keyboard = [
            ["Barcha foydalanuvchilarga", "Bitta foydalanuvchiga"],
            ["⬅️ Orqaga"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            "Foydalanuvchilarga xabar yuborish. Kimga yubormoqchisiz?",
            reply_markup=reply_markup
        )
        return ADMIN_MESSAGE
    
    elif text == "🎁 Tanga sovg'a qilish":
        keyboard = [
            ["Barcha foydalanuvchilarga", "Bitta foydalanuvchiga"],
            ["⬅️ Orqaga"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            "Tanga sovg'a qilish. Kimga sovg'a qilmoqchisiz?",
            reply_markup=reply_markup
        )
        return ADMIN_GIFT
    
    elif text == "⚙️ Sozlamalar":
        config = load_config()
        
        keyboard = [
            ["Boshlang'ich tangalarni o'zgartirish"],
            ["Salomlashish xabarini o'zgartirish"],
            ["⬅️ Orqaga"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            f"Sozlamalar:\n\n"
            f"Boshlang'ich tangalar: {config['initial_coins']}\n"
            f"Salomlashish xabari: {config['welcome_message']}",
            reply_markup=reply_markup
        )
        return ADMIN_SETTINGS
    
    elif text == "❌ Chiqish":
        await update.message.reply_text(
            "Admin paneldan chiqildi.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    
    elif text == "⬅️ Orqaga":
        return await admin(update, context)
    
    return ADMIN_MAIN

# Xabar yuborish bo'limini qayta ishlash
async def handle_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    
    if text == "Barcha foydalanuvchilarga":
        context.user_data["msg_target"] = "all"
        await update.message.reply_text(
            "Barcha foydalanuvchilarga yuboriladigan xabarni kiriting:"
        )
        return MESSAGE_TEXT
    
    elif text == "Bitta foydalanuvchiga":
        # Foydalanuvchilar ro'yxatini ko'rsatish
        return await show_users_list(update, context, "msg")
    
    elif text == "⬅️ Orqaga":
        return await admin(update, context)
    
    return ADMIN_MESSAGE

# Tanga sovg'a qilish bo'limini qayta ishlash
async def handle_admin_gift(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    
    if text == "Barcha foydalanuvchilarga":
        context.user_data["gift_target"] = "all"
        await update.message.reply_text(
            "Barcha foydalanuvchilarga qancha tanga sovg'a qilmoqchisiz?"
        )
        return GIFT_AMOUNT
    
    elif text == "Bitta foydalanuvchiga":
        # Foydalanuvchilar ro'yxatini ko'rsatish
        return await show_users_list(update, context, "gift")
    
    elif text == "⬅️ Orqaga":
        return await admin(update, context)
    
    return ADMIN_GIFT

# Sozlamalar bo'limini qayta ishlash
async def handle_admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    
    if text == "Boshlang'ich tangalarni o'zgartirish":
        await update.message.reply_text(
            "Yangi boshlang'ich tanga miqdorini kiriting:"
        )
        context.user_data["setting_type"] = "initial_coins"
        return ADMIN_SETTINGS
    
    elif text == "Salomlashish xabarini o'zgartirish":
        await update.message.reply_text(
            "Yangi salomlashish xabarini kiriting:"
        )
        context.user_data["setting_type"] = "welcome_message"
        return ADMIN_SETTINGS
    
    elif text == "⬅️ Orqaga":
        return await admin(update, context)
    
    # Sozlamalarni o'zgartirish
    if "setting_type" in context.user_data:
        setting_type = context.user_data["setting_type"]
        config = load_config()
        
        if setting_type == "initial_coins":
            try:
                new_value = int(text)
                if new_value < 0:
                    await update.message.reply_text("Miqdor musbat bo'lishi kerak.")
                    return ADMIN_SETTINGS
                
                config["initial_coins"] = new_value
                save_config(config)
                
                await update.message.reply_text(
                    f"Boshlang'ich tanga miqdori {new_value} ga o'zgartirildi."
                )
            except ValueError:
                await update.message.reply_text("Iltimos, raqam kiriting.")
                return ADMIN_SETTINGS
        
        elif setting_type == "welcome_message":
            config["welcome_message"] = text
            save_config(config)
            
            await update.message.reply_text(
                "Salomlashish xabari o'zgartirildi."
            )
        
        # Sozlamalar bo'limiga qaytish
        del context.user_data["setting_type"]
        return await handle_admin_menu(update, context)
    
    return ADMIN_SETTINGS

# Xabar matnini qabul qilish
async def receive_message_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    logger.info(f"Xabar matni qabul qilindi: {text}")
    logger.info(f"User data: {context.user_data}")
    
    # Xabar matnini saqlash
    context.user_data["message_text"] = text
    
    # Tasdiqlash so'rash
    keyboard = [["✅ Tasdiqlash", "❌ Bekor qilish"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    # Foydalanuvchi nomini olish
    target_name = "barcha foydalanuvchilarga"
    if context.user_data.get("msg_target") == "one":
        target_id = context.user_data.get("target_id")
        users = load_users()
        if str(target_id) in users:
            target_name = f"foydalanuvchi {users[str(target_id)]['name']} ga"
        else:
            target_name = f"foydalanuvchi {target_id} ga"
    
    await update.message.reply_text(
        f"Quyidagi xabarni {target_name} yuborishni tasdiqlaysizmi?\n\n"
        f"{text}",
        reply_markup=reply_markup
    )
    return MESSAGE_CONFIRM

# Xabarni yuborish tasdig'ini qayta ishlash
async def handle_message_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    logger.info(f"Xabar tasdiqlash: {text}")
    logger.info(f"User data: {context.user_data}")
    
    # Agar bu tanga sovg'a qilish tasdiqlash bo'lsa
    if "gift_target" in context.user_data and "gift_amount" in context.user_data:
        return await handle_gift_confirm(update, context)
    
    if text == "✅ Tasdiqlash":
        users = load_users()
        message_text = context.user_data.get("message_text", "")
        msg_target = context.user_data.get("msg_target")
        
        sent_count = 0
        failed_count = 0
        
        if msg_target == "all":
            # Barcha foydalanuvchilarga yuborish
            for user_id in users:
                try:
                    await context.bot.send_message(
                        chat_id=int(user_id),
                        text=f"📢 Admin xabari:\n\n{message_text}"
                    )
                    sent_count += 1
                except Exception as e:
                    logger.error(f"Xabar yuborishda xatolik: {e}")
                    failed_count += 1
            
            await update.message.reply_text(
                f"Xabar {sent_count} ta foydalanuvchiga yuborildi. {failed_count} ta yuborishda xatolik."
            )
        else:
            # Bitta foydalanuvchiga yuborish
            target_id = context.user_data.get("target_id")
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=f"📢 Admin xabari:\n\n{message_text}"
                )
                await update.message.reply_text(
                    f"Xabar foydalanuvchi {target_id} ga muvaffaqiyatli yuborildi."
                )
            except Exception as e:
                logger.error(f"Xabar yuborishda xatolik: {e}")
                await update.message.reply_text(
                    f"Xabar yuborishda xatolik yuz berdi: {str(e)}"
                )
        
        # Admin panelga qaytish
        return await admin(update, context)
    
    elif text == "❌ Bekor qilish":
        await update.message.reply_text("Xabar yuborish bekor qilindi.")
        return await admin(update, context)
    
    return MESSAGE_CONFIRM

# Tanga sovg'a qilish - miqdorni qabul qilish
async def receive_gift_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = int(update.message.text.strip())
        if amount <= 0:
            await update.message.reply_text(
                "Miqdor musbat bo'lishi kerak. Iltimos, qayta urinib ko'ring:"
            )
            return GIFT_AMOUNT
        
        context.user_data["gift_amount"] = amount
        
        # Tasdiqlash so'rash
        keyboard = [["✅ Tasdiqlash", "❌ Bekor qilish"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        gift_target = context.user_data.get("gift_target")
        if gift_target == "all":
            await update.message.reply_text(
                f"Barcha foydalanuvchilarga {amount} tanga sovg'a qilishni tasdiqlaysizmi?",
                reply_markup=reply_markup
            )
        else:
            users = load_users()
            user_id = context.user_data.get("gift_user_id")
            user_name = users[str(user_id)]["name"] if str(user_id) in users else "Noma'lum"
            
            await update.message.reply_text(
                f"Foydalanuvchi {user_name} ga {amount} tanga sovg'a qilishni tasdiqlaysizmi?",
                reply_markup=reply_markup
            )
        
        # Bu yerda MESSAGE_CONFIRM holatiga o'tish kerak
        return MESSAGE_CONFIRM
    except ValueError:
        await update.message.reply_text(
            "Noto'g'ri format. Iltimos, raqam kiriting:"
        )
        return GIFT_AMOUNT

# Tanga sovg'a qilish - tasdiqlash
async def handle_gift_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    logger.info(f"Tanga sovg'a qilish tasdiqlash: {text}")
    logger.info(f"User data: {context.user_data}")
    
    if text == "✅ Tasdiqlash":
        users = load_users()
        gift_target = context.user_data.get("gift_target")
        amount = context.user_data.get("gift_amount", 0)
        
        logger.info(f"Gift target: {gift_target}, amount: {amount}")
        
        if gift_target == "all":
            # Barcha foydalanuvchilarga sovg'a qilish
            for user_id in users:
                users[user_id]["coins"] += amount
            
            save_users(users)
            
            # Statistikani yangilash
            stats = load_stats()
            stats["total_coins"] += amount * len(users)
            save_stats(stats)
            
            # Xabar yuborish
            sent_count = 0
            failed_count = 0
            for user_id in users:
                try:
                    await context.bot.send_message(
                        chat_id=int(user_id),
                        text=f"🎁 Tabriklaymiz! Admin sizga {amount} tanga sovg'a qildi.\n"
                             f"Yangi hisobingiz: {users[user_id]['coins']} tanga."
                    )
                    sent_count += 1
                except Exception as e:
                    logger.error(f"Xabar yuborishda xatolik: {e}")
                    failed_count += 1
            
            await update.message.reply_text(
                f"Barcha foydalanuvchilarga {amount} tanga sovg'a qilindi.\n"
                f"{sent_count} ta foydalanuvchiga xabar yuborildi. {failed_count} ta yuborishda xatolik."
            )
        else:
            # Bitta foydalanuvchiga sovg'a qilish
            user_id = context.user_data.get("gift_user_id")
            user_id_str = str(user_id)
            
            if user_id_str in users:
                users[user_id_str]["coins"] += amount
                save_users(users)
                
                # Statistikani yangilash
                stats = load_stats()
                stats["total_coins"] += amount
                save_stats(stats)
                
                # Xabar yuborish
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"🎁 Tabriklaymiz! Admin sizga {amount} tanga sovg'a qildi.\n"
                             f"Yangi hisobingiz: {users[user_id_str]['coins']} tanga."
                    )
                    await update.message.reply_text(
                        f"Foydalanuvchi {users[user_id_str]['name']} ga {amount} tanga sovg'a qilindi."
                    )
                except Exception as e:
                    logger.error(f"Xabar yuborishda xatolik: {e}")
                    await update.message.reply_text(
                        f"Tanga sovg'a qilindi, lekin xabar yuborishda xatolik: {str(e)}"
                    )
            else:
                await update.message.reply_text(
                    "Foydalanuvchi topilmadi."
                )
        
        # Admin panelga qaytish
        return await admin(update, context)
    
    elif text == "❌ Bekor qilish":
        await update.message.reply_text("Tanga sovg'a qilish bekor qilindi.")
        return await admin(update, context)
    
    return MESSAGE_CONFIRM

def main() -> None:
    """Botni ishga tushirish."""
    # JSON fayllarni tekshirish
    ensure_json_files()
    
    # Applicationni yaratish
    application = Application.builder().token("7670097486:AAGo0jqQQThtSDCGbe6nlI74b5p6_PhPvdc").build()

    # Admin panel uchun ConversationHandler
    admin_handler = ConversationHandler(
        entry_points=[CommandHandler("admin", admin)],
        states={
            ADMIN_MAIN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_menu),
                CallbackQueryHandler(show_admin_stats, pattern="^admin_stats$"),
                CallbackQueryHandler(lambda u, c: ADMIN_MESSAGE, pattern="^admin_message$"),
                CallbackQueryHandler(lambda u, c: ADMIN_GIFT, pattern="^admin_gift$"),
                CallbackQueryHandler(lambda u, c: ADMIN_SETTINGS, pattern="^admin_settings$"),
                CallbackQueryHandler(admin_exit, pattern="^admin_exit$"),
            ],
            ADMIN_STATS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_menu),
                CallbackQueryHandler(lambda u, c: ADMIN_MAIN, pattern="^admin_back$"),
            ],
            ADMIN_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_message),
                CallbackQueryHandler(lambda u, c: ADMIN_MAIN, pattern="^admin_back$"),
                CallbackQueryHandler(lambda u, c: MESSAGE_TEXT, pattern="^msg_all$"),
                CallbackQueryHandler(lambda u, c: show_users_list(u, c, "msg"), pattern="^msg_one$"),
            ],
            MESSAGE_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_message_text),
                CallbackQueryHandler(lambda u, c: ADMIN_MESSAGE, pattern="^admin_message$"),
            ],
            MESSAGE_CONFIRM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: handle_message_confirm(u, c) if "msg_target" in c.user_data else handle_gift_confirm(u, c)),
            ],
            ADMIN_GIFT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_gift),
                CallbackQueryHandler(lambda u, c: ADMIN_MAIN, pattern="^admin_back$"),
                CallbackQueryHandler(lambda u, c: GIFT_AMOUNT, pattern="^gift_all$"),
                CallbackQueryHandler(lambda u, c: show_users_list(u, c, "gift"), pattern="^gift_one$"),
            ],
            GIFT_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_gift_amount),
                CallbackQueryHandler(lambda u, c: ADMIN_GIFT, pattern="^admin_gift$"),
            ],
            ADMIN_SETTINGS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_settings),
                CallbackQueryHandler(lambda u, c: ADMIN_MAIN, pattern="^admin_back$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_exit)],
        allow_reentry=True,
    )

    # Buyruq handlerlarini qo'shish
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(admin_handler)

    # Xabar handlerlarini qo'shish
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Callback query handlerini qo'shish
    application.add_handler(CallbackQueryHandler(handle_callback))

    # Botni ishga tushirish
    application.run_polling()

if __name__ == "__main__":
    main()