from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import sqlite3
from datetime import datetime
import pandas as pd
import io
import math

app = Flask(__name__)
CORS(app)

def init_db():
    conn = sqlite3.connect('diem_danh.db')
    c = conn.cursor()
    # Bảng lưu điểm danh (Thêm cột device_id)
    c.execute('''CREATE TABLE IF NOT EXISTS diem_danh (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mssv TEXT,
                    ho_ten TEXT,
                    ngay_diem_danh TEXT,
                    thoi_gian TEXT,
                    device_id TEXT
                )''')
    # Bảng lưu báo cáo lỗi thiết bị
    c.execute('''CREATE TABLE IF NOT EXISTS bao_loi (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mssv TEXT,
                    ho_ten TEXT,
                    ly_do TEXT,
                    ngay TEXT,
                    thoi_gian TEXT,
                    device_id TEXT,
                    trang_thai TEXT DEFAULT 'pending'
                )''')
    # Bảng cấu hình
    c.execute('''CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )''')
    
    c.execute("INSERT OR IGNORE INTO config VALUES ('is_open', 'false')")
    c.execute("INSERT OR IGNORE INTO config VALUES ('close_at', '')")
    c.execute("INSERT OR IGNORE INTO config VALUES ('selected_date', '')")
    c.execute("INSERT OR IGNORE INTO config VALUES ('network_mode', 'all')")
    c.execute("INSERT OR IGNORE INTO config VALUES ('allowed_ip_prefix', '192.168.1.')")
    c.execute("INSERT OR IGNORE INTO config VALUES ('class_lat', '10.762622')")
    c.execute("INSERT OR IGNORE INTO config VALUES ('class_lng', '106.660172')")
    c.execute("INSERT OR IGNORE INTO config VALUES ('max_distance_meters', '100')")
    
    conn.commit()
    conn.close()

init_db()

def get_config():
    conn = sqlite3.connect('diem_danh.db')
    c = conn.cursor()
    c.execute("SELECT key, value FROM config")
    config = dict(c.fetchall())
    conn.close()
    return config

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# --- ROUTES SINH VIÊN ---
@app.route('/')
def student_page():
    return render_template('student.html')

@app.route('/api/check-status', methods=['GET'])
def check_status():
    config = get_config()
    is_open = config.get('is_open') == 'true'
    close_at = config.get('close_at', '')

    if is_open and close_at:
        now = datetime.now()
        try:
            close_time = datetime.strptime(close_at, '%Y-%m-%dT%H:%M')
            if now >= close_time:
                is_open = False
                conn = sqlite3.connect('diem_danh.db')
                c = conn.cursor()
                c.execute("UPDATE config SET value = 'false' WHERE key = 'is_open'")
                conn.commit()
                conn.close()
        except Exception:
            pass

    return jsonify({
        'is_open': is_open, 
        'close_at': close_at,
        'network_mode': config.get('network_mode', 'all')
    })

@app.route('/api/diem-danh', methods=['POST'])
def submit_diem_danh():
    config = get_config()
    is_open = config.get('is_open') == 'true'
    
    if not is_open:
        return jsonify({'status': 'error', 'message': 'Cổng điểm danh hiện đang ĐÓNG!'}), 400

    data = request.json
    mssv = data.get('mssv', '').strip()
    ho_ten = data.get('ho_ten', '').strip()
    device_id = data.get('device_id', '').strip()
    user_lat = data.get('lat')
    user_lng = data.get('lng')

    if not mssv or not ho_ten:
        return jsonify({'status': 'error', 'message': 'Vui lòng điền đầy đủ thông tin!'}), 400

    ngay_dd = config.get('selected_date') or datetime.now().strftime('%Y-%m-%d')
    conn = sqlite3.connect('diem_danh.db')
    c = conn.cursor()

    # 1. Kiểm tra chống trùng MSSV trong ngày
    c.execute("SELECT * FROM diem_danh WHERE mssv = ? AND ngay_diem_danh = ?", (mssv, ngay_dd))
    if c.fetchone():
        conn.close()
        return jsonify({'status': 'error', 'message': f'MSSV {mssv} đã điểm danh cho ngày hôm nay rồi!'}), 400

    # 2. Kiểm tra chống trùng Thiết bị (Device ID) trong ngày
    if device_id:
        c.execute("SELECT mssv FROM diem_danh WHERE device_id = ? AND ngay_diem_danh = ?", (device_id, ngay_dd))
        exist_device = c.fetchone()
        if exist_device:
            conn.close()
            return jsonify({
                'status': 'error', 
                'message': f'Thiết bị này đã được dùng để điểm danh cho MSSV {exist_device[0]}! Vui lòng báo lỗi nếu cần hỗ trợ.'
            }), 400

    # 3. Kiểm tra Vị trí GPS nếu chọn chế độ GPS
    mode = config.get('network_mode', 'all')
    if mode == 'gps_location':
        if not user_lat or not user_lng:
            conn.close()
            return jsonify({'status': 'error', 'message': 'Vui lòng bật GPS/Vị trí trên thiết bị để điểm danh!'}), 400
        
        target_lat = float(config.get('class_lat', 0))
        target_lng = float(config.get('class_lng', 0))
        max_dist = float(config.get('max_distance_meters', 100))

        dist = calculate_distance(float(user_lat), float(user_lng), target_lat, target_lng)
        if dist > max_dist:
            conn.close()
            return jsonify({'status': 'error', 'message': f'Bạn đang ở ngoài phạm vi cho phép ({int(dist)}m / tối đa {int(max_dist)}m)!'}), 403

    thoi_gian_hien_tai = datetime.now().strftime('%H:%M:%S')
    c.execute("INSERT INTO diem_danh (mssv, ho_ten, ngay_diem_danh, thoi_gian, device_id) VALUES (?, ?, ?, ?, ?)",
              (mssv, ho_ten, ngay_dd, thoi_gian_hien_tai, device_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'message': 'Điểm danh thành công!'})

# Báo lỗi thiết bị gửi về Admin
@app.route('/api/bao-loi', methods=['POST'])
def submit_bao_loi():
    data = request.json
    mssv = data.get('mssv', '').strip()
    ho_ten = data.get('ho_ten', '').strip()
    ly_do = data.get('ly_do', '').strip()
    device_id = data.get('device_id', '').strip()
    
    ngay_hien_tai = datetime.now().strftime('%Y-%m-%d')
    thoi_gian = datetime.now().strftime('%H:%M:%S')

    conn = sqlite3.connect('diem_danh.db')
    c = conn.cursor()
    c.execute("INSERT INTO bao_loi (mssv, ho_ten, ly_do, ngay, thoi_gian, device_id) VALUES (?, ?, ?, ?, ?, ?)",
              (mssv, ho_ten, ly_do, ngay_hien_tai, thoi_gian, device_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'message': 'Đã gửi báo lỗi thành công tới Cán sự!'})

# --- ROUTES ADMIN ---
@app.route('/admin')
def admin_page():
    return render_template('admin.html')

@app.route('/api/admin/get-config', methods=['GET'])
def admin_get_config():
    config = get_config()
    return jsonify(config)

@app.route('/api/admin/update-config', methods=['POST'])
def update_config():
    data = request.json
    conn = sqlite3.connect('diem_danh.db')
    c = conn.cursor()
    
    keys = ['is_open', 'close_at', 'selected_date', 'network_mode', 'allowed_ip_prefix', 'class_lat', 'class_lng', 'max_distance_meters']
    for k in keys:
        if k in data:
            val = 'true' if data[k] is True else ('false' if data[k] is False else str(data[k]))
            c.execute("UPDATE config SET value = ? WHERE key = ?", (val, k))
            
    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'message': 'Đã cập nhật cấu hình cổng!'})

# Lấy danh sách điểm danh để hiển thị/xóa trên Admin
@app.route('/api/admin/list-diem-danh', methods=['GET'])
def list_diem_danh():
    selected_date = request.args.get('date', '')
    conn = sqlite3.connect('diem_danh.db')
    c = conn.cursor()
    if selected_date:
        c.execute("SELECT id, mssv, ho_ten, ngay_diem_danh, thoi_gian, device_id FROM diem_danh WHERE ngay_diem_danh = ? ORDER BY id DESC", (selected_date,))
    else:
        c.execute("SELECT id, mssv, ho_ten, ngay_diem_danh, thoi_gian, device_id FROM diem_danh ORDER BY id DESC LIMIT 100")
    
    rows = c.fetchall()
    conn.close()
    
    result = [{'id': r[0], 'mssv': r[1], 'ho_ten': r[2], 'ngay': r[3], 'thoi_gian': r[4], 'device_id': r[5]} for r in rows]
    return jsonify(result)

# Xóa 1 bản ghi điểm danh
@app.route('/api/admin/delete-diem-danh', methods=['POST'])
def delete_diem_danh():
    record_id = request.json.get('id')
    conn = sqlite3.connect('diem_danh.db')
    c = conn.cursor()
    c.execute("DELETE FROM diem_danh WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'message': 'Đã xóa bản ghi điểm danh!'})

# Lấy danh sách báo lỗi thiết bị
@app.route('/api/admin/list-bao-loi', methods=['GET'])
def list_bao_loi():
    conn = sqlite3.connect('diem_danh.db')
    c = conn.cursor()
    c.execute("SELECT id, mssv, ho_ten, ly_do, ngay, thoi_gian, device_id FROM bao_loi WHERE trang_thai = 'pending' ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    result = [{'id': r[0], 'mssv': r[1], 'ho_ten': r[2], 'ly_do': r[3], 'ngay': r[4], 'thoi_gian': r[5], 'device_id': r[6]} for r in rows]
    return jsonify(result)

# Giải quyết báo lỗi (Reset lượt điểm danh thiết bị)
@app.route('/api/admin/resolve-bao-loi', methods=['POST'])
def resolve_bao_loi():
    data = request.json
    loi_id = data.get('id')
    device_id = data.get('device_id')
    action = data.get('action') # 'reset' hoặc 'dismiss'

    conn = sqlite3.connect('diem_danh.db')
    c = conn.cursor()
    
    if action == 'reset' and device_id:
        # Xóa dữ liệu điểm danh gắn liền với thiết bị đó trong ngày để cho điểm danh lại
        ngay_hien_tai = datetime.now().strftime('%Y-%m-%d')
        c.execute("DELETE FROM diem_danh WHERE device_id = ? AND ngay_diem_danh = ?", (device_id, ngay_hien_tai))
    
    c.execute("UPDATE bao_loi SET trang_thai = 'resolved' WHERE id = ?", (loi_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'message': 'Đã xử lý xong yêu cầu báo lỗi!'})

@app.route('/api/admin/export', methods=['GET'])
def export_excel():
    filter_type = request.args.get('type')
    filter_val = request.args.get('value')

    conn = sqlite3.connect('diem_danh.db')
    query = "SELECT mssv AS 'Mã Sinh Viên', ho_ten AS 'Họ và Tên', ngay_diem_danh AS 'Ngày', thoi_gian AS 'Giờ Điểm Danh' FROM diem_danh"
    params = []

    if filter_type == 'day' and filter_val:
        query += " WHERE ngay_diem_danh = ?"
        params.append(filter_val)
    elif filter_type == 'month' and filter_val:
        query += " WHERE strftime('%Y-%m', ngay_diem_danh) = ?"
        params.append(filter_val)

    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='DiemDanh')
    output.seek(0)

    filename = f"diem_danh_{filter_val if filter_val else 'tat_ca'}.xlsx"
    return send_file(output, download_name=filename, as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)