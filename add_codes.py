import sqlite3
from db import init_db

def upload_from_file(file_name):
    init_db() # Bazani tekshirish
    conn = sqlite3.connect('promo_codes.db')
    cursor = conn.cursor()
    
    try:
        # Faylni o'qish
        with open(file_name, 'r') as f:
            # Bo'sh bo'lmagan qatorlarni olish va probellarni o'chirish
            codes = [(line.strip().upper(), 'active') for line in f if line.strip()]
        
        # Kodlarni bazaga quyish (takrorlanishdan himoyalangan)
        cursor.executemany("INSERT OR IGNORE INTO codes (code, status) VALUES (?, ?)", codes)
        conn.commit()
        print(f"✅ Muvaffaqiyatli! {len(codes)} ta kod ko'rib chiqildi va yangilari bazaga qo'shildi.")
        
    except FileNotFoundError:
        print(f"❌ Xato: '{file_name}' fayli topilmadi!")
    finally:
        conn.close()

if __name__ == "__main__":
    upload_from_file('kodlar.txt')