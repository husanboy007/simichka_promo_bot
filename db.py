import sqlite3

def init_db():
    """Bazani va jadvallarni yaratish"""
    conn = sqlite3.connect('promo_codes.db', timeout=10)
    cursor = conn.cursor()
    # Promo-kodlar jadvali
    cursor.execute('''CREATE TABLE IF NOT EXISTS codes 
                      (code TEXT PRIMARY KEY, status TEXT DEFAULT 'active')''')
    # Ishtirokchilar jadvali
    cursor.execute('''CREATE TABLE IF NOT EXISTS participants 
                      (user_id INTEGER, username TEXT, phone TEXT, code TEXT)''')
    conn.commit()
    conn.close()

def check_code_status(code):
    """Kod holatini tekshirish (active, used yoki None)"""
    conn = sqlite3.connect('promo_codes.db', timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM codes WHERE code=?", (code,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def save_participant(user_id, username, phone, code):
    """Ishtirokchini saqlash va kodni 'used' holatiga o'tkazish"""
    conn = sqlite3.connect('promo_codes.db', timeout=10)
    try:
        cursor = conn.cursor()
        # 1. Kodni ishlatilgan deb belgilash
        cursor.execute("UPDATE codes SET status='used' WHERE code=?", (code,))
        # 2. Ishtirokchini ro'yxatga qo'shish
        cursor.execute("INSERT INTO participants (user_id, username, phone, code) VALUES (?, ?, ?, ?)", 
                       (user_id, username, phone, code))
        conn.commit()
    except Exception as e:
        print(f"Bazaga yozishda xatolik: {e}")
    finally:
        # Bazani har doim yopish (bloklanib qolmasligi uchun)
        conn.close()