from flask import Flask, render_template, request, jsonify, send_file
import sqlite3
from datetime import datetime
import openpyxl
import os

app = Flask(__name__)
DB_NAME = 'diem_danh.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Bảng cấu hình hệ thống
    c.execute('''CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY, 
                    value TEXT
                )''')
    # Bảng lưu thông tin sinh viên Premium (Đăng ký/Lưu session)
    c.execute('''CREATE TABLE IF NOT EXISTS students (
                    mssv TEXT PRIMARY KEY,
                    ho_ten TEXT,
                    email TEXT,
                    device_id TEXT
                )''')
    # Bảng điểm danh
    c.execute('''CREATE TABLE IF NOT EXISTS diem_danh (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mssv TEXT,
                    ho_ten TEXT,
                    ngay TEXT,
                    thoi_gian TEXT,
                    device_id TEXT
                )''')
    # Bảng báo lỗi thiết bị
    c.execute('''CREATE TABLE IF NOT EXISTS bao_loi (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mssv TEXT,
                    ho_ten TEXT,
                    ly_do TEXT,
                    device_id TEXT,
                    ngay TEXT,
                    thoi_gian TEXT
                )''')
    
    # Giá trị mặc định nếu chưa có
    default_configs = {
        'is_open': 'false',
        'selected_date': datetime.now().strftime('%Y-%m-%d'),
        'close_at': '',
        'network_mode': 'all',
        'class_lat': '16.047079',
        'class_lng': '108.206230',
        'max_distance_meters': '100'
    }
    for k, v in default_configs.items():
        c.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (k, v))
    conn.commit()
    conn.close()

init_db()

def get_configs():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT key, value FROM config")
    rows = c.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}

# ---------- ROUTES GIAO DIỆN ----------
@app.route('/')
def student_page():
    return render_template('index.html')

@app.route('/admin')
def admin_page():
    return render_template('admin.html')

# ---------- API CHO SINH VIÊN (FREE & PREMIUM) ----------

# [PREMIUM] Đăng ký / Lưu thông tin tài khoản 1 lần
@app.route('/api/student/auth', methods=['POST'])
def student_auth():
    data = request.json
    mssv = data.get('mssv', '').strip().upper()
    ho_ten = data.get('ho_ten', '').strip()
    email = data.get('email', '').strip().lower()

    if not mssv or not ho_ten or not email:
        return jsonify({'success': False, 'message': 'Vui lòng nhập đầy đủ thông tin!'}), 400

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO students (mssv, ho_ten, email) VALUES (?, ?, ?)", (mssv, ho_ten, email))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Xác thực tài khoản thành công!'})

# API Thực hiện điểm danh (Cơ bản + Premium 1-Click)
@app.route('/api/student/checkin', methods=['POST'])
def student_checkin():
    data = request.json
    mssv = data.get('mssv', '').strip().upper()
    ho_ten = data.get('ho_ten', '').strip()
    device_id = data.get('device_id', '').strip()
    user_lat = data.get('lat')
    user_lng = data.get('lng')

    configs = get_configs()

    # 1. Kiểm tra cổng điểm danh
    if configs.get('is_open') != 'true':
        return jsonify({'success': False, 'message': 'Cổng điểm danh hiện đang ĐÓNG!'}), 400

    # 2. Kiểm tra vị trí GPS nếu bật chế độ bắt buộc GPS
    if configs.get('network_mode') == 'gps_location':
        if user_lat is None or user_lng is None:
            return jsonify({'success': False, 'message': 'Vui lòng bật định vị GPS trên thiết bị!'}), 400
        
        from math import radians, cos, sin, asin, sqrt
        def haversine(lon1, lat1, lon2, lat2):
            lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
            dlon = lon2 - lon1 
            dlat = lat2 - lat1 
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            return 2 * asin(sqrt(a)) * 6371000 # Mét

        class_lat = float(configs.get('class_lat', 0))
        class_lng = float(configs.get('class_lng', 0))
        max_dist = float(configs.get('max_distance_meters', 100))
        
        dist = haversine(user_lng, user_lat, class_lng, class_lat)
        if dist > max_dist:
            return jsonify({'success': False, 'message': f'Bạn đang ở quá xa lớp học ({int(dist)}m)! Bán kính cho phép: {int(max_dist)}m.'}), 400

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    today = configs.get('selected_date', datetime.now().strftime('%Y-%m-%d'))

    # 3. Kiểm tra trùng MSSV trong ngày
    c.execute("SELECT id FROM diem_danh WHERE mssv = ? AND ngay = ?", (mssv, today))
    if c.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': 'MSSV này đã điểm danh hôm nay rồi!'}), 400

    # 4. Kiểm tra trùng Thiết bị (Chống điểm danh hộ)
    c.execute("SELECT id FROM diem_danh WHERE device_id = ? AND ngay = ?", (device_id, today))
    if c.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': 'Thiết bị này đã được dùng để điểm danh cho sinh viên khác hôm nay!'}), 400

    now_time = datetime.now().strftime('%H:%M:%S')
    c.execute("INSERT INTO diem_danh (mssv, ho_ten, ngay, thoi_gian, device_id) VALUES (?, ?, ?, ?, ?)",
              (mssv, ho_ten, today, now_time, device_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': f'Điểm danh thành công cho {ho_ten} ({mssv})!'})

# API Báo lỗi thiết bị
@app.route('/api/student/bao-loi', methods=['POST'])
def bao_loi():
    data = request.json
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    now_date = datetime.now().strftime('%Y-%m-%d')
    now_time = datetime.now().strftime('%H:%M:%S')
    c.execute("INSERT INTO bao_loi (mssv, ho_ten, ly_do, device_id, ngay, thoi_gian) VALUES (?, ?, ?, ?, ?, ?)",
              (data.get('mssv'), data.get('ho_ten'), data.get('ly_do'), data.get('device_id'), now_date, now_time))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Đã gửi yêu cầu báo lỗi tới Cán sự!'})

# ---------- API DÀNH CHO CÁN SỰ (ADMIN) ----------

@app.route('/api/admin/get-config', methods=['GET'])
def get_config_api():
    return jsonify(get_configs())

@app.route('/api/admin/update-config', methods=['POST'])
def update_config_api():
    data = request.json
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    for k, v in data.items():
        c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (k, str(v).lower() if isinstance(v, bool) else str(v)))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Đã lưu cấu hình mới!'})

@app.route('/api/admin/list-diem-danh', methods=['GET'])
def list_diem_danh():
    date_val = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, mssv, ho_ten, ngay, thoi_gian, device_id FROM diem_danh WHERE ngay = ? ORDER BY id DESC", (date_val,))
    rows = c.fetchall()
    conn.close()
    return jsonify([{'id': r[0], 'mssv': r[1], 'ho_ten': r[2], 'ngay': r[3], 'thoi_gian': r[4], 'device_id': r[5]} for r in rows])

@app.route('/api/admin/delete-diem-danh', methods=['POST'])
def delete_diem_danh():
    rec_id = request.json.get('id')
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM diem_danh WHERE id = ?", (rec_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Đã xóa record!'})

@app.route('/api/admin/list-bao-loi', methods=['GET'])
def list_bao_loi():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, mssv, ho_ten, ly_do, device_id, ngay, thoi_gian FROM bao_loi ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return jsonify([{'id': r[0], 'mssv': r[1], 'ho_ten': r[2], 'ly_do': r[3], 'device_id': r[4], 'ngay': r[5], 'thoi_gian': r[6]} for r in rows])

@app.route('/api/admin/resolve-bao-loi', methods=['POST'])
def resolve_bao_loi():
    data = request.json
    rec_id = data.get('id')
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM bao_loi WHERE id = ?", (rec_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Đã xử lý xong báo lỗi!'})

@app.route('/api/admin/export', methods=['GET'])
def export_excel():
    export_type = request.args.get('type', 'all')
    val = request.args.get('value', '')

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    if export_type == 'day' and val:
        c.execute("SELECT mssv, ho_ten, ngay, thoi_gian FROM diem_danh WHERE ngay = ?", (val,))
    elif export_type == 'month' and val:
        c.execute("SELECT mssv, ho_ten, ngay, thoi_gian FROM diem_danh WHERE ngay LIKE ?", (f"{val}%",))
    else:
        c.execute("SELECT mssv, ho_ten, ngay, thoi_gian FROM diem_danh")
        
    rows = c.fetchall()
    conn.close()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "DiemDanh"
    ws.append(["STT", "MSSV", "Họ và Tên", "Ngày", "Giờ"])

    for idx, r in enumerate(rows, 1):
        ws.append([idx, r[0], r[1], r[2], r[3]])

    file_path = "DiemDanh_Export.xlsx"
    wb.save(file_path)
    return send_file(file_path, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
