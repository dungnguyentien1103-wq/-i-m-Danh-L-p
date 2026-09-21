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
# --- CHÈN THÊM ĐOẠN NÀY VÀO HÀM init_db() TRONG database.py ---

# Bảng Báo lỗi điểm danh (để Cán sự duyệt)
cursor.execute('''
    CREATE TABLE IF NOT EXISTS attendance_errors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT,
        student_name TEXT,
        class_code TEXT,
        error_type TEXT,
        description TEXT,
        status TEXT DEFAULT 'PENDING', -- PENDING, APPROVED, REJECTED
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
''')

# Bảng Log hoạt động của Cán sự / Admin
cursor.execute('''
    CREATE TABLE IF NOT EXISTS admin_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        action TEXT,
        class_code TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
''')

# Bảng Cấu hình Lịch trình mở cổng tự động (Theo tuần / tháng)
cursor.execute('''
    CREATE TABLE IF NOT EXISTS auto_schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_code TEXT,
        day_of_week INTEGER, -- 0: T2, 1: T3 ... 6: CN
        start_time TEXT,     -- "07:30"
        end_time TEXT,       -- "08:00"
        is_active INTEGER DEFAULT 1
    )
''')

# Bảng Quản lý Quyền Premium linh hoạt (Dynamic Premium Features)
cursor.execute('''
    CREATE TABLE IF NOT EXISTS premium_features (
        feature_key TEXT PRIMARY KEY,
        feature_name TEXT,
        is_enabled INTEGER DEFAULT 1
    )
''')

# Khởi tạo một số quyền Premium mặc định
default_features = [
    ('one_click_checkin', 'Điểm danh 1-Touch không cần nhập lại tên/lớp', 1),
    ('auto_fill_location', 'Tự động lấy vị trí định vị cao cấp', 1),
    ('priority_error_report', 'Gửi báo lỗi ưu tiên cho Cán sự', 1)
]
cursor.executemany("INSERT OR IGNORE INTO premium_features VALUES (?, ?, ?)", default_features)
