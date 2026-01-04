
from db import init_db, get_connection

def upload_from_file(file_name):
    init_db() # Bazani tekshirish
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Faylni o'qish
        with open(file_name, 'r') as f:
            # Bo'sh bo'lmagan qatorlarni olish va probellarni o'chirish
            codes = [(line.strip().upper(), 'active') for line in f if line.strip()]

        # Hozirgi bazada qaysi kodlar allaqachon bor
        cursor.execute(
            "SELECT code FROM codes WHERE code IN (%s)" %
            ','.join(['%s'] * len(codes)),
            [c[0] for c in codes]
        )
        existing_codes = [row[0] for row in cursor.fetchall()]

        # Qayta insert qilishdan oldin print qilamiz
        ignored_codes = [c[0] for c in codes if c[0] in existing_codes]
        if ignored_codes:
            print("Ignore bo'lgan kodlar:", ignored_codes)

        # Endi insert qilamiz
        cursor.executemany(
            "INSERT IGNORE INTO codes (code, status) VALUES (%s, %s)",
            codes
        )
        conn.commit()
        print(f"✅ Muvaffaqiyatli! {len(codes)} ta kod ko'rib chiqildi va yangilari bazaga qo'shildi.")
        
    except FileNotFoundError:
        print(f"❌ Xato: '{file_name}' fayli topilmadi!")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    upload_from_file('kodlar.txt')