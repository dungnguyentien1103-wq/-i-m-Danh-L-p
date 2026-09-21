from flask import Flask, render_template, request, jsonify, send_file
import sqlite3
import datetime
import pandas as pd
import os

app = Flask(__name__)
DB_NAME = "database.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Bảng cấu hình
    c.execute('''CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )''')
    # Bảng điểm danh
    c.execute('''CREATE TABLE IF NOT EXISTS diem_danh (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mssv TEXT,
                    ho_ten TEXT,
                    email TEXT,
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
    
    # Khởi tạo giá trị cấu hình mặc định nếu chưa có
    default_configs = {
        'is_open': 'true',
        'selected_date': datetime.date.today().strftime("%Y-%m-%d"),
        'close_at': '',
        'network_mode': 'all',
        'class_lat': '',
        'class_lng': '',
        'max_distance_meters': '100'
    }
    for key, val in default_configs.items():
        c.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (key, val))
    
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

# --- ROUTES GIAO DIỆN ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

# --- API CÁN SỰ (ADMIN) ---
@app.route('/api/admin/get-config', methods=['GET'])
def get_config():
    return jsonify(get_configs())

@app.route('/api/admin/update-config', methods=['POST'])
def update_config():
    data = request.json
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    for key, val in data.items():
        c.execute("REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(val)))
    conn.commit()
    conn.close()
    return jsonify({"message": "Cập nhật cấu hình thành công!"})

@app.route('/api/admin/list-diem-danh', methods=['GET'])
def list_diem_danh():
    date_filter = request.args.get('date', datetime.date.today().strftime("%Y-%m-%d"))
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, mssv, ho_ten, ngay, thoi_gian, device_id FROM diem_danh WHERE ngay = ? ORDER BY id DESC", (date_filter,))
    rows = c.fetchall()
    conn.close()
    
    result = []
    for r in rows:
        result.append({
            "id": r[0], "mssv": r[1], "ho_ten": r[2], 
            "ngay": r[3], "thoi_gian": r[4], "device_id": r[5]
        })
    return jsonify(result)

@app.route('/api/admin/delete-diem-danh', methods=['POST'])
def delete_diem_danh():
    rec_id = request.json.get('id')
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM diem_danh WHERE id = ?", (rec_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Đã xóa bản ghi!"})

@app.route('/api/admin/list-bao-loi', methods=['GET'])
def list_bao_loi():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, mssv, ho_ten, ly_do, device_id, ngay, thoi_gian FROM bao_loi ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    
    result = []
    for r in rows:
        result.append({
            "id": r[0], "mssv": r[1], "ho_ten": r[2], 
            "ly_do": r[3], "device_id": r[4], "ngay": r[5], "thoi_gian": r[6]
        })
    return jsonify(result)

@app.route('/api/admin/resolve-bao-loi', methods=['POST'])
def resolve_bao_loi():
    data = request.json
    bl_id = data.get('id')
    device_id = data.get('device_id')
    action = data.get('action') # 'reset' hoặc 'dismiss'

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    if action == 'reset':
        c.execute("DELETE FROM diem_danh WHERE device_id = ?", (device_id,))
    c.execute("DELETE FROM bao_loi WHERE id = ?", (bl_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Đã xử lý yêu cầu!"})

@app.route('/api/admin/export', methods=['GET'])
def export_data():
    export_type = request.args.get('type', 'all')
    val = request.args.get('value', '')
    
    conn = sqlite3.connect(DB_NAME)
    query = "SELECT mssv AS 'MSSV', ho_ten AS 'Họ và Tên', email AS 'Email', ngay AS 'Ngày', thoi_gian AS 'Thời Gian' FROM diem_danh"
    
    if export_type == 'day' and val:
        query += f" WHERE ngay = '{val}'"
    elif export_type == 'month' and val:
        query += f" WHERE ngay LIKE '{val}%'"
        
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    file_path = "danh_sach_diem_danh.xlsx"
    df.to_excel(file_path, index=False)
    return send_file(file_path, as_attachment=True)

# --- API SINH VIÊN ---
@app.route('/api/student/checkin', methods=['POST'])
def student_checkin():
    data = request.json
    mssv = data.get('mssv')
    ho_ten = data.get('ho_ten')
    email = data.get('email', '')
    device_id = data.get('device_id')
    user_lat = data.get('lat')
    user_lng = data.get('lng')

    configs = get_configs()
    
    if configs.get('is_open') != 'true':
        return jsonify({"success": False, "message": "Cổng điểm danh hiện đang ĐÓNG!"})

    today = datetime.date.today().strftime("%Y-%m-%d")
    now_time = datetime.datetime.now().strftime("%H:%M:%S")

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Kiểm tra trùng thiết bị hoặc MSSV trong ngày
    c.execute("SELECT id FROM diem_danh WHERE ngay = ? AND (mssv = ? OR device_id = ?)", (today, mssv, device_id))
    if c.fetchone():
        conn.close()
        return jsonify({"success": False, "message": "Thiết bị hoặc MSSV này đã điểm danh hôm nay rồi!"})

    # Lưu dữ liệu
    c.execute("INSERT INTO diem_danh (mssv, ho_ten, email, ngay, thoi_gian, device_id) VALUES (?, ?, ?, ?, ?, ?)",
              (mssv, ho_ten, email, today, now_time, device_id))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": f"Điểm danh thành công lúc {now_time}!"})

@app.route('/api/student/bao-loi', methods=['POST'])
def student_bao_loi():
    data = request.json
    today = datetime.date.today().strftime("%Y-%m-%d")
    now_time = datetime.datetime.now().strftime("%H:%M:%S")

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO bao_loi (mssv, ho_ten, ly_do, device_id, ngay, thoi_gian) VALUES (?, ?, ?, ?, ?, ?)",
              (data.get('mssv'), data.get('ho_ten'), data.get('ly_do'), data.get('device_id'), today, now_time))
    conn.commit()
    conn.close()
    return jsonify({"message": "Đã gửi yêu cầu báo lỗi đến Cán sự lớp!"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
