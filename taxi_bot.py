import json
import logging
import os
import re
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackContext, CallbackQueryHandler

# =============================================
# ASOSIY KONFIGURATSIYA - BU QISMNI O'ZGARTIRING
# =============================================
# Telegram bot tokeni (BotFather dan olinadi)
BOT_TOKEN = "7670097486:AAFaRKes3WH9Ev_aronONWjr6ls306nPAtI"

# Kanal ID raqami (habarlar yuborilishi kerak bo'lgan kanal)
CHANNEL_ID = "-1001522285580"  # Kanal ID raqamini kiriting

# Haydovchilar kanali havolasi
DRIVERS_CHANNEL_LINK = "https://t.me/your_channel"  # Haydovchilar kanali havolasini kiriting

# Ma'lumotlar fayllari
USERS_FILE = 'users.json'
DRIVERS_FILE = 'drivers.json'
OFFERS_FILE = 'offers.json'  # Yo'lovchi berish uchun
CHANNEL_CONVERSATIONS_FILE = 'channel_conversATIONS.json'  # Kanal suhbatlari uchun
STATS_FILE = 'stats.json'  # Statistika uchun

# Botni kanalga ulash kerakmi?
SEND_TO_CHANNEL = True  # True qilsangiz, habarlar kanalga yuboriladi

# Debug rejimi
DEBUG = True  # Debug xabarlarini ko'rsatish uchun

# Admin foydalanuvchilar ro'yxati
ADMIN_USERS = ["7578618626"]  # Admin foydalanuvchilar ID raqamlari

# Yangi haydovchilarga beriladigan boshlang'ich tangalar soni
INITIAL_DRIVER_COINS = 5

# Qayta ishlangan xabarlar uchun set
PROCESSED_MESSAGES = set()  # Qayta ishlangan xabar ID larini saqlash uchun

# =============================================

# Logging sozlamalari
logging.basicConfig(
format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
level=logging.INFO
)
logger = logging.getLogger(__name__)

# Holatlar
START, REGISTER_DRIVER, DRIVER_MENU = range(3)
ENTER_NAME, ENTER_PHONE = range(3, 5)
DRIVER_ACTION, DRIVER_PASSENGER_COUNT, DRIVER_DESTINATION, DRIVER_TIME, DRIVER_CONTACT, DRIVER_COMMENT = range(5, 11)
WAITING_FOR_PHONE = 11  # Kanal suhbati uchun

# Admin panel holatlari
ADMIN_MENU, ADMIN_STATS, ADMIN_SETTINGS, ADMIN_MESSAGE, ADMIN_GIFT = range(12, 17)
ADMIN_MESSAGE_TEXT, ADMIN_MESSAGE_TARGET, ADMIN_GIFT_AMOUNT, ADMIN_GIFT_TARGET = range(17, 21)
ADMIN_SETTINGS_MENU, ADMIN_SETTINGS_INITIAL_COINS = range(21, 23)

# Telefon raqamini formatlash
def format_phone(phone):
    # Raqamni tozalash (faqat raqamlar qolsin)
    phone = re.sub(r'\D', '', phone)

    # Agar raqam 998 bilan boshlansa, oldiga + qo'shish
    if phone.startswith('998'):
        return f"+{phone}"
    # Agar raqam 9 bilan boshlansa va 9 raqamli bo'lsa, +998 qo'shish
    elif len(phone) == 9 and phone.startswith('9'):
        return f"+998{phone}"
    # Boshqa holatlarda o'zini qaytarish
    else:
        return phone

# Fayllarni tekshirish va yaratish
def ensure_files_exist():
    for file in [USERS_FILE, DRIVERS_FILE, OFFERS_FILE, CHANNEL_CONVERSATIONS_FILE, STATS_FILE]:
        if not os.path.exists(file):
            with open(file, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False)

# Ma'lumotlarni yuklash
def load_data(file_name):
    try:
        with open(file_name, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# Ma'lumotlarni saqlash
def save_data(data, file_name):
    with open(file_name, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Statistikani yangilash
def update_stats(stat_type, value=1):
    stats = load_data(STATS_FILE)

    # Bugungi sana
    today = datetime.now().strftime("%Y-%m-%d")

    # Agar bugungi sana uchun statistika bo'lmasa, yaratish
    if today not in stats:
        stats[today] = {}

    # Statistikani yangilash
    if stat_type not in stats[today]:
        stats[today][stat_type] = 0

    stats[today][stat_type] += value

    # Umumiy statistikani yangilash
    if "total" not in stats:
        stats["total"] = {}

    if stat_type not in stats["total"]:
        stats["total"][stat_type] = 0

    stats["total"][stat_type] += value

    save_data(stats, STATS_FILE)

# Foydalanuvchi turini aniqlash
def get_user_type(user_id):
    users = load_data(USERS_FILE)
    user_id_str = str(user_id)

    if user_id_str in users:
        return users[user_id_str].get('role', 'new')
    return 'new'

# Foydalanuvchi admin ekanligini tekshirish
def is_admin(user_id):
    return str(user_id) in ADMIN_USERS

# Foydalanuvchi profilini olish
def get_user_profile_link(user):
    if user.username:
        return f"<a href='https://t.me/{user.username}'>{user.full_name}</a>"
    else:
        return f"<a href='tg://user?id={user.id}'>{user.full_name}</a>"

# Start buyrug'i
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Guruh chatlarida botni ishlatishni oldini olish
    if update.effective_chat.type != "private":
        return
        
    user_id = update.effective_user.id
    user_type = get_user_type(user_id)

    # Admin ekanligini tekshirish
    if is_admin(user_id):
        await show_admin_menu(update, context)
        return ADMIN_MENU

    if user_type == 'new':
        await update.message.reply_text(
            "Assalomu alaykum! Taksi botimizga xush kelibsiz!",
            reply_markup=ReplyKeyboardMarkup([
                ["Haydovchi sifatida ro'yxatdan o'tish"]
            ], resize_keyboard=True)
        )
        return REGISTER_DRIVER
    elif user_type == 'driver':
        await show_driver_menu(update, context)
        return DRIVER_MENU

# Ro'yxatdan o'tish
async def register_driver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    choice = update.message.text

    users = load_data(USERS_FILE)
    user_id_str = str(user_id)

    if choice == "Haydovchi sifatida ro'yxatdan o'tish":
        # Yangi haydovchilarga boshlang'ich tangalar berish
        users[user_id_str] = {"role": "driver_pending", "coins": INITIAL_DRIVER_COINS}
        save_data(users, USERS_FILE)
        await update.message.reply_text(
            "Siz haydovchi sifatida ro'yxatdan o'tmoqchisiz. Iltimos, to'liq ismingizni kiriting:"
        )
        return ENTER_NAME
    else:
        await update.message.reply_text(
            "Iltimos, taqdim etilgan tugmalardan birini tanlang."
        )
        return REGISTER_DRIVER

# Ism kiritish
async def enter_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    full_name = update.message.text

    users = load_data(USERS_FILE)
    user_id_str = str(user_id)

    users[user_id_str]["full_name"] = full_name
    save_data(users, USERS_FILE)

    # Telefon raqamini so'rash
    contact_button = KeyboardButton("Telefon raqamni yuborish", request_contact=True)
    await update.message.reply_text(
        "Rahmat! Endi telefon raqamingizni yuboring:",
        reply_markup=ReplyKeyboardMarkup([[contact_button]], resize_keyboard=True)
    )
    return ENTER_PHONE

# Telefon raqamini kiritish
async def enter_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = update.message.text

    # Telefon raqamini formatlash
    phone = format_phone(phone)

    users = load_data(USERS_FILE)
    user_id_str = str(user_id)

    users[user_id_str]["phone"] = phone
    users[user_id_str]["role"] = "driver"
    # Yangi haydovchilarga boshlang'ich tangalar berish
    # Bu allaqachon register_driver da berilgan
    save_data(users, USERS_FILE)

    # Statistikani yangilash
    update_stats("new_drivers")

    await show_driver_menu(update, context)
    return DRIVER_MENU

# Haydovchi menyusini ko'rsatish
async def show_driver_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Guruh chatlarida botni ishlatishni oldini olish
    if update.effective_chat.type != "private":
        return
        
    user_id = update.effective_user.id
    users = load_data(USERS_FILE)
    user_id_str = str(user_id)

    coins = users[user_id_str].get("coins", 0)

    await update.message.reply_text(
        f"Haydovchi menyusi:\nSizning tangalaringiz: {coins}",
        reply_markup=ReplyKeyboardMarkup([
            ["Yo'lovchi berish"]
        ], resize_keyboard=True)
    )
    # Joriy holatni saqlash
    context.user_data['state'] = DRIVER_MENU

# Haydovchi menyusini boshqarish
async def handle_driver_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Guruh chatlarida botni ishlatishni oldini olish
    if update.effective_chat.type != "private":
        return
        
    choice = update.message.text
    message_id = update.message.message_id

    # Xabar allaqachon qayta ishlangan bo'lsa, o'tkazib yuborish
    if message_id in PROCESSED_MESSAGES:
        if DEBUG:
            logger.info(f"Xabar {message_id} allaqachon qayta ishlangan, o'tkazib yuborildi")
        return DRIVER_MENU

    if choice == "Yo'lovchi berish":
        await update.message.reply_text(
            "Yo'lovchi berish uchun quyidagi formatda xabar yuboring:\n"
            "<telefon raqam> <yo'nalish (n yoki t)> <yo'lovchilar soni>\n\n"
            "Masalan: +998901234567 n 3\n"
            "Bu degani: +998901234567 raqamli haydovchi Namangandan Toshkentga 3 ta yo'lovchi bilan ketmoqchi.\n\n"
            "Yoki: 901234567 t 2\n"
            "Bu degani: 901234567 raqamli haydovchi Toshkentdan Namanganga 2 ta yo'lovchi bilan ketmoqchi.",
            reply_markup=ReplyKeyboardMarkup([
                ["Yo'lovchi berish"]
            ], resize_keyboard=True)
        )
        return DRIVER_MENU

    elif choice == "Soxta so'rov ekan":
        # Taklif ID sini olish
        if 'current_offer_id' in context.user_data:
            offer_id = context.user_data['current_offer_id']
            await handle_fake_offer(update, context, offer_id)
            return DRIVER_MENU
        else:
            await update.message.reply_text("Siz hozirda hech qanday taklifni ko'rmayapsiz.")
            return DRIVER_MENU

    elif choice == "Oldim":
        # Taklif ID sini olish
        if 'current_offer_id' in context.user_data:
            offer_id = context.user_data['current_offer_id']
            await handle_successful_pickup(update, context, offer_id)
            return DRIVER_MENU
        else:
            await update.message.reply_text("Siz hozirda hech qanday taklifni ko'rmayapsiz.")
            return DRIVER_MENU

    elif choice == "Kelisha olmadim":
        # Taklif ID sini olish
        if 'current_offer_id' in context.user_data:
            offer_id = context.user_data['current_offer_id']
            await handle_failed_agreement(update, context, offer_id)
            return DRIVER_MENU
        else:
            await update.message.reply_text("Siz hozirda hech qanday taklifni ko'rmayapsiz.")
            return DRIVER_MENU

    else:
        # Qisqartirilgan formatni tekshirish
        shortened_format = re.search(r'(\+?\d+)\s+([nt])\s+(\d+)', choice)
        if shortened_format:
            # Xabarni qayta ishlangan deb belgilash
            PROCESSED_MESSAGES.add(message_id)
            # Qisqartirilgan formatni qayta ishlash
            await handle_shortened_format(update, context)
            return DRIVER_MENU
        
        await update.message.reply_text("Noto'g'ri tanlov. Iltimos, menyudan tanlang yoki yo'lovchi berish uchun ko'rsatilgan formatda xabar yuboring.")
        return DRIVER_MENU

# Soxta taklifni qayta ishlash
async def handle_fake_offer(update: Update, context: ContextTypes.DEFAULT_TYPE, offer_id):
    user_id = update.effective_user.id
    user_id_str = str(user_id)

    # Ma'lumotlarni yuklash
    users = load_data(USERS_FILE)
    offers = load_data(OFFERS_FILE)

    # Taklif mavjudmi?
    if offer_id not in offers:
        await update.message.reply_text("Bu taklif topilmadi!")
        return

    # Taklif allaqachon olinganmi?
    if offers[offer_id].get("status") == "taken":
        await update.message.reply_text("Bu taklif allaqachon olingan!")
        return

    # Taklif bergan haydovchidan 1 tanga ayirish
    offerer_id_str = str(offers[offer_id]["user_id"])
    if offerer_id_str in users:
        users[offerer_id_str]["coins"] = max(0, users[offerer_id_str].get("coins", 0) - 1)
        save_data(users, USERS_FILE)

    # Taklifni soxta deb belgilash
    offers[offer_id]["status"] = "fake"
    offers[offer_id]["fake_reporter_id"] = user_id
    offers[offer_id]["fake_reported_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_data(offers, OFFERS_FILE)

    # Statistikani yangilash
    update_stats("fake_offers")

    # Foydalanuvchi profilini olish
    user_profile_link = get_user_profile_link(update.effective_user)

    # Kanalda xabarni yangilash
    try:
        await context.bot.edit_message_text(
            chat_id=CHANNEL_ID,
            message_id=offers[offer_id]["message_id"],
            text=f"{offers[offer_id].get('channel_message', 'Yo\'lovchi berish taklifi')}\n\n❌ SOXTA: {user_profile_link}",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Xabarni yangilashda xatolik: {e}")

    # Haydovchiga xabar yuborish
    await update.message.reply_text(
        f"Siz bu taklifni soxta deb belgiladingiz. Taklif bergan haydovchidan 1 tanga ayirildi.",
        reply_markup=ReplyKeyboardMarkup([
            ["Yo'lovchi berish"]
        ], resize_keyboard=True)
    )

    # Taklif bergan haydovchiga xabar yuborish
    try:
        await context.bot.send_message(
            chat_id=offers[offer_id]["user_id"],
            text=f"Sizning yo'lovchi berish taklifingiz soxta deb belgilandi!\n"
                f"Hisobingizdan 1 tanga ayirildi.\n"
                f"Joriy tangalar soni: {users[offerer_id_str].get('coins', 0)}"
        )
    except Exception as e:
        logger.error(f"Xabar yuborishda xatolik: {e}")

    # Joriy taklif ID sini o'chirish
    if 'current_offer_id' in context.user_data:
        del context.user_data['current_offer_id']

# Muvaffaqiyatli yo'lovchi olishni qayta ishlash
async def handle_successful_pickup(update: Update, context: ContextTypes.DEFAULT_TYPE, offer_id):
    user_id = update.effective_user.id
    user_id_str = str(user_id)

    # Ma'lumotlarni yuklash
    users = load_data(USERS_FILE)
    offers = load_data(OFFERS_FILE)

    # Taklif mavjudmi?
    if offer_id not in offers:
        await update.message.reply_text("Bu taklif topilmadi!")
        return

    # Taklif allaqachon olinganmi?
    if offers[offer_id].get("status") == "taken":
        await update.message.reply_text("Bu taklif allaqachon olingan!")
        return

    # Yo'lovchilar sonini olish
    passenger_count = offers[offer_id].get("passenger_count", 1)

    # Haydovchida yetarli tanga bormi?
    if users[user_id_str].get("coins", 0) < passenger_count:
        await update.message.reply_text(
            f"Sizda yetarli tanga yo'q! {passenger_count} tanga kerak, sizda esa {users[user_id_str].get('coins', 0)} tanga bor."
        )
        return

    # Taklifni olindi deb belgilash
    offers[offer_id]["status"] = "taken"
    offers[offer_id]["taker_id"] = user_id
    offers[offer_id]["taken_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_data(offers, OFFERS_FILE)

    # Haydovchidan tanga ayirish (yo'lovchilar soniga qarab)
    users[user_id_str]["coins"] = users[user_id_str].get("coins", 0) - passenger_count

    # Taklif bergan haydovchiga tanga qo'shish
    offerer_id_str = str(offers[offer_id]["user_id"])
    if offerer_id_str in users:
        users[offerer_id_str]["coins"] = users[offerer_id_str].get("coins", 0) + passenger_count

    save_data(users, USERS_FILE)

    # Statistikani yangilash
    update_stats("offers_taken")

    # Foydalanuvchi profilini olish
    user_profile_link = get_user_profile_link(update.effective_user)

    # Kanalda xabarni yangilash
    try:
        await context.bot.edit_message_text(
            chat_id=CHANNEL_ID,
            message_id=offers[offer_id]["message_id"],
            text=f"{offers[offer_id].get('channel_message', 'Yo\'lovchi berish taklifi')}\n\n✅ OLINDI: {user_profile_link}",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Xabarni yangilashda xatolik: {e}")

    # Haydovchiga xabar yuborish
    await update.message.reply_text(
        f"Siz yo'lovchi berish taklifini muvaffaqiyatli oldingiz!\n"
        f"Hisobingizdan {passenger_count} tanga ayirildi.\n"
        f"Joriy tangalar soni: {users[user_id_str].get('coins', 0)}",
        reply_markup=ReplyKeyboardMarkup([
            ["Yo'lovchi berish"]
        ], resize_keyboard=True)
    )

    # Taklif bergan haydovchiga xabar yuborish
    try:
        await context.bot.send_message(
            chat_id=offers[offer_id]["user_id"],
            text=f"Sizning yo'lovchi berish taklifingiz qabul qilindi!\n"
                f"Hisobingizga {passenger_count} tanga qo'shildi.\n"
                f"Joriy tangalar soni: {users[offerer_id_str].get('coins', 0)}\n\n"
                f"Haydovchi: {users[user_id_str]['full_name']}\n"
                f"Telefon: {format_phone(users[user_id_str].get('phone', ''))}"
        )
    except Exception as e:
        logger.error(f"Xabar yuborishda xatolik: {e}")

    # Joriy taklif ID sini o'chirish
    if 'current_offer_id' in context.user_data:
        del context.user_data['current_offer_id']

# Kelisha olmaslikni qayta ishlash
async def handle_failed_agreement(update: Update, context: ContextTypes.DEFAULT_TYPE, offer_id):
    user_id = update.effective_user.id
    user_id_str = str(user_id)

    # Ma'lumotlarni yuklash
    offers = load_data(OFFERS_FILE)

    # Taklif mavjudmi?
    if offer_id not in offers:
        await update.message.reply_text("Bu taklif topilmadi!")
        return

    # Taklif allaqachon olinganmi?
    if offers[offer_id].get("status") == "taken":
        await update.message.reply_text("Bu taklif allaqachon olingan!")
        return

    # Taklifni qayta kanalga yuborish
    offers[offer_id]["status"] = "waiting"
    if "taker_id" in offers[offer_id]:
        del offers[offer_id]["taker_id"]
    save_data(offers, OFFERS_FILE)

    # Statistikani yangilash
    update_stats("failed_agreements")

    # Kanalga yuborish uchun xabar tayyorlash
    channel_message = offers[offer_id].get('channel_message', 
        f"Yangi yo'lovchilar taklifi:\n"
        f"Kim yubordi: {offers[offer_id].get('full_name', 'Nomsiz')}\n"
        f"Nechta yo'lovchi: {offers[offer_id].get('passenger_count', 1)}\n"
        f"Qayerga: {offers[offer_id].get('destination', 'Belgilanmagan')}\n\n"
        f"Yo'lovchini olish uchun ushbu xabarga javob bering (reply) va 'olaman' deb yozing."
    )

    # Eski xabarni o'chirish
    try:
        await context.bot.delete_message(
            chat_id=CHANNEL_ID,
            message_id=offers[offer_id]["message_id"]
        )
    except Exception as e:
        logger.error(f"Xabarni o'chirishda xatolik: {e}")

    # Kanalga qayta yuborish
    try:
        message = await context.bot.send_message(
            chat_id=CHANNEL_ID, 
            text=channel_message
        )
        
        # Xabar ID ni saqlash
        offers[offer_id]["message_id"] = message.message_id
        save_data(offers, OFFERS_FILE)
        
    except Exception as e:
        logger.error(f"Kanalga yuborishda xatolik: {e}")

    # Haydovchiga xabar yuborish
    await update.message.reply_text(
        f"Siz yo'lovchi bilan kelisha olmadingiz. Taklif qayta kanalga yuborildi.",
        reply_markup=ReplyKeyboardMarkup([
            ["Yo'lovchi berish"]
        ], resize_keyboard=True)
    )

    # Taklif bergan haydovchiga xabar yuborish
    try:
        await context.bot.send_message(
            chat_id=offers[offer_id]["user_id"],
            text=f"Haydovchi siz bilan kelisha olmadi. Taklifingiz qayta kanalga yuborildi."
        )
    except Exception as e:
        logger.error(f"Xabar yuborishda xatolik: {e}")

    # Joriy taklif ID sini o'chirish
    if 'current_offer_id' in context.user_data:
        del context.user_data['current_offer_id']

# Qisqartirilgan formatni qayta ishlash (shaxsiy chatda)
async def handle_shortened_format(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Guruh chatlarida botni ishlatishni oldini olish
    if update.effective_chat.type != "private":
        return
        
    message_text = update.message.text.lower()
    user_id = update.effective_user.id
    user_id_str = str(user_id)
    message_id = update.message.message_id

    if DEBUG:
        logger.info(f"handle_shortened_format: Xabar {message_id} qayta ishlanmoqda")

    # Qisqartirilgan formatni tekshirish
    shortened_format = re.search(r'(\+?\d+)\s+([nt])\s+(\d+)', message_text)
    if not shortened_format:
        return

    # Ma'lumotlarni olish
    phone = shortened_format.group(1)
    direction_code = shortened_format.group(2)
    passenger_count = int(shortened_format.group(3))

    # Telefon raqamini formatlash
    phone = format_phone(phone)

    # Yo'nalishni aniqlash
    if direction_code == 'n':
        destination = "Namangandan Toshkentga"
    else:  # 't'
        destination = "Toshkentdan Namanganga"

    # Foydalanuvchi ma'lumotlarini yuklash
    users = load_data(USERS_FILE)

    # Foydalanuvchi haydovchimi?
    is_driver = user_id_str in users and users[user_id_str].get("role") == "driver"

    # Haydovchi bo'lmasa, ro'yxatdan o'tkazish
    if not is_driver:
        users[user_id_str] = {
            "role": "driver",
            "coins": INITIAL_DRIVER_COINS,  # Yangi haydovchilarga boshlang'ich tangalar berish
            "full_name": update.effective_user.first_name,
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
        "full_name": users[user_id_str].get("full_name", update.effective_user.first_name),
        "phone": phone,
        "passenger_count": passenger_count,
        "destination": destination,
        "time": "Tez orada",  # Vaqt ma'lumoti yo'q
        "contact": phone,
        "comment": "",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "waiting"
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

    # Kanalga yuborish uchun xabar tayyorlash (telefon raqamisiz)
    channel_message = (
        f"Yangi yo'lovchilar taklifi:\n"
        f"Kim yubordi: {driver_data['full_name']}\n"
        f"Nechta yo'lovchi: {driver_data['passenger_count']}\n"
        f"Qayerga: {driver_data['destination']}\n\n"
        f"Yo'lovchini olish uchun ushbu xabarga javob bering (reply) va 'olaman' deb yozing."
    )

    # Xabar matnini saqlash
    offers[offer_id]["channel_message"] = channel_message
    save_data(offers, OFFERS_FILE)

    # Kanalga yuborish
    if SEND_TO_CHANNEL:
        try:
            message = await context.bot.send_message(
                chat_id=CHANNEL_ID, 
                text=channel_message
            )
            
            # Xabar ID ni saqlash
            offers[offer_id]["message_id"] = message.message_id
            save_data(offers, OFFERS_FILE)
            
        except Exception as e:
            logger.error(f"Kanalga yuborishda xatolik: {e}")

    await update.message.reply_text(
        f"Rahmat! Sizning taklifingiz qabul qilindi va kanalga yuborildi.\n"
        f"Agar biror haydovchi yo'lovchilaringizni olsa, sizga {passenger_count} tanga beriladi."
    )

# Qisqartirilgan formatni qayta ishlash (kanalda)
async def handle_shortened_format_in_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, match):
    user_id = update.effective_user.id
    user_id_str = str(user_id)
    message_id = update.message.message_id
    chat_id = str(update.effective_chat.id)

    if DEBUG:
        logger.info(f"handle_shortened_format_in_channel: Xabar {message_id} qayta ishlanmoqda")
        logger.info(f"Kanal ID: {chat_id}, CHANNEL_ID: {CHANNEL_ID}")

    # Ma'lumotlarni olish
    phone = match.group(1)
    direction_code = match.group(2)
    passenger_count = int(match.group(3))

    # Telefon raqamini formatlash
    phone = format_phone(phone)

    # Yo'nalishni aniqlash
    if direction_code == 'n':
        destination = "Namangandan Toshkentga"
    else:  # 't'
        destination = "Toshkentdan Namanganga"

    # Foydalanuvchi ma'lumotlarini yuklash
    users = load_data(USERS_FILE)

    # Foydalanuvchi haydovchimi?
    is_driver = user_id_str in users and users[user_id_str].get("role") == "driver"

    # Haydovchi bo'lmasa, ro'yxatdan o'tkazish
    if not is_driver:
        users[user_id_str] = {
            "role": "driver",
            "coins": INITIAL_DRIVER_COINS,  # Yangi haydovchilarga boshlang'ich tangalar berish
            "full_name": update.effective_user.first_name,
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
        "full_name": users[user_id_str].get("full_name", update.effective_user.first_name),
        "phone": phone,
        "passenger_count": passenger_count,
        "destination": destination,
        "time": "Tez orada",  # Vaqt ma'lumoti yo'q
        "contact": phone,
        "comment": "",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "waiting"
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

    # Kanalga yuborish uchun xabar tayyorlash (telefon raqamisiz)
    channel_message = (
        f"Yangi yo'lovchilar taklifi:\n"
        f"Kim yubordi: {driver_data['full_name']}\n"
        f"Nechta yo'lovchi: {driver_data['passenger_count']}\n"
        f"Qayerga: {driver_data['destination']}\n\n"
        f"Yo'lovchini olish uchun ushbu xabarga javob bering (reply) va 'olaman' deb yozing."
    )

    # Xabar matnini saqlash
    offers[offer_id]["channel_message"] = channel_message
    save_data(offers, OFFERS_FILE)

    # Xabarni o'chirish
    try:
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=update.message.message_id
        )
    except Exception as e:
        logger.error(f"Xabarni o'chirishda xatolik: {e}")

    # Kanalga yuborish
    if SEND_TO_CHANNEL:
        try:
            message = await context.bot.send_message(
                chat_id=CHANNEL_ID, 
                text=channel_message
            )
            
            # Xabar ID ni saqlash
            offers[offer_id]["message_id"] = message.message_id
            save_data(offers, OFFERS_FILE)
            
        except Exception as e:
            logger.error(f"Kanalga yuborishda xatolik: {e}")

    # Foydalanuvchiga xabar yuborish
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"Rahmat! Sizning taklifingiz qabul qilindi va kanalga yuborildi.\n"
                f"Agar biror haydovchi yo'lovchilaringizni olsa, sizga {passenger_count} tanga beriladi."
        )
    except Exception as e:
        logger.error(f"Foydalanuvchiga xabar yuborishda xatolik: {e}")

# Kanalda yozilgan xabarlarni tekshirish
async def handle_channel_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Xabar ma'lumotlarini olish
    if not update.message:
        return

    # Xabar ID ni olish
    message_id = update.message.message_id

    # Xabar allaqachon qayta ishlangan bo'lsa, o'tkazib yuborish
    if message_id in PROCESSED_MESSAGES:
        if DEBUG:
            logger.info(f"Xabar {message_id} allaqachon qayta ishlangan, o'tkazib yuborildi")
        return

    # Kanal ID ni tekshirish
    chat_id = update.effective_chat.id
    chat_id_str = str(chat_id)

    # Debug uchun
    if DEBUG:
        logger.info(f"Xabar keldi: chat_id={chat_id_str}, CHANNEL_ID={CHANNEL_ID}")
        logger.info(f"Xabar turi: {update.effective_chat.type}")
        if update.message.text:
            logger.info(f"Xabar matni: {update.message.text}")
        elif update.message.voice:
            logger.info("Ovozli xabar")
        elif update.message.photo:
            logger.info("Rasmli xabar")
        else:
            logger.info("Boshqa turdagi xabar")
        
        if update.message.reply_to_message:
            logger.info(f"Javob xabar: {update.message.reply_to_message.text if update.message.reply_to_message.text else 'Matn yo\'q'}")

    # Agar bu shaxsiy chat bo'lsa
    if update.effective_chat.type == "private":
        # Joriy holat DRIVER_MENU bo'lsa, bu xabarni o'tkazib yuborish
        # chunki u handle_driver_menu() tomonidan qayta ishlanadi
        current_state = context.user_data.get('state')
        if current_state == DRIVER_MENU and update.message.text:
            shortened_format = re.search(r'(\+?\d+)\s+([nt])\s+(\d+)', update.message.text.lower())
            if shortened_format:
                if DEBUG:
                    logger.info(f"Xabar {message_id} DRIVER_MENU holatida, o'tkazib yuborildi")
                return
        
        # Ovozli xabar kelgan bo'lsa
        if update.message.voice:
            await handle_voice_message(update, context)
            return

        if update.message.text:  # Faqat matn xabarlarini tekshirish
            # Qisqartirilgan formatni tekshirish
            shortened_format = re.search(r'(\+?\d+)\s+([nt])\s+(\d+)', update.message.text.lower())
            if shortened_format:
                # Xabarni qayta ishlangan deb belgilash
                PROCESSED_MESSAGES.add(message_id)
                await handle_shortened_format(update, context)
                return
        return

    # Agar bu kanal bo'lsa
    if update.effective_chat.type in ["channel", "supergroup", "group"]:
        # Agar bu javob xabar bo'lsa, yo'lovchi olish jarayonini tekshirish
        # Har qanday turdagi javob xabarni qabul qilish (matn, ovozli, rasm, video, hujjat va h.k.)
        if update.message.reply_to_message:
            # Xabarni qayta ishlangan deb belgilash
            PROCESSED_MESSAGES.add(message_id)
            await handle_passenger_claim(update, context)
            return
        
        # Qisqartirilgan formatni tekshirish (faqat matn xabarlarida)
        if update.message.text:
            shortened_format = re.search(r'(\+?\d+)\s+([nt])\s+(\d+)', update.message.text.lower())
            if shortened_format:
                # Xabarni qayta ishlangan deb belgilash
                PROCESSED_MESSAGES.add(message_id)
                await handle_shortened_format_in_channel(update, context, shortened_format)
                return

    # Agar bu yerga kelgan bo'lsa, xabar bizga kerakli formatda emas
    if DEBUG:
        logger.info(f"Xabar bizga kerakli formatda emas")

# Ovozli xabarlarni qayta ishlash
async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Guruh chatlarida botni ishlatishni oldini olish
    if update.effective_chat.type != "private":
        return
        
    user_id = update.effective_user.id
    user_id_str = str(user_id)
    message_id = update.message.message_id

    # Xabar allaqachon qayta ishlangan bo'lsa, o'tkazib yuborish
    if message_id in PROCESSED_MESSAGES:
        if DEBUG:
            logger.info(f"Xabar {message_id} allaqachon qayta ishlangan, o'tkazib yuborildi")
        return

    # Xabarni qayta ishlangan deb belgilash
    PROCESSED_MESSAGES.add(message_id)

    # Foydalanuvchi ma'lumotlarini yuklash
    users = load_data(USERS_FILE)

    # Foydalanuvchi ro'yxatdan o'tganmi?
    if user_id_str not in users:
        # Foydalanuvchi ro'yxatdan o'tmagan bo'lsa, ro'yxatdan o'tkazish
        users[user_id_str] = {
            "role": "driver_pending",
            "coins": INITIAL_DRIVER_COINS,
            "full_name": update.effective_user.first_name,
            "phone": ""
        }
        save_data(users, USERS_FILE)
        
        await update.message.reply_text(
            "Siz haydovchi sifatida ro'yxatdan o'tmagan ekansiz. Iltimos, to'liq ismingizni kiriting:"
        )
        return ENTER_NAME

    # Ovozli xabarni saqlash
    voice_file_id = update.message.voice.file_id
    context.user_data['voice_file_id'] = voice_file_id

    # Tasdiqlovchi inline keyboard yaratish
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Ha", callback_data=f"voice_confirm_yes"),
            InlineKeyboardButton("Yo'q", callback_data=f"voice_confirm_no")
        ]
    ])

    # Foydalanuvchiga tasdiqlovchi xabar yuborish
    await update.message.reply_text(
        "Siz ovozli xabar yubordingiz. Bu yo'lovchi taklifi sifatida kanalga yuborilsinmi?",
        reply_markup=keyboard
    )

# Yo'lovchini olish jarayoni (reply orqali)
async def handle_passenger_claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_id_str = str(user_id)
    message_id = update.message.message_id

    if DEBUG:
        logger.info(f"handle_passenger_claim: Xabar {message_id} qayta ishlanmoqda")

    # Har qanday turdagi javob xabarni qabul qilish (matn, ovozli, rasm, video, hujjat va h.k.)
    if DEBUG:
        logger.info(f"Javob xabar qabul qilindi: {update.message}")
        logger.info(f"Xabar turi: {update.message.voice is not None and 'Ovozli' or update.message.text and 'Matn' or 'Boshqa'}")

    # Javob berilgan xabarni olish
    original_message = update.message.reply_to_message
    if not original_message:
        return

    # Tekshirish: original xabar botdan kelganmi?
    if original_message.from_user.id != context.bot.id:
        # Agar xabar botdan kelmagan bo'lsa, funksiyadan chiqish
        if DEBUG:
            logger.info(f"Bu xabar botdan kelmagan, qayta ishlanmaydi")
        return

    # Ma'lumotlarni yuklash
    users = load_data(USERS_FILE)
    offers = load_data(OFFERS_FILE)

    # Foydalanuvchi haydovchimi?
    if user_id_str not in users:
        # Haydovchi bo'lmasa, ro'yxatdan o'tkazish
        users[user_id_str] = {
            "role": "driver",
            "coins": INITIAL_DRIVER_COINS,  # Yangi haydovchilarga boshlang'ich tangalar berish
            "full_name": update.effective_user.first_name,
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

    # Xabar ID orqali offer ni topish
    offer_id = None

    # Ovozli xabar uchun
    if original_message.voice:
        # Ovozli xabar ID orqali offer ni topish
        for oid, offer_data in offers.items():
            if offer_data.get("voice_file_id") == original_message.voice.file_id:
                offer_id = oid
                break
    else:
        # Matn xabar ID orqali offer ni topish
        for oid, offer_data in offers.items():
            if offer_data.get("message_id") == original_message.message_id:
                offer_id = oid
                break

    # Agar offer topilmasa
    if not offer_id:
        await update.message.reply_text(
            "Bu taklif topilmadi!"
        )
        return

    # Yo'lovchilar sonini aniqlash
    passenger_count = offers[offer_id].get("passenger_count", 1)

    # Offer allaqachon olinganmi?
    if offers[offer_id].get("status") == "taken":
        await update.message.reply_text(
            "Bu taklif allaqachon olingan!"
        )
        return

    # Haydovchida yetarli tanga bormi?
    if users[user_id_str].get("coins", 0) < passenger_count:
        await update.message.reply_text(
            f"Sizda yetarli tanga yo'q! {passenger_count} tanga kerak, sizda esa {users[user_id_str].get('coins', 0)} tanga bor."
        )
        return

    # Foydalanuvchi profilini olish
    user_profile_link = get_user_profile_link(update.effective_user)

    # Taklifni olindi deb belgilash
    offers[offer_id]["status"] = "pending"  # Kutish holatiga o'tkazish
    offers[offer_id]["taker_id"] = user_id
    offers[offer_id]["pending_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_data(offers, OFFERS_FILE)

    # Kanalda xabarni yangilash
    try:
        if original_message.text:
            await context.bot.edit_message_text(
                chat_id=CHANNEL_ID,
                message_id=original_message.message_id,
                text=f"{original_message.text}\n\n⏳ KUTILMOQDA: {user_profile_link}",
                parse_mode="HTML"
            )
        # Ovozli xabar uchun javob xabarini yangilash
        elif original_message.voice:
            # Ovozli xabar uchun info xabarini topish
            info_message_id = offers[offer_id].get("info_message_id")
            if info_message_id:
                await context.bot.edit_message_text(
                    chat_id=CHANNEL_ID,
                    message_id=info_message_id,
                    text=f"Yangi yo'lovchilar taklifi (ovozli xabar):\n"
                        f"Kim yubordi: {offers[offer_id]['full_name']}\n"
                        f"Nechta yo'lovchi: {offers[offer_id]['passenger_count']}\n\n"
                        f"⏳ KUTILMOQDA: {user_profile_link}",
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

    # Knopkalar yaratish
    keyboard = ReplyKeyboardMarkup([
        ["Oldim"],
        ["Soxta so'rov ekan"],
        ["Kelisha olmadim"]
    ], resize_keyboard=True)

    # Joriy taklif ID sini saqlash
    context.user_data['current_offer_id'] = offer_id

    await context.bot.send_message(
        chat_id=user_id,
        text=f"Siz yo'lovchi berish taklifini oldingiz!\n\n{offer_info}\n\n"
            f"Agar yo'lovchilarni muvaffaqiyatli olsangiz, 'Oldim' tugmasini bosing.\n"
            f"Agar taklif soxta bo'lsa, 'Soxta so'rov ekan' tugmasini bosing.\n"
            f"Agar yo'lovchi bilan kelisha olmasangiz, 'Kelisha olmadim' tugmasini bosing.",
        reply_markup=keyboard
    )

    # Taklif bergan haydovchiga xabar yuborish
    try:
        await context.bot.send_message(
            chat_id=offers[offer_id]["user_id"],
            text=f"Sizning yo'lovchi berish taklifingiz qabul qilindi!\n\n"
                f"Haydovchi: {users[user_id_str]['full_name']}\n"
                f"Telefon: {format_phone(users[user_id_str].get('phone', ''))}\n\n"
                f"Haydovchi yo'lovchilarni olganini tasdiqlagandan so'ng, hisobingizga {passenger_count} tanga qo'shiladi."
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
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=update.message.message_id
        )
    except Exception as e:
        logger.error(f"Xabarni o'chirishda xatolik: {e}")

# Yo'lovchi berish uchun callback query handler
async def take_passenger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_id_str = str(user_id)

    # Callback data ni tekshirish
    data = query.data

    # Ovozli xabar tasdiqlovini tekshirish
    if data == "voice_confirm_yes":
        # Yo'lovchilar sonini so'rash
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("1", callback_data=f"voice_count_1"),
                InlineKeyboardButton("2", callback_data=f"voice_count_2"),
                InlineKeyboardButton("3", callback_data=f"voice_count_3"),
                InlineKeyboardButton("4", callback_data=f"voice_count_4")
            ]
        ])
        
        await query.edit_message_text(
            "Nechta yo'lovchi bilan ketmoqchisiz?",
            reply_markup=keyboard
        )
        return

    elif data == "voice_confirm_no":
        await query.edit_message_text("Ovozli xabar bekor qilindi.")
        return

    # Yo'lovchilar sonini tekshirish
    elif data.startswith("voice_count_"):
        passenger_count = int(data.split("_")[-1])
        context.user_data['passenger_count'] = passenger_count
        
        # Telefon raqamini so'rash
        await query.edit_message_text(
            f"Siz {passenger_count} yo'lovchi bilan ketmoqchisiz. Iltimos, telefon raqamingizni yuboring:"
        )
        
        # Telefon raqamini kutish holatiga o'tish
        context.user_data['waiting_for_phone'] = True
        context.user_data['voice_message'] = True
        return

# Telefon raqamini qabul qilish
async def handle_phone_for_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Guruh chatlarida botni ishlatishni oldini olish
    if update.effective_chat.type != "private":
        return
        
    user_id = update.effective_user.id
    user_id_str = str(user_id)
    message_id = update.message.message_id

    # Xabar allaqachon qayta ishlangan bo'lsa, o'tkazib yuborish
    if message_id in PROCESSED_MESSAGES:
        if DEBUG:
            logger.info(f"Xabar {message_id} allaqachon qayta ishlangan, o'tkazib yuborildi")
        return

    # Xabarni qayta ishlangan deb belgilash
    PROCESSED_MESSAGES.add(message_id)

    # Telefon raqamini olish
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = update.message.text

    # Telefon raqamini formatlash
    phone = format_phone(phone)

    # Foydalanuvchi ma'lumotlarini yuklash
    users = load_data(USERS_FILE)
    drivers = load_data(DRIVERS_FILE)
    offers = load_data(OFFERS_FILE)

    # Foydalanuvchi ma'lumotlarini yangilash
    users[user_id_str]["phone"] = phone
    save_data(users, USERS_FILE)

    # Yo'lovchi berish taklifini yaratish
    passenger_count = context.user_data.get('passenger_count', 1)
    voice_file_id = context.user_data.get('voice_file_id')

    # Haydovchi ma'lumotlarini saqlash
    driver_data = {
        "user_id": user_id,
        "full_name": users[user_id_str].get("full_name", update.effective_user.first_name),
        "phone": phone,
        "passenger_count": passenger_count,
        "destination": "Ovozli xabar",
        "time": "Tez orada",
        "contact": phone,
        "comment": "",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "waiting",
        "voice_file_id": voice_file_id
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
                voice=voice_file_id
            )
            
            # Xabar ID ni saqlash
            offers[offer_id]["message_id"] = voice_message.message_id
            save_data(offers, OFFERS_FILE)
            
            # Ovozli xabar haqida ma'lumot yuborish (telefon raqamisiz)
            info_message = (
                f"Yangi yo'lovchilar taklifi (ovozli xabar):\n"
                f"Kim yubordi: {driver_data['full_name']}\n"
                f"Nechta yo'lovchi: {driver_data['passenger_count']}\n\n"
                f"Yo'lovchini olish uchun ushbu xabarga javob bering (reply) va 'olaman' deb yozing."
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
    await update.message.reply_text(
        f"Rahmat! Sizning ovozli taklifingiz qabul qilindi va kanalga yuborildi.\n"
        f"Agar biror haydovchi yo'lovchilaringizni olsa, sizga {passenger_count} tanga beriladi.",
        reply_markup=ReplyKeyboardMarkup([
            ["Yo'lovchi berish"]
        ], resize_keyboard=True)
    )

    # Kutish holatini o'chirish
    if 'waiting_for_phone' in context.user_data:
        del context.user_data['waiting_for_phone']
    if 'voice_message' in context.user_data:
        del context.user_data['voice_message']
    if 'voice_file_id' in context.user_data:
        del context.user_data['voice_file_id']
    if 'passenger_count' in context.user_data:
        del context.user_data['passenger_count']

    return DRIVER_MENU

# Admin menyusini ko'rsatish
async def show_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Admin paneli:",
        reply_markup=ReplyKeyboardMarkup([
            ["📊 Statistika", "⚙️ Sozlamalar"],
            ["📨 Xabar yuborish", "🎁 Sovg'a berish"],
            ["👤 Foydalanuvchilar"]
        ], resize_keyboard=True)
    )

# Admin menyusini boshqarish
async def handle_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text

    if choice == "📊 Statistika":
        await show_admin_stats(update, context)
        return ADMIN_MENU
    elif choice == "⚙️ Sozlamalar":
        await show_admin_settings(update, context)
        return ADMIN_SETTINGS_MENU
    elif choice == "📨 Xabar yuborish":
        await update.message.reply_text(
            "Yubormoqchi bo'lgan xabaringizni kiriting:",
            reply_markup=ReplyKeyboardRemove()
        )
        return ADMIN_MESSAGE_TEXT
    elif choice == "🎁 Sovg'a berish":
        await update.message.reply_text(
            "Qancha tanga sovg'a qilmoqchisiz?",
            reply_markup=ReplyKeyboardRemove()
        )
        return ADMIN_GIFT_AMOUNT
    elif choice == "👤 Foydalanuvchilar":
        await show_admin_users(update, context)
        return ADMIN_MENU
    else:
        await update.message.reply_text("Noto'g'ri tanlov. Iltimos, menyudan tanlang.")
        return ADMIN_MENU

# Admin statistikasini ko'rsatish
async def show_admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = load_data(STATS_FILE)

    # Bugungi sana
    today = datetime.now().strftime("%Y-%m-%d")

    # Bugungi statistika
    today_stats = stats.get(today, {})

    # Umumiy statistika
    total_stats = stats.get("total", {})

    # Statistika xabarini tayyorlash
    stats_message = (
        "📊 STATISTIKA\n\n"
        "Bugungi:\n"
        f"- Yangi haydovchilar: {today_stats.get('new_drivers', 0)}\n"
        f"- Yangi takliflar: {today_stats.get('new_offers', 0)}\n"
        f"- Qabul qilingan takliflar: {today_stats.get('offers_taken', 0)}\n"
        f"- Soxta takliflar: {today_stats.get('fake_offers', 0)}\n"
        f"- Kelisha olmasliklar: {today_stats.get('failed_agreements', 0)}\n\n"
        "Umumiy:\n"
        f"- Haydovchilar: {total_stats.get('new_drivers', 0)}\n"
        f"- Takliflar: {total_stats.get('new_offers', 0)}\n"
        f"- Qabul qilingan takliflar: {total_stats.get('offers_taken', 0)}\n"
        f"- Soxta takliflar: {total_stats.get('fake_offers', 0)}\n"
        f"- Kelisha olmasliklar: {total_stats.get('failed_agreements', 0)}"
    )

    await update.message.reply_text(
        stats_message,
        reply_markup=ReplyKeyboardMarkup([
            ["📊 Statistika", "⚙️ Sozlamalar"],
            ["📨 Xabar yuborish", "🎁 Sovg'a berish"],
            ["👤 Foydalanuvchilar"]
        ], resize_keyboard=True)
    )

# Admin sozlamalarini ko'rsatish
async def show_admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"⚙️ SOZLAMALAR\n\n"
        f"1. Yangi haydovchilarga beriladigan boshlang'ich tangalar: {INITIAL_DRIVER_COINS}\n"
        f"2. Kanal ID: {CHANNEL_ID}\n"
        f"3. Haydovchilar kanali havolasi: {DRIVERS_CHANNEL_LINK}",
        reply_markup=ReplyKeyboardMarkup([
            ["Boshlang'ich tangalar"],
            ["Orqaga"]
        ], resize_keyboard=True)
    )

# Admin sozlamalar menyusini boshqarish
async def handle_admin_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text

    if choice == "Boshlang'ich tangalar":
        await update.message.reply_text(
            "Yangi haydovchilarga beriladigan boshlang'ich tangalar sonini kiriting:",
            reply_markup=ReplyKeyboardRemove()
        )
        return ADMIN_SETTINGS_INITIAL_COINS
    elif choice == "Orqaga":
        await show_admin_menu(update, context)
        return ADMIN_MENU
    else:
        await update.message.reply_text("Noto'g'ri tanlov. Iltimos, menyudan tanlang.")
        return ADMIN_SETTINGS_MENU

# Boshlang'ich tangalar sonini o'zgartirish
async def admin_settings_initial_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        coins = int(update.message.text)
        
        # global o'zgaruvchini yangilash
        global INITIAL_DRIVER_COINS
        INITIAL_DRIVER_COINS = coins
        
        await update.message.reply_text(
            f"Yangi haydovchilarga beriladigan boshlang'ich tangalar soni {coins} ga o'zgartirildi.",
            reply_markup=ReplyKeyboardMarkup([
                ["📊 Statistika", "⚙️ Sozlamalar"],
                ["📨 Xabar yuborish", "🎁 Sovg'a berish"],
                ["👤 Foydalanuvchilar"]
            ], resize_keyboard=True)
        )
        
        return ADMIN_MENU
    except ValueError:
        await update.message.reply_text(
            "Iltimos, raqam kiriting.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ADMIN_SETTINGS_INITIAL_COINS

# Xabar matnini kiritish
async def admin_message_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text
    context.user_data['message_text'] = message_text

    await update.message.reply_text(
        "Xabar kimga yuborilsin?",
        reply_markup=ReplyKeyboardMarkup([
            ["Hamma haydovchilarga"],
            ["Bekor qilish"]
        ], resize_keyboard=True)
    )

    return ADMIN_MESSAGE_TARGET

# Xabar yuborish maqsadini tanlash
async def admin_message_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message.text
    message_text = context.user_data.get('message_text', '')

    if target == "Bekor qilish":
        await update.message.reply_text(
            "Xabar yuborish bekor qilindi.",
            reply_markup=ReplyKeyboardMarkup([
                ["📊 Statistika", "⚙️ Sozlamalar"],
                ["📨 Xabar yuborish", "🎁 Sovg'a berish"],
                ["👤 Foydalanuvchilar"]
            ], resize_keyboard=True)
        )
        return ADMIN_MENU

    users = load_data(USERS_FILE)
    sent_count = 0

    for user_id, user_data in users.items():
        # Foydalanuvchi turini tekshirish
        if target == "Hamma haydovchilarga" and user_data.get('role') == 'driver':
            try:
                await context.bot.send_message(
                    chat_id=int(user_id),
                    text=message_text
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Xabar yuborishda xatolik: {e}")

    await update.message.reply_text(
        f"Xabar {sent_count} ta foydalanuvchiga yuborildi.",
        reply_markup=ReplyKeyboardMarkup([
            ["📊 Statistika", "⚙️ Sozlamalar"],
            ["📨 Xabar yuborish", "🎁 Sovg'a berish"],
            ["👤 Foydalanuvchilar"]
        ], resize_keyboard=True)
    )

    return ADMIN_MENU

# Sovg'a miqdorini kiritish
async def admin_gift_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        context.user_data['gift_amount'] = amount
        
        await update.message.reply_text(
            "Sovg'a kimga berilsin?",
            reply_markup=ReplyKeyboardMarkup([
                ["Hamma haydovchilarga"],
                ["Aniq foydalanuvchiga"],
                ["Bekor qilish"]
            ], resize_keyboard=True)
        )
        
        return ADMIN_GIFT_TARGET
    except ValueError:
        await update.message.reply_text(
            "Iltimos, raqam kiriting.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ADMIN_GIFT_AMOUNT

# Sovg'a maqsadini tanlash
async def admin_gift_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message.text
    amount = context.user_data.get('gift_amount', 0)

    if target == "Bekor qilish":
        await update.message.reply_text(
            "Sovg'a berish bekor qilindi.",
            reply_markup=ReplyKeyboardMarkup([
                ["📊 Statistika", "⚙️ Sozlamalar"],
                ["📨 Xabar yuborish", "🎁 Sovg'a berish"],
                ["👤 Foydalanuvchilar"]
            ], resize_keyboard=True)
        )
        return ADMIN_MENU

    if target == "Aniq foydalanuvchiga":
        await update.message.reply_text(
            "Foydalanuvchi ID raqamini kiriting:",
            reply_markup=ReplyKeyboardRemove()
        )
        return ADMIN_GIFT_TARGET

    users = load_data(USERS_FILE)
    gift_count = 0

    for user_id, user_data in users.items():
        # Foydalanuvchi turini tekshirish
        if (target == "Hamma haydovchilarga" and user_data.get('role') == 'driver') or \
           (target.isdigit() and user_id == target):
            # Tangalarni qo'shish
            users[user_id]["coins"] = users[user_id].get("coins", 0) + amount
            gift_count += 1
            
            # Foydalanuvchiga xabar yuborish
            try:
                await context.bot.send_message(
                    chat_id=int(user_id),
                    text=f"🎁 Tabriklaymiz! Sizga {amount} tanga sovg'a qilindi.\n"
                         f"Joriy tangalar soni: {users[user_id]['coins']}"
                )
            except Exception as e:
                logger.error(f"Xabar yuborishda xatolik: {e}")

    save_data(users, USERS_FILE)

    await update.message.reply_text(
        f"Sovg'a {gift_count} ta foydalanuvchiga yuborildi.",
        reply_markup=ReplyKeyboardMarkup([
            ["📊 Statistika", "⚙️ Sozlamalar"],
            ["📨 Xabar yuborish", "🎁 Sovg'a berish"],
            ["👤 Foydalanuvchilar"]
        ], resize_keyboard=True)
    )

    return ADMIN_MENU

# Foydalanuvchilar ro'yxatini ko'rsatish
async def show_admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_data(USERS_FILE)

    # Foydalanuvchilar sonini hisoblash
    driver_count = sum(1 for user in users.values() if user.get('role') == 'driver')

    # Top 5 haydovchilarni tangalar bo'yicha saralash
    top_drivers = sorted(
        [(user_id, user_data) for user_id, user_data in users.items() if user_data.get('role') == 'driver'],
        key=lambda x: x[1].get('coins', 0),
        reverse=True
    )[:5]

    # Xabarni tayyorlash
    users_message = (
        "👤 FOYDALANUVCHILAR\n\n"
        f"Umumiy foydalanuvchilar: {len(users)}\n"
        f"Haydovchilar: {driver_count}\n\n"
        "Top 5 haydovchilar (tangalar bo'yicha):\n"
    )

    for i, (user_id, user_data) in enumerate(top_drivers, 1):
        users_message += f"{i}. {user_data.get('full_name', 'Nomsiz')} - {user_data.get('coins', 0)} tanga\n"

    await update.message.reply_text(
        users_message,
        reply_markup=ReplyKeyboardMarkup([
            ["📊 Statistika", "⚙️ Sozlamalar"],
            ["📨 Xabar yuborish", "🎁 Sovg'a berish"],
            ["👤 Foydalanuvchilar"]
        ], resize_keyboard=True)
    )

# Xatolikni qayta ishlash
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    if update.effective_message:
        await update.effective_message.reply_text(
            "Xatolik yuz berdi. Iltimos, /start buyrug'i bilan qayta boshlang."
        )

async def check_channel_connection(bot):
    try:
        await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=bot.id)
        logger.info("Bot kanalga ulangan va huquqlari bor.")
    except Exception as e:
        logger.error(f"Bot kanalga ulana olmadi yoki huquqlari yo'q: {e}")

# main funksiyasini o'zgartirish
def main():
    # Fayllarni tekshirish
    ensure_files_exist()

    # Bot yaratish
    application = Application.builder().token(BOT_TOKEN).build()

    # ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            REGISTER_DRIVER: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_driver)],
            ENTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_name)],
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
    application.add_handler(CallbackQueryHandler(take_passenger), group=1)

    # Ovozli xabar uchun telefon raqamini qabul qilish
    application.add_handler(
        MessageHandler(
            (filters.TEXT | filters.CONTACT) & 
            filters.ChatType.PRIVATE & 
            ~filters.COMMAND,
            lambda update, context: handle_phone_for_voice(update, context) 
            if context.user_data.get('waiting_for_phone') and context.user_data.get('voice_message') 
            else None
        ),
        group=2
    )

    # Kanal xabarlarini tekshirish uchun handler qo'shish
    # Har qanday turdagi xabarlarni qabul qilish uchun
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_channel_message), group=3)

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