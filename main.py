import logging
import pandas as pd
import io
import os
import random
import re
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from dotenv import load_dotenv
from db import init_db, check_code_status, save_participant, get_connection
import asyncio
from aiogram import executor
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

# Klaviaturalar
def main_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("👨‍💻 Adminga murojaat qilish"))
    return kb

def phone_keyboard():
    return ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True).add(
        KeyboardButton("📱 Telefon raqamni yuborish", request_contact=True)
    )

# --- ADMIN BUYRUQLARI ---

# db.py ichiga yoki main.py boshiga qo'shing
def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    # Hamma start bosganlar uchun jadval
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    # Kod yuborganlar jadvali (mavjud)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS participants (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id BIGINT,
        username VARCHAR(255),
        phone VARCHAR(32),
        code VARCHAR(64),
        INDEX(code),
        CONSTRAINT fk_code
            FOREIGN KEY (code) REFERENCES codes(code)
            ON UPDATE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    conn.commit()
    cursor.close()
    conn.close()

@dp.callback_query_handler(lambda c: c.data.startswith('all_'))
async def process_all_participants_report(callback_query: types.CallbackQuery):
    action = callback_query.data.split('_')[1]
    conn = get_connection()
    
    try:
        # 1. Bazadagi barcha ma'lumotlarni o'qiymiz
        df = pd.read_sql_query("SELECT * FROM participants", conn)
    except Exception as e:
        await callback_query.answer(f"Baza xatosi: {e}", show_alert=True)
        return
    finally:
        conn.close()

    if df.empty:
        await callback_query.answer("Hozircha ishtirokchilar yo'q.", show_alert=True)
        return

    # Ism ustunini bazadagi ehtimoliy nomlar bo'yicha aniqlab olamiz
    # Agar 'full_name' bo'lmasa, 'name'ni, u ham bo'lmasa 'username'ni qidiradi
    def get_user_name(row):
        return row.get('full_name') or row.get('name') or row.get('username') or "Noma'lum"

    if action == 'text':
        # --- MATN KO'RINISHIDA YUBORISH ---
        text = f"👥 **Barcha ishtirokchilar ({len(df)} ta):**\n\n"
        for _, row in df.iterrows():
            phone = row.get('phone', 'Noma\'lum')
            code = row.get('code', 'Noma\'lum')
            name = get_user_name(row)
            text += f"• {phone} | {code} | {name}\n"
        
        # Telegram xabari 4096 belgidan oshsa, bo'lib yuboradi
        if len(text) > 4096:
            for x in range(0, len(text), 4096):
                await bot.send_message(callback_query.from_user.id, text[x:x+4096], parse_mode="Markdown")
        else:
            await bot.send_message(callback_query.from_user.id, text, parse_mode="Markdown")
            
    elif action == 'excel':
        # --- EXCEL KO'RINISHIDA YUBORISH ---
        report_df = pd.DataFrame()
        
        # Ustunlarni siz xohlagan tartibda tuzamiz: A: Telefon, B: Kod, C: Ism
        report_df['Telefon Nomer'] = df.get('phone', 'Noma\'lum')
        report_df['Promokod'] = df.get('code', 'Noma\'lum')
        report_df['Ism / Nik'] = df.apply(get_user_name, axis=1)

        # Barcha ma'lumotlarni matnga o'tkazamiz (E+09 xatosi va astype xatosi bo'lmasligi uchun)
        report_df = report_df.astype(str)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            report_df.to_excel(writer, index=False, sheet_name='Ishtirokchilar')
            
            workbook = writer.book
            worksheet = writer.sheets['Ishtirokchilar']
            
            # Sarlavhani formatlash (Rangli va qalin)
            header_format = workbook.add_format({
                'bold': True, 
                'bg_color': '#D7E4BC', 
                'border': 1,
                'align': 'center'
            })
            
            # Ustun kengliklarini sozlash
            worksheet.set_column('A:A', 20) # Telefon
            worksheet.set_column('B:B', 15) # Kod
            worksheet.set_column('C:C', 30) # Nik
            
            for col_num, value in enumerate(report_df.columns.values):
                worksheet.write(0, col_num, value, header_format)

        output.seek(0)
        await bot.send_document(
            callback_query.from_user.id, 
            types.InputFile(output, filename="ishtirokchilar_bazasi.xlsx"),
            caption=f"✅ Excel hisoboti tayyor.\nJami: {len(df)} ta ishtirokchi"
        )
    
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('used_'))
async def process_used_codes_report(callback_query: types.CallbackQuery):
    action = callback_query.data.split('_')[1]
    conn = get_connection()
    try:
        # SELECT * barcha ustunlarni avtomatik oladi, xato bermaydi
        df = pd.read_sql_query("SELECT * FROM participants", conn)
    except Exception as e:
        await callback_query.answer(f"Baza xatosi: {e}", show_alert=True)
        return
    finally:
        conn.close()

    if df.empty:
        await callback_query.answer("📭 Ma'lumot topilmadi.", show_alert=True)
        return

    if action == 'text':
        text = "❌ **Ishlatilgan kodlar:**\n\n" + "\n".join([f"• `{c}`" for c in df['code']])
        await bot.send_message(callback_query.from_user.id, text[:4096], parse_mode="Markdown")
    elif action == 'excel':
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Kodlar')
        output.seek(0)
        await bot.send_document(
            callback_query.from_user.id, 
            types.InputFile(output, filename="used_codes.xlsx"),
            caption="📊 Ishlatilgan kodlar hisoboti"
        )
    
    await callback_query.answer()

@dp.message_handler(commands=['list_codes'])
async def list_promo_codes(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        args = message.get_args()
        page = int(args) if args.isnumeric() else 1
        limit = 50
        offset = (page - 1) * limit

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM codes")
        total_codes = cursor.fetchone()[0]
        cursor.execute(
            "SELECT code, status FROM codes LIMIT %s OFFSET %s",
            (limit, offset)
        )
        codes = cursor.fetchall()
        cursor.close()
        conn.close()

        if not codes:
            await message.answer("📭 Bu sahifada kodlar mavjud emas.")
            return

        total_pages = (total_codes + limit - 1) // limit
        text = f"📋 **Promokodlar ro'yxati (Sahifa {page}/{total_pages}):**\n\n"
        
        for code, status in codes:
            icon = "✅" if status == 'active' else "❌"
            text += f"{icon} `{code}` - {status}\n"
        
        kb = InlineKeyboardMarkup(row_width=2)
        buttons = []
        if page > 1:
            buttons.append(InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"list_page_{page-1}"))
        if page < total_pages:
            buttons.append(InlineKeyboardButton(text="Oldinga ➡️", callback_data=f"list_page_{page+1}"))
        kb.add(*buttons)

        await message.answer(text, parse_mode="Markdown", reply_markup=kb)

@dp.message_handler(commands=['all_participants'])
async def get_all_participants(message: types.Message):
    # Admin tekshiruvi (.env dan yoki ro'yxatdan)
    if message.from_user.id in ADMIN_IDS:
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        btn_text = types.InlineKeyboardButton("📝 Matn ko'rinishida", callback_data="all_text")
        btn_excel = types.InlineKeyboardButton("📊 Excel ko'rinishida", callback_data="all_excel")
        keyboard.add(btn_text, btn_excel)

        await message.answer("Barcha ishtirokchilar ro'yxatini qanday shaklda olmoqchisiz?", reply_markup=keyboard)
    else:
        await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q!")

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('list_page_'))
async def process_callback_list_page(callback_query: types.CallbackQuery):
    if callback_query.from_user.id in ADMIN_IDS:
        page = int(callback_query.data.split('_')[2])
        callback_query.message.text = f"/list_codes {page}"
        await list_promo_codes(callback_query.message)
        await callback_query.answer()
    else:
        await callback_query.answer("⚠️ Bu buyruq faqat admin uchun!", show_alert=True)

@dp.message_handler(commands=['used_codes'])
async def list_used_codes(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        btn_text = types.InlineKeyboardButton("📝 Matn", callback_data="used_text")
        btn_excel = types.InlineKeyboardButton("📊 Excel", callback_data="used_excel")
        keyboard.add(btn_text, btn_excel)
        await message.answer("Hisobot turini tanlang:", reply_markup=keyboard)

@dp.message_handler(commands=['clear_participants'])
async def clear_data(message: types.Message):
    # Faqat SUPER_ADMIN_ID ga ruxsat beriladi
    if message.from_user.id == SUPER_ADMIN_ID:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM participants")
        conn.commit()
        cursor.close()
        conn.close()
        await message.answer("✅ Haftalik o'yin ma'lumotlari muvaffaqiyatli tozalandi!")
    else:
        # Boshqa adminlar bossa ham rad etiladi
        await message.answer("❌ Kechirasiz, bu buyruq faqat asosiy admin uchun!")

@dp.message_handler(commands=['stats'])
async def get_stats(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Jami start bosganlar
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        # Kod yuborganlar soni
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM participants")
        participants_count = cursor.fetchone()[0]
        
        # Barcha promo-kodlar (Jami)
        cursor.execute("SELECT COUNT(*) FROM codes")
        total_codes = cursor.fetchone()[0]
        
        # Faol va ishlatilgan kodlar
        cursor.execute("SELECT COUNT(*) FROM codes WHERE status = 'active'")
        active_codes = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM codes WHERE status = 'used'")
        used_codes = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        stats_text = (
            "📊 **Bot Statistikasi:**\n\n"
            f"👥 **Jami start bosganlar:** {total_users} ta\n"
            f"🎫 **Kod yuborganlar:** {participants_count} ta\n"
            "------------------------\n"
            f"💰 **Jami kodlar soni:** {total_codes} ta\n"
            f"✅ Faol (ishlatilmagan): {active_codes} ta\n"
            f"❌ Ishlatilgan: {used_codes} ta"
        )
        await message.answer(stats_text, parse_mode="Markdown")

@dp.message_handler(commands=['draw'])
async def pick_winner(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        conn = get_connection()
        cursor = conn.cursor()
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

@dp.message_handler(commands=['clear_participants'])
async def clear_all_participants(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM participants")
        conn.commit()
        cursor.close()
        conn.close()
        await message.answer("🗑 **Haftalik ishtirokchilar o'chirildi!**\n(Ishlatilgan kodlar admin uchun saqlanib qoldi)")

@dp.message_handler(commands=['reklama'])
async def broadcast_message(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        broadcast_text = message.get_args()
        if not broadcast_text:
            await message.answer("⚠️ Foydalanish: `/reklama matn`")
            return

        conn = get_connection()
        cursor = conn.cursor()
        # Endi participants'dan emas, users jadvalidan olamiz
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

# --- FOYDALANUVCHI HANDLERLARI ---

@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    # Foydalanuvchini users jadvaliga saqlash
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT IGNORE INTO users (user_id) VALUES (%s)",
        (message.from_user.id,)
    )
    conn.commit()
    cursor.close()
    conn.close()

    # Siz xohlagan to'liq matn:
    await message.answer(
        f"Assalomu alaykum, {message.from_user.first_name}!\n\n"
        "😊 Simichka botiga xush kelibsiz. O'yinda qatnashish uchun avval "
        "telefon raqamingizni yuboring:",
        reply_markup=phone_keyboard()
    )

@dp.message_handler(lambda message: message.text == "👨‍💻 Adminga murojaat qilish")
async def start_murojaat(message: types.Message):
    user_states[message.from_user.id] = "waiting_for_muro_state"
    await message.answer("📝 Murojaatingizni yozing:", reply_markup=ReplyKeyboardRemove())

@dp.message_handler(lambda message: message.from_user.id in ADMIN_IDS and message.reply_to_message)
async def admin_reply(message: types.Message):
    match = re.search(r"🆔:(\d+)", message.reply_to_message.text)
    if match:
        user_id = match.group(1)
        try:
            await bot.send_message(user_id, f"👨‍💻 **Admin javobi:**\n\n{message.text}", reply_markup=main_keyboard())
            await message.answer("✅ Javob yuborildi!")
        except Exception as e: await message.answer(f"❌ Xatolik: {e}")

@dp.message_handler(content_types=['contact'])
async def contact_handler(message: types.Message):
    user_temp_data[message.from_user.id] = message.contact.phone_number
    await message.answer(
        "✅ Raqamingiz qabul qilindi. Endi qadoq ichidagi 6 xonali kodni yuboring:\n"
        "Kodlar haftaning yakshanba kuni 16:00 gacha qabul qilinadi",
        reply_markup=main_keyboard()
    )

@dp.message_handler(commands=['find'])
async def find_promo_code(message: types.Message):
    # Adminlarni tekshirish
    ADMIN_IDS = [7110271171, 183943783, 1328801]
    if message.from_user.id not in ADMIN_IDS:
        return

    args = message.get_args()
    if not args:
        return await message.answer("🔍 Kodni yozing: <code>/find X25308</code>", parse_mode="HTML")

    # Kodni tozalash: bo'sh joylarni olib tashlash va KATTA harfga o'tkazish
    promo_code = args.strip().upper()

    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # 'codes' jadvalidan qidirish (stats kodingizga asosan)
        cursor.execute(
            "SELECT status FROM codes WHERE code = %s",
            (promo_code,)
        )
        result = cursor.fetchone()

        if result:
            status = result[0]
            # Statusni tekshirish
            if status == 'active':
                status_text = "✅ Faol (ishlatilmagan)"
            elif status == 'used':
                status_text = "❌ Ishlatilgan"
                # Kim ishlatganini aniqlash
                cursor.execute(
                    "SELECT user_id FROM participants WHERE code = %s",
                    (promo_code,)
                )
                user_info = cursor.fetchone()
                if user_info:
                    status_text += f"\n👤 Kim: <code>{user_info[0]}</code>"
            else:
                status_text = f"❓ Holati: {status}"
            
            await message.answer(f"📦 Kod: <b>{promo_code}</b>\n📊 Holati: {status_text}", parse_mode="HTML")
        else:
            # Agar kod bazada topilmasa
            await message.answer(f"❓ <b>{promo_code}</b> bazada mavjud emas.")
        cursor.close()
        conn.close()
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")

@dp.message_handler()
async def main_handler(message: types.Message):
    uid = message.from_user.id
    
    # 1. Murojaat kutish holati
    if user_states.get(uid) == "waiting_for_muro_state":
        user_states[uid] = None
        phone = user_temp_data.get(uid, "Noma'lum")
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, f"📩 **Yangi murojaat!**\n\n👤 {message.from_user.full_name}\n📞 {phone}\n💬 {message.text}\n🆔:{uid}")
            except Exception: pass
        await message.answer("✅ Xabaringiz yuborildi.", reply_markup=main_keyboard())
        return

    # 2. Telefon raqami tekshiruvi
    if uid not in user_temp_data:
        await message.answer("Iltimos, avval telefon raqamingizni yuboring!", reply_markup=phone_keyboard())
        return

    # 3. Kodni tekshirish
    code = message.text.upper().strip()
    status = check_code_status(code)

    if status == 'active':
        # Siz xohlagan yangi tabrik matni
        success_text = (
            "✅ **TABRIKLAYMIZ 🥳**\n\n"
            "Kod qabul qilindi siz o'yin ishtirokchisiga aylandingiz!\n\n"
            "Yakshanba kuni soat 20:00 da [INSTAGRAM](https://www.instagram.com/quqon_bozorida?igsh=MXd6ZWd1MmN0cTEyNw==) 👈"
            "profili orqali jonli efirda g'olibni aniqlaymiz. \n\n"
            "Bot orqali barcha ishtirokchilarga g'olib bo'lgan promokod yuboriladi."
        )

        # ADMINLAR UCHUN: Bazaga yozmaydi, faqat tekshiradi
        if uid in ADMIN_IDS:
            try: 
                await message.answer_sticker("CAACAgIAAxkBAAMlaUnxsZIrK2QGHcyDi1JMKXoI2JQAAqoYAAIPZQhKBszc59D9vtM2BA")
            except Exception: pass
            
            await message.answer(f"✅ Kod to'g'ri! (Admin test: {code})", reply_markup=main_keyboard())
            await message.answer(success_text, parse_mode="Markdown", disable_web_page_preview=False)
            await message.answer("⚠️ **Diqqat: Siz adminsiz, bu kod bazaga yozilmadi.**")
            return 

        # ODDIY FOYDALANUVCHILAR UCHUN: Bazaga saqlash va javob berish
        save_participant(uid, message.from_user.full_name, user_temp_data.get(uid), code)
        try: 
            await message.answer_sticker("CAACAgIAAxkBAAMlaUnxsZIrK2QGHcyDi1JMKXoI2JQAAqoYAAIPZQhKBszc59D9vtM2BA")
        except Exception: pass
        
        await message.answer(success_text, parse_mode="Markdown", disable_web_page_preview=False)

    elif status == 'used':
        await message.answer("❌ Bu kod allaqachon ishlatilgan!", reply_markup=main_keyboard())
    else:
        await message.answer("⚠️ Kod xato yoki mavjud emas!", reply_markup=main_keyboard())

@dp.message_handler(content_types=['video'])
async def handle_admin_video_broadcast(message: types.Message):
    # Faqat adminlar reklama yubora oladi
    if message.from_user.id in ADMIN_IDS:
        # Agar video ostiga "reklama" so'zi yozilgan bo'lsa
        if message.caption and "reklama" in message.caption.lower():
            video_id = message.video.file_id
            # "reklama" so'zini olib tashlab, qolgan matnni caption sifatida qoldiramiz
            caption_text = message.caption.replace("reklama", "").strip()
            
            conn = get_connection()
            try:
                # Barcha foydalanuvchilarni bazadan olamiz
                # 'user_id' ustuni jadvalingizda qanday nomlanganini tekshiring
                df = pd.read_sql_query("SELECT DISTINCT user_id FROM participants", conn)
            except Exception as e:
                await message.answer(f"❌ Baza bilan bog'liq xatolik: {e}")
                return
            finally:
                conn.close()

            if df.empty:
                await message.answer("📭 Bazada foydalanuvchilar topilmadi.")
                return

            sent_count = 0
            status_msg = await message.answer(f"🚀 Reklama yuborish boshlandi ({len(df)} ta foydalanuvchiga)...")

            for user_id in df['user_id']:
                try:
                    # Har bir foydalanuvchiga videoni yuboramiz
                    await bot.send_video(chat_id=user_id, video=video_id, caption=caption_text)
                    sent_count += 1
                    # Telegram spam deb hisoblamasligi uchun kichik tanaffus
                    await asyncio.sleep(0.05) 
                except Exception:
                    # Agar foydalanuvchi botni bloklagan bo'lsa, o'tkazib yuboramiz
                    continue
            
            await status_msg.edit_text(f"✅ Reklama yakunlandi!\nJami: {sent_count} ta foydalanuvchiga yuborildi.")
        else:
            # Agar "reklama" so'zi bo'lmasa, shunchaki file_id ni terminalga chiqaradi
            print(f"🎥 Video file_id: {message.video.file_id}")
            await message.answer("ℹ️ Reklama yuborish uchun video ostiga 'reklama' so'zini yozing.")

'''
# Bu ma'lumotlarni Olimhon berishi kerak
WEBHOOK_HOST = 'https://semechka.blizetaxi.uz' # Server manzili
WEBHOOK_PATH = '/webhook'
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# Webapp sozlamalari
WEBAPP_HOST = '127.0.0.1'
WEBAPP_PORT = 2004

async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)
    # Ma'lumotlar bazasini ham shu yerda ishga tushiramiz
    init_db()

async def on_shutdown(dp):
    await bot.delete_webhook()

if __name__ == '__main__':
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT,
    )
'''

# Tekshirib ko'rish (Test) uchun quyidagi kodni ishlating:
if __name__ == '__main__':
    init_db() # Ma'lumotlar bazasini yoqish

    asyncio.set_event_loop(asyncio.new_event_loop())
    executor.start_polling(dp, skip_updates=True)