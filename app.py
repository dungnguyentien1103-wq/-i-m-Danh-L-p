import os
import math
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
import openpyxl
from io import BytesIO

app = Flask(__name__)

# ==========================================
# 1. CẤU HÌNH BẢO MẬT & BIẾN MÔI TRƯỜNG (CLOUD / RENDER)
# ==========================================
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-super-safe-123')
DATABASE_URL = os.environ.get('DATABASE_URL')

# Cấu hình GPS mặc định hệ thống (Tọa độ trường/lớp & bán kính cho phép tính bằng mét)
DEFAULT_CONFIG = {
    "lat": 16.0738,
    "lng": 108.1499,
    "radius": 100 # mét
}

# ==========================================
# 2. KẾT NỐI CƠ SỞ DỮ LIỆU ĐA NĂNG (POSTGRESQL & SQLITE)
# ==========================================
def get_db_connection():
    if DATABASE_URL:
        db_url = DATABASE_URL.replace("postgres://", "postgresql://")
        conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
        return conn, "postgres"
    else:
        conn = sqlite3.connect('database.db')
        conn.row_factory = sqlite3.Row
        return conn, "sqlite"

# ==========================================
# 3. KHỞI TẠO CƠ SỞ DỮ LIỆU TỰ ĐỘNG
# ==========================================
def init_db():
    conn, db_type = get_db_connection()
    cursor = conn.cursor()

    if db_type == "postgres":
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS students (
                student_id VARCHAR(50) PRIMARY KEY,
                full_name VARCHAR(100),
                class_code VARCHAR(50),
                has_premium INT DEFAULT 0,
                device_hash VARCHAR(100)
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS class_admins (
                username VARCHAR(50) PRIMARY KEY,
                password VARCHAR(100),
                class_code VARCHAR(50) UNIQUE,
                is_super INT DEFAULT 0
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS error_reports (
                id SERIAL PRIMARY KEY,
                student_id VARCHAR(50),
                student_name VARCHAR(100),
                class_code VARCHAR(50),
                error_type VARCHAR(100),
                description TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS checkin_logs (
                id SERIAL PRIMARY KEY,
                student_id VARCHAR(50),
                full_name VARCHAR(100),
                class_code VARCHAR(50),
                device_hash VARCHAR(100),
                lat FLOAT,
                lng FLOAT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_features (
                feature_key TEXT PRIMARY KEY,
                feature_name TEXT,
                is_free_tier INTEGER DEFAULT 1
            );
        ''')
        # Tạo Super Admin mặc định nếu chưa có
        cursor.execute("SELECT * FROM class_admins WHERE username = %s", ('admin',))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO class_admins (username, password, class_code, is_super) VALUES (%s, %s, %s, %s)",
                           ('admin', 'admin123', 'ALL', 1))
    else:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS students (
                student_id TEXT PRIMARY KEY,
                full_name TEXT,
                class_code TEXT,
                has_premium INTEGER DEFAULT 0,
                device_hash TEXT
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS class_admins (
                username TEXT PRIMARY KEY,
                password TEXT,
                class_code TEXT UNIQUE,
                is_super INTEGER DEFAULT 0
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS error_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT,
                student_name TEXT,
                class_code TEXT,
                error_type TEXT,
                description TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS checkin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT,
                full_name TEXT,
                class_code TEXT,
                device_hash TEXT,
                lat REAL,
                lng REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_features (
                feature_key TEXT PRIMARY KEY,
                feature_name TEXT,
                is_free_tier INTEGER DEFAULT 1
            );
        ''')
        # Tạo Super Admin mặc định nếu chưa có
        cursor.execute("SELECT * FROM class_admins WHERE username = ?", ('admin',))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO class_admins (username, password, class_code, is_super) VALUES (?, ?, ?, ?)",
                           ('admin', 'admin123', 'ALL', 1))

    conn.commit()
    conn.close()

try:
    init_db()
except Exception as e:
    print(f"Lỗi khởi tạo CSDL: {e}")

# Công thức Haversine tính khoảng cách giữa 2 tọa độ GPS (mét)
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000  # Bán kính Trái Đất (mét)
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# ==========================================
# 4. ROUTE TRANG GIAO DIỆN HTML
# ==========================================
@app.route('/')
def index_student():
    return render_template('student.html')

@app.route('/class-admin')
def page_class_admin():
    return render_template('class_admin.html')

@app.route('/super-admin')
def page_super_admin():
    return render_template('super_admin.html')

@app.route('/login-page')
def page_login():
    return render_template('login.html')

@app.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index_student'))

# ==========================================
# 5. API DÀNH CHO SINH VIÊN
# ==========================================
@app.route('/api/student/check-status', methods=['POST'])
def check_status():
    data = request.json or {}
    student_id = data.get('student_id', '').strip()

    if not student_id:
        return jsonify({'registered': False, 'message': 'Chưa nhập MSSV'})

    conn, db_type = get_db_connection()
    cursor = conn.cursor()

    if db_type == "postgres":
        cursor.execute("SELECT * FROM students WHERE student_id = %s", (student_id,))
    else:
        cursor.execute("SELECT * FROM students WHERE student_id = ?", (student_id,))

    student = cursor.fetchone()
    conn.close()

    if student:
        return jsonify({
            'registered': True,
            'full_name': student['full_name'],
            'class_code': student['class_code'],
            'has_premium': bool(student['has_premium'])
        })
    return jsonify({'registered': False})

@app.route('/api/student/register-first-time', methods=['POST'])
def register_first_time():
    data = request.json or {}
    student_id = data.get('student_id', '').strip()
    full_name = data.get('full_name', '').strip()
    class_code = data.get('class_code', '').strip()

    if not student_id or not full_name or not class_code:
        return jsonify({'success': False, 'message': 'Vui lòng nhập đầy đủ thông tin!'})

    conn, db_type = get_db_connection()
    cursor = conn.cursor()

    try:
        if db_type == "postgres":
            cursor.execute('''
                INSERT INTO students (student_id, full_name, class_code, has_premium)
                VALUES (%s, %s, %s, 0)
                ON CONFLICT (student_id) DO NOTHING
            ''', (student_id, full_name, class_code))
        else:
            cursor.execute('''
                INSERT OR IGNORE INTO students (student_id, full_name, class_code, has_premium)
                VALUES (?, ?, ?, 0)
            ''', (student_id, full_name, class_code))

        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Đăng ký thành công!'})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': f'Lỗi đăng ký: {str(e)}'})

@app.route('/api/student/checkin-v2', methods=['POST'])
def checkin_v2():
    data = request.json or {}
    student_id = data.get('student_id', '').strip()
    full_name = data.get('full_name', '').strip()
    class_code = data.get('class_code', '').strip()
    device_hash = data.get('device_hash', '').strip()
    user_lat = data.get('lat')
    user_lng = data.get('lng')

    if not student_id or user_lat is None or user_lng is None:
        return jsonify({'success': False, 'message': 'Thiếu dữ liệu điểm danh hoặc vị trí GPS!'})

    dist = calculate_distance(user_lat, user_lng, DEFAULT_CONFIG['lat'], DEFAULT_CONFIG['lng'])
    if dist > DEFAULT_CONFIG['radius']:
        return jsonify({
            'success': False, 
            'message': f'Điểm danh thất bại! Bạn đang cách lớp {int(dist)}m (Cho phép max {DEFAULT_CONFIG["radius"]}m).'
        })

    conn, db_type = get_db_connection()
    cursor = conn.cursor()

    if db_type == "postgres":
        cursor.execute("SELECT device_hash FROM students WHERE student_id = %s", (student_id,))
    else:
        cursor.execute("SELECT device_hash FROM students WHERE student_id = ?", (student_id,))

    row = cursor.fetchone()

    if row and row['device_hash']:
        if row['device_hash'] != device_hash:
            conn.close()
            return jsonify({'success': False, 'message': 'Cảnh báo: Phát hiện thiết bị lạ! Không thể điểm danh hộ.'})
    else:
        if db_type == "postgres":
            cursor.execute("UPDATE students SET device_hash = %s WHERE student_id = %s", (device_hash, student_id))
        else:
            cursor.execute("UPDATE students SET device_hash = ? WHERE student_id = ?", (device_hash, student_id))

    if db_type == "postgres":
        cursor.execute('''
            INSERT INTO checkin_logs (student_id, full_name, class_code, device_hash, lat, lng)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (student_id, full_name, class_code, device_hash, user_lat, user_lng))
    else:
        cursor.execute('''
            INSERT INTO checkin_logs (student_id, full_name, class_code, device_hash, lat, lng)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (student_id, full_name, class_code, device_hash, user_lat, user_lng))

    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': f'Điểm danh thành công cho sinh viên {student_id}!'})

@app.route('/api/student/report-error', methods=['POST'])
def report_error():
    data = request.json or {}
    conn, db_type = get_db_connection()
    cursor = conn.cursor()

    if db_type == "postgres":
        cursor.execute('''
            INSERT INTO error_reports (student_id, student_name, class_code, error_type, description)
            VALUES (%s, %s, %s, %s, %s)
        ''', (data.get('student_id'), data.get('student_name'), data.get('class_code'), data.get('error_type'), data.get('description')))
    else:
        cursor.execute('''
            INSERT INTO error_reports (student_id, student_name, class_code, error_type, description)
            VALUES (?, ?, ?, ?, ?)
        ''', (data.get('student_id'), data.get('student_name'), data.get('class_code'), data.get('error_type'), data.get('description')))

    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Gửi báo lỗi thành công! Cán sự lớp sẽ hỗ trợ kiểm tra.'})

@app.route('/api/student/remember-session', methods=['POST'])
def remember_student_session():
    data = request.json or {}
    student_id = data.get('student_id', '').strip()
    class_code = data.get('class_code', '').strip().upper()

    if not student_id or not class_code:
        return jsonify({'success': False, 'message': 'Thiếu thông tin sinh viên hoặc mã lớp.'})

    conn, db_type = get_db_connection()
    cursor = conn.cursor()

    if db_type == "postgres":
        cursor.execute("SELECT * FROM class_admins WHERE class_code = %s", (class_code,))
    else:
        cursor.execute("SELECT * FROM class_admins WHERE class_code = ?", (class_code,))
    
    if not cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': 'Mã lớp không tồn tại trong hệ thống!'})

    session['student_id'] = student_id
    session['class_code'] = class_code
    conn.close()
    
    return jsonify({'success': True, 'message': 'Đã ghi nhớ phiên đăng nhập sinh viên.'})

# ==========================================
# 6. API DÀNH CHO CÁN SỰ LỚP & SUPER ADMIN
# ==========================================
@app.route('/api/class-admin/toggle-student-premium', methods=['POST'])
@app.route('/api/super-admin/toggle-premium-manual', methods=['POST'])
def toggle_premium():
    data = request.json or {}
    student_id = data.get('student_id', '').strip()
    status = data.get('status')

    if not student_id:
        return jsonify({'success': False, 'message': 'Vui lòng nhập MSSV!'})

    conn, db_type = get_db_connection()
    cursor = conn.cursor()

    if db_type == "postgres":
        cursor.execute("UPDATE students SET has_premium = %s WHERE student_id = %s", (status, student_id))
    else:
        cursor.execute("UPDATE students SET has_premium = ? WHERE student_id = ?", (status, student_id))

    conn.commit()
    conn.close()

    act = "Mở" if status == 1 else "Khóa"
    return jsonify({'success': True, 'message': f'Đã {act} thành công Premium cho MSSV: {student_id}'})

@app.route('/api/class-admin/register', methods=['POST'])
def register_class_admin():
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    class_code = data.get('class_code', '').strip().upper()

    if not username or not password or not class_code:
        return jsonify({'success': False, 'message': 'Vui lòng nhập đầy đủ Tài khoản, Mật khẩu và Mã lớp!'})

    conn, db_type = get_db_connection()
    cursor = conn.cursor()

    try:
        if db_type == "postgres":
            cursor.execute("SELECT * FROM class_admins WHERE class_code = %s", (class_code,))
        else:
            cursor.execute("SELECT * FROM class_admins WHERE class_code = ?", (class_code,))
        
        if cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'message': f'Mã lớp "{class_code}" đã tồn tại! Vui lòng chọn mã lớp khác.'})

        if db_type == "postgres":
            cursor.execute('''
                INSERT INTO class_admins (username, password, class_code, is_super)
                VALUES (%s, %s, %s, 0)
            ''', (username, password, class_code))
        else:
            cursor.execute('''
                INSERT INTO class_admins (username, password, class_code, is_super)
                VALUES (?, ?, ?, 0)
            ''', (username, password, class_code))

        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': f'Tạo lớp thành công với mã: {class_code}!'})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': f'Lỗi: Tên tài khoản quản lý này đã được sử dụng.'})

@app.route('/api/super-admin/delete-class-admin', methods=['POST'])
def delete_class_admin():
    data = request.json or {}
    username = data.get('username', '').strip()

    conn, db_type = get_db_connection()
    cursor = conn.cursor()

    if db_type == "postgres":
        cursor.execute("DELETE FROM class_admins WHERE username = %s", (username,))
    else:
        cursor.execute("DELETE FROM class_admins WHERE username = ?", (username,))

    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': f'Đã xóa thành công tài khoản cán sự: {username}'})

@app.route('/api/class-admin/get-errors', methods=['GET'])
def get_errors():
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM error_reports ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        result.append({
            'id': r['id'],
            'student_id': r['student_id'],
            'student_name': r['student_name'],
            'class_code': r['class_code'],
            'error_type': r['error_type'],
            'description': r['description'],
            'timestamp': str(r['timestamp'])
        })
    return jsonify(result)

@app.route('/api/super-admin/clear-errors', methods=['POST'])
def clear_errors():
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM error_reports")
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Đã dọn dẹp sạch toàn bộ báo lỗi hệ thống!'})

@app.route('/api/super-admin/update-config', methods=['POST'])
def update_config():
    data = request.json or {}
    DEFAULT_CONFIG['lat'] = data.get('lat', DEFAULT_CONFIG['lat'])
    DEFAULT_CONFIG['lng'] = data.get('lng', DEFAULT_CONFIG['lng'])
    DEFAULT_CONFIG['radius'] = data.get('radius', DEFAULT_CONFIG['radius'])
    return jsonify({'success': True, 'message': 'Đã cập nhật tọa độ GPS và bán kính thành công!'})

@app.route('/api/admin/toggle-feature-tier', methods=['POST'])
def toggle_feature_tier():
    data = request.json or {}
    feature_key = data.get('feature_key')
    is_free = data.get('is_free')

    conn, db_type = get_db_connection()
    cursor = conn.cursor()

    if db_type == "postgres":
        cursor.execute("UPDATE system_features SET is_free_tier = %s WHERE feature_key = %s", (is_free, feature_key))
    else:
        cursor.execute("UPDATE system_features SET is_free_tier = ? WHERE feature_key = ?", (is_free, feature_key))

    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Đã cập nhật trạng thái kinh doanh tính năng thành công!'})

@app.route('/api/class-admin/export-excel', methods=['GET'])
def export_excel():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Nhat Ky Diem Danh"

    ws.append(["STT", "MSSV", "Họ và Tên", "Mã Lớp", "Thiết Bị (Device Hash)", "Thời Gian Điểm Danh"])

    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM checkin_logs ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()

    for idx, row in enumerate(rows, 1):
        ws.append([
            idx,
            row['student_id'],
            row['full_name'],
            row['class_code'],
            row['device_hash'],
            str(row['timestamp'])
        ])

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)

    return send_file(
        stream,
        as_attachment=True,
        download_name='danh_sach_diem_danh_chi_tiet.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

# ==========================================
# 7. KHỞI CHẠY SERVER VỚI CỔNG ĐỘNG
# ==========================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
