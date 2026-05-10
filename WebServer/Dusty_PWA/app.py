import os
import sqlite3
import traceback
import datetime
from functools import wraps
from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta

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
            if 'events' in tables:
                cursor.execute("PRAGMA table_info(events)")
                cols = [r['name'] for r in cursor.fetchall()]
                print(f"[DB DEBUG] events columns = {cols}")
                try:
                    cursor.execute("SELECT COUNT(*) as cnt FROM events")
                    cnt = cursor.fetchone()['cnt']
                    print(f"[DB DEBUG] events row count = {cnt}")
                except Exception as e:
                    print("[DB DEBUG] could not count rows:", e)
            connection.close()
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
    
#Calendar API and Google Calendar Integration + FullCalendar Setup
def get_google_service(user_id):
    conn = get_db_connection()
    creds_row = conn.execute(
        "SELECT accessToken, refreshToken, expiry FROM google_creds WHERE userID=?",
        (user_id,)
    ).fetchone()
    conn.close()

    if not creds_row:
        return None

    from datetime import datetime
    expiry_str = creds_row['expiry']
    expiry_dt = None
    if expiry_str:
        try:
            expiry_dt = datetime.fromisoformat(expiry_str)
        except ValueError:
            # If not ISO, try parsing as str(datetime)
            try:
                expiry_dt = datetime.strptime(expiry_str, '%Y-%m-%d %H:%M:%S.%f')
            except ValueError:
                expiry_dt = None
    credentials = Credentials(
        token=creds_row['accessToken'],
        refresh_token=creds_row['refreshToken'],
        token_uri='https://oauth2.googleapis.com/token',
        client_id=None,
        client_secret=None,
        scopes=['https://www.googleapis.com/auth/calendar'],
        expiry=expiry_dt
    )

    if credentials.expired:
        from google.auth.transport.requests import Request
        credentials.refresh(Request())

        # Update the database with refreshed token
        conn = get_db_connection()
        conn.execute("""
            UPDATE google_creds SET accessToken=?, expiry=?
            WHERE userID=?
        """, (credentials.token, credentials.expiry.isoformat(), user_id))
        conn.commit()
        conn.close()

    return build('calendar', 'v3', credentials=credentials)


@app.route('/auth/google')
@login_required
def auth_google():
    flow = Flow.from_client_secrets_file(
        'static/uploads/client_secret.json',
        scopes=['https://www.googleapis.com/auth/calendar'],
        redirect_uri='http://localhost:5000/oauth2callback'
    )
    auth_url, state = flow.authorization_url(prompt='consent')
    
    session['state'] = state
    
    return redirect(auth_url)

@app.route('/oauth2callback')
def oauth2callback():
    try:
        # Get state from session, with error handling
        state = session.get('state')
        if not state:
            return redirect('/calendar?google_error=State not found in session. Please try connecting again.')

        # Check if user is logged in
        if 'user_id' not in session:
            return redirect('/calendar?google_error=User not logged in. Please log in first.')

        flow = Flow.from_client_secrets_file(
            'static/uploads/client_secret.json',
            scopes=['https://www.googleapis.com/auth/calendar'],
            state=state,
            redirect_uri='http://localhost:5000/oauth2callback'
        )

        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials

        # STORE THESE IN DATABASE
        access_token = credentials.token
        refresh_token = credentials.refresh_token
        expiry = credentials.expiry

        conn = get_db_connection()

        conn.execute("""
        INSERT INTO google_creds (userID, accessToken, refreshToken, expiry)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(userID) DO UPDATE SET
            accessToken=excluded.accessToken,
            refreshToken=excluded.refreshToken,
            expiry=excluded.expiry
        """, (
            session['user_id'],
            access_token,
            refresh_token,
            expiry.isoformat()
        ))

        conn.commit()
        conn.close()

        return redirect('/calendar?google_connected=true')

    except Exception as e:
        return redirect(f'/calendar?google_error=Connection failed: {str(e)}')

@app.route('/calendar')
@login_required
def calendar():
        return render_template('calendar.html')

@app.route('/tasks')
@login_required
def tasks():
    user_id = session.get('user_id')
    default_subjects = [
        ('Software Engineering', 'purple', 4),
        ('Mathematics', 'red', 1),
        ('English', 'yellow', 2),
        ('Science', 'blue', 3),
        ('Humanities', 'brown', 5),
    ]

    try:
        conn = get_db_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subjects (
                subjectID INTEGER PRIMARY KEY AUTOINCREMENT,
                userID INTEGER NOT NULL,
                subjectName TEXT NOT NULL,
                colourScheme TEXT DEFAULT 'orange',
                sortOrder INTEGER DEFAULT 0,
                FOREIGN KEY(userID) REFERENCES users(userID) ON DELETE CASCADE
            )
        """)

        tasks = [dict(row) for row in conn.execute("""
                SELECT *
                FROM tasks
                WHERE userID = ?
                ORDER BY dueDate ASC
            """, (user_id,)).fetchall()]

        existing_count = conn.execute(
            'SELECT COUNT(*) AS count FROM subjects WHERE userID = ?',
            (user_id,)
        ).fetchone()['count']

        if existing_count == 0:
            conn.executemany(
                'INSERT INTO subjects (userID, subjectName, colourScheme, sortOrder) VALUES (?, ?, ?, ?)',
                [(user_id, name, colour, order) for name, colour, order in default_subjects]
            )
            conn.commit()

        subjects = [dict(row) for row in conn.execute("""
            SELECT subjectID, subjectName, colourScheme
            FROM subjects
            WHERE userID = ?
            ORDER BY sortOrder, subjectID
            LIMIT 5
        """, (user_id,)).fetchall()]
        conn.close()
    except sqlite3.Error as e:
        print(f"[TASKS] Could not load subjects from database: {e}")
        subjects = [
            {'subjectID': index, 'subjectName': name, 'colourScheme': colour}
            for index, (name, colour, _) in enumerate(default_subjects, start=1)
        ]

    return render_template('tasks.html', tasks=tasks, subjects=subjects)

def ensure_task_subject_schema(conn):
    """Add subject ownership to older local task tables."""
    task_columns = [
        row['name']
        for row in conn.execute("PRAGMA table_info(tasks)").fetchall()
    ]

    if 'subjectID' not in task_columns:
        conn.execute('ALTER TABLE tasks ADD COLUMN subjectID INTEGER')
        conn.commit()

@app.route('/create_task', methods=['POST'])
@login_required
def create_task():
    user_id = session.get('user_id')
    data = request.get_json() or {}

    title = (data.get('taskTitle') or '').strip()
    subject_id = data.get('subjectID')
    due_date = (data.get('taskDueDate') or '').strip()
    task_type = (data.get('taskType') or '').strip()
    progress = data.get('taskStatusInput')
    
    #Calculate days remaining

    try:
        due_date_obj = datetime.strptime(due_date, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Due date must be a valid date'}), 400

    days_remaining = (due_date_obj - datetime.now().date()).days

    valid_types = {'Homework', 'Exam', 'Project', 'Study', 'Assignment', 'Other'}

    if not title or not subject_id or not due_date or not task_type:
        return jsonify({'error': 'Missing required fields'}), 400

    if task_type not in valid_types:
        return jsonify({'error': 'Invalid task type'}), 400

    try:
        subject_id = int(subject_id)
        progress = int(progress)
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid numeric task values'}), 400

    if progress < 0 or progress > 100:
        return jsonify({'error': 'Progress must be between 0 and 100'}), 400

    if days_remaining < 0:
        return jsonify({'error': 'Days remaining cannot be negative'}), 400

    try:
        datetime.strptime(due_date, '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'Due date must be a valid date'}), 400

    conn = get_db_connection()

    try:
        ensure_task_subject_schema(conn)

        subject = conn.execute(
            'SELECT subjectID FROM subjects WHERE subjectID = ? AND userID = ?',
            (subject_id, user_id)
        ).fetchone()

        if not subject:
            conn.close()
            return jsonify({'error': 'Invalid subject'}), 403

        cursor = conn.execute("""
            INSERT INTO tasks
            (userID, subjectID, title, dueDate, taskType, progress, daysRemaining, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            subject_id,
            title,
            due_date,
            task_type,
            progress,
            days_remaining,
            'completed' if progress == 100 else 'in_progress' if progress > 0 else 'pending'
        ))
        conn.commit()
        task_id = cursor.lastrowid
        conn.close()

        return jsonify({
            'status': 'created',
            'taskID': task_id,
            'subjectID': subject_id,
            'daysRemaining': days_remaining
        }), 201
    except sqlite3.Error as e:
        conn.rollback()
        conn.close()
        print(f"[TASKS] Could not create task: {e}")
        return jsonify({'error': 'Could not save task'}), 500



@app.route('/get_tasks', methods=['GET'])
@login_required
def get_tasks():
    user_id = session.get('user_id')
    
    try:
        conn = get_db_connection()
        tasks = conn.execute("""
            SELECT taskID, subjectID, title, dueDate, taskType, progress, daysRemaining
            FROM tasks
            WHERE userID = ?
            ORDER BY dueDate ASC
        """, (user_id,)).fetchall()
        conn.close()
        
        # Format tasks for the frontend
        formatted_tasks = []
        for task in tasks:
            formatted_tasks.append({
                'taskID': task['taskID'],
                'subjectID': task['subjectID'],
                'task': task['title'],
                'date': task['dueDate'],
                'type': task['taskType'],
                'status': f"{task['progress']}%",
                'time': task['daysRemaining']
            })
        
        return jsonify({'tasks': formatted_tasks}), 200
    except sqlite3.Error as e:
        print(f"[GET_TASKS] Could not fetch tasks: {e}")
        return jsonify({'error': 'Could not fetch tasks'}), 500



@app.route('/update_task', methods=['POST'])
@login_required
def update_task():
    user_id = session.get('user_id')
    data = request.get_json() or {}

    task_id = data.get('taskID')
    field = data.get('field')
    value = data.get('value')
    
    if not task_id or not field:
        return jsonify({'error': 'Missing required fields'}), 400

    # Validate field and value
    valid_fields = {'task', 'date', 'type', 'status'}
    if field not in valid_fields:
        return jsonify({'error': 'Invalid field'}), 400

    try:
        conn = get_db_connection()
        
        # Verify task ownership
        task = conn.execute(
            'SELECT taskID FROM tasks WHERE taskID = ? AND userID = ?',
            (task_id, user_id)
        ).fetchone()
        
        if not task:
            conn.close()
            return jsonify({'error': 'Task not found'}), 404

        # Update the specific field
        if field == 'task':
            if not value or not value.strip():
                conn.close()
                return jsonify({'error': 'Task name cannot be empty'}), 400
            conn.execute('UPDATE tasks SET title = ? WHERE taskID = ?', (value.strip(), task_id))
        
        elif field == 'date':
            try:
                due_date_obj = datetime.strptime(value, '%Y-%m-%d').date()
                days_remaining = (due_date_obj - datetime.now().date()).days
                if days_remaining < 0:
                    conn.close()
                    return jsonify({'error': 'Due date cannot be in the past'}), 400
                conn.execute('UPDATE tasks SET dueDate = ?, daysRemaining = ? WHERE taskID = ?', 
                           (value, days_remaining, task_id))
            except ValueError:
                conn.close()
                return jsonify({'error': 'Invalid date format'}), 400
        
        elif field == 'type':
            valid_types = {'Homework', 'Exam', 'Project', 'Study', 'Assignment', 'Other'}
            if value not in valid_types:
                conn.close()
                return jsonify({'error': 'Invalid task type'}), 400
            conn.execute('UPDATE tasks SET taskType = ? WHERE taskID = ?', (value, task_id))
        
        elif field == 'status':
            try:
                progress = int(value.replace('%', ''))
                if progress < 0 or progress > 100:
                    conn.close()
                    return jsonify({'error': 'Progress must be between 0 and 100'}), 400
                status = 'completed' if progress == 100 else 'in_progress' if progress > 0 else 'pending'
                conn.execute('UPDATE tasks SET progress = ?, status = ? WHERE taskID = ?', 
                           (progress, status, task_id))
            except ValueError:
                conn.close()
                return jsonify({'error': 'Invalid progress value'}), 400

        conn.commit()
        conn.close()
        
        return jsonify({'status': 'updated'}), 200
    except sqlite3.Error as e:
        print(f"[UPDATE_TASK] Could not update task: {e}")
        return jsonify({'error': 'Could not update task'}), 500



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

# ======================== CALENDAR API ROUTES ========================

def check_overlap(start_time, end_time, user_id, exclude_event_id=None):
    """Check if a time slot overlaps with existing events."""
    conn = get_db_connection()
    query = "SELECT COUNT(*) as count FROM events WHERE userID = ? AND isDeleted = 0 AND source != 'google' AND startTime < ? AND endTime > ?"
    params = [user_id, end_time, start_time]
    
    if exclude_event_id:
        query += " AND eventID != ?"
        params.append(exclude_event_id)
    
    result = conn.execute(query, params).fetchone()
    conn.close()
    return result['count'] > 0


def find_available_slot(duration_minutes, user_id, before_date=None):
    """Find the next available time slot for the specified duration."""
    WORK_START_HOUR = 8
    WORK_END_HOUR = 22
    
    conn = get_db_connection()
    
    search_date = datetime.now().replace(hour=WORK_START_HOUR, minute=0, second=0, microsecond=0)
    
    for day_offset in range(14):
        current_date = search_date + timedelta(days=day_offset)
        
        if before_date:
            try:
                before = datetime.fromisoformat(before_date.replace('Z', '+00:00') if isinstance(before_date, str) and 'Z' in before_date else before_date)
            except:
                before = before_date if isinstance(before_date, datetime) else datetime.fromisoformat(before_date)
            
            if current_date.date() > before.date():
                conn.close()
                return None
        
        date_str = current_date.strftime('%Y-%m-%d')
        cursor = conn.cursor()
        cursor.execute("""
            SELECT startTime, endTime FROM events
            WHERE userID = ? AND DATE(startTime) = ? AND isDeleted = 0
            ORDER BY startTime
        """, (user_id, date_str))
        
        events = cursor.fetchall()
        
        # Try slot at start of work day
        slot_start = current_date.replace(hour=WORK_START_HOUR, minute=0)
        slot_end = slot_start + timedelta(minutes=duration_minutes)
        
        if slot_end.hour < WORK_END_HOUR:
            has_overlap = False
            for event in events:
                try:
                    e_start = datetime.fromisoformat(event['startTime'].replace('Z', '+00:00') if 'Z' in str(event['startTime']) else event['startTime'])
                    e_end = datetime.fromisoformat(event['endTime'].replace('Z', '+00:00') if 'Z' in str(event['endTime']) else event['endTime'])
                except:
                    e_start = datetime.fromisoformat(event['startTime'])
                    e_end = datetime.fromisoformat(event['endTime'])
                
                if not (slot_end <= e_start or slot_start >= e_end):
                    has_overlap = True
                    break
            
            if not has_overlap:
                conn.close()
                return {'start': slot_start.isoformat(), 'end': slot_end.isoformat()}
    
    conn.close()
    return None


@app.route('/calendar/events', methods=['GET'])
@login_required
def get_events():
    """Get all events for the logged-in user."""
    user_id = session.get('user_id')
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    
    conn = get_db_connection()
    query = "SELECT * FROM events WHERE userID = ? AND isDeleted = 0"
    params = [user_id]
    
    if start_date:
        query += " AND startTime >= ?"
        params.append(start_date)
    
    if end_date:
        query += " AND endTime <= ?"
        params.append(end_date)
    
    query += " ORDER BY startTime"
    
    events = [dict(row) for row in conn.execute(query, params).fetchall()]
    conn.close()
    
    return jsonify(events), 200


def get_event_color(source, priority=None):
    if priority == 3:
        return '#ef4444'
    if source == 'auto':
        return '#ead666'
    if source == 'google':
        return '#db6e07'
    return '#f5761c'

@app.route('/calendar/events', methods=['POST'])
@login_required
def create_event():
    """Create a new event."""
    user_id = session.get('user_id')
    data = request.get_json() or {}

    print(f"[DEBUG] Creating event for user {user_id}")
    print(f"[DEBUG] Request data: {data}")

    # Validate required fields
    if not data.get('title') or not data.get('startTime') or not data.get('endTime'):
        print("[DEBUG] Missing required fields")
        return jsonify({'error': 'Missing required fields'}), 400

    # Check for overlaps
    if check_overlap(data['startTime'], data['endTime'], user_id):
        print("[DEBUG] Time slot overlaps")
        return jsonify({'error': 'Time slot overlaps with existing event'}), 409

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 1. INSERT INTO DB FIRST
        cursor.execute("""
            INSERT INTO events 
            (userID, title, description, startTime, endTime, source, isDeleted, googleEventID)
            VALUES (?, ?, ?, ?, ?, ?, 0, NULL)
        """, (
            user_id,
            data['title'],
            data.get('description', ''),
            data['startTime'],
            data['endTime'],
            'user'
        ))

        event_id = cursor.lastrowid
        conn.commit()

        # 2. CREATE GOOGLE EVENT
        service = get_google_service(user_id)
        google_event_id = None

        if service:
            google_event = {
                'summary': data['title'],
                'description': data.get('description', ''),
                'start': {'dateTime': data['startTime'], 'timeZone': 'Australia/Sydney'},
                'end': {'dateTime': data['endTime'], 'timeZone': 'Australia/Sydney'}
            }

            created = service.events().insert(
                calendarId='primary',
                body=google_event
            ).execute()

            google_event_id = created.get('id')

            # 3. UPDATE LOCAL EVENT WITH GOOGLE ID
            cursor.execute("""
                UPDATE events SET googleEventID=? WHERE eventID=?
            """, (google_event_id, event_id))
            conn.commit()

        conn.close()
        return jsonify({
            'status': 'created',
            'eventID': event_id,
            'googleEventID': google_event_id
        }), 201

    except Exception as e:
        print(f"[DEBUG] Error creating event: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Database error: {str(e)}'}), 500


@app.route('/calendar/events/<int:event_id>', methods=['PUT'])
@login_required
def update_event(event_id):
    """Update an existing event."""
    user_id = session.get('user_id')
    data = request.get_json() or {}

    print(f"[DEBUG] Updating event {event_id} for user {user_id}")
    print(f"[DEBUG] Update data: {data}")

    conn = get_db_connection()

    # Verify ownership and load current event details
    event = conn.execute('SELECT userID, title, description, startTime, endTime, googleEventID FROM events WHERE eventID = ?', (event_id,)).fetchone()
    if not event or event['userID'] != user_id:
        conn.close()
        print("[DEBUG] Unauthorized access")
        return jsonify({'error': 'Unauthorized'}), 403

    # Check for overlaps if time changed
    if 'startTime' in data and 'endTime' in data:
        if check_overlap(data['startTime'], data['endTime'], user_id, exclude_event_id=event_id):
            conn.close()
            print("[DEBUG] Time slot overlaps")
            return jsonify({'error': 'Time slot overlaps with another event'}), 409

    update_fields = []
    params = []

    if 'title' in data:
        update_fields.append('title = ?')
        params.append(data['title'])
    if 'description' in data:
        update_fields.append('description = ?')
        params.append(data['description'])
    if 'startTime' in data:
        update_fields.append('startTime = ?')
        params.append(data['startTime'])
    if 'endTime' in data:
        update_fields.append('endTime = ?')
        params.append(data['endTime'])

    if update_fields:
        update_fields.append('updatedAt = CURRENT_TIMESTAMP')
        params.append(event_id)

        query = f"UPDATE events SET {', '.join(update_fields)} WHERE eventID = ?"
        try:
            conn.execute(query, params)
            conn.commit()
            print(f"[DEBUG] Event {event_id} updated successfully")
        except Exception as e:
            conn.close()
            print(f"[DEBUG] Error updating event: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'Database error: {str(e)}'}), 500

    # Sync to Google
    google_event_id = event['googleEventID']
    service = get_google_service(user_id)

    if service and google_event_id:
        google_event = {
            'summary': data.get('title', event['title']),
            'description': data.get('description', event['description'] or ''),
            'start': {'dateTime': data.get('startTime', event['startTime']), 'timeZone': 'Australia/Sydney'},
            'end': {'dateTime': data.get('endTime', event['endTime']), 'timeZone': 'Australia/Sydney'}
        }

        service.events().update(
            calendarId='primary',
            eventId=google_event_id,
            body=google_event
        ).execute()

    conn.close()
    return jsonify({'status': 'updated'}), 200


@app.route('/calendar/events/<int:event_id>', methods=['DELETE'])
@login_required
def delete_event(event_id):
    """Delete (soft delete) an event."""
    user_id = session.get('user_id')
    
    conn = get_db_connection()
    
    # Verify ownership
    event = conn.execute('SELECT userID FROM events WHERE eventID = ?', (event_id,)).fetchone()
    if not event or event['userID'] != user_id:
        conn.close()
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Get googleEventID
    event_row = conn.execute(
        "SELECT googleEventID FROM events WHERE eventID=?",
        (event_id,)
    ).fetchone()

    google_event_id = event_row['googleEventID']

    # Delete from Google
    service = get_google_service(user_id)

    if service and google_event_id:
        service.events().delete(
            calendarId='primary',
            eventId=google_event_id
        ).execute()

    # Soft delete
    conn.execute('UPDATE events SET isDeleted = 1, updatedAt = CURRENT_TIMESTAMP WHERE eventID = ?', (event_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'deleted'}), 200


@app.route('/calendar/generate', methods=['POST'])
@login_required
def generate_schedule():
    """Generate automatic schedule from pending tasks."""
    user_id = session.get('user_id')
    color = get_event_color('auto')

    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Get unscheduled tasks
        cursor.execute("""
            INSERT INTO events 
            (userID, title, description, startTime, endTime, source, color, isDeleted)
            VALUES (?, ?, ?, ?, ?, 'auto', ?, 0)
        """, (
            user_id,
            f"Study: {task['title']}",
            task['description'] or f"Study task: {task['title']}",
            slot['start'],
            slot['end'],
            color
        ))
        
        tasks = cursor.fetchall()
        created_events = []
        failed_tasks = []
        
        for task in tasks:
            duration = task['duration'] or 60
            due_date = task['dueDate']
            
            slot = find_available_slot(duration, user_id, before_date=due_date)
            
            if slot:
                cursor.execute("""
                    INSERT INTO events 
                    (userID, title, description, startTime, endTime, source, isDeleted)
                    VALUES (?, ?, ?, ?, ?, 'auto', 0)
                """, (
                    user_id,
                    f"Study: {task['title']}",
                    task['description'] or f"Study task: {task['title']}",
                    slot['start'],
                    slot['end']
                ))
                
                event_id = cursor.lastrowid
                cursor.execute('UPDATE tasks SET eventID = ? WHERE taskID = ?', (event_id, task['taskID']))
                
                created_events.append({
                    'eventID': event_id,
                    'taskID': task['taskID'],
                    'title': task['title']
                })
            else:
                failed_tasks.append({
                    'taskID': task['taskID'],
                    'title': task['title'],
                    'reason': 'No available time slot'
                })
        
        conn.commit()
        
        return jsonify({
            'status': 'success',
            'created': len(created_events),
            'failed': len(failed_tasks),
            'created_events': created_events,
            'failed_tasks': failed_tasks
        }), 200
    
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()


@app.route('/calendar/reschedule', methods=['POST'])
@login_required
def reschedule_event():
    """Reschedule an event based on instruction."""
    user_id = session.get('user_id')
    data = request.get_json() or {}
    
    event_id = data.get('eventID')
    new_start = data.get('startTime')
    new_end = data.get('endTime')
    
    if not event_id or not new_start or not new_end:
        return jsonify({'error': 'Missing required fields'}), 400
    
    conn = get_db_connection()
    
    # Verify ownership
    event = conn.execute('SELECT userID FROM events WHERE eventID = ?', (event_id,)).fetchone()
    if not event or event['userID'] != user_id:
        conn.close()
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Check for overlaps
    if check_overlap(new_start, new_end, user_id, exclude_event_id=event_id):
        conn.close()
        return jsonify({'error': 'Time slot overlaps with another event'}), 409
    
    conn.execute(
        'UPDATE events SET startTime = ?, endTime = ?, updatedAt = CURRENT_TIMESTAMP WHERE eventID = ?',
        (new_start, new_end, event_id)
    )
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'rescheduled'}), 200


@app.route('/calendar/check-google-auth', methods=['GET'])
@login_required
def check_google_auth():
    """Check if user has connected Google Calendar."""
    user_id = session.get('user_id')
    
    try:
        conn = get_db_connection()
        creds_row = conn.execute(
            "SELECT accessToken FROM google_creds WHERE userID=?",
            (user_id,)
        ).fetchone()
        conn.close()
        
        if creds_row and creds_row[0]:
            return jsonify({'connected': True}), 200
        else:
            return jsonify({'connected': False}), 200
    except Exception as e:
        print(f"Error checking Google auth: {e}")
        return jsonify({'connected': False, 'error': str(e)}), 500


@app.route('/calendar/sync/google', methods=['POST'])
@login_required
def sync_google_calendar():
    """Import events from Google Calendar."""
    user_id = session.get('user_id')

    try:
        # Check if user has Google credentials
        conn = get_db_connection()
        creds_row = conn.execute(
            "SELECT accessToken, refreshToken, expiry FROM google_creds WHERE userID=?",
            (user_id,)
        ).fetchone()

        if not creds_row:
            conn.close()
            return jsonify({'error': 'Google Calendar not connected. Please link your account first.'}), 400

        # Create credentials object
        credentials = Credentials(
            token=creds_row['accessToken'],
            refresh_token=creds_row['refreshToken'],
            token_uri='https://oauth2.googleapis.com/token',
            client_id=None,  # Will be loaded from client_secret.json if needed
            client_secret=None,
            scopes=['https://www.googleapis.com/auth/calendar']
        )

        # Check if token is expired and refresh if needed
        if credentials.expired:
            from google.auth.transport.requests import Request
            credentials.refresh(Request())

            # Update refreshed token in database
            conn.execute("""
                UPDATE google_creds SET accessToken=?, expiry=?
                WHERE userID=?
            """, (credentials.token, credentials.expiry.isoformat(), user_id))
            conn.commit()

        # Build Google Calendar service
        service = build('calendar', 'v3', credentials=credentials)

        # Get events from the last 30 days to next 90 days
        now = datetime.utcnow()
        time_min = (now - timedelta(days=30)).isoformat() + 'Z'
        time_max = (now + timedelta(days=90)).isoformat() + 'Z'

        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        # Import events to local database
        imported_count = 0
        skipped_count = 0
        imported_events = []

        for event in events:
            try:
                # Skip cancelled events
                if event.get('status') == 'cancelled':
                    continue

                # Parse start and end times
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))

                # Convert to ISO format if needed
                if 'T' not in start:  # All-day event
                    start += 'T00:00:00Z'
                    end = end.replace('T00:00:00', 'T23:59:59') if 'T' not in end else end
                    if 'T' not in end:
                        end += 'T23:59:59Z'

                # Check if event already exists (by title and start time)
                existing = conn.execute("""
                    SELECT eventID FROM events
                    WHERE googleEventID=?
                """, (event.get('id'),)).fetchone()

                if existing:
                    skipped_count += 1
                    continue

                # Insert new event
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO events
                    (userID, title, description, startTime, endTime, source, color, isDeleted)
                    VALUES (?, ?, ?, ?, ?, 'google', ?, 0)
                """, (
                    user_id,
                    event.get('summary', 'Untitled Event'),
                    event.get('description', ''),
                    start,
                    end,
                    get_event_color('google')
                ))

                event_id = cursor.lastrowid
                imported_count += 1
                imported_events.append({
                    'eventID': event_id,
                    'title': event.get('summary', 'Untitled Event'),
                    'start': start,
                    'end': end
                })

            except Exception as e:
                print(f"Error importing event {event.get('summary', 'Unknown')}: {e}")
                continue

        conn.commit()
        conn.close()

        return jsonify({
            'status': 'success',
            'message': f'Successfully imported {imported_count} events from Google Calendar',
            'imported': imported_count,
            'skipped': skipped_count,
            'events': imported_events
        }), 200

    except Exception as e:
        print(f"Error syncing Google Calendar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Sync failed: {str(e)}'}), 500


# SPA fallback -> index
@app.errorhandler(404)
def not_found(e):
    return render_template('index.html'), 404

if __name__ == '__main__':
    debug_db()
    print("Templates folder:", app.template_folder)
    print("Static folder:", app.static_folder)
    app.run(debug=True, port=5000)
