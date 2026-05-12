import sqlite3
import os

def init_database(db_path: str = "data/liquidity_risk.db") -> sqlite3.Connection:
    """
    Khởi tạo SQLite database từ schema file.
    Idempotent: chạy nhiều lần không bị lỗi (nhờ IF NOT EXISTS).
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # trả về dict thay vì tuple
    
    # Đọc và chạy schema
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    
    conn.executescript(schema_sql)
    conn.commit()
    
    print(f"✅ Database initialized: {db_path}")
    return conn


def seed_banks(conn: sqlite3.Connection):
    """
    Insert danh sách 6 ngân hàng target.
    """
    banks = [
        ("TCB",  "Ngân hàng TMCP Kỹ thương Việt Nam",      "Techcombank",    "JSB", "HOSE"),
        ("MBB",  "Ngân hàng TMCP Quân đội",                 "MB Bank",        "JSB", "HOSE"),
        ("VPB",  "Ngân hàng TMCP Việt Nam Thịnh vượng",     "VPBank",         "JSB", "HOSE"),
        ("ACB",  "Ngân hàng TMCP Á Châu",                   "ACB",            "JSB", "HOSE"),
        ("VCB",  "Ngân hàng TMCP Ngoại thương Việt Nam",    "Vietcombank",    "SOE", "HOSE"),
        ("OCB",  "Ngân hàng TMCP Phương Đông",              "OCB",            "JSB", "HOSE"),
    ]
    
    conn.executemany("""
        INSERT OR IGNORE INTO banks 
            (bank_code, bank_name_vn, bank_name_en, bank_type, listing_exchange)
        VALUES (?, ?, ?, ?, ?)
    """, banks)
    conn.commit()
    
    count = conn.execute("SELECT COUNT(*) FROM banks").fetchone()[0]
    print(f"✅ Banks seeded: {count} records")


if __name__ == "__main__":
    conn = init_database()
    seed_banks(conn)
    
    # Verify
    print("\n📊 Tables created:")
    tables = conn.execute("""
        SELECT name, type FROM sqlite_master 
        WHERE type IN ('table', 'view', 'index')
        ORDER BY type, name
    """).fetchall()
    for row in tables:
        print(f"   [{row['type']:6}] {row['name']}")
    
    conn.close()