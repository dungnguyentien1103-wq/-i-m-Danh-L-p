import sqlite3

DB_NAME = "diem_danh.db"

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Bảng Cấu hình hệ thống
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # Bảng Tài khoản cán sự / Admin lớp
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS class_admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            class_code TEXT,
            is_super INTEGER DEFAULT 0
        )
    ''')
    
    # Bảng Sinh viên
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT UNIQUE,
            full_name TEXT,
            class_code TEXT,
            has_premium INTEGER DEFAULT 0
        )
    ''')
    
    # Bảng Điểm danh
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT,
            student_name TEXT,
            class_code TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            lat REAL,
            lng REAL,
            status TEXT
        )
    ''')
    
    # Tạo tài khoản Super Admin mặc định nếu chưa có
    cursor.execute("SELECT * FROM class_admins WHERE username = 'admin'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO class_admins (username, password, class_code, is_super) VALUES (?, ?, ?, ?)",
                       ('admin', 'admin123', 'ALL', 1))
        
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Khởi tạo Database thành công!")
