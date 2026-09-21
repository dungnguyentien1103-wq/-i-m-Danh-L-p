from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from database import get_db, init_db
import math
from datetime import datetime

app = Flask(__name__)
app.secret_key = "secret_key_point_danh_system"

init_db()

# --- HÀM TRỢ GIÚP ---
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000  # Bán kính Trái Đất (mét)
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def get_config():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM config")
    rows = cursor.fetchall()
    conn.close()
    return {row['key']: row['value'] for row in rows}

# --- ROUTE CHÍNH SAU ĐÂY ---

@app.route('/')
def student_page():
    return render_template('student.html')

@app.route('/super-admin')
def super_admin_page():
    if not session.get('is_super'):
        return redirect(url_for('login_page'))
    return render_template('super_admin.html')

@app.route('/canser')
def class_admin_page():
    if not session.get('user_id'):
        return redirect(url_for('login_page'))
    return render_template('class_admin.html')

@app.route('/privacy-policy')
def privacy_page():
    return render_template('privacy.html')

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        data = request.json
        username = data.get('username')
        password = data.get('password')
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM class_admins WHERE username = ? AND password = ?", (username, password))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['class_code'] = user['class_code']
            session['is_super'] = user['is_super']
            return jsonify({'success': True, 'is_super': bool(user['is_super'])})
        return jsonify({'success': False, 'message': 'Sai tài khoản hoặc mật khẩu!'}), 401
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

# --- API DÀNH CHO SINH VIÊN ---

@app.route('/api/student/check-status', methods=['POST'])
def check_student_status():
    data = request.json
    student_id = data.get('student_id')
    
    conn = get_db()
    cursor = conn.cursor()
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
    return jsonify({'registered': False, 'has_premium': False})

@app.route('/api/student/register-first-time', methods=['POST'])
def register_first_time():
    data = request.json
    student_id = data.get('student_id')
    full_name = data.get('full_name')
    class_code = data.get('class_code')
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Tự động mở Premium nếu sinh viên đăng ký lượt đầu thành công
    auto_premium = 1 
    
    try:
        cursor.execute(
            "INSERT INTO students (student_id, full_name, class_code, has_premium) VALUES (?, ?, ?, ?)",
            (student_id, full_name, class_code, auto_premium)
        )
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Đăng ký thành công và kích hoạt Premium 1-Click!'})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': 'Mã sinh viên đã tồn tại!'}), 400

@app.route('/api/student/checkin', methods=['POST'])
def student_checkin():
    data = request.json
    student_id = data.get('student_id')
    full_name = data.get('full_name')
    class_code = data.get('class_code')
    user_lat = float(data.get('lat', 0))
    user_lng = float(data.get('lng', 0))
    
    cfg = get_config()
    if cfg.get('active') != 'true':
        return jsonify({'success': False, 'message': 'Cổng điểm danh hiện đang đóng!'}), 400
        
    admin_lat = float(cfg.get('lat', 0))
    admin_lng = float(cfg.get('lng', 0))
    max_radius = float(cfg.get('radius', 100))
    
    dist = haversine(user_lat, user_lng, admin_lat, admin_lng)
    if dist > max_radius:
        return jsonify({'success': False, 'message': f'Bạn ở ngoài khoảng cách cho phép ({int(dist)}m > {int(max_radius)}m)'}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO attendance (student_id, student_name, class_code, lat, lng, status) VALUES (?, ?, ?, ?, ?, ?)",
        (student_id, full_name, class_code, user_lat, user_lng, 'Hợp lệ')
    )
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Điểm danh thành công!'})

# --- API CÁN SỰ LỚP ---

@app.route('/api/class-admin/create-sub-admin', methods=['POST'])
def create_sub_admin():
    if not session.get('user_id'):
        return jsonify({'success': False, 'message': 'Chưa đăng nhập'}), 401
    
    data = request.json
    username = data.get('username')
    password = data.get('password')
    class_code = data.get('class_code') or session.get('class_code')
    
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO class_admins (username, password, class_code, is_super) VALUES (?, ?, ?, 0)",
                       (username, password, class_code))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Thêm cán sự thành công!'})
    except:
        conn.close()
        return jsonify({'success': False, 'message': 'Tên đăng nhập đã tồn tại!'}), 400

@app.route('/api/class-admin/toggle-student-premium', methods=['POST'])
def class_toggle_premium():
    if not session.get('user_id'):
        return jsonify({'success': False, 'message': 'Chưa đăng nhập'}), 401
        
    data = request.json
    student_id = data.get('student_id')
    status = data.get('status', 1)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE students SET has_premium = ? WHERE student_id = ?", (status, student_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Cập nhật trạng thái Premium cho SV thành công!'})

# --- API SUPER ADMIN ---

@app.route('/api/super-admin/toggle-premium-manual', methods=['POST'])
def super_toggle_premium():
    if not session.get('is_super'):
        return jsonify({'success': False, 'message': 'Không có quyền truy cập'}), 403
        
    data = request.json
    student_id = data.get('student_id')
    status = data.get('status') # 1 hoặc 0
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE students SET has_premium = ? WHERE student_id = ?", (status, student_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Đã điều chỉnh Premium thủ công!'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
