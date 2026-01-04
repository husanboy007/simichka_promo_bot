import logging
import os
import sqlite3
import random
import re
import time
from database import get_db_connection
import pandas as pd  # Excel uchun bu shart!
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from dotenv import load_dotenv
from db import init_db, check_code_status, save_participant
# from aiogram.utils.executor import start_webhook # Hozircha pollingda sinash uchun yopiq tursin

load_dotenv() # .env fayldagi ma'lumotlarni yuklash

# .env yuklash
load_dotenv()
API_TOKEN = os.getenv("BOT_TOKEN")

# Adminlarni ro'yxat qilib olish
admin_env = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(i.strip()) for i in admin_env.split(",") if i.strip()]

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

user_temp_data = {}
user_states = {} 
init_db()

# --- Admin va Foydalanuvchi buyruqlari menyusi ---
async def set_bot_commands(bot: Bot):
    # Foydalanuvchilar uchun
    user_commands = [
        BotCommand(command="/start", description="Botni qayta ishga tushirish")
    ]
    await bot.set_my_commands(user_commands, scope=types.BotCommandScopeDefault())
    
    # Adminlar uchun
    admin_commands = [
        BotCommand(command="/start", description="ishga tushirish"),
        BotCommand(command="/stats", description="Statistikani ko'rish"),
        BotCommand(command="/draw", description="G'olibni aniqlash"),
        BotCommand(command="/used_codes", description="Ishlatilgan kodlar ro'yxati"),
        BotCommand(command="/all_participants", description="Barcha ishtirokchilar"),
        BotCommand(command="/list_codes", description="Barcha kodlarni ko'rish (sahifali)"),
        BotCommand(command="/clear_participants", description="Haftalik o'yinni tozalash"),
        BotCommand(command="/reklama", description="Xabar yuborish")
    ]
    for admin_id in ADMIN_IDS:
        try:
            await bot.set_my_commands(admin_commands, scope=types.BotCommandScopeChat(chat_id=admin_id))
        except Exception:
            continue
from database import get_db_connection # MySQL ulanish funksiyasini chaqiramiz

async def on_startup_notify(dp: Dispatcher):
    await set_bot_commands(dp.bot)
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id, 
                "🚀 **Bot muvaffaqiyatli ishga tushdi!**\n\n"
                "✅ Hozirda bot 24/7 rejimda xizmat ko'rsatishga tayyor.",
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Admin {admin_id} ga xabar yuborishda xatolik: {e}")

# Klaviaturalar (O'zgarishsiz qoldi)
def main_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("👨‍💻 Adminga murojaat qilish"))
    return kb

def phone_keyboard():
    return ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True).add(
        KeyboardButton("📱 Telefon raqamni yuborish", request_contact=True)
    )

# --- ADMIN BUYRUQLARI ---

def init_db():
    # MySQL ulanishini ochamiz
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Hamma start bosganlar uchun jadval (MySQL-da BIGINT Telegram ID uchun yaxshiroq)
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY)''')
    
    # Kod yuborganlar jadvali
    cursor.execute('''CREATE TABLE IF NOT EXISTS participants (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id BIGINT, 
                        username VARCHAR(255), 
                        phone VARCHAR(50), 
                        code VARCHAR(50))''')
    
    # codes jadvali ham mavjud bo'lishi kerak
    cursor.execute('''CREATE TABLE IF NOT EXISTS codes (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        code VARCHAR(50) UNIQUE,
                        status VARCHAR(20) DEFAULT 'active')''')
    
    conn.commit()
    cursor.close()
    conn.close()

from database import get_db_connection # MySQL ulanishini chaqiramiz
import pandas as pd
import os

@dp.message_handler(commands=['list_codes'])
async def list_promo_codes(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        args = message.get_args()
        page = int(args) if args.isnumeric() else 1
        limit = 50
        offset = (page - 1) * limit

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Jami kodlarni sanash
            cursor.execute("SELECT COUNT(*) FROM codes")
            total_codes = cursor.fetchone()[0]
            
            # MySQL-da ? o'rniga %s ishlatiladi
            cursor.execute("SELECT code, status FROM codes LIMIT %s OFFSET %s", (limit, offset))
            codes = cursor.fetchall()
            
            cursor.close()
            conn.close()

            if not codes:
                await message.answer("📭 Bu sahifada kodlar mavjud emas.")
                return

            total_pages = (total_codes + limit - 1) // limit
            text = f"📋 **Promokodlar ro'yxati (Sahifa {page}/{total_pages}):**\n\n"
            
            for code, status in codes:
                icon = "✅" if status == 'active' else "❌" # Stats-dagi statusga mos
                text += f"{icon} `{code}` - {status}\n"
            
            kb = InlineKeyboardMarkup(row_width=2)
            buttons = []
            if page > 1:
                buttons.append(InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"list_page_{page-1}"))
            if page < total_pages:
                buttons.append(InlineKeyboardButton(text="Oldinga ➡️", callback_data=f"list_page_{page+1}"))
            kb.add(*buttons)

            await message.answer(text, parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            await message.answer(f"❌ Xatolik: {e}")

@dp.message_handler(commands=['all_participants'])
async def get_all_participants(message: types.Message):
    ADMIN_IDS = [7110271171, 183943783] #
    
    if message.from_user.id not in ADMIN_IDS:
        return await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q!")

    try:
        # 1. MySQL bazasidan ma'lumotlarni o'qish
        conn = get_db_connection()
        
        # Pandas MySQL ulanishi bilan to'g'ridan-to'g'ri ishlay oladi
        df = pd.read_sql_query("SELECT user_id, phone, code FROM participants", conn)
        conn.close()

        if df.empty:
            return await message.answer("Hozircha ishtirokchilar yo'q.")

        # Ma'lumotlarni matn formatiga o'tkazish
        df['user_id'] = df['user_id'].astype(str)
        df['phone'] = df['phone'].astype(str)
        df['code'] = df['code'].astype(str)

        # 2. Excel faylini yaratish
        file_path = "ishtirokchilar_va_kodlar.xlsx"
        writer = pd.ExcelWriter(file_path, engine='xlsxwriter')
        df.to_excel(writer, sheet_name='Ishtirokchilar', index=False)

        workbook  = writer.book
        worksheet = writer.sheets['Ishtirokchilar']
        
        # Ustun kengliklarini sozlash
        worksheet.set_column('A:A', 20) # User ID
        worksheet.set_column('B:B', 20) # Telefon
        worksheet.set_column('C:C', 15) # Promokod

        writer.close()

        # 3. Faylni yuborish
        with open(file_path, "rb") as file:
            await message.answer_document(
                file, 
                caption=f"✅ Ishtirokchilar va kodlar ro'yxati tayyor.\nJami ishlatilgan kodlar: {len(df)} ta"
            )

        os.remove(file_path)

    except Exception as e:
        await message.answer(f"❌ Xatolik yuz berdi: {e}")

from database import get_db_connection # MySQL ulanish funksiyasi

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('list_page_'))
async def process_callback_list_page(callback_query: types.CallbackQuery):
    if callback_query.from_user.id in ADMIN_IDS:
        page = int(callback_query.data.split('_')[2])
        # Bu qism mantiqan o'zgarmaydi, u list_promo_codes funksiyasini chaqiradi
        callback_query.message.text = f"/list_codes {page}"
        await list_promo_codes(callback_query.message)
        await callback_query.answer()
    else:
        await callback_query.answer("⚠️ Bu buyruq faqat admin uchun!", show_alert=True)

@dp.message_handler(commands=['used_codes'])
async def list_used_codes(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        try:
            conn = get_db_connection() # MySQL ulanishi
            cursor = conn.cursor()
            cursor.execute("SELECT code FROM codes WHERE status = 'used'")
            used_codes = cursor.fetchall()
            
            cursor.close()
            conn.close()

            if not used_codes:
                await message.answer("📭 Hali ishlatilgan kodlar mavjud emas.")
                return

            text = f"❌ **Ishlatilgan kodlar ro'yxati ({len(used_codes)} ta):**\n\n"
            for code in used_codes:
                text += f"• `{code[0]}`\n"
            
            # Telegram xabar limiti (4096 belgi) uchun tekshiruv
            if len(text) > 4096:
                for x in range(0, len(text), 4096):
                    await message.answer(text[x:x+4096], parse_mode="Markdown")
            else:
                await message.answer(text, parse_mode="Markdown")
        except Exception as e:
            await message.answer(f"❌ Xatolik: {e}")

# Faqat bitta asosiy admin ID sini shu yerga yozing
SUPER_ADMIN_ID = 183943783

@dp.message_handler(commands=['clear_participants'])
async def clear_data(message: types.Message):
    # Faqat SUPER_ADMIN_ID ga ruxsat beriladi
    if message.from_user.id == SUPER_ADMIN_ID:
        try:
            conn = get_db_connection() # MySQL ulanishi
            cursor = conn.cursor()
            
            # participants jadvalini tozalash
            cursor.execute("DELETE FROM participants")
            conn.commit()
            
            cursor.close()
            conn.close()
            await message.answer("✅ Haftalik o'yin ma'lumotlari muvaffaqiyatli tozalandi!")
        except Exception as e:
            await message.answer(f"❌ Xatolik: {e}")
    else:
        await message.answer("❌ Kechirasiz, bu buyruq faqat asosiy admin uchun!")

@dp.message_handler(commands=['stats'])
async def show_stats(message: types.Message):
    # Faqat adminlar ko'ra olishi uchun tekshiruv (ixtiyoriy)
    if message.from_user.id in ADMIN_IDS:
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # Jami start bosganlar
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]

            # Kod yuborganlar
            cursor.execute("SELECT COUNT(DISTINCT user_id) FROM participants")
            users_with_codes = cursor.fetchone()[0]

            # Jami kodlar soni (1310 ta bo'lishi kerak)
            cursor.execute("SELECT COUNT(*) FROM codes")
            total_codes = cursor.fetchone()[0]

            # Ishlatilmagan kodlar
            cursor.execute("SELECT COUNT(*) FROM codes WHERE status = 'active'")
            active_codes = cursor.fetchone()[0]

            # Ishlatilgan kodlar
            cursor.execute("SELECT COUNT(*) FROM codes WHERE status = 'used'")
            used_codes = cursor.fetchone()[0]

            stats_text = (
                "📊 **Bot Statistikasi:**\n\n"
                f"👥 Jami start bosganlar: {total_users} ta\n"
                f"📝 Kod yuborganlar: {users_with_codes} ta\n\n"
                f"💰 Jami kodlar soni: {total_codes} ta\n"
                f"✅ Faol (Ishlatilmagan): {active_codes} ta\n"
                f"❌ Ishlatilgan: {used_codes} ta"
            )

            await message.answer(stats_text, parse_mode="Markdown")

        except Exception as e:
            await message.answer(f"❌ Xatolik yuz berdi: {e}")
        finally:
            cursor.close()
            conn.close()

@dp.message_handler(commands=['draw'])
async def pick_winner(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            # MySQL-da ishtirokchilarni olish
            cursor.execute("SELECT username, phone, code FROM participants")
            participants = cursor.fetchall()
            
            cursor.close()
            conn.close()

            if not participants:
                await message.answer("📭 Ishtirokchilar mavjud emas.")
                return

            winner = random.choice(participants)
            winner_text = (
                "🎉 **G'olib aniqlandi!**\n\n"
                f"👤 Ism: {winner[0]}\n"
                f"📞 Tel: {winner[1]}\n"
                f"🎫 Omadli kod: `{winner[2]}`\n\nTabriklaymiz!"
            )
            await message.answer(winner_text, parse_mode="Markdown")
        except Exception as e:
            await message.answer(f"❌ Xatolik: {e}")

@dp.message_handler(commands=['reklama'])
async def broadcast_message(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        broadcast_text = message.get_args()
        if not broadcast_text:
            await message.answer("⚠️ Foydalanish: `/reklama matn`")
            return

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            # Users jadvalidan barcha ID-larni olamiz
            cursor.execute("SELECT user_id FROM users")
            users = cursor.fetchall()
            
            cursor.close()
            conn.close()

            count = 0
            for user in users:
                try:
                    await bot.send_message(user[0], broadcast_text)
                    count += 1
                except Exception:
                    continue
            await message.answer(f"✅ Xabar jami {count} ta foydalanuvchiga yuborildi!")
        except Exception as e:
            await message.answer(f"❌ Xatolik: {e}")

# --- FOYDALANUVCHI HANDLERLARI ---

@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # MySQL-da 'OR IGNORE' o'rniga faqat 'IGNORE' ishlatiladi
        cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (%s)", (message.from_user.id,))
        conn.commit()
        
        cursor.close()
        conn.close()

        await message.answer(
            f"Assalomu alaykum, {message.from_user.first_name}!\n\n"
            "😊 Simichka botiga xush kelibsiz. O'yinda qatnashish uchun avval "
            "telefon raqamingizni yuboring:",
            reply_markup=phone_keyboard()
        )
    except Exception as e:
        logging.error(f"Start xatoligi: {e}")

@dp.message_handler(content_types=['contact'])
async def contact_handler(message: types.Message):
    user_temp_data[message.from_user.id] = message.contact.phone_number
    await message.answer(
        "✅ Raqamingiz qabul qilindi. Endi qadoq ichidagi 6 xonali kodni yuboring:\n"
        "Kodlar haftaning yakshanba kuni 16:00 gacha qabul qilinadi",
        reply_markup=main_keyboard()
    )

# Qolgan murojaat va admin javob handlerlari database bilan ishlamagani uchun o'zgarmaydi.

from database import get_db_connection # MySQL ulanishi

# 1. Kod holatini tekshirish funksiyasi
def check_code_status(code):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM codes WHERE code = %s", (code,)) # %s MySQL uchun
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        print(f"Xatolik check_code: {e}")
        return None

# 2. Ishtirokchini saqlash va kodni 'used' qilish
def save_participant(user_id, full_name, phone, code):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Ishtirokchini qo'shish
        cursor.execute(
            "INSERT INTO participants (user_id, username, phone, code) VALUES (%s, %s, %s, %s)",
            (user_id, full_name, phone, code)
        )
        
        # Kod holatini o'zgartirish
        cursor.execute("UPDATE codes SET status = 'used' WHERE code = %s", (code,))
        
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Xatolik save_participant: {e}")

# --- HANDLERLAR ---

@dp.message_handler(commands=['find'])
async def find_promo_code(message: types.Message):
    ADMIN_IDS = [7110271171, 183943783] #
    if message.from_user.id not in ADMIN_IDS:
        return

    args = message.get_args()
    if not args:
        return await message.answer("🔍 Kodni yozing: <code>/find X25308</code>", parse_mode="HTML")

    promo_code = args.strip().upper()

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT status FROM codes WHERE code = ?", (promo_code,))
        result = cursor.fetchone()

        if result:
            status = result[0]
            if status == 'active':
                status_text = "✅ Faol (ishlatilmagan)"
            elif status == 'used':
                status_text = "❌ Ishlatilgan"
                # Kim ishlatganini aniqlash
                cursor.execute("SELECT user_id FROM participants WHERE code = ?", (promo_code,))
                user_info = cursor.fetchone()
                if user_info:
                    status_text += f"\n👤 Kim: <code>{user_info[0]}</code>"
            else:
                status_text = f"❓ Holati: {status}"
            
            await message.answer(f"📦 Kod: <b>{promo_code}</b>\n📊 Holati: {status_text}", parse_mode="HTML")
        else:
            await message.answer(f"❓ <b>{promo_code}</b> bazada mavjud emas.")
        
        cursor.close()
        conn.close()
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")

@dp.message_handler()
async def main_handler(message: types.Message):
    uid = message.from_user.id
    
    # Murojaat qismi o'zgarmaydi (DB ishlatmaydi)
    if user_states.get(uid) == "waiting_for_muro_state":
        # ... (sizning murojaat kodingiz) ...
        return

    if uid not in user_temp_data:
        await message.answer("Iltimos, avval telefon raqamingizni yuboring!", reply_markup=phone_keyboard())
        return

    code = message.text.upper().strip()
    status = check_code_status(code)

    if status == 'active':
        save_participant(uid, message.from_user.full_name, user_temp_data[uid], code)
        # Stiker va javob xabari
        await message.answer(f"✅ Rahmat! {code} kodi qabul qilindi!", reply_markup=main_keyboard())
        await message.answer("Yakshanba 20:00 da Instagramda g'olibni aniqlaymiz.", parse_mode="Markdown")
    elif status == 'used':
        await message.answer("❌ Bu kod allaqachon ishlatilgan!", reply_markup=main_keyboard())
    else:
        await message.answer("⚠️ Kod xato yoki mavjud emas!", reply_markup=main_keyboard())

# Tekshirib ko'rish (Test) uchun
if __name__ == '__main__':
    from aiogram import executor
    init_db() # Jadvallarni MySQL-da yaratish
    executor.start_polling(dp, skip_updates=True)