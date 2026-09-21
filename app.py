import os
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
import openpyxl
from io import BytesIO

app = Flask(__name__)

# ==========================================
# 1. CẤU HÌNH BÀO MẬT & BIẾN MÔI TRƯỜNG (CLOUD)
# ==========================================
# Lấy SECRET_KEY từ biến môi trường của Render (nếu không có sẽ dùng chuỗi mặc định cho dev)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-super-safe-123')

# Lấy DATABASE_URL từ Render (Thường là PostgreSQL)
DATABASE_URL = os.environ.get('DATABASE_URL')


# ==========================================
# 2. HÀM KẾT NỐI CƠ SỞ DỮ LIỆU ĐA NĂNG
# ==========================================
def get_db_connection():
    """
    Tự động kết nối PostgreSQL nếu chạy trên Cloud (có DATABASE_URL),
    hoặc dùng SQLite local nếu chạy ở máy cá nhân.
    """
    if DATABASE_URL:
        # Xử lý chuẩn hóa URL cho psycopg2 (nếu Render trả về postgres://)
        db_url = DATABASE_URL.replace("postgres://", "postgresql://")
        conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
        return conn, "postgres"
    else:
        # Dùng file CSDL local nếu chưa cài DATABASE_URL
        conn = sqlite3.connect('database.db')
        conn.row_factory = sqlite3.Row
        return conn, "sqlite"


# ==========================================
# 3. KHOỞI TẠO BẢNG DỮ LIỆU (TỰ ĐỘNG)
# ==========================================
def init_db():
    conn, db_type = get_db_connection()
    cursor = conn.cursor()

    # Bảng sinh viên
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            student_id VARCHAR(50) PRIMARY KEY,
            full_name VARCHAR(100),
            class_code VARCHAR(50),
            has_premium INT DEFAULT 0
        )
    ''')

    # Bảng báo lỗi
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS error_reports (
            id SERIAL PRIMARY KEY if db_type == "postgres" else "id INTEGER PRIMARY KEY AUTOINCREMENT",
            student_id VARCHAR(50),
            student_name VARCHAR(100),
            class_code VARCHAR(50),
            error_type VARCHAR(100),
            description TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()

# Chạy khởi tạo bảng khi app cất cánh
try:
    init_db()
except Exception as e:
    print(f"Lỗi khởi tạo CSDL: {e}")


# ==========================================
# 4. ROUTE GIAO DIỆN HTML (PAGES)
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


# ==========================================
# 5. API XỬ LÝ CHO SINH VIÊN
# ==========================================

# Kiểm tra trạng thái Sinh viên
@app.route('/api/student/check-status', methods=['POST'])
def check_status():
    data = request.json or {}
    student_id = data.get('student_id')

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

# Điểm danh v2 (Tính năng Fingerprint + GPS)
@app.route('/api/student/checkin-v2', methods=['POST'])
def checkin_v2():
    data = request.json or {}
    student_id = data.get('student_id')
    device_hash = data.get('device_hash')
    lat = data.get('lat')
    lng = data.get('lng')

    # Tại đây anh bạn xử lý logic kiểm tra GPS & lưu thông tin điểm danh...
    return jsonify({'success': True, 'message': f'Điểm danh thành công! (Device: {device_hash})'})

# Báo lỗi sự cố
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
    return jsonify({'success': True, 'message': 'Gửi báo lỗi thành công! Cán sự lớp sẽ kiểm tra.'})


# ==========================================
# 6. API XỬ LÝ CHO CÁN SỰ LỚP & SUPER ADMIN
# ==========================================

# Mở / Khóa Premium Sinh viên
@app.route('/api/class-admin/toggle-student-premium', methods=['POST'])
@app.route('/api/super-admin/toggle-premium-manual', methods=['POST'])
def toggle_premium():
    data = request.json or {}
    student_id = data.get('student_id')
    status = data.get('status')

    conn, db_type = get_db_connection()
    cursor = conn.cursor()

    if db_type == "postgres":
        cursor.execute("UPDATE students SET has_premium = %s WHERE student_id = %s", (status, student_id))
    else:
        cursor.execute("UPDATE students SET has_premium = ? WHERE student_id = ?", (status, student_id))

    conn.commit()
    conn.close()
    
    action_str = "Mở" if status == 1 else "Khóa"
    return jsonify({'success': True, 'message': f'Đã {action_str} thành công Premium cho MSSV: {student_id}'})

# Xuất dữ liệu ra file Excel
@app.route('/api/class-admin/export-excel', methods=['GET'])
def export_excel():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Danh Sach Diem Danh"
    
    # Tiêu đề bảng
    ws.append(["MSSV", "Họ và Tên", "Mã Lớp", "Trạng Thái Premium"])
    
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students")
    rows = cursor.fetchall()
    conn.close()

    for row in rows:
        ws.append([row['student_id'], row['full_name'], row['class_code'], "Có" if row['has_premium'] else "Không"])

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)

    return send_file(
        stream,
        as_attachment=True,
        download_name='danh_sach_diem_danh.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


# ==========================================
# 7. CẤU HÌNH CỔNG ĐỘNG ĐỂ CHẠY TRÊN RENDER
# ==========================================
if __name__ == '__main__':
    # Lấy cổng do Render cấp tự động qua biến môi trường PORT (mặc định là 5000 nếu chạy máy local)
    port = int(os.environ.get('PORT', 5000))
    # Chạy trên tất cả IP (0.0.0.0) để Render kết nối được
    app.run(host='0.0.0.0', port=port, debug=False)
