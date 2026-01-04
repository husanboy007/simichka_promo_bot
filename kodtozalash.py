import sqlite3

# Bazaga ulanamiz
conn = sqlite3.connect('promo_codes.db')
cursor = conn.cursor()

try:
    # FAQAT promokodlar jadvalini tozalaymiz
    # Bu orqali foydalanuvchilar (15 ta start bosganlar) o'chib ketmaydi
    cursor.execute("DELETE FROM codes")
    
    conn.commit()
    print("✅ Promokodlar muvaffaqiyatli tozalandi!")
    print("📊 Foydalanuvchilar statistikasi saqlab qolindi.")
except Exception as e:
    print(f"❌ Xatolik: {e}")
finally:
    conn.close()