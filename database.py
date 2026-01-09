import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    # Faqat SQLite-ga ulanish
    conn = sqlite3.connect('promo_codes.db')
    conn.row_factory = sqlite3.Row
    return conn