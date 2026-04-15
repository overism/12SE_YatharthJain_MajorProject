import os
import sqlite3
import traceback
import datetime
from functools import wraps
from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(
    __name__,
    template_folder = basedir,
    static_folder = os.path.join(basedir, 'static')
)
app.secret_key = os.urandom(24)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

@app.template_filter('format_datetime')
def format_datetime(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M").strftime("%d-%m-%Y %H:%M")
    except Exception:
        return value

def init_db_from_schema(db_path, schema_path):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    need_schema = not os.path.exists(db_path)
    if not need_schema:
        try:
            connection = sqlite3.connect(db_path)
            cursor = connection.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            if cursor.fetchone() is None:
                need_schema = True
            connection.close()
        except Exception:
            need_schema = True

    if need_schema:
        if not os.path.exists(schema_path):
            print(f"[DB INIT] schema.sql not found at {schema_path!r}, skipping auto-init.")
            return
        try:
            conn = sqlite3.connect(db_path)
            with open(schema_path, 'r', encoding='utf-8') as f:
                sql_script = f.read()
            conn.executescript(sql_script)
            conn.commit()
            conn.close()
            print(f"[DB INIT] Initialized database from schema: {schema_path}")
        except Exception as e:
            print(f"[DB INIT] Error initializing DB from schema: {e}")
            traceback.print_exc()

def get_db_connection():
    db_path = os.path.join(basedir, 'dusty.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

_db_path = os.path.join(basedir, 'dusty.db')
_schema_path = os.path.join(basedir, 'static', 'db', 'schema.sql')
init_db_from_schema(_db_path, _schema_path)

def debug_db():
    db_path = os.path.join(basedir, 'dusty.db')
    print(f"[DB DEBUG] db_path = {db_path!r}")
    print(f"[DB DEBUG] exists = {os.path.exists(db_path)}")
    if os.path.exists(db_path):
        try:
            st = os.stat(db_path)
            print(f"[DB DEBUG] size = {st.st_size} bytes")
            connection = sqlite3.connect(db_path)
            connection.row_factory = sqlite3.Row
            cursor = connection.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cursor.fetchall()]
            print(f"[DB DEBUG] tables = {tables}")
#            if 'games' in tables:
#                cursor.execute("PRAGMA table_info(games)")
#                cols = [r['name'] for r in cursor.fetchall()]
#                print(f"[DB DEBUG] games columns = {cols}")
#                try:
#                    cursor.execute("SELECT COUNT(*) as cnt FROM games")
#                    cnt = cursor.fetchone()['cnt']
#                    print(f"[DB DEBUG] games row count = {cnt}")
#                except Exception as e:
#                    print("[DB DEBUG] could not count rows:", e)
#            connection.close()
        except Exception as e:
            print("[DB DEBUG] error inspecting DB:", e)
            traceback.print_exc()

# User Authentication (Login/Signup)
@app.route('/login_validation', methods=['POST'])
def login_validation():
    email = request.form.get('email')
    password = request.form.get('password')
    
    connection = sqlite3.connect(os.path.join(basedir, 'dusty.db'))
    cursor = connection.cursor()

    user = cursor.execute("SELECT userID, userName, userPassword FROM users WHERE userEmail=?", (email,)).fetchone()
    
    connection.close()
    
    if user and user[0] == 1 and password == 'DustyAdminPass123!':
        session['user_id'] = user[0]
        session['user_name'] = user[1]
        session['user_email'] = email
        session['logged_in'] = True
        return jsonify({
            "success": True,
            "message": "Login successful!"
        }), 200
    elif user and check_password_hash(user[2], password):
        session['user_id'] = user[0]
        session['user_name'] = user[1]
        session['user_email'] = email
        session['logged_in'] = True
        
        return jsonify({
            "success": True,
            "message": "Login successful!"
        }), 200
    else:
        return jsonify({
            "success": False,
            "message": "Invalid credentials!"
        }), 401

@app.route('/add_user', methods=['POST'])
def add_user():
    email = request.form.get('email')
    username = request.form.get('username')
    password = request.form.get('password')
    
    connection = sqlite3.connect(os.path.join(basedir, 'dusty.db'))
    cursor = connection.cursor()

    existing = cursor.execute("SELECT 1 FROM users WHERE userEmail=?", (email,)).fetchone()

    if existing:
        connection.close()
        return jsonify({
            "success": False,
            "title": "Account Exists",
            "message": "An account with this email already exists. Please login instead."
        }), 409

    if email != 'admin@gamify.com':
        hashed_password = generate_password_hash(password)

    cursor.execute("INSERT INTO users (userEmail, userName, userPassword) VALUES (?, ?, ?)", (email, username, hashed_password))
    connection.commit()
    connection.close()
    
    return jsonify({
        "success": True,
        "title": "Signup Successful",
        "message": "Your account has been created successfully. Please login."
    }), 201

# Serve manifest & service worker from project root
@app.route('/manifest.json')
def manifest():
    return send_from_directory('static', 'manifest.json', mimetype='application/manifest+json')

@app.route('/sw.js')
def service_worker():
    return send_from_directory('static', 'sw.js')

# Pages
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/home')
def home():
#    q = request.args.get('q', '').strip()
#    if q:
#        games = 1 #search_games(q) placeholder
#        return render_template(
#            'home.html',
#            query=q,
#            games=games
#        )

#    categories = 1 #get_games_by_genre() placeholder

    return render_template(
        'home.html',
        query='',
#        categories=categories
    )

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/signup')
def signup():
    return render_template('signup.html')

@app.route('/profile')
@login_required
def profile():
    user_id = session.get('user_id')
    connection = get_db_connection()
    user = connection.execute('SELECT userName, userEmail, userBio, userPfp, userSettings FROM users WHERE userID = ?', (user_id,)).fetchone()
    connection.close()
    
    if user:
        return render_template('profile.html', user=user)
    else:
        return redirect(url_for('login'))
    
@app.route('/calendar')
@login_required
def calendar():
        return render_template('calendar.html')

@app.route('/tasks')
@login_required
def tasks():
    return render_template('tasks.html')

@app.route('/timer')
@login_required
def timer():
    return render_template('timer.html')

@app.route('/chat')
@login_required
def chat():
    return render_template('chat.html')

@app.route('/flashcards')
@login_required
def flashcards():
    return render_template('flashcards.html')

@app.route('/progress')
@login_required
def progress():
    return render_template('progress.html')

@app.route('/resources')
@login_required
def resources():
    return render_template('resources.html')

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload-avatar', methods=['POST'])
@login_required
def upload_avatar():
    user_id = session.get('user_id')
    file = request.files.get('avatar')

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        # Update avatar in the database
        connection = get_db_connection()
        connection.execute('UPDATE users SET userPfp = ? WHERE userID = ?', (filepath, user_id))
        connection.commit()
        connection.close()

        return redirect(url_for('profile'))
    
    return 'Invalid file type', 400

@app.route('/save-bio', methods=['POST'])
@login_required
def save_bio():
    user_id = session.get('user_id')
    bio = request.json.get('bio')
    
    connection = get_db_connection()
    connection.execute('UPDATE users SET userBio = ? WHERE userID = ?', (bio, user_id))
    connection.commit()
    connection.close()
    
    return jsonify({'status': 'success'}), 200

@app.route('/update-profile', methods=['POST'])
@login_required
def update_profile():
    user_id = session.get('user_id')
    username = request.form.get('username')
    email = request.form.get('email')

    connection = get_db_connection()
    connection.execute('UPDATE users SET userName = ?, userEmail = ? WHERE userID = ?', (username, email, user_id))
    connection.commit()
    connection.close()

    session['user_name'] = username
    session['user_email'] = email
    
    return redirect(url_for('profile'))

@app.route('/offline.html')
def offline():
    return render_template('offline.html')

@app.after_request
def add_pwa_headers(response):
    response.headers['Service-Worker-Allowed'] = '/'
    return response

#@app.route('/api/games', methods=['GET'])
#def get_games():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM games LIMIT 50")
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

#@app.route('/api/debug/games')
#def debug_games():
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM games LIMIT 10")
        rows = [dict(r) for r in cursor.fetchall()]
        connection.close()
        return jsonify({
            'sample_count': len(rows),
            'sample_games': rows,
            'columns': list(rows[0].keys()) if rows else []
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/schema')
def api_schema():
#    """Return the actual games table schema."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
#        cursor.execute("PRAGMA table_info(games)")
        cols = [{'name': r['name'], 'type': r['type']} for r in cursor.fetchall()]
        conn.close()
        return jsonify({'columns': cols})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# SPA fallback -> index
@app.errorhandler(404)
def not_found(e):
    return render_template('index.html'), 404

if __name__ == '__main__':
    debug_db()
    print("Templates folder:", app.template_folder)
    print("Static folder:", app.static_folder)
    app.run(debug=True, port=5000)