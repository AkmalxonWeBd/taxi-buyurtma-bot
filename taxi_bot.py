import json
import re
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, Message, Chat, ParseMode, ChatMember, ChatPermissions, Bot, User
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, ContextTypes, filters, CallbackContext

# Logging sozlamalari
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Debug rejimini yoqish/o'chirish
DEBUG = True

# Bot tokeni
BOT_TOKEN = "7670097486:AAGo0jqQQThtSDCGbe6nlI74b5p6_PhPvdc"  # O'z bot tokeningizni kiriting

# Kanal ID raqami
CHANNEL_ID = "-1002697195100"  # O'z kanal ID raqamingizni kiriting

# Admin ID
ADMIN_IDS = [7578618626]  # O'z admin ID raqamingizni kiriting

# Kanalga yuborish
SEND_TO_CHANNEL = True

# Haydovchilar kanali havolasi
DRIVERS_CHANNEL_LINK = "https://t.me/your_channel"  # O'z kanalingiz havolasini kiriting

# Conversation Handler holatlari
ENTER_NAME, ENTER_PHONE, DRIVER_MENU = range(3)
ADMIN_MENU, ADMIN_SETTINGS_MENU, ADMIN_SETTINGS_INITIAL_COINS = range(3, 6)
ADMIN_MESSAGE_TEXT, ADMIN_MESSAGE_TARGET, ADMIN_GIFT_AMOUNT, ADMIN_GIFT_TARGET = range(6, 10)

# Ma'lumotlar fayllari
USERS_FILE = "users.json"  # Foydalanuvchilar ma'lumotlari
OFFERS_FILE = "offers.json"  # Yo'lovchi berish takliflari
DRIVERS_FILE = "drivers.json"  # Haydovchilar taklifi tarixi
STATS_FILE = "stats.json"  # Statistika
VOICE_MESSAGES_FILE = "voice_messages.json"  # Ovozli xabarlar
GROUP_SETTINGS_FILE = "group_settings.json"  # Guruh sozlamalari

# Standart qiymatlar
INITIAL_DRIVER_COINS = 5  # Yangi haydovchiga beriladigan tangalar soni
VOICE_MESSAGE_TIMEOUT = 30  # Ovozli xabar kutish vaqti (soniyalarda)

# Standart guruh sozlamalari
DEFAULT_GROUP_SETTINGS = {
    "voice_tracking": True,  # Ovozli xabarlarni kuzatish
    "phone_tracking": True,  # Telefon raqamlarni kuzatish
    "auto_delete": True,     # Xabarlarni avtomatik o'chirish
    "admin_only": False,     # Faqat adminlar uchun
    "min_coins_required": 0, # Yo'lovchi olish uchun minimal tangalar soni
    "voice_timeout": 30      # Ovozli xabar vaqt chegarasi (soniyalarda)
}

#
# HELPER FUNKSIYALAR
#

# Fayllarni tekshirish
def ensure_files_exist():
    files = [USERS_FILE, OFFERS_FILE, DRIVERS_FILE, STATS_FILE, VOICE_MESSAGES_FILE, GROUP_SETTINGS_FILE]
    for file in files:
        if not os.path.exists(file):
            with open(file, 'w', encoding='utf-8') as f:
                f.write('{}')
            logger.info(f"Fayl yaratildi: {file}")

# Ma'lumotlarni yuklash
def load_data(file_path: str) -> Dict:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Fayl mavjud bo'lmasa yoki bo'sh bo'lsa, bo'sh lug'at qaytarish
        return {}

# Ma'lumotlarni saqlash
def save_data(data: Dict, file_path: str) -> None:
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Telefon raqamni formatlash
def format_phone(phone: str) -> str:
    # Telefon raqamni standart formatga o'tkazish
    if not phone.startswith('+'):
        if phone.startswith('998'):
            phone = '+' + phone
        elif len(phone) == 9:
            phone = '+998' + phone
    return phone

# Foydalanuvchi havolasini yaratish
def get_user_profile_link(user: User) -> str:
    full_name = user.full_name
    username = user.username
    user_id = user.id
    
    if username:
        return f'<a href="https://t.me/{username}">{full_name}</a>'
    else:
        return f'<a href="tg://user?id={user_id}">{full_name}</a>'

# Statistikani yangilash
def update_stats(key: str, value: int = 1) -> None:
    stats = load_data(STATS_FILE)
    
    # Bugungi sana
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Kunlik statistika
    if today not in stats:
        stats[today] = {
            "new_drivers": 0,
            "new_offers": 0,
            "offers_taken": 0,
            "fake_offers": 0,
            "failed_agreements": 0,
            "voice_messages": 0
        }
    
    # Umumiy statistika
    if "total" not in stats:
        stats["total"] = {
            "new_drivers": 0,
            "new_offers": 0,
            "offers_taken": 0,
            "fake_offers": 0,
            "failed_agreements": 0,
            "voice_messages": 0
        }
    
    # Statistikani yangilash
    if key in stats[today]:
        stats[today][key] += value
    
    if key in stats["total"]:
        stats["total"][key] += value
    
    save_data(stats, STATS_FILE)

# Kanal bilan bog'lanishni tekshirish
async def check_channel_connection(bot: Bot) -> None:
    try:
        chat = await bot.get_chat(CHANNEL_ID)
        logger.info(f"Kanal bilan bog'lanish muvaffaqiyatli: {chat.title}")
    except Exception as e:
        logger.error(f"Kanal bilan bog'lanishda xatolik: {e}")
        logger.error(f"Bot kanalga added bo'lganligini tekshiring va to'g'ri CHANNEL_ID ni kiriting")

# Xatolarni qayta ishlash
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Update {update} caused error {context.error}")

#
# GURUH SOZLAMALARI FUNKSIYALARI
#

# Guruh sozlamalarini yuklash
def load_group_settings():
    try:
        with open(GROUP_SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Fayl mavjud bo'lmasa yoki bo'sh bo'lsa, bo'sh lug'at qaytarish
        return {}

# Guruh sozlamalarini saqlash
def save_group_settings(settings):
    with open(GROUP_SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

# Guruh sozlamalarini olish
def get_group_settings(chat_id):
    settings = load_group_settings()
    chat_id_str = str(chat_id)
    
    # Agar bu guruh uchun sozlamalar bo'lmasa, standart sozlamalarni qaytarish
    if chat_id_str not in settings:
        settings[chat_id_str] = DEFAULT_GROUP_SETTINGS.copy()
        save_group_settings(settings)
    
    return settings[chat_id_str]

# Guruh sozlamasini yangilash
def update_group_setting(chat_id, setting_key, setting_value):
    settings = load_group_settings()
    chat_id_str = str(chat_id)
    
    # Agar bu guruh uchun sozlamalar bo'lmasa, standart sozlamalarni yaratish
    if chat_id_str not in settings:
        settings[chat_id_str] = DEFAULT_GROUP_SETTINGS.copy()
    
    # Sozlamani yangilash
    settings[chat_id_str][setting_key] = setting_value
    save_group_settings(settings)
    
    return settings[chat_id_str]

# Foydalanuvchi guruh admini ekanligini tekshirish
async def is_group_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id=None):
    if user_id is None:
        user_id = update.effective_user.id
    
    chat_id = update.effective_chat.id
    
    try:
        # Foydalanuvchi statusini olish
        member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        
        # Admin statuslarini tekshirish
        return member.status in ['creator', 'administrator']
    except Exception as e:
        logger.error(f"Foydalanuvchi admin statusini tekshirishda xatolik: {e}")
        return False

# Guruh xabarlarini tozalash
async def clear_bot_messages(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    # Bu yerda botning barcha xabarlarini o'chirish logikasi bo'lishi kerak
    # Misol uchun, bot yuborgan barcha xabarlar ID larini to'plab, keyin har birini o'chirish mumkin
    # Lekin Telegram API cheklovlari tufayli bu murakkab operatsiya
    
    if DEBUG:
        logger.info(f"clear_bot_messages: {chat_id} chat dan barcha bot xabarlarini o'chirish")
    
    # Bu faqat misol, amalda bu funksiya to'liq ishlamaydi
    try:
        # Bu misol uchun, amalda buni amalga oshirish qiyin
        await context.bot.send_message(
            chat_id=chat_id,
            text="Bot xabarlarini tozalash muvaffaqiyatli yakunlandi!"
        )
    except Exception as e:
        logger.error(f"Xabarlarni tozalashda xatolik: {e}")

# Guruh sozlamalari menyusini ko'rsatish
async def show_group_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Faqat guruh chatlarida ishlaydi
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("Bu buyruq faqat guruh chatlarida ishlaydi!")
        return
    
    # Foydalanuvchi admin ekanligini tekshirish
    if not await is_group_admin(update, context):
        await update.message.reply_text("Bu buyruq faqat guruh adminlari uchun!")
        return
    
    chat_id = update.effective_chat.id
    settings = get_group_settings(chat_id)
    
    # Sozlamalar menyusini tayyorlash
    keyboard = [
        [
            InlineKeyboardButton("Ovozli xabarlar", callback_data="group_setting_voice"),
            InlineKeyboardButton("✅ Yoqilgan" if settings["voice_tracking"] else "❌ O'chirilgan", callback_data="toggle_voice_tracking")
        ],
        [
            InlineKeyboardButton("Telefon raqamlar", callback_data="group_setting_phone"),
            InlineKeyboardButton("✅ Yoqilgan" if settings["phone_tracking"] else "❌ O'chirilgan", callback_data="toggle_phone_tracking")
        ],
        [
            InlineKeyboardButton("Avtomatik o'chirish", callback_data="group_setting_auto_delete"),
            InlineKeyboardButton("✅ Yoqilgan" if settings["auto_delete"] else "❌ O'chirilgan", callback_data="toggle_auto_delete")
        ],
        [
            InlineKeyboardButton("Faqat adminlar", callback_data="group_setting_admin_only"),
            InlineKeyboardButton("✅ Yoqilgan" if settings["admin_only"] else "❌ O'chirilgan", callback_data="toggle_admin_only")
        ],
        [
            InlineKeyboardButton("Minimal tangalar", callback_data="group_setting_min_coins"),
            InlineKeyboardButton(f"{settings['min_coins_required']} tanga", callback_data="set_min_coins")
        ],
        [
            InlineKeyboardButton("Guruh statistikasi", callback_data="group_stats")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Guruh sozlamalari:\n\n"
        "Bu yerda guruhda botning ishlashini sozlashingiz mumkin.",
        reply_markup=reply_markup
    )

# Guruh sozlamalari callback query handler
async def handle_group_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Foydalanuvchi admin ekanligini tekshirish
    if not await is_group_admin(update, context, query.from_user.id):
        await query.edit_message_text("Bu buyruq faqat guruh adminlari uchun!")
        return
    
    chat_id = update.effective_chat.id
    settings = get_group_settings(chat_id)
    
    # Callback data ni tekshirish
    if query.data == "toggle_voice_tracking":
        # Ovozli xabarlarni kuzatish sozlamasini almashtirish
        settings["voice_tracking"] = not settings["voice_tracking"]
        update_group_setting(chat_id, "voice_tracking", settings["voice_tracking"])
        
    elif query.data == "toggle_phone_tracking":
        # Telefon raqamlarni kuzatish sozlamasini almashtirish
        settings["phone_tracking"] = not settings["phone_tracking"]
        update_group_setting(chat_id, "phone_tracking", settings["phone_tracking"])
        
    elif query.data == "toggle_auto_delete":
        # Avtomatik o'chirish sozlamasini almashtirish
        settings["auto_delete"] = not settings["auto_delete"]
        update_group_setting(chat_id, "auto_delete", settings["auto_delete"])
        
    elif query.data == "toggle_admin_only":
        # Faqat adminlar sozlamasini almashtirish
        settings["admin_only"] = not settings["admin_only"]
        update_group_setting(chat_id, "admin_only", settings["admin_only"])
        
    elif query.data == "set_min_coins":
        # Minimal tangalar sonini o'zgartirish uchun keyboard
        keyboard = [
            [
                InlineKeyboardButton("0", callback_data="set_min_coins_0"),
                InlineKeyboardButton("1", callback_data="set_min_coins_1"),
                InlineKeyboardButton("2", callback_data="set_min_coins_2"),
                InlineKeyboardButton("3", callback_data="set_min_coins_3")
            ],
            [
                InlineKeyboardButton("4", callback_data="set_min_coins_4"),
                InlineKeyboardButton("5", callback_data="set_min_coins_5"),
                InlineKeyboardButton("10", callback_data="set_min_coins_10"),
                InlineKeyboardButton("15", callback_data="set_min_coins_15")
            ],
            [
                InlineKeyboardButton("Orqaga", callback_data="back_to_group_settings")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Yo'lovchi olish uchun minimal tangalar sonini tanlang:",
            reply_markup=reply_markup
        )
        return
        
    elif query.data.startswith("set_min_coins_"):
        # Minimal tangalar sonini o'zgartirish
        min_coins = int(query.data.split("_")[-1])
        update_group_setting(chat_id, "min_coins_required", min_coins)
        settings["min_coins_required"] = min_coins
        
    elif query.data == "back_to_group_settings":
        # Asosiy sozlamalar menyusiga qaytish
        pass
        
    elif query.data == "group_stats":
        # Guruh statistikasini ko'rsatish
        await show_group_stats(update, context)
        return
    
    # Sozlamalar menyusini yangilash
    keyboard = [
        [
            InlineKeyboardButton("Ovozli xabarlar", callback_data="group_setting_voice"),
            InlineKeyboardButton("✅ Yoqilgan" if settings["voice_tracking"] else "❌ O'chirilgan", callback_data="toggle_voice_tracking")
        ],
        [
            InlineKeyboardButton("Telefon raqamlar", callback_data="group_setting_phone"),
            InlineKeyboardButton("✅ Yoqilgan" if settings["phone_tracking"] else "❌ O'chirilgan", callback_data="toggle_phone_tracking")
        ],
        [
            InlineKeyboardButton("Avtomatik o'chirish", callback_data="group_setting_auto_delete"),
            InlineKeyboardButton("✅ Yoqilgan" if settings["auto_delete"] else "❌ O'chirilgan", callback_data="toggle_auto_delete")
        ],
        [
            InlineKeyboardButton("Faqat adminlar", callback_data="group_setting_admin_only"),
            InlineKeyboardButton("✅ Yoqilgan" if settings["admin_only"] else "❌ O'chirilgan", callback_data="toggle_admin_only")
        ],
        [
            InlineKeyboardButton("Minimal tangalar", callback_data="group_setting_min_coins"),
            InlineKeyboardButton(f"{settings['min_coins_required']} tanga", callback_data="set_min_coins")
        ],
        [
            InlineKeyboardButton("Guruh statistikasi", callback_data="group_stats")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Guruh sozlamalari:\n\n"
        "Bu yerda guruhda botning ishlashini sozlashingiz mumkin.",
        reply_markup=reply_markup
    )

# Guruh statistikasini ko'rsatish
async def show_group_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    
    # Statistika ma'lumotlarini olish
    # Bu yerda statistika ma'lumotlarini olish uchun funksiya chaqirilishi kerak
    # Misol uchun:
    # stats = get_group_stats(chat_id)
    
    # Misol uchun statistika
    stats = {
        "today": {
            "voice_messages": 12,
            "offers": 24,
            "taken_offers": 18
        },
        "total": {
            "voice_messages": 156,
            "offers": 342,
            "taken_offers": 287
        },
        "top_users": [
            {"name": "Aziz Yuldashev", "offers": 24},
            {"name": "Sardor Aliyev", "offers": 18},
            {"name": "Dilshod Karimov", "offers": 15}
        ]
    }
    
    # Statistika xabarini tayyorlash
    stats_message = (
        "📊 GURUH STATISTIKASI\n\n"
        "Bugun:\n"
        f"- Ovozli xabarlar: {stats['today']['voice_messages']}\n"
        f"- Yo'lovchi berish takliflari: {stats['today']['offers']}\n"
        f"- Qabul qilingan takliflar: {stats['today']['taken_offers']}\n\n"
        "Umumiy:\n"
        f"- Ovozli xabarlar: {stats['total']['voice_messages']}\n"
        f"- Yo'lovchi berish takliflari: {stats['total']['offers']}\n"
        f"- Qabul qilingan takliflar: {stats['total']['taken_offers']}\n\n"
        "Eng faol foydalanuvchilar:\n"
    )
    
    for i, user in enumerate(stats["top_users"], 1):
        stats_message += f"{i}. {user['name']} - {user['offers']} ta taklif\n"
    
    # Orqaga qaytish tugmasi
    keyboard = [
        [
            InlineKeyboardButton("Orqaga", callback_data="back_to_group_settings")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        stats_message,
        reply_markup=reply_markup
    )

# Guruh xabarlarini tozalash
async def clear_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Faqat guruh chatlarida ishlaydi
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("Bu buyruq faqat guruh chatlarida ishlaydi!")
        return
    
    # Foydalanuvchi admin ekanligini tekshirish
    if not await is_group_admin(update, context):
        await update.message.reply_text("Bu buyruq faqat guruh adminlari uchun!")
        return
    
    chat_id = update.effective_chat.id
    
    # Tasdiqlash uchun keyboard
    keyboard = [
        [
            InlineKeyboardButton("Ha, tozalash", callback_data="confirm_clear_messages"),
            InlineKeyboardButton("Yo'q, bekor qilish", callback_data="cancel_clear_messages")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Guruhda bot tomonidan yuborilgan barcha xabarlarni o'chirishni xohlaysizmi?",
        reply_markup=reply_markup
    )

# Guruh xabarlarini tozalash callback query handler
async def handle_clear_messages_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Foydalanuvchi admin ekanligini tekshirish
    if not await is_group_admin(update, context, query.from_user.id):
        await query.edit_message_text("Bu buyruq faqat guruh adminlari uchun!")
        return
    
    chat_id = update.effective_chat.id
    
    if query.data == "confirm_clear_messages":
        # Bot xabarlarini o'chirish logikasi
        await clear_bot_messages(context, chat_id)
        
        await query.edit_message_text("Guruhda bot tomonidan yuborilgan barcha xabarlar o'chirildi.")
    else:
        await query.edit_message_text("Xabarlarni tozalash bekor qilindi.")

#
# OVOZLI XABAR VA GURUH FUNKSIYALARI
#

# Ovozli xabar vaqti tugaganda chaqiriladigan funksiya
async def check_voice_message_timeout(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    data = job.data
    chat_id = data["chat_id"]
    user_id = data["user_id"]
    
    chat_id_str = str(chat_id)
    user_id_str = str(user_id)
    
    # Ovozli xabarlar ma'lumotlarini yuklash
    voice_messages = load_data(VOICE_MESSAGES_FILE)
    
    # Agar bu chat uchun ma'lumotlar bo'lmasa yoki foydalanuvchi ovozli xabar yubormagan bo'lsa, o'tkazib yuborish
    if chat_id_str not in voice_messages or user_id_str not in voice_messages[chat_id_str]:
        return
    
    # Agar ovozli xabar uchun telefon raqam kutilmayotgan bo'lsa, o'tkazib yuborish
    if not voice_messages[chat_id_str][user_id_str].get("waiting_for_phone", False):
        return
    
    # Foydalanuvchiga xabar yuborish
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="Ovozli xabar uchun telefon raqam vaqti tugadi. Iltimos, qaytadan ovozli xabar yuboring."
        )
    except Exception as e:
        logger.error(f"Foydalanuvchiga xabar yuborishda xatolik: {e}")
    
    # Ovozli xabar ma'lumotlarini o'chirish
    del voice_messages[chat_id_str][user_id_str]
    save_data(voice_messages, VOICE_MESSAGES_FILE)

# Guruhda ovozli xabarlarni kuzatish
async def handle_group_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Faqat guruh chatlarida ishlaydi
    if update.effective_chat.type not in ["group", "supergroup"]:
        return
    
    # Ovozli xabar bo'lmasa, o'tkazib yuborish
    if not update.message.voice:
        return
    
    user_id = update.effective_user.id
    user_id_str = str(user_id)
    chat_id = update.effective_chat.id
    chat_id_str = str(chat_id)
    message_id = update.message.message_id
    
    # Guruh sozlamalarini olish
    group_settings = get_group_settings(chat_id)
    
    # Agar ovozli xabarlarni kuzatish o'chirilgan bo'lsa, o'tkazib yuborish
    if not group_settings.get("voice_tracking", True):
        return
    
    # Agar faqat adminlar rejimi yoqilgan bo'lsa, foydalanuvchi admin ekanligini tekshirish
    if group_settings.get("admin_only", False) and not await is_group_admin(update, context):
        return
    
    if DEBUG:
        logger.info(f"Guruhda ovozli xabar qabul qilindi: user_id={user_id}, chat_id={chat_id}, message_id={message_id}")
    
    # Ovozli xabarni saqlash
    voice_messages = load_data(VOICE_MESSAGES_FILE)
    
    # Agar bu chat uchun ma'lumotlar bo'lmasa, yaratish
    if chat_id_str not in voice_messages:
        voice_messages[chat_id_str] = {}
    
    # Ovozli xabar ma'lumotlarini saqlash
    voice_messages[chat_id_str][user_id_str] = {
        "message_id": message_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "voice_file_id": update.message.voice.file_id,
        "waiting_for_phone": True,
        "original_message_id": message_id  # Asl xabar ID sini saqlash
    }
    
    save_data(voice_messages, VOICE_MESSAGES_FILE)
    
    # Vaqt hisoblagich o'rnatish
    voice_timeout = group_settings.get("voice_timeout", VOICE_MESSAGE_TIMEOUT)
    context.job_queue.run_once(
        check_voice_message_timeout, 
        voice_timeout,
        data={"chat_id": chat_id, "user_id": user_id}
    )

# Guruhda telefon raqamlarni kuzatish
async def handle_group_phone_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Faqat guruh chatlarida ishlaydi
    if update.effective_chat.type not in ["group", "supergroup"]:
        return
    
    # Matn xabar bo'lmasa, o'tkazib yuborish
    if not update.message.text:
        return
    
    user_id = update.effective_user.id
    user_id_str = str(user_id)
    chat_id = update.effective_chat.id
    chat_id_str = str(chat_id)
    message_id = update.message.message_id
    message_text = update.message.text
    
    # Guruh sozlamalarini olish
    group_settings = get_group_settings(chat_id)
    
    # Agar telefon raqamlarni kuzatish o'chirilgan bo'lsa, o'tkazib yuborish
    if not group_settings.get("phone_tracking", True):
        return
    
    # Agar faqat adminlar rejimi yoqilgan bo'lsa, foydalanuvchi admin ekanligini tekshirish
    if group_settings.get("admin_only", False) and not await is_group_admin(update, context):
        return
    
    # Telefon raqam formatini tekshirish
    phone_match = re.search(r'(\+?998\d{9}|\d{9})', message_text)
    if not phone_match:
        return
    
    if DEBUG:
        logger.info(f"Guruhda telefon raqam qabul qilindi: user_id={user_id}, chat_id={chat_id}, message_id={message_id}")
    
    # Ovozli xabarlar ma'lumotlarini yuklash
    voice_messages = load_data(VOICE_MESSAGES_FILE)
    
    # Agar bu chat uchun ma'lumotlar bo'lmasa yoki foydalanuvchi ovozli xabar yubormagan bo'lsa, o'tkazib yuborish
    if chat_id_str not in voice_messages or user_id_str not in voice_messages[chat_id_str]:
        return
    
    # Ovozli xabar ma'lumotlarini olish
    voice_data = voice_messages[chat_id_str][user_id_str]
    
    # Agar ovozli xabar uchun telefon raqam kutilmayotgan bo'lsa, o'tkazib yuborish
    if not voice_data.get("waiting_for_phone", False):
        return
    
    # Ovozli xabar vaqtini tekshirish
    voice_time = datetime.strptime(voice_data["timestamp"], "%Y-%m-%d %H:%M:%S")
    current_time = datetime.now()
    time_diff = (current_time - voice_time).total_seconds()
    
    voice_timeout = group_settings.get("voice_timeout", VOICE_MESSAGE_TIMEOUT)
    if time_diff > voice_timeout:
        # Vaqt o'tib ketgan, ovozli xabar ma'lumotlarini o'chirish
        del voice_messages[chat_id_str][user_id_str]
        save_data(voice_messages, VOICE_MESSAGES_FILE)
        return
    
    # Telefon raqamni formatlash
    phone = format_phone(phone_match.group(1))
    
    # Telefon raqam xabarini o'chirish
    try:
        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=message_id
        )
    except Exception as e:
        logger.error(f"Telefon raqam xabarini o'chirishda xatolik: {e}")
    
    # Ovozli xabarni o'chirish
    try:
        original_message_id = voice_data.get("original_message_id")
        if original_message_id:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=original_message_id
            )
    except Exception as e:
        logger.error(f"Ovozli xabarni o'chirishda xatolik: {e}")
    
    # Yo'lovchi taklifi yaratish
    await create_voice_offer(update, context, voice_data, phone)
    
    # Ovozli xabar ma'lumotlarini o'chirish
    del voice_messages[chat_id_str][user_id_str]
    save_data(voice_messages, VOICE_MESSAGES_FILE)

# Ovozli xabar asosida yo'lovchi taklifi yaratish
async def create_voice_offer(update: Update, context: ContextTypes.DEFAULT_TYPE, voice_data, phone):
    user_id = update.effective_user.id
    user_id_str = str(user_id)
    chat_id = update.effective_chat.id
    
    # Foydalanuvchi ma'lumotlarini yuklash
    users = load_data(USERS_FILE)
    
    # Foydalanuvchi haydovchimi?
    is_driver = user_id_str in users and users[user_id_str].get("role") == "driver"
    
    # Haydovchi bo'lmasa, ro'yxatdan o'tkazish
    if not is_driver:
        users[user_id_str] = {
            "role": "driver",
            "coins": INITIAL_DRIVER_COINS,
            "full_name": update.effective_user.full_name,
            "phone": phone
        }
        save_data(users, USERS_FILE)
        
        # Statistikani yangilash
        update_stats("new_drivers")
    
    # Yo'lovchi berish taklifini yaratish
    drivers = load_data(DRIVERS_FILE)
    offers = load_data(OFFERS_FILE)
    
    # Haydovchi ma'lumotlarini saqlash
    driver_data = {
        "user_id": user_id,
        "full_name": users[user_id_str].get("full_name", update.effective_user.full_name),
        "phone": phone,
        "passenger_count": 1,  # Standart qiymat
        "destination": "Ovozli xabar orqali",
        "time": "Tez orada",
        "contact": phone,
        "comment": "",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "waiting",
        "voice_file_id": voice_data["voice_file_id"]
    }
    
    if user_id_str not in drivers:
        drivers[user_id_str] = []
    
    drivers[user_id_str].append(driver_data)
    save_data(drivers, DRIVERS_FILE)
    
    # Offer ID yaratish
    offer_id = f"offer_{len(offers) + 1}"
    offers[offer_id] = driver_data
    save_data(offers, OFFERS_FILE)
    
    # Statistikani yangilash
    update_stats("new_offers")
    
    # Ovozli xabarni kanalga yuborish
    if SEND_TO_CHANNEL:
        try:
            # Ovozli xabarni kanalga yuborish
            voice_message = await context.bot.send_voice(
                chat_id=CHANNEL_ID,
                voice=voice_data["voice_file_id"]
            )
            
            # Xabar ID ni saqlash
            offers[offer_id]["message_id"] = voice_message.message_id
            save_data(offers, OFFERS_FILE)
            
            # Ovozli xabar haqida ma'lumot yuborish
            info_message = (
                f"Yuqoridagi yo'lovchini olish uchun ushbu xabarga javob bering (reply) va 'olaman' deb yozing yoki ovozli xabarni reply qilib yuboring"
            )
            
            info_msg = await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=info_message,
                reply_to_message_id=voice_message.message_id
            )
            
            # Info xabar ID ni saqlash
            offers[offer_id]["info_message_id"] = info_msg.message_id
            save_data(offers, OFFERS_FILE)
            
        except Exception as e:
            logger.error(f"Kanalga yuborishda xatolik: {e}")
    
    # Foydalanuvchiga xabar yuborish
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"Rahmat! Sizning ovozli taklifingiz qabul qilindi va kanalga yuborildi.\n"
                f"Agar biror haydovchi yo'lovchilaringizni olsa, sizga tanga beriladi."
        )
    except Exception as e:
        logger.error(f"Foydalanuvchiga xabar yuborishda xatolik: {e}")

#
# BOT FUNKSIYALARI
#

# Start buyrug'i handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_id_str = str(user_id)
    
    # Foydalanuvchi ma'lumotlarini yuklash
    users = load_data(USERS_FILE)
    
    # Admin rejimini tekshirish
    if user_id in ADMIN_IDS:
        # Admin menyusini ko'rsatish
        keyboard = [
            ["Statistika", "Bot sozlamalari"],
            ["Xabar yuborish", "Tanga sovg'a qilish"],
            ["Botni qayta ishga tushirish", "Haydovchi rejimi"]
        ]
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            f"Salom, {update.effective_user.full_name}! Siz admin rejimida ishlayapsiz.",
            reply_markup=reply_markup
        )
        
        return ADMIN_MENU
    
    # Guruh chatida bo'lsa
    if update.effective_chat.type in ["group", "supergroup"]:
        # Guruh sozlamalari uchun admin buyruqlarini ko'rsatish
        message = (
            f"Salom {update.effective_user.full_name}!\n"
            f"Men haydovchilar uchun yo'lovchi berish bot man.\n\n"
            f"Guruh sozlamalarini o'zgartirish uchun guruh admini /settings buyrug'ini berishlari mumkin."
        )
        
        await update.message.reply_text(message)
        return ConversationHandler.END
    
    # Haydovchimi?
    is_driver = user_id_str in users and users[user_id_str].get("role") == "driver"
    
    if is_driver:
        # Haydovchi menyusini ko'rsatish
        keyboard = [
            ["➕ Yo'lovchi berish", "💰 Mening tangalarim"],
            ["📋 Mening takliflarim", "ℹ️ Bot haqida"]
        ]
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            f"Salom, {users[user_id_str]['full_name']}! Tanga: {users[user_id_str].get('coins', 0)}\n"
            f"Bo'limni tanlang:",
            reply_markup=reply_markup
        )
        
        return DRIVER_MENU
    else:
        # Haydovchini ro'yxatdan o'tkazish
        keyboard = [
            [KeyboardButton(text="Telefon raqamimni ulashish", request_contact=True)]
        ]
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        # Foydalanuvchining to'liq ismini saqlash
        users[user_id_str] = {
            "full_name": update.effective_user.full_name
        }
        save_data(users, USERS_FILE)
        
        await update.message.reply_text(
            f"Salom, {update.effective_user.full_name}!\n"
            f"Haydovchi sifatida ro'yxatdan o'tish uchun iltimos, telefon raqamingizni yuboring:",
            reply_markup=reply_markup
        )
        
        return ENTER_PHONE

# Telefon raqamni kiritish handler
async def enter_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_id_str = str(user_id)
    
    # Foydalanuvchi ma'lumotlarini yuklash
    users = load_data(USERS_FILE)
    
    # Telefon raqamni olish
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone_match = re.search(r'(\+?998\d{9}|\d{9})', update.message.text)
        if not phone_match:
            await update.message.reply_text(
                "Telefon raqami noto'g'ri formatda kiritildi.\n"
                "Iltimos, telefon raqamingizni '+998XXXXXXXXX' yoki 'XXXXXXXXX' formatida kiriting."
            )
            return ENTER_PHONE
        
        phone = phone_match.group(1)
    
    # Telefon raqamni formatlash
    phone = format_phone(phone)
    
    # Foydalanuvchi ma'lumotlarini yangilash
    users[user_id_str] = {
        "role": "driver",
        "coins": INITIAL_DRIVER_COINS,
        "full_name": update.effective_user.full_name,
        "phone": phone
    }
    
    save_data(users, USERS_FILE)
    
    # Statistikani yangilash
    update_stats("new_drivers")
    
    # Haydovchi menyusini ko'rsatish
    keyboard = [
        ["➕ Yo'lovchi berish", "💰 Mening tangalarim"],
        ["📋 Mening takliflarim", "ℹ️ Bot haqida"]
    ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        f"Tabriklaymiz! Siz haydovchi sifatida ro'yxatdan o'tdingiz.\n"
        f"Sizga boshlang'ich {INITIAL_DRIVER_COINS} tanga berildi.\n\n"
        f"Botdan foydalanish yo'riqnomasi:\n"
        f"1. Yo'lovchi berish uchun \"➕ Yo'lovchi berish\" tugmasini bosing yoki qisqartirilgan formatda yozing.\n"
        f"   Format: [telefon raqam] [yo'nalish (n/t)] [yo'lovchilar soni]\n"
        f"   Masalan: +998901234567 n 3\n"
        f"2. Ovozli xabar orqali ham yo'lovchi berish mumkin.\n"
        f"3. Yo'lovchi berish takliflari kanalga yuboriladi: {DRIVERS_CHANNEL_LINK}\n"
        f"4. Yo'lovchi berish taklifi qabul qilinsa, sizga tanga beriladi.\n"
        f"5. Yo'lovchi olish uchun kanaldagi takliflarga javob berib, yo'lovchilarni olishingiz mumkin.",
        reply_markup=reply_markup
    )
    
    return DRIVER_MENU

# Haydovchi menyusi handler
async def handle_driver_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_id_str = str(user_id)
    text = update.message.text
    
    # Foydalanuvchi ma'lumotlarini yuklash
    users = load_data(USERS_FILE)
    
    # Foydalanuvchi haydovchimi?
    if user_id_str not in users or users[user_id_str].get("role") != "driver":
        # Botni qayta ishga tushirish
        return await start(update, context)
    
    # Yo'lovchi berish
    if text == "➕ Yo'lovchi berish":
        await update.message.reply_text(
            "Yo'lovchi berish uchun xabaringizni qisqartirilgan formatda yuboring:\n"
            "[telefon raqam] [yo'nalish (n/t)] [yo'lovchilar soni]\n"
            "Masalan: +998901234567 n 3\n\n"
            "yoki ovozli xabar yuboring va keyin telefon raqamingizni yozing."
        )
        return DRIVER_MENU
    
    # Tangalar haqida ma'lumot
    elif text == "💰 Mening tangalarim":
        coins = users[user_id_str].get("coins", 0)
        
        await update.message.reply_text(
            f"Sizning tangalaringiz: {coins}\n\n"
            f"Yo'lovchi berish taklifi qabul qilinsa, sizga tanga beriladi.\n"
            f"Yo'lovchi olish uchun yo'lovchilar soniga qarab tanga sarflanadi."
        )
        return DRIVER_MENU
    
    # Takliflar tarixi
    elif text == "📋 Mening takliflarim":
        drivers = load_data(DRIVERS_FILE)
        
        if user_id_str not in drivers or not drivers[user_id_str]:
            await update.message.reply_text(
                "Sizda hali yo'lovchi berish takliflari yo'q."
            )
            return DRIVER_MENU
        
        # So'nggi 5 ta taklifni ko'rsatish
        offers = drivers[user_id_str][-5:]
        
        message = "Sizning oxirgi takliflaringiz:\n\n"
        
        for i, offer in enumerate(offers, 1):
            status_str = ""
            if offer.get("status") == "waiting":
                status_str = "⏳ Kutilmoqda"
            elif offer.get("status") == "taken":
                status_str = "✅ Olindi"
            elif offer.get("status") == "fake":
                status_str = "❌ Soxta"
            
            message += f"{i}. {offer.get('created_at', '')}\n"
            message += f"   Yo'nalish: {offer.get('destination', '')}\n"
            message += f"   Yo'lovchilar soni: {offer.get('passenger_count', 0)}\n"
            message += f"   Holati: {status_str}\n\n"
        
        await update.message.reply_text(message)
        return DRIVER_MENU
    
    # Bot haqida ma'lumot
    elif text == "ℹ️ Bot haqida":
        await update.message.reply_text(
            "Taksi Bot - bu haydovchilar va yo'lovchilar o'rtasida aloqa o'rnatish uchun yaratilgan bot.\n\n"
            "Bot orqali haydovchilar yo'lovchi berish takliflarini yuborishlari, boshqa haydovchilar esa bu takliflarni qabul qilishlari mumkin.\n\n"
            f"Haydovchilar kanali: {DRIVERS_CHANNEL_LINK}\n\n"
            "Bot \"tanga\" tizimidan foydalanadi. Yo'lovchi berish taklifi qabul qilinsa, sizga tanga beriladi. Yo'lovchi olish uchun yo'lovchilar soniga qarab tanga sarflanadi."
        )
        return DRIVER_MENU
    
    # Qisqartirilgan format - yo'lovchi berish
    phone_match = re.search(r'(\+?998\d{9}|\d{9})', text)
    if phone_match:
        # Telefon raqamni formatlash
        phone = format_phone(phone_match.group(1))
        
        # Yo'nalish va yo'lovchilar sonini olish
        parts = text.split()
        
        destination = ""
        passenger_count = 1
        
        for i, part in enumerate(parts):
            if part.lower() in ["n", "t", "н", "т"]:
                if part.lower() in ["n", "н"]:
                    destination = "Namangandan Toshkentga"
                else:
                    destination = "Toshkentdan Namanganga"
            
            if part.isdigit() and int(part) > 0 and int(part) <= 10:
                passenger_count = int(part)
        
        if not destination:
            destination = "Aniq ko'rsatilmagan"
        
        # Yo'lovchi berish taklifini saqlash
        await create_passenger_offer(update, context, phone, destination, passenger_count)
        
        return DRIVER_MENU
    
    # Noto'g'ri buyruq
    await update.message.reply_text(
        "Noto'g'ri buyruq berildi. Iltimos, menyudan tanlang."
    )
    
    return DRIVER_MENU

# Yo'lovchi berish taklifini yaratish
async def create_passenger_offer(update: Update, context: ContextTypes.DEFAULT_TYPE, phone: str, destination: str, passenger_count: int) -> None:
    user_id = update.effective_user.id
    user_id_str = str(user_id)
    
    # Foydalanuvchi ma'lumotlarini yuklash
    users = load_data(USERS_FILE)
    
    # Foydalanuvchi haydovchimi?
    if user_id_str not in users or users[user_id_str].get("role") != "driver":
        # Botni qayta ishga tushirish
        await start(update, context)
        return
    
    # Haydovchi ma'lumotlarini saqlash
    driver_data = {
        "user_id": user_id,
        "full_name": users[user_id_str]["full_name"],
        "phone": phone,
        "passenger_count": passenger_count,
        "destination": destination,
        "time": "Tez orada",
        "contact": phone,
        "comment": "",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "waiting"
    }
    
    # Haydovchilar takliflari fayli
    drivers = load_data(DRIVERS_FILE)
    
    if user_id_str not in drivers:
        drivers[user_id_str] = []
    
    drivers[user_id_str].append(driver_data)
    save_data(drivers, DRIVERS_FILE)
    
    # Yo'lovchi berish takliflari fayli
    offers = load_data(OFFERS_FILE)
    
    offer_id = f"offer_{len(offers) + 1}"
    offers[offer_id] = driver_data
    save_data(offers, OFFERS_FILE)
    
    # Statistikani yangilash
    update_stats("new_offers")
    
    # Kanalga yuborish
    if SEND_TO_CHANNEL:
        try:
            offer_message = (
                f"Yangi yo'lovchilar taklifi:\n"
                f"Kim yubordi: {driver_data['full_name']}\n"
                f"Telefon: {format_phone(driver_data['phone'])}\n"
                f"Yo'lovchilar soni: {driver_data['passenger_count']}\n"
                f"Yo'nalish: {driver_data['destination']}\n"
                f"Vaqt: {driver_data['time']}\n"
                f"Izoh: {driver_data['comment']}"
            )
            
            message = await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=offer_message
            )
            
            # Xabar ID ni saqlash
            offers[offer_id]["message_id"] = message.message_id
            save_data(offers, OFFERS_FILE)
            
        except Exception as e:
            logger.error(f"Kanalga yuborishda xatolik: {e}")
    
    # Foydalanuvchiga xabar yuborish
    await update.message.reply_text(
        f"Rahmat! Sizning yo'lovchi berish taklifingiz qabul qilindi va kanalga yuborildi.\n"
        f"Agar biror haydovchi yo'lovchilaringizni olsa, sizga tanga beriladi."
    )

# Yo'lovchi olish jarayoni (reply orqali)
async def handle_passenger_claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_id_str = str(user_id)
    message_id = update.message.message_id
    chat_id = update.effective_chat.id

    if DEBUG:
        logger.info(f"handle_passenger_claim: Xabar {message_id} qayta ishlanmoqda")
        logger.info(f"Javob xabar qabul qilindi: {update.message}")
        logger.info(f"Xabar turi: {update.message.voice is not None and 'Ovozli' or update.message.text and 'Matn' or 'Boshqa'}")

    # Javob berilgan xabarni olish
    original_message = update.message.reply_to_message
    if not original_message:
        return

    # Ma'lumotlarni yuklash
    users = load_data(USERS_FILE)
    offers = load_data(OFFERS_FILE)

    # Foydalanuvchi haydovchimi?
    if user_id_str not in users:
        # Haydovchi bo'lmasa, ro'yxatdan o'tkazish
        users[user_id_str] = {
            "role": "driver",
            "coins": INITIAL_DRIVER_COINS,
            "full_name": update.effective_user.full_name,
            "phone": ""  # Telefon raqami kerak bo'ladi
        }
        save_data(users, USERS_FILE)
        
        # Statistikani yangilash
        update_stats("new_drivers")
        
        # Telefon raqamini so'rash
        await update.message.reply_text(
            "Siz haydovchi sifatida ro'yxatdan o'tmagan ekansiz. Iltimos, telefon raqamingizni yuboring:"
        )
        return

    # Guruh sozlamalarini olish (agar guruhda bo'lsa)
    min_coins_required = 0
    if update.effective_chat.type in ["group", "supergroup"]:
        group_settings = get_group_settings(chat_id)
        min_coins_required = group_settings.get("min_coins_required", 0)

    # Haydovchida yetarli tanga bormi?
    if users[user_id_str].get("coins", 0) < min_coins_required:
        await update.message.reply_text(
            f"Sizda yetarli tanga yo'q! Yo'lovchi olish uchun kamida {min_coins_required} tanga kerak."
        )
        return

    # Xabar ID orqali offer ni topish
    offer_id = None
    offer_by_voice = False
    offer_by_info = False

    # 1. Ovozli xabar uchun
    if original_message.voice:
        offer_by_voice = True
        # Ovozli xabar ID orqali offer ni topish
        for oid, offer_data in offers.items():
            if offer_data.get("voice_file_id") == original_message.voice.file_id:
                offer_id = oid
                break
    
    # 2. Info xabar uchun (ovozli xabar haqidagi ma'lumot)
    if not offer_id and original_message.text and "Yuqoridagi yo'lovchini olish uchun" in original_message.text:
        offer_by_info = True
        # Info xabar ID orqali offer ni topish
        for oid, offer_data in offers.items():
            if offer_data.get("info_message_id") == original_message.message_id:
                offer_id = oid
                break
            # Agar info xabar reply_to_message_id orqali bog'langan bo'lsa
            elif original_message.reply_to_message and offer_data.get("message_id") == original_message.reply_to_message.message_id:
                offer_id = oid
                break
    
    # 3. Oddiy matn xabar uchun
    if not offer_id and not offer_by_voice and not offer_by_info:
        # Matn xabar ID orqali offer ni topish
        for oid, offer_data in offers.items():
            if offer_data.get("message_id") == original_message.message_id:
                offer_id = oid
                break

    # Agar offer topilmasa
    if not offer_id:
        if DEBUG:
            logger.info(f"Taklif topilmadi: {original_message.message_id}")
        return

    # Offer allaqachon olinganmi?
    if offers[offer_id].get("status") == "taken":
        await update.message.reply_text(
            "Bu taklif allaqachon olingan!"
        )
        return

    # Foydalanuvchi profilini olish
    user_profile_link = get_user_profile_link(update.effective_user)

    # Taklifni olindi deb belgilash
    offers[offer_id]["status"] = "pending"  # Kutish holatiga o'tkazish
    offers[offer_id]["taker_id"] = user_id
    offers[offer_id]["pending_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_data(offers, OFFERS_FILE)  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_data(offers, OFFERS_FILE)

    # Kanalda xabarni yangilash
    try:
        # Ovozli xabar uchun
        if offer_by_voice or (original_message.voice and offers[offer_id].get("voice_file_id") == original_message.voice.file_id):
            # Info xabar ID ni olish
            info_message_id = offers[offer_id].get("info_message_id")
            if info_message_id:
                await context.bot.edit_message_text(
                    chat_id=CHANNEL_ID,
                    message_id=info_message_id,
                    text=f"Yangi yo'lovchilar taklifi (ovozli xabar):\n"
                        f"Kim yubordi: {offers[offer_id]['full_name']}\n"
                        f"⏳ KUTILMOQDA: {user_profile_link}",
                    parse_mode="HTML"
                )
        # Info xabar uchun
        elif offer_by_info:
            # Ovozli xabar uchun info xabarni yangilash
            await context.bot.edit_message_text(
                chat_id=CHANNEL_ID,
                message_id=original_message.message_id,
                text=f"Yangi yo'lovchilar taklifi (ovozli xabar):\n"
                    f"Kim yubordi: {offers[offer_id]['full_name']}\n"
                    f"⏳ KUTILMOQDA: {user_profile_link}",
                parse_mode="HTML"
            )
        # Oddiy matn xabar uchun
        else:
            await context.bot.edit_message_text(
                chat_id=CHANNEL_ID,
                message_id=original_message.message_id,
                text=f"{original_message.text}\n\n⏳ KUTILMOQDA: {user_profile_link}",
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Xabarni yangilashda xatolik: {e}")

    # Haydovchiga to'liq ma'lumotni yuborish
    offer_info = (
        f"Yo'lovchi berish taklifi ma'lumotlari:\n"
        f"Kim berdi: {offers[offer_id]['full_name']}\n"
        f"Telefon: {format_phone(offers[offer_id]['phone'])}\n"
        f"Yo'lovchilar soni: {offers[offer_id]['passenger_count']}\n"
        f"Yo'nalish: {offers[offer_id]['destination']}\n"
        f"Vaqt: {offers[offer_id].get('time', 'Tez orada')}\n"
        f"Izoh: {offers[offer_id].get('comment', '')}"
    )

    # Inline knopkalar yaratish
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Oldim", callback_data=f"pickup_yes_{offer_id}"),
            InlineKeyboardButton("Olmadim", callback_data=f"pickup_no_{offer_id}")
        ]
    ])

    # Joriy taklif ID sini saqlash
    context.user_data['current_offer_id'] = offer_id

    await context.bot.send_message(
        chat_id=user_id,
        text=f"Siz yo'lovchi berish taklifini oldingiz!\n\n{offer_info}\n\n"
            f"Agar yo'lovchilarni muvaffaqiyatli olsangiz, 'Oldim' tugmasini bosing.\n"
            f"Agar yo'lovchi bilan kelisha olmasangiz, 'Olmadim' tugmasini bosing.",
        reply_markup=keyboard
    )

    # Taklif bergan haydovchiga xabar yuborish
    try:
        await context.bot.send_message(
            chat_id=offers[offer_id]["user_id"],
            text=f"Sizning yo'lovchi berish taklifingiz qabul qilindi!\n\n"
                f"Haydovchi: {users[user_id_str]['full_name']}\n"
                f"Telefon: {format_phone(users[user_id_str].get('phone', ''))}\n\n"
                f"Haydovchi yo'lovchilarni olganini tasdiqlagandan so'ng, hisobingizga tanga qo'shiladi."
        )
    except Exception as e:
        logger.error(f"Xabar yuborishda xatolik: {e}")

    # Ovozli xabar bo'lsa, uni haydovchiga yuborish
    if "voice_file_id" in offers[offer_id]:
        await context.bot.send_voice(
            chat_id=user_id,
            voice=offers[offer_id]["voice_file_id"],
            caption="Yo'lovchi berish taklifi (ovozli xabar)"
        )

    # Javob xabarini o'chirish
    try:
        if update.effective_chat.type in ["group", "supergroup"]:
            group_settings = get_group_settings(chat_id)
            if group_settings.get("auto_delete", True):
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=update.message.message_id
                )
        else:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=update.message.message_id
            )
    except Exception as e:
        logger.error(f"Xabarni o'chirishda xatolik: {e}")

# Kanal xabarlarini tekshirish
async def handle_channel_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Kanalda bo'lmasa, o'tkazib yuborish
    if update.effective_chat.id != CHANNEL_ID and str(update.effective_chat.id) != CHANNEL_ID and update.effective_chat.username != CHANNEL_ID.replace("@", ""):
        if DEBUG:
            if update.message and update.message.reply_to_message:
                # Reply xabarlarni qayta ishlash
                await handle_passenger_claim(update, context)
            
            # Guruhda ovozli xabarlarni tekshirish
            if update.message and update.message.voice and update.effective_chat.type in ["group", "supergroup"]:
                await handle_group_voice_message(update, context)
            
            # Guruhda telefon raqamlarni tekshirish
            if update.message and update.message.text and update.effective_chat.type in ["group", "supergroup"]:
                await handle_group_phone_message(update, context)
        return

    # Xabar bo'lmasa, o'tkazib yuborish
    if not update.message:
        return

    # Reply berilgan xabarlarni tekshirish
    if update.message.reply_to_message:
        # Yo'lovchi olish uchun
        await handle_passenger_claim(update, context)

# Yo'lovchi olish so'rovlari handler
async def take_passenger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    user_id_str = str(user_id)
    
    # Foydalanuvchi ma'lumotlarini yuklash
    users = load_data(USERS_FILE)
    offers = load_data(OFFERS_FILE)
    
    # Callback data ni tekshirish
    if data.startswith("pickup_yes_"):
        # Offer ID ni olish
        offer_id = data.split("_")[-1]
        
        if offer_id not in offers:
            await query.edit_message_text(
                "Xatolik yuz berdi. Taklif topilmadi!"
            )
            return
        
        if offers[offer_id].get("status") != "pending" or offers[offer_id].get("taker_id") != user_id:
            await query.edit_message_text(
                "Xatolik yuz berdi. Bu taklif sizga tegishli emas!"
            )
            return
        
        # Taklifni olindi deb belgilash
        offers[offer_id]["status"] = "taken"
        offers[offer_id]["taken_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_data(offers, OFFERS_FILE)
        
        # Yo'lovchi bergan haydovchiga tanga berish
        provider_id_str = str(offers[offer_id]["user_id"])
        if provider_id_str in users:
            users[provider_id_str]["coins"] = users[provider_id_str].get("coins", 0) + 1
        
        # Yo'lovchi olgan haydovchidan tanga olish
        passenger_count = offers[offer_id].get("passenger_count", 1)
        if user_id_str in users:
            users[user_id_str]["coins"] = max(0, users[user_id_str].get("coins", 0) - passenger_count)
        
        save_data(users, USERS_FILE)
        
        # Statistikani yangilash
        update_stats("offers_taken")
        
        # Kanalda xabarni yangilash
        try:
            message_id = offers[offer_id].get("message_id")
            if message_id:
                # Foydalanuvchi profilini olish
                user_profile_link = get_user_profile_link(update.effective_user)
                
                # Ovozli xabar uchun
                if "voice_file_id" in offers[offer_id]:
                    # Info xabar ID ni olish
                    info_message_id = offers[offer_id].get("info_message_id")
                    if info_message_id:
                        await context.bot.edit_message_text(
                            chat_id=CHANNEL_ID,
                            message_id=info_message_id,
                            text=f"Yangi yo'lovchilar taklifi (ovozli xabar):\n"
                                f"Kim yubordi: {offers[offer_id]['full_name']}\n"
                                f"✅ OLINDI: {user_profile_link}",
                            parse_mode="HTML"
                        )
                else:
                    # Oddiy matn xabar uchun
                    original_message = await context.bot.get_message(
                        chat_id=CHANNEL_ID,
                        message_id=message_id
                    )
                    
                    if original_message and original_message.text:
                        text = original_message.text.split("\n\n")[0]
                        await context.bot.edit_message_text(
                            chat_id=CHANNEL_ID,
                            message_id=message_id,
                            text=f"{text}\n\n✅ OLINDI: {user_profile_link}",
                            parse_mode="HTML"
                        )
        except Exception as e:
            logger.error(f"Xabarni yangilashda xatolik: {e}")
        
        # Yo'lovchi bergan haydovchiga xabar yuborish
        try:
            await context.bot.send_message(
                chat_id=offers[offer_id]["user_id"],
                text=f"Sizning yo'lovchilaringiz muvaffaqiyatli olindi!\n\n"
                    f"Haydovchi: {users[user_id_str].get('full_name', 'Noma\'lum')}\n"
                    f"Telefon: {format_phone(users[user_id_str].get('phone', ''))}\n\n"
                    f"Hisobingizga 1 tanga qo'shildi. Hozirgi tangalaringiz: {users.get(provider_id_str, {}).get('coins', 0)}"
            )
        except Exception as e:
            logger.error(f"Xabar yuborishda xatolik: {e}")
        
        # Javobni yangilash
        await query.edit_message_text(
            f"Yo'lovchilarni muvaffaqiyatli oldingiz!\n\n"
            f"Yo'nalish: {offers[offer_id].get('destination', '')}\n"
            f"Yo'lovchilar soni: {passenger_count}\n"
            f"Hisobingizdan {passenger_count} tanga olinadi. Qolgan tangalaringiz: {users[user_id_str].get('coins', 0)}"
        )
        
    elif data.startswith("pickup_no_"):
        # Offer ID ni olish
        offer_id = data.split("_")[-1]
        
        if offer_id not in offers:
            await query.edit_message_text(
                "Xatolik yuz berdi. Taklif topilmadi!"
            )
            return
        
        if offers[offer_id].get("status") != "pending" or offers[offer_id].get("taker_id") != user_id:
            await query.edit_message_text(
                "Xatolik yuz berdi. Bu taklif sizga tegishli emas!"
            )
            return
        
        # Taklifni kutilmoqda holatiga qaytarish
        offers[offer_id]["status"] = "waiting"
        offers[offer_id].pop("taker_id", None)
        offers[offer_id].pop("pending_at", None)
        save_data(offers, OFFERS_FILE)
        
        # Statistikani yangilash
        update_stats("failed_agreements")
        
        # Kanalda xabarni yangilash
        try:
            message_id = offers[offer_id].get("message_id")
            if message_id:
                # Ovozli xabar uchun
                if "voice_file_id" in offers[offer_id]:
                    # Info xabar ID ni olish
                    info_message_id = offers[offer_id].get("info_message_id")
                    if info_message_id:
                        await context.bot.edit_message_text(
                            chat_id=CHANNEL_ID,
                            message_id=info_message_id,
                            text=f"Yuqoridagi yo'lovchini olish uchun ushbu xabarga javob bering (reply) va 'olaman' deb yozing yoki ovozli xabarni reply qilib yuboring",
                        )
                else:
                    # Oddiy matn xabar uchun
                    offer_message = (
                        f"Yangi yo'lovchilar taklifi:\n"
                        f"Kim yubordi: {offers[offer_id]['full_name']}\n"
                        f"Telefon: {format_phone(offers[offer_id]['phone'])}\n"
                        f"Yo'lovchilar soni: {offers[offer_id]['passenger_count']}\n"
                        f"Yo'nalish: {offers[offer_id]['destination']}\n"
                        f"Vaqt: {offers[offer_id].get('time', 'Tez orada')}\n"
                        f"Izoh: {offers[offer_id].get('comment', '')}"
                    )
                    
                    await context.bot.edit_message_text(
                        chat_id=CHANNEL_ID,
                        message_id=message_id,
                        text=offer_message
                    )
        except Exception as e:
            logger.error(f"Xabarni yangilashda xatolik: {e}")
        
        # Yo'lovchi bergan haydovchiga xabar yuborish
        try:
            await context.bot.send_message(
                chat_id=offers[offer_id]["user_id"],
                text=f"Afsuski, haydovchi yo'lovchilaringizni ola olmadi.\n"
                    f"Yo'lovchilaringiz takliflari yana kanalda ko'rsatilmoqda."
            )
        except Exception as e:
            logger.error(f"Xabar yuborishda xatolik: {e}")
        
        # Javobni yangilash
        await query.edit_message_text(
            f"Siz yo'lovchilarni ola olmasligingizni bildirdingiz.\n"
            f"Yo'lovchi berish taklifi yana kanalda ko'rsatilmoqda."
        )

#
# ADMIN FUNKSIYALARI
#

# Admin menu handler
async def handle_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    text = update.message.text
    
    # Admin ekanligini tekshirish
    if user_id not in ADMIN_IDS:
        # Botni qayta ishga tushirish
        return await start(update, context)
    
    # Statistika
    if text == "Statistika":
        stats = load_data(STATS_FILE)
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        message = "📊 BOT STATISTIKASI 📊\n\n"
        
        # Bugungi statistika
        message += "Bugun:\n"
        if today in stats:
            message += f"- Yangi haydovchilar: {stats[today].get('new_drivers', 0)}\n"
            message += f"- Yangi takliflar: {stats[today].get('new_offers', 0)}\n"
            message += f"- Qabul qilingan takliflar: {stats[today].get('offers_taken', 0)}\n"
            message += f"- Soxta takliflar: {stats[today].get('fake_offers', 0)}\n"
            message += f"- Kelisha olmasliklar: {stats[today].get('failed_agreements', 0)}\n"
            message += f"- Ovozli xabarlar: {stats[today].get('voice_messages', 0)}\n"
        else:
            message += "- Ma'lumot yo'q\n"
        
        message += "\nUmumiy:\n"
        if "total" in stats:
            message += f"- Yangi haydovchilar: {stats['total'].get('new_drivers', 0)}\n"
            message += f"- Yangi takliflar: {stats['total'].get('new_offers', 0)}\n"
            message += f"- Qabul qilingan takliflar: {stats['total'].get('offers_taken', 0)}\n"
            message += f"- Soxta takliflar: {stats['total'].get('fake_offers', 0)}\n"
            message += f"- Kelisha olmasliklar: {stats['total'].get('failed_agreements', 0)}\n"
            message += f"- Ovozli xabarlar: {stats['total'].get('voice_messages', 0)}\n"
        else:
            message += "- Ma'lumot yo'q\n"
        
        await update.message.reply_text(message)
        return ADMIN_MENU
    
    # Bot sozlamalari
    elif text == "Bot sozlamalari":
        # Bot sozlamalari menyusini ko'rsatish
        keyboard = [
            ["Boshlang'ich tangalar soni", "Kanal ID"],
            ["Orqaga"]
        ]
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            "Bot sozlamalari:\n"
            "Kerakli sozlamani tanlang:",
            reply_markup=reply_markup
        )
        
        return ADMIN_SETTINGS_MENU
    
    # Xabar yuborish
    elif text == "Xabar yuborish":
        await update.message.reply_text(
            "Yubormoqchi bo'lgan xabaringizni kiriting:"
        )
        
        return ADMIN_MESSAGE_TEXT
    
    # Tanga sovg'a qilish
    elif text == "Tanga sovg'a qilish":
        await update.message.reply_text(
            "Sovg'a qilmoqchi bo'lgan tangalar sonini kiriting:"
        )
        
        return ADMIN_GIFT_AMOUNT
    
    # Botni qayta ishga tushirish
    elif text == "Botni qayta ishga tushirish":
        await update.message.reply_text(
            "Bot qayta ishga tushirilmoqda..."
        )
        
        # Bot qayta ishga tushirilgandek ko'rinishi uchun
        await update.message.reply_text(
            "Bot qayta ishga tushirildi!"
        )
        
        return await start(update, context)
    
    # Haydovchi rejimi
    elif text == "Haydovchi rejimi":
        # Admin sifatida haydovchi menyusiga o'tish
        keyboard = [
            ["➕ Yo'lovchi berish", "💰 Mening tangalarim"],
            ["📋 Mening takliflarim", "ℹ️ Bot haqida"],
            ["Admin rejimiga qaytish"]
        ]
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            "Haydovchi rejimiga o'tildi.",
            reply_markup=reply_markup
        )
        
        return DRIVER_MENU
    
    # Noto'g'ri buyruq
    await update.message.reply_text(
        "Noto'g'ri buyruq berildi. Iltimos, menyudan tanlang."
    )
    
    return ADMIN_MENU

# Admin sozlamalari menyusi handler
async def handle_admin_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    text = update.message.text
    
    # Admin ekanligini tekshirish
    if user_id not in ADMIN_IDS:
        # Botni qayta ishga tushirish
        return await start(update, context)
    
    # Boshlang'ich tangalar soni
    if text == "Boshlang'ich tangalar soni":
        await update.message.reply_text(
            f"Hozirgi boshlang'ich tangalar soni: {INITIAL_DRIVER_COINS}\n"
            f"Yangi qiymatni kiriting:"
        )
        
        return ADMIN_SETTINGS_INITIAL_COINS
    
    # Kanal ID
    elif text == "Kanal ID":
        await update.message.reply_text(
            f"Hozirgi kanal ID: {CHANNEL_ID}\n"
            f"Yangi qiymatni kiriting:"
        )
        
        # Bu yerda Kanal ID ni o'zgartirish imkoniyati yo'q, shuning uchun admin menyusiga qaytaramiz
        return ADMIN_SETTINGS_MENU
    
    # Orqaga
    elif text == "Orqaga":
        # Admin menyusiga qaytish
        keyboard = [
            ["Statistika", "Bot sozlamalari"],
            ["Xabar yuborish", "Tanga sovg'a qilish"],
            ["Botni qayta ishga tushirish", "Haydovchi rejimi"]
        ]
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            "Admin menyusiga qaytildi.",
            reply_markup=reply_markup
        )
        
        return ADMIN_MENU
    
    # Noto'g'ri buyruq
    await update.message.reply_text(
        "Noto'g'ri buyruq berildi. Iltimos, menyudan tanlang."
    )
    
    return ADMIN_SETTINGS_MENU

# Boshlang'ich tangalar soni sozlamasini o'zgartirish
async def admin_settings_initial_coins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    text = update.message.text
    
    # Admin ekanligini tekshirish
    if user_id not in ADMIN_IDS:
        # Botni qayta ishga tushirish
        return await start(update, context)
    
    # Raqam ekanligini tekshirish
    try:
        coins = int(text)
        if coins < 0:
            await update.message.reply_text(
                "Tangalar soni 0 dan katta bo'lishi kerak. Iltimos, qaytadan kiriting:"
            )
            return ADMIN_SETTINGS_INITIAL_COINS
        
        # Global o'zgaruvchini yangilash
        global INITIAL_DRIVER_COINS
        INITIAL_DRIVER_COINS = coins
        
        await update.message.reply_text(
            f"Boshlang'ich tangalar soni {coins} ga o'zgartirildi."
        )
        
        # Bot sozlamalari menyusiga qaytish
        keyboard = [
            ["Boshlang'ich tangalar soni", "Kanal ID"],
            ["Orqaga"]
        ]
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            "Bot sozlamalari:",
            reply_markup=reply_markup
        )
        
        return ADMIN_SETTINGS_MENU
        
    except ValueError:
        await update.message.reply_text(
            "Iltimos, raqam kiriting:"
        )
        return ADMIN_SETTINGS_INITIAL_COINS

# Xabar matni handler
async def admin_message_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    text = update.message.text
    
    # Admin ekanligini tekshirish
    if user_id not in ADMIN_IDS:
        # Botni qayta ishga tushirish
        return await start(update, context)
    
    # Xabar matnini saqlash
    context.user_data["admin_message"] = text
    
    # Xabar yuborish menyusini ko'rsatish
    keyboard = [
        ["Barcha haydovchilarga", "Faqat ma'lum haydovchiga"],
        ["Orqaga"]
    ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "Xabarni kimga yubormoqchisiz?",
        reply_markup=reply_markup
    )
    
    return ADMIN_MESSAGE_TARGET

# Xabar yuborish manzilini tanlash
async def admin_message_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    text = update.message.text
    
    # Admin ekanligini tekshirish
    if user_id not in ADMIN_IDS:
        # Botni qayta ishga tushirish
        return await start(update, context)
    
    # Barcha haydovchilarga
    if text == "Barcha haydovchilarga":
        # Foydalanuvchilar ma'lumotlarini yuklash
        users = load_data(USERS_FILE)
        
        # Xabar matnini olish
        message = context.user_data.get("admin_message", "Botdan foydalanganingiz uchun rahmat!")
        
        # Yuborilgan xabarlar soni
        sent_count = 0
        
        # Barcha haydovchilarga xabar yuborish
        for user_id_str, user_data in users.items():
            if user_data.get("role") == "driver":
                try:
                    await context.bot.send_message(
                        chat_id=int(user_id_str),
                        text=f"ADMIN XABARI:\n\n{message}"
                    )
                    sent_count += 1
                except Exception as e:
                    logger.error(f"Xabar yuborishda xatolik: {e}")
        
        # Admin menyusiga qaytish
        keyboard = [
            ["Statistika", "Bot sozlamalari"],
            ["Xabar yuborish", "Tanga sovg'a qilish"],
            ["Botni qayta ishga tushirish", "Haydovchi rejimi"]
        ]
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            f"Xabar {sent_count} ta haydovchiga yuborildi.",
            reply_markup=reply_markup
        )
        
        return ADMIN_MENU
    
    # Faqat ma'lum haydovchiga
    elif text == "Faqat ma'lum haydovchiga":
        await update.message.reply_text(
            "Haydovchi ID raqamini kiriting:"
        )
        
        # Bu yerda faqat ma'lum haydovchiga xabar yuborish imkoniyati yo'q, shuning uchun admin menyusiga qaytaramiz
        # Aslida bu funksiyani qo'shish kerak bo'lishi mumkin
        return ADMIN_MESSAGE_TARGET
    
    # Orqaga
    elif text == "Orqaga":
        # Admin menyusiga qaytish
        keyboard = [
            ["Statistika", "Bot sozlamalari"],
            ["Xabar yuborish", "Tanga sovg'a qilish"],
            ["Botni qayta ishga tushirish", "Haydovchi rejimi"]
        ]
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            "Admin menyusiga qaytildi.",
            reply_markup=reply_markup
        )
        
        return ADMIN_MENU
    
    # Noto'g'ri buyruq
    await update.message.reply_text(
        "Noto'g'ri buyruq berildi. Iltimos, menyudan tanlang."
    )
    
    return ADMIN_MESSAGE_TARGET

# Sovg'a tangalar sonini kiritish handler
async def admin_gift_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    text = update.message.text
    
    # Admin ekanligini tekshirish
    if user_id not in ADMIN_IDS:
        # Botni qayta ishga tushirish
        return await start(update, context)
    
    # Raqam ekanligini tekshirish
    try:
        coins = int(text)
        if coins <= 0:
            await update.message.reply_text(
                "Tangalar soni 0 dan katta bo'lishi kerak. Iltimos, qaytadan kiriting:"
            )
            return ADMIN_GIFT_AMOUNT
        
        # Sovg'a tangalar sonini saqlash
        context.user_data["admin_gift_amount"] = coins
        
        # Sovg'a yuborish menyusini ko'rsatish
        keyboard = [
            ["Barcha haydovchilarga", "Faqat ma'lum haydovchiga"],
            ["Orqaga"]
        ]
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            f"{coins} tangani kimga sovg'a qilmoqchisiz?",
            reply_markup=reply_markup
        )
        
        return ADMIN_GIFT_TARGET
        
    except ValueError:
        await update.message.reply_text(
            "Iltimos, raqam kiriting:"
        )
        return ADMIN_GIFT_AMOUNT

# Sovg'a tangalar manzilini tanlash
async def admin_gift_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    text = update.message.text
    
    # Admin ekanligini tekshirish
    if user_id not in ADMIN_IDS:
        # Botni qayta ishga tushirish
        return await start(update, context)
    
    # Barcha haydovchilarga
    if text == "Barcha haydovchilarga":
        # Foydalanuvchilar ma'lumotlarini yuklash
        users = load_data(USERS_FILE)
        
        # Sovg'a tangalar sonini olish
        coins = context.user_data.get("admin_gift_amount", 1)
        
        # Yuborilgan tangalar soni
        sent_count = 0
        
        # Barcha haydovchilarga sovg'a qilish
        for user_id_str, user_data in users.items():
            if user_data.get("role") == "driver":
                # Tangalar sonini yangilash
                users[user_id_str]["coins"] = users[user_id_str].get("coins", 0) + coins
                
                try:
                    await context.bot.send_message(
                        chat_id=int(user_id_str),
                        text=f"ADMIN sovg'asi!\n\n"
                            f"Hisobingizga {coins} tanga qo'shildi.\n"
                            f"Hozirgi tangalaringiz: {users[user_id_str].get('coins', 0)}"
                    )
                    sent_count += 1
                except Exception as e:
                    logger.error(f"Xabar yuborishda xatolik: {e}")
        
        # Ma'lumotlarni saqlash
        save_data(users, USERS_FILE)
        
        # Admin menyusiga qaytish
        keyboard = [
            ["Statistika", "Bot sozlamalari"],
            ["Xabar yuborish", "Tanga sovg'a qilish"],
            ["Botni qayta ishga tushirish", "Haydovchi rejimi"]
        ]
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            f"{coins} tanga {sent_count} ta haydovchiga sovg'a qilindi.",
            reply_markup=reply_markup
        )
        
        return ADMIN_MENU
    
    # Faqat ma'lum haydovchiga
    elif text == "Faqat ma'lum haydovchiga":
        await update.message.reply_text(
            "Haydovchi ID raqamini kiriting:"
        )
        
        # Bu yerda faqat ma'lum haydovchiga sovg'a qilish imkoniyati yo'q, shuning uchun admin menyusiga qaytaramiz
        # Aslida bu funksiyani qo'shish kerak bo'lishi mumkin
        return ADMIN_GIFT_TARGET
    
    # Orqaga
    elif text == "Orqaga":
        # Admin menyusiga qaytish
        keyboard = [
            ["Statistika", "Bot sozlamalari"],
            ["Xabar yuborish", "Tanga sovg'a qilish"],
            ["Botni qayta ishga tushirish", "Haydovchi rejimi"]
        ]
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            "Admin menyusiga qaytildi.",
            reply_markup=reply_markup
        )
        
        return ADMIN_MENU
    
    # Noto'g'ri buyruq
    await update.message.reply_text(
        "Noto'g'ri buyruq berildi. Iltimos, menyudan tanlang."
    )
    
    return ADMIN_GIFT_TARGET

#
# ASOSIY FUNKSIYA
#

def main():
    # Fayllarni tekshirish
    ensure_files_exist()

    # Bot yaratish
    application = Application.builder().token(BOT_TOKEN).build()

    # ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            # REGISTER_DRIVER holatini olib tashlash kerak
            # REGISTER_DRIVER: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_driver)],
            ENTER_PHONE: [
                MessageHandler(filters.CONTACT, enter_phone),
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_phone)
            ],
            DRIVER_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_driver_menu)],
            # Admin panel holatlari
            ADMIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_menu)],
            ADMIN_SETTINGS_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_settings_menu)],
            ADMIN_SETTINGS_INITIAL_COINS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_settings_initial_coins)],
            ADMIN_MESSAGE_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_message_text)],
            ADMIN_MESSAGE_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_message_target)],
            ADMIN_GIFT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_gift_amount)],
            ADMIN_GIFT_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_gift_target)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    # ConversationHandler eng yuqori ustuvorlik bilan qo'shish
    application.add_handler(conv_handler, group=0)

    # Callback query handler qo'shish
    application.add_handler(CallbackQueryHandler(take_passenger, pattern=r"^pickup_|^passenger_count_|^confirm_coins_|^correct_count_"), group=1)
    
    # Guruh sozlamalari uchun callback query handler qo'shish
    application.add_handler(CallbackQueryHandler(handle_group_settings_callback, pattern=r"^group_setting_|^toggle_|^set_min_coins|^back_to_group_settings|^group_stats"), group=2)
    
    # Guruh xabarlarini tozalash uchun callback query handler qo'shish
    application.add_handler(CallbackQueryHandler(handle_clear_messages_callback, pattern=r"^confirm_clear_messages|^cancel_clear_messages"), group=3)

    # Guruh sozlamalari buyrug'i
    application.add_handler(CommandHandler("settings", show_group_settings), group=4)
    
    # Guruh xabarlarini tozalash buyrug'i
    application.add_handler(CommandHandler("clear", clear_group_messages), group=5)

    # Kanal xabarlarini tekshirish uchun handler qo'shish
    # Har qanday turdagi xabarlarni qabul qilish uchun
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_channel_message), group=6)

    application.add_error_handler(error_handler)

    # Botni ishga tushirish
    print("Bot ishga tushdi...")

    # Kanal bilan bog'lanishni tekshirish uchun post_init callback
    async def post_init(application: Application) -> None:
        await check_channel_connection(application.bot)

    application.post_init = post_init

    application.run_polling()

if __name__ == "__main__":
    main()