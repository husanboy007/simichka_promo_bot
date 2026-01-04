import mysql.connector
from mysql.connector import Error

DB_CONFIG = {
    "host": "217.30.169.148",
    "user": "semechka_user",
    "password": "Seme4k@2026",
    "database": "semechka",
    "autocommit": False
}

def get_connection():
    return mysql.connector.connect(**DB_CONFIG)


def init_db():
    """Bazani va jadvallarni yaratish"""
    conn = get_connection()
    cursor = conn.cursor()

    # Promo-kodlar jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS codes (
            code VARCHAR(64) PRIMARY KEY,
            status ENUM('active', 'used') DEFAULT 'active'
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    # Ishtirokchilar jadvali
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


def check_code_status(code):
    """Kod holatini tekshirish (active, used yoki None)"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT status FROM codes WHERE code = %s",
        (code,)
    )
    result = cursor.fetchone()

    cursor.close()
    conn.close()

    return result[0] if result else None


def save_participant(user_id, username, phone, code):
    """Ishtirokchini saqlash va kodni 'used' holatiga o'tkazish"""
    conn = get_connection()

    try:
        cursor = conn.cursor()

        # 1. Kod active ekanligini tekshiramiz
        cursor.execute(
            "SELECT status FROM codes WHERE code = %s FOR UPDATE",
            (code,)
        )
        row = cursor.fetchone()

        if not row or row[0] != 'active':
            raise Exception("Kod mavjud emas yoki allaqachon ishlatilgan")

        # 2. Kodni ishlatilgan deb belgilash
        cursor.execute(
            "UPDATE codes SET status = 'used' WHERE code = %s",
            (code,)
        )

        # 3. Ishtirokchini qo‘shish
        cursor.execute("""
            INSERT INTO participants (user_id, username, phone, code)
            VALUES (%s, %s, %s, %s)
        """, (user_id, username, phone, code))

        conn.commit()

    except Exception as e:
        conn.rollback()
        print(f"Bazaga yozishda xatolik: {e}")

    finally:
        cursor.close()
        conn.close()
