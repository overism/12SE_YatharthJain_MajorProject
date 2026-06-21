from ast import Return
import os

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

import sqlite3
import traceback
import json
import datetime
from functools import wraps
from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for, abort
from flask_cors import CORS
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta
import scheduler
load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))
GOOGLE_SCOPES = ['https://www.googleapis.com/auth/calendar']
GOOGLE_CLIENT_SECRET_FILE = os.path.join(basedir, 'static', 'secrets', 'client_secret_2_718545971467-nk6uf6oai3gtf7lit9cac1gnkpur55a7.apps.googleusercontent.com.json')
GOOGLE_CALENDAR_ID = 'primary'
VALID_SUBJECT_COLOURS = {'orange', 'blue', 'green', 'red', 'purple', 'yellow', 'brown', 'amber', 'teal', 'pink'}
USER_UPLOADS_DIR = os.path.join(basedir, 'data', 'user_uploads')
ALLOWED_UPLOAD_EXTENSIONS = {
    'pdf', 'docx', 'doc', 'pptx', 'ppt',
    'txt', 'md', 'png', 'jpg', 'jpeg',
}
AMBIENCE_DIR           = os.path.join(basedir, 'data', 'user_uploads', 'timer_ambience')
ALLOWED_AMBIENCE_BG    = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'mp4', 'webm'}
ALLOWED_AMBIENCE_SOUND = {'mp3', 'wav', 'ogg', 'm4a', 'opus'}

app = Flask(
    __name__,
    template_folder = basedir,
    static_folder = os.path.join(basedir, 'static')
)
_secret_key = os.getenv('SECRET_KEY')
if not _secret_key:
    import hashlib, socket
    # Stable per-machine fallback — not random on every restart
    _secret_key = hashlib.sha256(socket.gethostname().encode()).hexdigest()
    print("[WARN] SECRET_KEY not set in .env — using hostname-derived key. "
          "Sessions will persist across restarts but are not cryptographically unique. "
          "Set SECRET_KEY in your .env file for production.")
app.secret_key = _secret_key
CORS(app)

@app.context_processor
def inject_globals():
    return {'current_user_id': session.get('user_id', 0)}

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in') or not session.get('user_id'):
            session.clear()
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


def ensure_column(conn, table_name, column_name, column_sql):
    columns = {row['name'] for row in conn.execute(f'PRAGMA table_info({table_name})').fetchall()}
    if column_name not in columns:
        conn.execute(f'ALTER TABLE {table_name} ADD COLUMN {column_sql}')


def ensure_runtime_schema():
    """Keep older local databases aligned with the app's current API contract."""
    conn = get_db_connection()
    try:
        ensure_column(conn, 'google_creds', 'calendarID', "calendarID TEXT DEFAULT 'primary'")
        ensure_column(conn, 'google_creds', 'syncToken', 'syncToken TEXT')
        ensure_column(conn, 'events', 'googleEventID', 'googleEventID TEXT')
        ensure_column(conn, 'events', 'color', "color TEXT DEFAULT '#f6863b'")
        ensure_column(conn, 'events', 'lastSynced', 'lastSynced DATETIME')
        ensure_column(conn, 'events', 'updatedAt', 'updatedAt DATETIME DEFAULT CURRENT_TIMESTAMP')
        ensure_column(conn, 'tasks', 'eventID', 'eventID INTEGER')
        ensure_column(conn, 'subjects', 'isActive', 'isActive INTEGER DEFAULT 1')
        conn.commit()
    finally:
        conn.close()

from RAG.warmup import warm_rag_on_startup
warm_rag_on_startup()

DEFAULT_SCHEDULER_SETTINGS = {
    'study_start': 8,
    'study_end': 22,
    'sleep_start': 22,
    'sleep_end': 7,
    'school_start': 9,
    'school_end': 15,
    'session_duration': 60,
    'max_daily_hours': 4,
    'priority_subjects': [],
    'scheduler_onboarded': False,
    'study_techniques': []
}


def _coerce_int(value, default, minimum=None, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def _load_user_settings(raw_settings):
    if not raw_settings:
        print("[SETTINGS] No userSettings found, using defaults.")
        return {}
    if isinstance(raw_settings, dict):
        return raw_settings
    try:
        parsed = json.loads(raw_settings)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        print("[SETTINGS] Could not parse userSettings JSON:", raw_settings)
        return {}


def _scheduler_settings_from(settings):
    scheduler_settings = dict(DEFAULT_SCHEDULER_SETTINGS)
    scheduler_settings.update({
        'study_start': _coerce_int(settings.get('study_start'), 8, 0, 23),
        'study_end': _coerce_int(settings.get('study_end'), 22, 1, 24),
        'sleep_start': _coerce_int(settings.get('sleep_start'), 22, 0, 23),
        'sleep_end': _coerce_int(settings.get('sleep_end'), 7, 0, 23),
        'school_start': _coerce_int(settings.get('school_start'), 9, 0, 23),
        'school_end': _coerce_int(settings.get('school_end'), 15, 1, 24),
        'session_duration': _coerce_int(settings.get('session_duration'), 60, 20, 180),
        'max_daily_hours': _coerce_int(settings.get('max_daily_hours'), 4, 1, 10),
        'priority_subjects': settings.get('priority_subjects')
            if isinstance(settings.get('priority_subjects'), list)
            else [],
        'study_techniques': settings.get('study_techniques')
            if isinstance(settings.get('study_techniques'), list)
            else DEFAULT_SCHEDULER_SETTINGS['study_techniques'],
        'scheduler_onboarded': bool(settings.get('scheduler_onboarded')),
    })
    return scheduler_settings


def _scheduler_onboarding_complete(settings):
    required_keys = (
        'study_start', 'study_end', 'sleep_start', 'sleep_end',
        'school_start', 'school_end', 'session_duration',
        'max_daily_hours', 'study_techniques'
    )
    return bool(settings.get('scheduler_onboarded')) and all(key in settings for key in required_keys)


def _normalize_relative_path(path):
    if not path:
        return ''
    parts = [part for part in path.replace('\\', '/').split('/') if part and part != '..']
    return os.path.join(*parts) if parts else ''


def _safe_join(root_dir, relative_path):
    relative_path = _normalize_relative_path(relative_path)
    if not relative_path:
        return None
    candidate = os.path.abspath(os.path.join(root_dir, relative_path))
    root_dir = os.path.abspath(root_dir)
    if os.path.commonpath([candidate, root_dir]) != root_dir:
        return None
    return candidate


def _build_directory_tree(root_dir, relative_path=''):
    directory = os.path.abspath(os.path.join(root_dir, relative_path))
    if not os.path.isdir(directory):
        return []

    entries = []
    for entry in sorted(os.listdir(directory)):
        if entry.startswith('.'):
            continue
        entry_path = os.path.join(directory, entry)
        entry_rel = os.path.join(relative_path, entry) if relative_path else entry

        if os.path.isdir(entry_path):
            children = _build_directory_tree(root_dir, entry_rel)
            entries.append({
                'name': entry,
                'type': 'directory',
                'path': entry_rel.replace('\\', '/'),
                'children': children,
            })
        elif os.path.isfile(entry_path):
            entries.append({
                'name': entry,
                'type': 'file',
                'path': entry_rel.replace('\\', '/'),
                'extension': os.path.splitext(entry)[1].lower(),
            })

    return entries


_db_path = os.path.join(basedir, 'dusty.db')

FLASHCARD_SCHEMA = """
CREATE TABLE IF NOT EXISTS flashcard_decks (
    deckID          INTEGER PRIMARY KEY AUTOINCREMENT,
    userID          INTEGER NOT NULL,
    title           TEXT    NOT NULL,
    subject         TEXT    NOT NULL DEFAULT 'General',
    module          TEXT    NOT NULL DEFAULT 'General',
    cardCount       INTEGER NOT NULL DEFAULT 0,
    createdAt       TEXT    NOT NULL DEFAULT (datetime('now')),
    updatedAt       TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (userID) REFERENCES users(userID) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS flashcards (
    cardID          INTEGER PRIMARY KEY AUTOINCREMENT,
    deckID          INTEGER NOT NULL,
    userID          INTEGER NOT NULL,
    question        TEXT    NOT NULL,
    answer          TEXT    NOT NULL,
    hint            TEXT,
    sortOrder       INTEGER NOT NULL DEFAULT 0,
    createdAt       TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (deckID)  REFERENCES flashcard_decks(deckID)  ON DELETE CASCADE,
    FOREIGN KEY (userID)  REFERENCES users(userID)             ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS flashcard_results (
    resultID        INTEGER PRIMARY KEY AUTOINCREMENT,
    deckID          INTEGER NOT NULL,
    userID          INTEGER NOT NULL,
    knew            INTEGER NOT NULL DEFAULT 0,
    unsure          INTEGER NOT NULL DEFAULT 0,
    missed          INTEGER NOT NULL DEFAULT 0,
    totalCards      INTEGER NOT NULL DEFAULT 0,
    studiedAt       TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (deckID)  REFERENCES flashcard_decks(deckID)  ON DELETE CASCADE,
    FOREIGN KEY (userID)  REFERENCES users(userID)             ON DELETE CASCADE
);
"""

def init_new_tables():
    conn = sqlite3.connect(_db_path)
    conn.executescript(FLASHCARD_SCHEMA)
    conn.commit()
    conn.close()

_schema_path = os.path.join(basedir, 'static', 'db', 'schema.sql')
init_db_from_schema(_db_path, _schema_path)
init_new_tables()
ensure_runtime_schema()

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
    email    = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()

    if not email or not password:
        return jsonify({"success": False, "message": "Email and password are required."}), 400

    conn = get_db_connection()
    user = conn.execute(
        'SELECT userID, userName, userPassword, userSettings FROM users WHERE userEmail = ?',
        (email,)
    ).fetchone()
    conn.close()  # only once

    authenticated = False
    if user:
        if user['userID'] == 1 and password == 'DustyAdminPass123!':
            authenticated = True
        elif check_password_hash(user['userPassword'], password):
            authenticated = True

    if not authenticated:
        return jsonify({"success": False, "message": "Invalid email or password."}), 401

    session['user_id']    = user['userID']
    session['user_name']  = user['userName']
    session['user_email'] = email
    session['logged_in']  = True

    settings = _load_user_settings(user['userSettings'])
    redirect_url = url_for('home') if _scheduler_onboarding_complete(settings) else url_for('onboarding')

    return jsonify({
        "success":      True,
        "message":      "You have logged in successfully.",
        "redirect_url": redirect_url
    }), 200

@app.route('/add_user', methods=['POST'])
def add_user():
    import re
    email    = request.form.get('email', '').strip()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()

    if not email or not username or not password:
        return redirect(url_for('signup') + '?error=missing_fields')

    # Validate email format
    email_regex = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
    if not re.match(email_regex, email):
        return redirect(url_for('signup') + '?error=invalid_email')

    # Validate username length
    if len(username) < 3:
        return redirect(url_for('signup') + '?error=invalid_username')

    # Validate password length
    if len(password) < 8:
        return redirect(url_for('signup') + '?error=weak_password')

    conn = get_db_connection()
    existing = conn.execute(
        'SELECT 1 FROM users WHERE userEmail = ?', (email,)
    ).fetchone()

    if existing:
        conn.close()
        return redirect(url_for('signup') + '?error=email_exists')

    hashed_password = generate_password_hash(password)
    cursor = conn.execute(
        'INSERT INTO users (userEmail, userName, userPassword) VALUES (?, ?, ?)',
        (email, username, hashed_password)
    )
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()

    session['user_id']    = user_id
    session['user_name']  = username
    session['user_email'] = email
    session['logged_in']  = True

    return redirect(url_for('onboarding'))

@app.route('/onboarding')
@login_required
def onboarding():
    user_id = session.get('user_id')
    conn = get_db_connection()
    row = conn.execute(
        'SELECT userSettings FROM users WHERE userID = ?', (user_id,)
    ).fetchone()
    conn.close()
    settings = _load_user_settings(row['userSettings'] if row else None)
    if _scheduler_onboarding_complete(settings):
        return redirect(url_for('home'))
    return render_template('onboarding.html')

@app.route('/api/subjects', methods=['GET'])
@login_required
def api_get_subjects():
    user_id = session.get('user_id')
    try:
        conn = get_db_connection()
        rows = conn.execute(
            '''SELECT subjectID, subjectName, colourScheme
               FROM subjects
               WHERE userID = ? AND isActive = 1
               ORDER BY sortOrder, subjectID''',
            (user_id,)
        ).fetchall()
        conn.close()
        return jsonify({'subjects': [dict(r) for r in rows]})
    except Exception as e:
        print('[API /api/subjects] Error:', e)
        return jsonify({'error': 'Could not load subjects'}), 500

@app.route('/api/syllabus/topics', methods=['GET'])
@login_required
def api_syllabus_topics():
    from RAG.syllabus_topics import SYLLABUS_TOPICS, get_subjects, find_best_match

    subject = (request.args.get('subject') or '').strip()

    if subject:
        matched_key = find_best_match(subject)
        if matched_key:
            return jsonify({
                'subject':  subject,
                'matched':  matched_key,
                'modules':  SYLLABUS_TOPICS[matched_key],
            })
        # No match at all — return empty so the UI shows a text input
        return jsonify({
            'subject': subject,
            'matched': None,
            'modules': [],
        })

    return jsonify({
        'subjects': get_subjects(),
        'modules':  [],
    })

@app.route('/debug_session')
def debug_session():
    print("DEBUG SESSION:", dict(session))
    return jsonify(dict(session))

@app.route('/api/user/preferences', methods=['GET', 'POST'])
def api_user_preferences():
    """Load or save user preferences in users.userSettings JSON column."""

    print("========== PREFERENCES ==========")
    print("SESSION:", dict(session))

    user_id = session.get('user_id')
    print("USER_ID:", user_id)

    if request.method == 'GET':
        try:
            conn = get_db_connection()
            user = conn.execute('SELECT userSettings FROM users WHERE userID = ?', (user_id,)).fetchone()
            settings = _load_user_settings(user['userSettings'] if user else None)
            subjects = conn.execute(
                'SELECT subjectID, subjectName, colourScheme FROM subjects WHERE userID = ? ORDER BY sortOrder, subjectID',
                (user_id,)
            ).fetchall()
            conn.close()
            scheduler_settings = _scheduler_settings_from(settings)
            return jsonify({
                'success': True,
                'theme': settings.get('theme', 'light'),
                'subjects': [dict(row) for row in subjects],
                'scheduler': scheduler_settings,
                'needsSchedulerOnboarding': not _scheduler_onboarding_complete(settings),
            })
        except Exception as e:
            print('[API /api/user/preferences GET] Error:', e)
            return jsonify({'error': 'Could not load preferences'}), 500

    data = request.get_json() or {}
    theme = data.get('theme')
    selected = data.get('subjects') or []
    scheduler_data = data.get('scheduler') or {}
    # Validate simple shape
    if theme not in (None, 'light', 'dark'):
        return jsonify({'error': 'Invalid theme value'}), 400
    if not isinstance(selected, list):
        return jsonify({'error': 'Invalid subjects list'}), 400
    if not isinstance(scheduler_data, dict):
        return jsonify({'error': 'Invalid scheduler preferences'}), 400

    normalized = []
    for item in selected:
        if not isinstance(item, dict):
            return jsonify({'error': 'Invalid subject item'}), 400

        colour = item.get('colourScheme')
        subject_id = item.get('subjectID')
        subject_name = item.get('subjectName') or item.get('subject_name')

        if colour == 'yellow':
            colour = 'amber'
        if colour not in VALID_SUBJECT_COLOURS:
            return jsonify({'error': 'Invalid subject colour'}), 400

        if subject_id is not None:
            if not isinstance(subject_id, int):
                return jsonify({'error': 'Invalid subjectID'}), 400
            normalized.append({'subjectID': subject_id, 'subjectName': subject_name, 'colourScheme': colour})
        elif isinstance(subject_name, str) and subject_name.strip():
            normalized.append({'subjectName': subject_name.strip(), 'colourScheme': colour})
        else:
            return jsonify({'error': 'Invalid subject selection'}), 400

    try:
        conn = get_db_connection()

        # Resolve subject IDs and persist colour selections
        for item in normalized:
            if 'subjectID' in item and item['subjectID'] is not None:
                row = conn.execute(
                    'SELECT subjectID, subjectName FROM subjects WHERE userID = ? AND subjectID = ?',
                    (user_id, item['subjectID'])
                ).fetchone()
                if row:
                    item['subjectName'] = item.get('subjectName') or row['subjectName']
                else:
                    return jsonify({'error': 'Subject not found'}), 400
            else:
                row = conn.execute(
                    'SELECT subjectID FROM subjects WHERE userID = ? AND subjectName = ?',
                    (user_id, item['subjectName'])
                ).fetchone()
                if row:
                    item['subjectID'] = row['subjectID']
                else:
                    next_order = conn.execute(
                        'SELECT COALESCE(MAX(sortOrder), 0) + 1 AS nextOrder FROM subjects WHERE userID = ?',
                        (user_id,)
                    ).fetchone()['nextOrder']
                    cursor = conn.execute(
                        'INSERT INTO subjects (userID, subjectName, colourScheme, sortOrder) VALUES (?, ?, ?, ?)',
                        (user_id, item['subjectName'], item['colourScheme'], next_order)
                    )
                    item['subjectID'] = cursor.lastrowid

            conn.execute(
                'UPDATE subjects SET colourScheme = ? WHERE userID = ? AND subjectID = ?',
                (item['colourScheme'], user_id, item['subjectID'])
            )

        # Deactivate subjects not in the selected list
        selected_ids = [item['subjectID'] for item in normalized if item.get('subjectID')]
        if selected_ids:
            placeholders = ','.join('?' * len(selected_ids))
            conn.execute(
                f'''UPDATE subjects SET isActive = 0
                    WHERE userID = ? AND subjectID NOT IN ({placeholders})''',
                [user_id] + selected_ids
            )
        # Activate selected subjects (in case re-selecting a previously deactivated one)
        for item in normalized:
            if item.get('subjectID'):
                conn.execute(
                    'UPDATE subjects SET isActive = 1, colourScheme = ? WHERE userID = ? AND subjectID = ?',
                    (item['colourScheme'], user_id, item['subjectID'])
                )

        existing = conn.execute('SELECT userSettings FROM users WHERE userID = ?', (user_id,)).fetchone()
        prefs = _load_user_settings(existing['userSettings'] if existing else None)
        if theme:
            prefs['theme'] = theme
        prefs['subjects'] = [
            {
                'subjectID': item['subjectID'],
                'subjectName': item.get('subjectName'),
                'colourScheme': item['colourScheme'],
            }
            for item in normalized
        ]

        if scheduler_data:
            prefs.update({
                'study_start': _coerce_int(scheduler_data.get('study_start'), 8, 0, 23),
                'study_end': _coerce_int(scheduler_data.get('study_end'), 22, 1, 24),
                'sleep_start': _coerce_int(scheduler_data.get('sleep_start'), 22, 0, 23),
                'sleep_end': _coerce_int(scheduler_data.get('sleep_end'), 7, 0, 23),
                'school_start': _coerce_int(scheduler_data.get('school_start'), 9, 0, 23),
                'school_end': _coerce_int(scheduler_data.get('school_end'), 15, 1, 24),
                'session_duration': _coerce_int(scheduler_data.get('session_duration'), 60, 20, 180),
                'max_daily_hours': _coerce_int(scheduler_data.get('max_daily_hours'), 4, 1, 10),
                'priority_subjects': (
                    scheduler_data.get('priority_subjects')
                    if isinstance(scheduler_data.get('priority_subjects'), list)
                    else []
                ),
                'study_techniques': (
                    scheduler_data.get('study_techniques')
                    if isinstance(scheduler_data.get('study_techniques'), list)
                    else DEFAULT_SCHEDULER_SETTINGS['study_techniques']
                ),
                'scheduler_onboarded': bool(scheduler_data.get('scheduler_onboarded', True)),
            })

        print(json.dumps(prefs, indent=2))    

        conn.execute('UPDATE users SET userSettings = ? WHERE userID = ?', (json.dumps(prefs), user_id))
        conn.commit()
        conn.close()
        return jsonify({
            'success': True,
            'needsSchedulerOnboarding': not _scheduler_onboarding_complete(prefs)
        })
    except Exception as e:
        print('[API /api/user/preferences] Error:', e)
        return jsonify({'error': 'Could not save preferences'}), 500


@app.route('/api/user/onboarding-status', methods=['GET'])
@login_required
def api_user_onboarding_status():
    user_id = session.get('user_id')
    try:
        conn = get_db_connection()
        row = conn.execute('SELECT userSettings FROM users WHERE userID = ?', (user_id,)).fetchone()
        conn.close()
        settings = _load_user_settings(row['userSettings'] if row else None)
        return jsonify({
            'success': True,
            'needsSchedulerOnboarding': not _scheduler_onboarding_complete(settings)
        })
    except Exception as e:
        print('[API /api/user/onboarding-status] Error:', e)
        return jsonify({'error': 'Could not check onboarding status'}), 500

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
@login_required
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

@app.route('/change-password', methods=['POST'])
@login_required
def change_password():
    user_id = session.get('user_id')
    data    = request.get_json() or {}
    current = (data.get('current_password') or '').strip()
    new_pw  = (data.get('new_password')     or '').strip()
 
    if not current or not new_pw:
        return jsonify({'error': 'Both current and new passwords are required.'}), 400
    if len(new_pw) < 8:
        return jsonify({'error': 'New password must be at least 8 characters.'}), 400
 
    try:
        conn = get_db_connection()
        user = conn.execute(
            'SELECT userPassword FROM users WHERE userID = ?', (user_id,)
        ).fetchone()
 
        if not user:
            conn.close()
            return jsonify({'error': 'User not found.'}), 404
 
        # Admin bypass (plaintext check for admin account)
        stored = user['userPassword']
        if not (check_password_hash(stored, current) or
                (user_id == 1 and current == 'DustyAdminPass123!')):
            conn.close()
            return jsonify({'error': 'Current password is incorrect.'}), 401
 
        hashed = generate_password_hash(new_pw)
        conn.execute('UPDATE users SET userPassword = ? WHERE userID = ?', (hashed, user_id))
        conn.commit()
        conn.close()
 
        return jsonify({'success': True, 'message': 'Password updated successfully.'})
 
    except Exception as exc:
        print(f'[CHANGE_PASSWORD] Error: {exc}')
        traceback.print_exc()
        return jsonify({'error': 'Could not update password.'}), 500
 
 
@app.route('/delete-account', methods=['POST'])
@login_required
def delete_account():
    """
    Permanently delete the current user and all their data.
    Relies on ON DELETE CASCADE in the schema for tasks, sessions, etc.
    """
    user_id = session.get('user_id')
 
    # Prevent deleting the admin account
    if user_id == 1:
        return jsonify({'error': 'The admin account cannot be deleted.'}), 403
 
    try:
        conn = get_db_connection()
 
        # Cascade delete covers: tasks, events, subjects, timer_sessions,
        # timer_presets, flashcard_decks, flashcards, flashcard_results,
        # chat_sessions, chat_messages, google_creds
        conn.execute('DELETE FROM users WHERE userID = ?', (user_id,))
        conn.commit()
        conn.close()
 
        session.clear()
        return jsonify({'success': True})
 
    except Exception as exc:
        print(f'[DELETE_ACCOUNT] Error: {exc}')
        traceback.print_exc()
        return jsonify({'error': 'Could not delete account.'}), 500
 
 
@app.route('/update-profile', methods=['POST'])
@login_required
def update_profile():
    """
    Accepts both form-encoded and JSON payloads so the profile page
    JS can call it directly without a page reload.
    """
    user_id = session.get('user_id')
 
    # Support both FormData and JSON
    if request.is_json:
        data     = request.get_json() or {}
        username = (data.get('username') or '').strip()
        email    = (data.get('email')    or '').strip()
        as_json  = True
    else:
        username = (request.form.get('username') or '').strip()
        email    = (request.form.get('email')    or '').strip()
        as_json  = False
 
    if not username or not email:
        if as_json:
            return jsonify({'error': 'Name and email are required.'}), 400
        return redirect(url_for('profile'))
 
    try:
        conn = get_db_connection()
 
        # Check email uniqueness (ignore own record)
        conflict = conn.execute(
            'SELECT userID FROM users WHERE userEmail = ? AND userID != ?',
            (email, user_id)
        ).fetchone()
        if conflict:
            conn.close()
            if as_json:
                return jsonify({'error': 'That email is already in use.'}), 409
            return redirect(url_for('profile'))
 
        conn.execute(
            'UPDATE users SET userName = ?, userEmail = ? WHERE userID = ?',
            (username, email, user_id)
        )
        conn.commit()
        conn.close()
 
        session['user_name']  = username
        session['user_email'] = email
 
        if as_json:
            return jsonify({'success': True})
        return redirect(url_for('profile'))
 
    except Exception as exc:
        print(f'[UPDATE_PROFILE] Error: {exc}')
        traceback.print_exc()
        if as_json:
            return jsonify({'error': 'Could not update profile.'}), 500
        return redirect(url_for('profile'))
    
#Calendar API and Google Calendar Integration + FullCalendar Setup
def get_google_redirect_uri():
    return os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:5000/oauth2callback')


def get_google_client_config():
    if not os.path.exists(GOOGLE_CLIENT_SECRET_FILE):
        return None, None
    try:
        with open(GOOGLE_CLIENT_SECRET_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        client = config.get('web') or config.get('installed') or {}
        return client.get('client_id'), client.get('client_secret')
    except Exception as e:
        print(f'[GOOGLE] Could not read client secret file: {e}')
        return None, None


def google_error_redirect(message, detail=None):
    if detail:
        session['google_last_error_detail'] = detail
        print(f'[GOOGLE OAUTH] {message}: {detail}')
    else:
        print(f'[GOOGLE OAUTH] {message}')
    return redirect('/calendar?google_error=' + message.replace(' ', '+'))


def get_google_service(user_id):
    conn = get_db_connection()
    creds_row = conn.execute(
        "SELECT accessToken, refreshToken, expiry FROM google_creds WHERE userID=?",
        (user_id,)
    ).fetchone()
    conn.close()

    if not creds_row:
        print(f"[GOOGLE SERVICE] No credentials found for user {user_id}")
        return None

    client_id, client_secret = get_google_client_config()
    if not client_id or not client_secret:
        print(f"[GOOGLE SERVICE] Missing client ID/secret")
        return None

    expiry_str = creds_row['expiry']
    expiry_dt = None
    if expiry_str:
        try:
            expiry_dt = datetime.fromisoformat(expiry_str)
        except ValueError:
            try:
                expiry_dt = datetime.strptime(expiry_str, '%Y-%m-%d %H:%M:%S.%f')
            except ValueError:
                expiry_dt = None

    credentials = Credentials(
        token=creds_row['accessToken'],
        refresh_token=creds_row['refreshToken'],
        token_uri='https://oauth2.googleapis.com/token',
        client_id=client_id,
        client_secret=client_secret,
        scopes=GOOGLE_SCOPES,
        expiry=expiry_dt
    )

    print(f"[GOOGLE SERVICE] Credentials expired: {credentials.expired}")
    print(f"[GOOGLE SERVICE] Has refresh token: {bool(credentials.refresh_token)}")

    if credentials.expired and credentials.refresh_token:
        from google.auth.transport.requests import Request
        from google.auth.exceptions import RefreshError

        try:
            credentials.refresh(Request())
            print(f"[GOOGLE SERVICE] Token refreshed successfully")

            conn = get_db_connection()
            conn.execute("""
                UPDATE google_creds
                SET accessToken=?, expiry=?
                WHERE userID=?
            """, (
                credentials.token,
                credentials.expiry.isoformat(),
                user_id
            ))
            conn.commit()
            conn.close()

        except RefreshError as e:
            print(f"[GOOGLE SERVICE] Token refresh failed: {e}")
            conn = get_db_connection()
            conn.execute(
                "DELETE FROM google_creds WHERE userID=?",
                (user_id,)
            )
            conn.commit()
            conn.close()
            return None

    service = build('calendar', 'v3', credentials=credentials)
    print(f"[GOOGLE SERVICE] Service built successfully for user {user_id}")
    return service


@app.route('/auth/google')
@login_required
def auth_google():

    if not os.path.exists(GOOGLE_CLIENT_SECRET_FILE):
        return google_error_redirect(
            'Google client secret file missing',
            f'Expected file at {GOOGLE_CLIENT_SECRET_FILE}'
        )

    flow = Flow.from_client_secrets_file(
        GOOGLE_CLIENT_SECRET_FILE,
        scopes=GOOGLE_SCOPES,
        redirect_uri=get_google_redirect_uri()
    )

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )

    # STORE STATE + PKCE VERIFIER
    session['google_oauth_state'] = state
    session['google_code_verifier'] = flow.code_verifier

    return redirect(authorization_url)

@app.route('/oauth2callback')
def oauth2callback():
    try:
        if request.args.get('error'):
            return google_error_redirect(
                'Google authorization was cancelled or rejected',
                request.args.get('error_description') or request.args.get('error')
            )

        # Get state from session, with error handling
        state = session.get('google_oauth_state')

        if not state:
            return google_error_redirect('OAuth session expired. Please reconnect Google Calendar.')

        # Check if user is logged in
        if 'user_id' not in session:
            return google_error_redirect('User not logged in. Please log in first.')

        flow = Flow.from_client_secrets_file(
        GOOGLE_CLIENT_SECRET_FILE,
        scopes=GOOGLE_SCOPES,
        state=session['google_oauth_state'],
        redirect_uri=get_google_redirect_uri()
        )

        # RESTORE VERIFIER
        flow.code_verifier = session['google_code_verifier']

        flow.fetch_token(
            authorization_response=request.url
        )

        credentials = flow.credentials

        # STORE THESE IN DATABASE
        access_token = credentials.token
        refresh_token = credentials.refresh_token
        expiry = credentials.expiry

        conn = get_db_connection()
        existing = conn.execute(
            'SELECT refreshToken FROM google_creds WHERE userID = ?',
            (session['user_id'],)
        ).fetchone()
        if not refresh_token and existing:
            refresh_token = existing['refreshToken']

        conn.execute("""
        INSERT INTO google_creds (userID, accessToken, refreshToken, expiry, calendarID)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(userID) DO UPDATE SET
            accessToken=excluded.accessToken,
            refreshToken=excluded.refreshToken,
            expiry=excluded.expiry,
            calendarID=excluded.calendarID
        """, (
            session['user_id'],
            access_token,
            refresh_token,
            expiry.isoformat(),
            GOOGLE_CALENDAR_ID
        ))

        conn.commit()
        conn.close()

        return redirect('/calendar?google_connected=true')

    except Exception as e:
        traceback.print_exc()
        return google_error_redirect('Connection failed', str(e))

@app.route('/calendar')
@login_required
def calendar():
        return render_template('calendar.html')

@app.route('/tasks')
@login_required
def tasks():
    user_id = session.get('user_id')

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

        subjects = [dict(row) for row in conn.execute("""
            SELECT subjectID, subjectName, colourScheme
            FROM subjects
            WHERE userID = ? AND isActive = 1
            ORDER BY sortOrder, subjectID
        """, (user_id,)).fetchall()]
        conn.close()
    except sqlite3.Error as e:
        print(f"[TASKS] Could not load subjects from database: {e}")
        return jsonify({'error': 'Could not load subjects'}), 500

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


@app.route('/delete_task', methods=['POST'])
@login_required
def delete_task():
    """Mark a task as complete and delete it from the database."""
    user_id = session.get('user_id')
    data = request.get_json() or {}

    task_id = data.get('taskID')

    if not task_id:
        return jsonify({'error': 'Missing task ID'}), 400

    try:
        conn = get_db_connection()

        # Verify task ownership before deleting
        task = conn.execute(
            'SELECT taskID FROM tasks WHERE taskID = ? AND userID = ?',
            (task_id, user_id)
        ).fetchone()

        if not task:
            conn.close()
            return jsonify({'error': 'Task not found'}), 404

        # Delete the task from database
        conn.execute('DELETE FROM tasks WHERE taskID = ? AND userID = ?', (task_id, user_id))
        conn.commit()
        conn.close()

        return jsonify({'status': 'deleted'}), 200
    except sqlite3.Error as e:
        print(f"[DELETE_TASK] Could not delete task: {e}")
        return jsonify({'error': 'Could not delete task'}), 500


@app.route('/timer')
@login_required
def timer():
    return render_template('timer.html')

@app.route('/chat')
@login_required
def chat():
    user_id = session.get('user_id')
    conn = get_db_connection()
    user = conn.execute(
        'SELECT userName, userEmail, userPfp FROM users WHERE userID = ?',
        (user_id,)
    ).fetchone()

    subjects = conn.execute(
        'SELECT subjectID, subjectName FROM subjects WHERE userID = ? AND isActive = 1 ORDER BY sortOrder, subjectID',
        (user_id,)
    ).fetchall()
    conn.close()

    return render_template('chat.html', user=user, subjects=subjects)

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
    """Upload and store a user avatar image"""
    user_id = session.get('user_id')
    file = request.files.get('avatar')

    if not file:
        return jsonify({'error': 'No file provided'}), 400

    # Validate MIME type (more secure than just extension)
    allowed_mime_types = {'image/png', 'image/jpeg', 'image/jpg', 'image/gif'}
    if file.content_type not in allowed_mime_types:
        return jsonify({'error': 'File type not allowed. Use PNG, JPG, or GIF.'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed. Use PNG, JPG, GIF.'}), 400

    try:
        # Create uploads directory if it doesn't exist
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)

        # Generate unique filename with timestamp
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f'avatar_{user_id}_{int(datetime.now().timestamp())}.{ext}'
        filepath = os.path.join(UPLOAD_FOLDER, filename)

        # Save file
        file.save(filepath)

        # Store relative URL in database (not absolute path)
        avatar_url = f'/static/uploads/{filename}'
        conn = get_db_connection()
        conn.execute('UPDATE users SET userPfp = ? WHERE userID = ?', (avatar_url, user_id))
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'avatar_url': avatar_url}), 200

    except Exception as e:
        print(f'[UPLOAD_AVATAR] Error: {e}')
        traceback.print_exc()
        return jsonify({'error': 'Could not upload avatar.'}), 500


@app.route('/save-bio', methods=['POST'])
@login_required
def save_bio():
    """Save user bio"""
    user_id = session.get('user_id')
    
    if not request.is_json:
        return jsonify({'error': 'Content-Type must be application/json'}), 400

    data = request.get_json() or {}
    bio = (data.get('bio') or '').strip()

    if len(bio) > 500:
        return jsonify({'error': 'Bio must not exceed 500 characters.'}), 400

    try:
        conn = get_db_connection()
        conn.execute('UPDATE users SET userBio = ? WHERE userID = ?', (bio, user_id))
        conn.commit()
        conn.close()

        return jsonify({'success': True}), 200

    except Exception as e:
        print(f'[SAVE_BIO] Error: {e}')
        traceback.print_exc()
        return jsonify({'error': 'Could not save bio.'}), 500



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

def parse_calendar_dt(value):
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value or '').replace('Z', '+00:00')
        dt = datetime.fromisoformat(text)
    if dt.tzinfo:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def google_event_body(title, description, start_time, end_time):
    start_dt = parse_calendar_dt(start_time)
    end_dt = parse_calendar_dt(end_time)
    print(f"[GOOGLE DEBUG] Parsed start: {start_dt}, end: {end_dt}")
    if not start_dt or not end_dt:
        raise ValueError(f"Could not parse event times: start={start_time}, end={end_time}")
    return {
        'summary': title,
        'description': description or '',
        'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'Australia/Sydney'},
        'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'Australia/Sydney'}
    }

def check_overlap(start_time, end_time, user_id, exclude_event_id=None):
    """
    Return True if [start_time, end_time) overlaps any non-deleted event
    owned by user_id (excluding exclude_event_id when supplied).

    Normalises both the incoming times and the stored times through
    parse_calendar_dt so that timezone suffixes, 'Z', and space-separated
    datetime strings are all handled consistently.
    """
    try:
        s = parse_calendar_dt(str(start_time))
        e = parse_calendar_dt(str(end_time))
        if s is None or e is None:
            return False
        start_str = s.isoformat()
        end_str   = e.isoformat()
    except Exception:
        return False

    conn = get_db_connection()
    query = """
        SELECT COUNT(*) AS count
        FROM events
        WHERE userID    = ?
          AND isDeleted = 0
          AND startTime < ?
          AND endTime   > ?
    """
    params = [user_id, end_str, start_str]

    if exclude_event_id is not None:
        query += " AND eventID != ?"
        params.append(exclude_event_id)

    result = conn.execute(query, params).fetchone()
    conn.close()
    return result["count"] > 0

def round_up_to_interval(dt, interval_minutes=15):
    """Round datetime up to nearest interval."""
    if dt.minute % interval_minutes == 0 and dt.second == 0 and dt.microsecond == 0:
        return dt
    
    discard = timedelta(
        minutes=dt.minute % interval_minutes,
        seconds=dt.second,
        microseconds=dt.microsecond
    )

    dt = dt - discard
    dt += timedelta(minutes=interval_minutes)

    discard = timedelta(
        minutes=dt.minute % interval_minutes,
        seconds=dt.second,
        microseconds=dt.microsecond
    )

    dt = dt - discard
    dt += timedelta(minutes=interval_minutes)

    return dt

def find_available_slot(duration_minutes, user_id, before_date=None):
    """
    Find next available slot.

    ```
    Respects:
    - User study hours
    - User school hours
    - Existing calendar events
    - Deadline/exam dates
    - 15 minute alignment
    """

    now = datetime.now()

    conn = get_db_connection()

    try:
        user_row = conn.execute(
            "SELECT userSettings FROM users WHERE userID = ?",
            (user_id,)
        ).fetchone()

        settings = {}

        if user_row and user_row["userSettings"]:
            try:
                settings = json.loads(user_row["userSettings"])
            except Exception:
                settings = {}

        study_start_hour = int(settings.get("study_start", 8))
        study_end_hour = int(settings.get("study_end", 22))

        school_start_hour = settings.get("school_start")
        school_end_hour = settings.get("school_end")

        deadline = None

        if before_date:
            try:
                deadline = parse_calendar_dt(before_date)
            except Exception:
                deadline = None

        search_start = now.replace(
            hour=study_start_hour,
            minute=0,
            second=0,
            microsecond=0
        )

        if search_start < now:
            search_start = now

        max_search_days = 365

        for day_offset in range(max_search_days):

            current_date = search_start + timedelta(days=day_offset)

            if deadline and current_date > deadline:
                break

            date_str = current_date.strftime("%Y-%m-%d")

            events = conn.execute(
                """
                SELECT startTime, endTime
                FROM events
                WHERE userID = ?
                AND DATE(startTime) = ?
                AND isDeleted = 0
                ORDER BY startTime
                """,
                (user_id, date_str)
            ).fetchall()

            busy = []

            for event in events:
                try:
                    busy.append((
                        parse_calendar_dt(event["startTime"]),
                        parse_calendar_dt(event["endTime"])
                    ))
                except Exception:
                    pass

            if (
                school_start_hour is not None and
                school_end_hour is not None
            ):
                try:
                    school_start = current_date.replace(
                        hour=int(school_start_hour),
                        minute=0,
                        second=0,
                        microsecond=0
                    )

                    school_end = current_date.replace(
                        hour=int(school_end_hour),
                        minute=0,
                        second=0,
                        microsecond=0
                    )

                    busy.append((school_start, school_end))

                except Exception:
                    pass

            busy.sort(key=lambda x: x[0])

            slot_start = current_date.replace(
                hour=study_start_hour,
                minute=0,
                second=0,
                microsecond=0
            )

            if slot_start < now:
                slot_start = round_up_to_interval(now)

            day_end = current_date.replace(
                hour=study_end_hour,
                minute=0,
                second=0,
                microsecond=0
            )

            for busy_start, busy_end in busy:

                slot_end = slot_start + timedelta(
                    minutes=duration_minutes
                )

                if (
                    slot_end <= busy_start and
                    slot_end <= day_end
                ):

                    if deadline and slot_end > deadline:
                        break

                    return {
                        "start": slot_start.isoformat(),
                        "end": slot_end.isoformat()
                    }

                if slot_start < busy_end:
                    slot_start = round_up_to_interval(busy_end)

            slot_end = slot_start + timedelta(
                minutes=duration_minutes
            )

            if slot_end <= day_end:

                if deadline and slot_end > deadline:
                    continue

                return {
                    "start": slot_start.isoformat(),
                    "end": slot_end.isoformat()
                }

        return None

    finally:
        conn.close()



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
    
    rows = [dict(row) for row in conn.execute(query, params).fetchall()]
    conn.close()

    events = []
    for row in rows:
        row['id'] = row.get('eventID')
        row['start'] = row.get('startTime')
        row['end'] = row.get('endTime')
        row['color'] = row.get('color') or get_event_color(row.get('source', 'user'))
        events.append(row)

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
            (userID, title, description, startTime, endTime, source, color, isDeleted, googleEventID)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL)
        """, (
            user_id,
            data['title'],
            data.get('description', ''),
            data['startTime'],
            data['endTime'],
            'user',
            get_event_color('user')
        ))

        event_id = cursor.lastrowid
        conn.commit()

        # 2. CREATE GOOGLE EVENT
        service = get_google_service(user_id)
        google_event_id = None

        if service:
            try:
                event_body = google_event_body(data['title'], data.get('description', ''), data['startTime'], data['endTime'])
                print(f"[GOOGLE DEBUG] Attempting to push event body: {event_body}")
                created = service.events().insert(
                    calendarId=GOOGLE_CALENDAR_ID,
                    body=event_body
                ).execute()
                print(f"[GOOGLE DEBUG] Push successful, Google event ID: {created.get('id')}")
                google_event_id = created.get('id')

                cursor.execute("""
                    UPDATE events SET googleEventID=?, lastSynced=CURRENT_TIMESTAMP WHERE eventID=?
                """, (google_event_id, event_id))
                conn.commit()
            except Exception as google_error:
                print(f"[GOOGLE] Could not push created event: {type(google_error).__name__}: {google_error}")
                traceback.print_exc()
        else:
            print(f"[GOOGLE DEBUG] Service is None — skipping push for event {event_id}")

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
        params.append(user_id)

        query = f"UPDATE events SET {', '.join(update_fields)} WHERE eventID = ? and userID = ?"
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
        try:
            service.events().update(
                calendarId=GOOGLE_CALENDAR_ID,
                eventId=google_event_id,
                body=google_event_body(
                    data.get('title', event['title']),
                    data.get('description', event['description'] or ''),
                    data.get('startTime', event['startTime']),
                    data.get('endTime', event['endTime'])
                )
            ).execute()
            conn.execute('UPDATE events SET lastSynced = CURRENT_TIMESTAMP WHERE eventID = ?', (event_id,))
            conn.commit()
        except Exception as google_error:
            print(f"[GOOGLE] Could not update event {event_id}: {google_error}")

    conn.close()
    return jsonify({'status': 'updated'}), 200


@app.route('/calendar/events/<int:event_id>', methods=['DELETE'])
@login_required
def delete_event(event_id):
    """Delete (soft delete) an event."""
    user_id = session.get('user_id')
    
    conn = get_db_connection()
    
    # Verify ownership
    event = conn.execute('SELECT userID, title, description, googleEventID FROM events WHERE eventID = ?', (event_id,)).fetchone()
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
        try:
            service.events().delete(
                calendarId=GOOGLE_CALENDAR_ID,
                eventId=google_event_id
            ).execute()
        except HttpError as google_error:
            if getattr(google_error, 'status_code', None) not in (404, 410):
                print(f"[GOOGLE] Could not delete event {event_id}: {google_error}")
        except Exception as google_error:
            print(f"[GOOGLE] Could not delete event {event_id}: {google_error}")

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
        cursor.execute("""
            SELECT taskID, title, description, dueDate, taskType, progress
            FROM tasks
            WHERE userID = ?
              AND (eventID IS NULL OR eventID = '')
              AND COALESCE(status, 'pending') != 'completed'
            ORDER BY dueDate ASC, taskID ASC
        """, (user_id,))
        tasks = cursor.fetchall()
        created_events = []
        failed_tasks = []
        service = None
        try:
            service = get_google_service(user_id)
        except Exception as e:
            print(f"[GOOGLE SERVICE ERROR] {e}")
        
        for task in tasks:
            duration = 60
            due_date = task['dueDate']
            
            slot = find_available_slot(duration, user_id, before_date=due_date)
            
            if check_overlap(
                slot['start'],
                slot['end'],
                user_id
            ):
                continue

            if slot:
                title = f"Study: {task['title']}"
                description = task['description'] or f"Study task: {task['title']}"
                cursor.execute("""
                    INSERT INTO events 
                    (userID, title, description, startTime, endTime, source, color, isDeleted)
                    VALUES (?, ?, ?, ?, ?, 'auto', ?, 0)
                """, (
                    user_id,
                    title,
                    description,
                    slot['start'],
                    slot['end'],
                    color
                ))
                
                event_id = cursor.lastrowid
                google_event_id = None

                if service:
                    try:
                        created_google = service.events().insert(
                            calendarId=GOOGLE_CALENDAR_ID,
                            body=google_event_body(title, description, slot['start'], slot['end'])
                        ).execute()
                        google_event_id = created_google.get('id')
                        cursor.execute(
                            'UPDATE events SET googleEventID = ?, lastSynced = CURRENT_TIMESTAMP WHERE eventID = ?',
                            (google_event_id, event_id)
                        )
                    except Exception as google_error:
                        print(f"[GOOGLE] Could not push generated event {event_id}: {google_error}")

                cursor.execute('UPDATE tasks SET eventID = ? WHERE taskID = ?', (event_id, task['taskID']))
                
                created_events.append({
                    'eventID': event_id,
                    'googleEventID': google_event_id,
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


# ============= SMART SCHEDULE API =============

@app.route('/api/schedule/generate', methods=['POST'])
@login_required
def smart_generate_schedule():
    """
    Generate an intelligent study schedule based on user input and existing data.

    This is the NEW comprehensive schedule generation that:
    1. Collects ALL user data (tasks, exams, events, subjects, free slots)
    2. Passes data to Gemini with evidence-based study techniques
    3. Allocates sessions to available free time windows
    4. Creates meaningful event names
    5. Uses user subject colours from database
    """
    user_id = session.get('user_id')
    data = request.get_json() or {}

    print(f"\n{'='*60}")
    print(f"[API_SCHEDULE] Starting NEW schedule generation for user {user_id}")
    print(f"{'='*60}")

    try:
        conn = get_db_connection()

        # Get user preferences
        user_preferences = get_user_preferences(conn, user_id)
        request_preferences = data.get('preferences') or {}
        if isinstance(request_preferences, dict):
            for key in ('study_start', 'study_end', 'sleep_start', 'sleep_end', 'school_start',
                        'school_end', 'session_duration', 'max_daily_hours'):
                if key in request_preferences:
                    user_preferences[key] = _coerce_int(request_preferences.get(key), user_preferences.get(key))
            if isinstance(request_preferences.get('priority_subjects'), list):
                user_preferences['priority_subjects'] = request_preferences['priority_subjects']
            if isinstance(request_preferences.get('study_techniques'), list):
                user_preferences['study_techniques'] = request_preferences['study_techniques']

        # Build options
        options = {
            'max_daily_hours': user_preferences.get('max_daily_hours', 4),
            'session_duration': user_preferences.get('session_duration', 60)
        }
        if isinstance(data.get('options'), dict):
            options.update(data.get('options'))

        # Get user's prompt
        user_prompt = data.get('freeform_text', '') or "Create a study schedule for my pending tasks and exams."

        print(f"[API_SCHEDULE] User prompt: {user_prompt}")
        print(f"[API_SCHEDULE] User preferences: study {user_preferences.get('study_start')}:00-{user_preferences.get('study_end')}:00")

        # ========== NEW: Collect all user data ==========
        print(f"[API_SCHEDULE] Collecting user data from database...")
        user_data = scheduler.collect_user_data(conn, user_id, user_preferences)

        print(f"[API_SCHEDULE] Collected:")
        print(f"  - Tasks: {len(user_data['tasks'])}")
        print(f"  - Exams: {len(user_data['exams'])}")
        print(f"  - Events: {len(user_data['events'])}")
        print(f"  - Subjects: {len(user_data['subjects'])}")
        print(f"  - Free slots: {len(user_data['free_slots'])}")
        print(f"  - Subject colour map: {user_data['subject_colour_map']}")
        print(f"[API_SCHEDULE] User preferences: {user_preferences}")
        print(f"[API_SCHEDULE] Options: {options}")
        print(f"[API_SCHEDULE] Techniques: {user_preferences.get('study_techniques', [])}")

        # ========== Call Gemini with full context ==========
        print(f"[API_SCHEDULE] Calling Gemini for intelligent schedule generation...")

        gemini_result = scheduler.generate_smart_schedule_with_gemini(
            user_prompt=user_prompt,
            user_data=user_data,
            user_preferences=user_preferences,
            options=options
        )

        print(f"[API_SCHEDULE] Gemini result: error={gemini_result.get('error')}, sessions={len(gemini_result.get('sessions', []))}")

        # Check if Gemini succeeded
        if gemini_result.get('sessions') and not gemini_result.get('error'):
            sessions = gemini_result['sessions']
            summary = gemini_result.get('summary', {})
            reasoning = gemini_result.get('reasoning', '')
            techniques = gemini_result.get('techniques_used', [])

            print(f"[API_SCHEDULE] SUCCESS - Generated {len(sessions)} sessions")
            print(f"[API_SCHEDULE] Techniques: {techniques}")
            print(f"[API_SCHEDULE] Summary: {summary}")

            conn.close()
            return jsonify({
                'status': 'success',
                'sessions': sessions,
                'summary': summary,
                'reasoning': reasoning,
                'techniques_used': techniques,
                'source': 'gemini'
            }), 200

        # ========== Fallback if Gemini fails ==========
        print(f"[API_SCHEDULE] Gemini failed or returned error: {gemini_result.get('error')}")
        print(f"[API_SCHEDULE] Using fallback local scheduler...")

        # Build schedule items from tasks and exams
        schedule_items = []

        # Add tasks from the collected data
        for task in user_data['tasks']:
            schedule_items.append({
                'id': task.get('id'),
                'title': task.get('title', 'Task'),
                'due_date': task.get('due_date'),
                'type': task.get('type', 'study'),
                'subject': task.get('subject', 'general')
            })

        # Add exams
        for exam in user_data['exams']:
            schedule_items.append({
                'title': exam.get('title', 'Exam'),
                'due_date': exam.get('exam_date'),
                'type': 'exam',
                'subject': exam.get('subject', 'general')
            })

        # If still no items, create some generic study sessions
        if not schedule_items:
            print(f"[API_SCHEDULE] No tasks/exams found, creating generic study sessions")
            for subj in user_data['subjects'][:3]:
                schedule_items.append({
                    'title': f"{subj['subjectName']} Revision",
                    'due_date': None,
                    'type': 'revision',
                    'subject': subj['subjectName']
                })

        # Use the free slots we calculated and allocate locally
        # (This is a simplified fallback - ideally Gemini handles this)
        from datetime import timedelta

        allocated = []
        used_dates = set()

        for i, item in enumerate(schedule_items[:10]):  # Limit to 10 sessions
            # Find a slot
            for slot in user_data['free_slots']:
                date_key = slot['start'].strftime('%Y-%m-%d')
                if date_key in used_dates:
                    continue
                if slot['duration_minutes'] < 45:
                    continue

                allocated.append({
                    'title': item.get('title', 'Study Session'),
                    'subject': item.get('subject', 'General'),
                    'start': slot['start'].isoformat(),
                    'end': (slot['start'] + timedelta(minutes=60)).isoformat(),
                    'duration_minutes': 60,
                    'priority': 'normal',
                    'strategy': 'Study',
                    'description': f"Study session for {item.get('title')}",
                    'colour': user_data['subject_colour_map'].get(item.get('subject', '').lower(), '#f5761b'),
                    'type': 'study'
                })
                used_dates.add(date_key)
                break

        summary = scheduler.get_schedule_summary(allocated)

        print(f"[API_SCHEDULE] Fallback generated {len(allocated)} sessions")
        conn.close()

        return jsonify({
            'status': 'success',
            'sessions': allocated,
            'summary': summary,
            'reasoning': 'Generated using local scheduler after Gemini failed',
            'source': 'fallback'
        }), 200

    except Exception as e:
        print(f'[API_SCHEDULE] Error: {e}')
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/schedule/save', methods=['POST'])
@login_required
def save_generated_schedule():
    """
    Save the generated study sessions to the calendar.

    Each session should contain:
    - title: The study session title
    - start: Start datetime ISO format
    - end: End datetime ISO format
    - colour: Subject colour (from user's saved preferences)
    - description: Strategy and reasoning info
    - task_id: Related task ID (optional)
    - exam_id: Related exam ID (optional)
    """
    user_id = session.get('user_id')
    data = request.get_json() or {}

    sessions = data.get('sessions', [])
    link_to_tasks = data.get('link_to_tasks', True)

    if not sessions:
        return jsonify({'error': 'No sessions to save'}), 400

    print(f"\n{'='*60}")
    print(f"[API_SCHEDULE_SAVE] Saving {len(sessions)} sessions for user {user_id}")
    print(f"{'='*60}")

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        created_events = []
        default_color = get_event_color('auto')
        service = None

        # Try to get Google service but don't fail if not available
        try:
            service = get_google_service(user_id)
            if service:
                print(f"[API_SCHEDULE_SAVE] Google Calendar connected")
            else:
                print(f"[API_SCHEDULE_SAVE] Google Calendar not connected - will save locally only")
        except Exception as e:
            print(f"[GOOGLE SERVICE ERROR] {e} - continuing without Google sync")

        for sesh in sessions:
            if not isinstance(sesh, dict):
                continue

            try:
                start_time = datetime.fromisoformat(sesh['start'])
                end_time = datetime.fromisoformat(sesh['end'])
            except Exception as e:
                print(f"[SCHEDULE_SAVE] Invalid time format: {e}")
                continue

            if end_time <= start_time:
                print("[SCHEDULE_SAVE] Skipping session with non-positive duration")
                continue

            # Get description - can be in 'notes' or 'description' field
            description = sesh.get('description') or sesh.get('notes', '')

            # Get colour - prefer session colour, fallback to default
            colour = sesh.get('colour') or sesh.get('color') or default_color

            print(f"[API_SCHEDULE_SAVE] Creating event: {sesh.get('title')} at {sesh.get('start')}")

            cursor.execute("""
                INSERT INTO events
                (userID, title, description, startTime, endTime, source, color, isDeleted)
                VALUES (?, ?, ?, ?, ?, 'auto', ?, 0)
            """, (
                user_id,
                sesh.get('title', 'Study Session'),
                description,
                start_time.isoformat(),
                end_time.isoformat(),
                colour
            ))

            event_id = cursor.lastrowid
            google_event_id = None

            # Sync to Google Calendar if connected - DON'T let failure break saving
            if service:
                try:
                    event_body = google_event_body(
                        sesh.get('title', 'Study Session'),
                        description,
                        start_time,  # pass datetime object directly
                        end_time     # pass datetime object directly
                    )
                    print(f"[GOOGLE DEBUG] Schedule save pushing event body: {event_body}")
                    google_event = service.events().insert(
                        calendarId=GOOGLE_CALENDAR_ID,
                        body=event_body
                    ).execute()
                    google_event_id = google_event.get('id')
                    cursor.execute(
                        'UPDATE events SET googleEventID = ?, lastSynced = CURRENT_TIMESTAMP WHERE eventID = ?',
                        (google_event_id, event_id)
                    )
                    print(f"[API_SCHEDULE_SAVE] Synced to Google: {google_event_id}")
                except Exception as google_error:
                    print(f"[GOOGLE] Could not push event {event_id}: {type(google_error).__name__}: {google_error}")
                    traceback.print_exc()
            else:
                print(f"[GOOGLE DEBUG] Service is None for schedule save — skipping Google sync")

            # Link to task if applicable - use task_id from session data
            task_id = sesh.get('task_id')
            if link_to_tasks and task_id:
                try:
                    cursor.execute(
                        'UPDATE tasks SET eventID = ? WHERE taskID = ? AND userID = ?',
                        (event_id, task_id, user_id)
                    )
                    print(f"[API_SCHEDULE_SAVE] Linked to task {task_id}")
                except Exception as e:
                    print(f"[API_SCHEDULE_SAVE] Could not link to task: {e}")

            created_events.append({
                'eventID': event_id,
                'googleEventID': google_event_id,
                'title': sesh.get('title'),
                'start': sesh['start'],
                'end': sesh['end']
            })

        if not created_events:
            conn.rollback()
            return jsonify({'status': 'error', 'message': 'No valid study sessions were available to save.'}), 400

        conn.commit()

        print(f"[API_SCHEDULE_SAVE] Successfully saved {len(created_events)} events")
        print(f"{'='*60}\n")

        return jsonify({
            'status': 'success',
            'created': len(created_events),
            'events': created_events
        }), 200

    except Exception as e:
        if conn:
            conn.rollback()
        print(f'[SCHEDULE_SAVE] Error: {e}')
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/schedule/recommended', methods=['GET'])
@login_required
def get_recommended_times():
    """
    Get recommended study times based on user's existing schedule and preferences.
    """
    user_id = session.get('user_id')
    

    try:
        conn = get_db_connection()
        user_preferences = get_user_preferences(conn, user_id)

        # Get existing events for the next 7 days
        cursor = conn.cursor()
        cursor.execute("""
            SELECT startTime, endTime, title
            FROM events
            WHERE userID = ?
              AND isDeleted = 0
              AND startTime >= datetime('now')
              AND startTime <= datetime('now', '+7 days')
            ORDER BY startTime
        """, (user_id,))

        events = []
        for row in cursor.fetchall():
            try:
                events.append({
                    'start': parse_calendar_dt(row['startTime']),
                    'end': parse_calendar_dt(row['endTime']),
                    'title': row['title']
                })
            except Exception:
                continue

        # Get pending tasks
        cursor.execute("""
            SELECT title, dueDate, taskType
            FROM tasks
            WHERE userID = ?
              AND COALESCE(status, 'pending') != 'completed'
              AND dueDate IS NOT NULL
            ORDER BY dueDate
            LIMIT 10
        """, (user_id,))

        tasks = []
        for row in cursor.fetchall():
            try:
                due_date = datetime.strptime(row['dueDate'], '%Y-%m-%d').date() if row['dueDate'] else None
            except Exception:
                due_date = None

            tasks.append({
                'title': row['title'],
                'due_date': due_date,
                'type': row['taskType']
            })

        conn.close()

        # Find available slots
        generator = scheduler.ScheduleGenerator(user_id, user_preferences)
        generator.events = events
        slots = generator.find_available_slots(
            duration_minutes=60,
            user_id=user_id,
            end_date=datetime.now() + timedelta(days=7)
        )

        # Format slots for response
        available_slots = []
        for slot in slots[:20]:  # Limit to 20 slots
            available_slots.append({
                'start': slot['start'].isoformat(),
                'end': slot['end'].isoformat(),
                'duration_minutes': int((slot['end'] - slot['start']).total_seconds() / 60)
            })

        return jsonify({
            'status': 'success',
            'available_slots': available_slots,
            'upcoming_tasks': tasks,
            'preferences': user_preferences
        }), 200

    except Exception as e:
        print(f'[RECOMMENDED_TIMES] Error: {e}')
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/schedule/parse-input', methods=['POST'])
@login_required
def parse_schedule_input():
    """
    Parse freeform text input and return structured data for preview.
    """
    data = request.get_json() or {}
    text = data.get('text', '')

    try:
        parsed = scheduler.parse_freeform_text(text)
        return jsonify({
            'status': 'success',
            'parsed': parsed
        }), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


def get_user_preferences(conn, user_id):
    """Get user scheduling preferences."""
    cursor = conn.cursor()
    cursor.execute("SELECT userSettings FROM users WHERE userID = ?", (user_id,))
    row = cursor.fetchone()

    settings = _load_user_settings(row['userSettings'] if row else None)
    return _scheduler_settings_from(settings)


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
    
    service = None
    try:
        service = get_google_service(user_id)
    except Exception as e:
        print(f"[GOOGLE SERVICE ERROR] {e}")
        
    if service and event['googleEventID']:
        try:
            service.events().update(
                calendarId=GOOGLE_CALENDAR_ID,
                eventId=event['googleEventID'],
                body=google_event_body(event['title'], event['description'] or '', new_start, new_end)
            ).execute()
            conn.execute('UPDATE events SET lastSynced = CURRENT_TIMESTAMP WHERE eventID = ?', (event_id,))
        except Exception as google_error:
            print(f"[GOOGLE] Could not reschedule event {event_id}: {google_error}")
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'rescheduled'}), 200


@app.route('/calendar/check-google-auth', methods=['GET'])
@login_required
def check_google_auth():
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


@app.route('/calendar/google-debug', methods=['GET'])
@login_required
def google_debug():
    """Return non-secret Google OAuth setup diagnostics for troubleshooting."""
    client_id, client_secret = get_google_client_config()
    return jsonify({
        'client_secret_file_exists': os.path.exists(GOOGLE_CLIENT_SECRET_FILE),
        'client_secret_path': GOOGLE_CLIENT_SECRET_FILE,
        'client_id_present': bool(client_id),
        'client_secret_present': bool(client_secret),
        'redirect_uri': get_google_redirect_uri(),
        'last_error_detail': session.get('google_last_error_detail')
    }), 500


@app.route('/calendar/sync/google', methods=['POST'])
@login_required
def sync_google_calendar():
    """Synchronize the user's primary Google Calendar into the local database."""
    user_id = session.get('user_id')

    try:
        conn = get_db_connection()
        creds_row = conn.execute(
            "SELECT syncToken FROM google_creds WHERE userID=?",
            (user_id,)
        ).fetchone()

        if not creds_row:
            conn.close()
            return jsonify({'error': 'Google Calendar not connected. Please link your account first.'}), 400

        service = get_google_service(user_id)
        if not service:
            conn.close()
            return jsonify({'error': 'Google Calendar credentials are unavailable or expired. Please reconnect Google Calendar.'}), 400

        sync_token = creds_row['syncToken']
        now = datetime.utcnow()
        time_min = (now - timedelta(days=30)).isoformat() + 'Z'
        time_max = (now + timedelta(days=90)).isoformat() + 'Z'

        def fetch_pages(use_sync_token=True):
            page_token = None
            all_events = []
            next_sync_token = None
            while True:
                request_kwargs = {
                    'calendarId': GOOGLE_CALENDAR_ID,
                    'singleEvents': True,
                    'showDeleted': True,
                    'maxResults': 2500,
                    'pageToken': page_token,
                }
                if sync_token and use_sync_token:
                    request_kwargs['syncToken'] = sync_token
                else:
                    request_kwargs.update({
                        'timeMin': time_min,
                        'timeMax': time_max,
                        'orderBy': 'startTime',
                    })

                events_result = service.events().list(**request_kwargs).execute()
                all_events.extend(events_result.get('items', []))
                page_token = events_result.get('nextPageToken')
                next_sync_token = events_result.get('nextSyncToken') or next_sync_token
                if not page_token:
                    return all_events, next_sync_token

        try:
            events, next_sync_token = fetch_pages(use_sync_token=True)
        except HttpError as e:
            status = getattr(getattr(e, 'resp', None), 'status', None)
            if status == 410:
                conn.execute('UPDATE google_creds SET syncToken = NULL WHERE userID = ?', (user_id,))
                conn.commit()
                sync_token = None
                events, next_sync_token = fetch_pages(use_sync_token=False)
            else:
                raise

        imported_count = 0
        updated_count = 0
        deleted_count = 0
        imported_events = []

        for event in events:
            try:
                google_event_id = event.get('id')
                if not google_event_id:
                    continue

                if event.get('status') == 'cancelled':
                    existing = conn.execute(
                        'SELECT eventID FROM events WHERE userID = ? AND googleEventID = ?',
                        (user_id, google_event_id)
                    ).fetchone()
                    if existing:
                        conn.execute(
                            'UPDATE events SET isDeleted = 1, updatedAt = CURRENT_TIMESTAMP, lastSynced = CURRENT_TIMESTAMP WHERE eventID = ?',
                            (existing['eventID'],)
                        )
                        deleted_count += 1
                    continue

                start = event['start'].get('dateTime', event['start'].get('date'))
                end   = event['end'].get('dateTime',   event['end'].get('date'))

                # Google all-day events use an EXCLUSIVE end date
                # (Jun 15 event → end.date = Jun 16).
                # Convert to inclusive so FullCalendar renders one day
                # and the overlap checker doesn't block the following day.
                if 'T' not in start:
                    start += 'T00:00:00'
                if 'T' not in end:
                    import datetime as _dt_mod
                    _end_d = _dt_mod.datetime.strptime(end, '%Y-%m-%d') - _dt_mod.timedelta(days=1)
                    end = _end_d.strftime('%Y-%m-%dT23:59:59')

                existing = conn.execute("""
                    SELECT eventID FROM events
                    WHERE userID = ? AND googleEventID = ?
                """, (user_id, google_event_id)).fetchone()

                if existing:
                    # Never overwrite colour/source for auto-generated
                    # study-session events — they should stay green.
                    _existing_meta = conn.execute(
                        "SELECT source, color FROM events WHERE eventID = ?",
                        (existing["eventID"],)
                    ).fetchone()
                    _is_auto = _existing_meta and _existing_meta["source"] == "auto"

                    if _is_auto:
                        conn.execute("""
                            UPDATE events
                            SET title = ?, description = ?, startTime = ?, endTime = ?,
                                isDeleted = 0,
                                updatedAt = CURRENT_TIMESTAMP, lastSynced = CURRENT_TIMESTAMP
                            WHERE eventID = ?
                        """, (
                            event.get("summary", "Untitled Event"),
                            event.get("description", ""),
                            start,
                            end,
                            existing["eventID"]
                        ))
                    else:
                        conn.execute("""
                            UPDATE events
                            SET title = ?, description = ?, startTime = ?, endTime = ?,
                                source = 'google', color = ?, isDeleted = 0,
                                updatedAt = CURRENT_TIMESTAMP, lastSynced = CURRENT_TIMESTAMP
                            WHERE eventID = ?
                        """, (
                            event.get("summary", "Untitled Event"),
                            event.get("description", ""),
                            start,
                            end,
                            get_event_color("google"),
                            existing["eventID"]
                        ))
                    event_id = existing["eventID"]
                    updated_count += 1
                else:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO events
                        (userID, googleEventID, title, description, startTime, endTime, source, color, isDeleted, lastSynced)
                        VALUES (?, ?, ?, ?, ?, ?, 'google', ?, 0, CURRENT_TIMESTAMP)
                    """, (
                        user_id,
                        google_event_id,
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
                    'googleEventID': google_event_id,
                    'title': event.get('summary', 'Untitled Event'),
                    'start': start,
                    'end': end
                })

            except Exception as e:
                print(f"Error importing event {event.get('summary', 'Unknown')}: {e}")
                continue

        if next_sync_token:
            conn.execute(
                'UPDATE google_creds SET syncToken = ? WHERE userID = ?',
                (next_sync_token, user_id)
            )
        conn.commit()
        conn.close()

        return jsonify({
            'status': 'success',
            'message': f'Successfully synced Google Calendar',
            'imported': imported_count,
            'updated': updated_count,
            'deleted': deleted_count,
            'skipped': 0,
            'events': imported_events
        }), 200

    except Exception as e:
        print(f"Error syncing Google Calendar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Sync failed: {str(e)}'}), 500


# ============= TIMER API ROUTES =============

@app.route('/api/subjects/all')
@login_required
def get_subjects():
    """Get all subjects for the current user"""
    try:
        conn = get_db_connection()
        user_id = session.get('user_id')
        
        subjects = conn.execute(
            'SELECT * FROM subjects WHERE userID = ? ORDER BY sortOrder ASC',
            (user_id,)
        ).fetchall()
        
        conn.close()
        return jsonify({
            'subjects': [dict(s) for s in subjects]
        })
    except Exception as e:
        print(f'[GET_SUBJECTS] Error: {e}')
        return jsonify({'error': 'Could not fetch subjects'}), 500

@app.route('/api/timer/presets', methods=['GET'])
@login_required
def get_timer_presets():
    """Get all timer presets for the current user"""
    try:
        conn = get_db_connection()
        user_id = session.get('user_id')
        
        presets = conn.execute(
            'SELECT * FROM timer_presets WHERE userID = ? ORDER BY createdAt DESC',
            (user_id,)
        ).fetchall()
        
        conn.close()
        return jsonify({
            'presets': [dict(p) for p in presets]
        })
    except Exception as e:
        print(f'[GET_TIMER_PRESETS] Error: {e}')
        return jsonify({'error': 'Could not fetch presets'}), 500

@app.route('/api/timer/presets', methods=['POST'])
@login_required
def create_timer_preset():
    """Create a new timer preset"""
    try:
        data = request.get_json() or {}
        user_id = session.get('user_id')
        
        if not data.get('presetName') or not data.get('durationSeconds'):
            return jsonify({'error': 'Missing required fields'}), 400
        
        conn = get_db_connection()
        conn.execute(
            '''INSERT INTO timer_presets 
               (userID, presetName, durationSeconds, description, createdAt, updatedAt)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)''',
            (user_id, data['presetName'], int(data['durationSeconds']), data.get('description', ''))
        )
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        print(f'[CREATE_TIMER_PRESET] Error: {e}')
        return jsonify({'error': 'Could not create preset'}), 500

@app.route('/api/timer/presets', methods=['PUT'])
@login_required
def update_timer_preset():
    """Update an existing timer preset"""
    try:
        data = request.get_json() or {}
        user_id = session.get('user_id')
        preset_id = data.get('presetID')
        
        if not preset_id:
            return jsonify({'error': 'Missing presetID'}), 400
        
        conn = get_db_connection()
        # Verify ownership
        preset = conn.execute(
            'SELECT userID FROM timer_presets WHERE presetID = ?',
            (preset_id,)
        ).fetchone()
        
        if not preset or preset['userID'] != user_id:
            conn.close()
            return jsonify({'error': 'Preset not found or unauthorized'}), 403
        
        conn.execute(
            '''UPDATE timer_presets 
               SET presetName = ?, durationSeconds = ?, description = ?, updatedAt = CURRENT_TIMESTAMP
               WHERE presetID = ?''',
            (data['presetName'], int(data['durationSeconds']), data.get('description', ''), preset_id)
        )
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        print(f'[UPDATE_TIMER_PRESET] Error: {e}')
        return jsonify({'error': 'Could not update preset'}), 500

@app.route('/api/timer/presets', methods=['DELETE'])
@login_required
def delete_timer_preset():
    """Delete a timer preset"""
    try:
        data = request.get_json() or {}
        user_id = session.get('user_id')
        preset_id = data.get('presetID')
        
        if not preset_id:
            return jsonify({'error': 'Missing presetID'}), 400
        
        conn = get_db_connection()
        # Verify ownership
        preset = conn.execute(
            'SELECT userID FROM timer_presets WHERE presetID = ?',
            (preset_id,)
        ).fetchone()
        
        if not preset or preset['userID'] != user_id:
            conn.close()
            return jsonify({'error': 'Preset not found or unauthorized'}), 403
        
        conn.execute('DELETE FROM timer_presets WHERE presetID = ?', (preset_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        print(f'[DELETE_TIMER_PRESET] Error: {e}')
        return jsonify({'error': 'Could not delete preset'}), 500

@app.route('/api/timer/sessions', methods=['POST'])
@login_required
def create_timer_session():
    """Create or record a timer session."""
    try:
        data = request.get_json() or {}
        user_id = session.get('user_id')
        status = data.get('status', 'completed')
        valid_statuses = {'in_progress', 'paused', 'completed', 'abandoned'}
        
        if not data.get('subjectID'):
            return jsonify({'error': 'Missing required fields'}), 400
        if status not in valid_statuses:
            return jsonify({'error': 'Invalid session status'}), 400
        
        conn = get_db_connection()
        end_time_sql = 'CURRENT_TIMESTAMP' if status in {'completed', 'abandoned'} else 'NULL'
        cursor = conn.execute(
            f'''INSERT INTO timer_sessions
                (userID, subjectID, presetID, durationSeconds, timeSpentSeconds, status, notes, startTime, endTime, createdAt, updatedAt)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, {end_time_sql}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)''',
            (user_id, int(data['subjectID']), data.get('presetID'),
             int(data.get('durationSeconds', 0)), int(data.get('timeSpentSeconds', 0)), status,
             data.get('notes', ''))
        )
        session_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'sessionID': session_id})
    except Exception as e:
        print(f'[CREATE_TIMER_SESSION] Error: {e}')
        return jsonify({'error': 'Could not save session'}), 500

@app.route('/api/timer/sessions/<int:session_id>', methods=['PATCH'])
@login_required
def update_timer_session(session_id):
    """Autosave an existing timer session for the current user."""
    try:
        data = request.get_json() or {}
        user_id = session.get('user_id')
        status = data.get('status')
        valid_statuses = {'in_progress', 'paused', 'completed', 'abandoned'}

        if status and status not in valid_statuses:
            return jsonify({'error': 'Invalid session status'}), 400

        conn = get_db_connection()
        existing = conn.execute(
            'SELECT userID FROM timer_sessions WHERE sessionID = ?',
            (session_id,)
        ).fetchone()

        if not existing or existing['userID'] != user_id:
            conn.close()
            return jsonify({'error': 'Session not found or unauthorized'}), 403

        fields = []
        values = []
        allowed_fields = {
            'subjectID': int,
            'presetID': lambda value: None if value in ('', None) else int(value),
            'durationSeconds': int,
            'timeSpentSeconds': int,
            'status': str,
            'notes': str
        }

        for field, caster in allowed_fields.items():
            if field in data:
                fields.append(f'{field} = ?')
                values.append(caster(data.get(field)))

        if data.get('endTime') or status in {'completed', 'abandoned'}:
            fields.append('endTime = CURRENT_TIMESTAMP')

        fields.append('updatedAt = CURRENT_TIMESTAMP')
        values.append(session_id)

        conn.execute(
            f'''UPDATE timer_sessions
                SET {', '.join(fields)}
                WHERE sessionID = ?''',
            values
        )
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'sessionID': session_id})
    except Exception as e:
        print(f'[UPDATE_TIMER_SESSION] Error: {e}')
        return jsonify({'error': 'Could not update session'}), 500

@app.route('/api/timer/sessions', methods=['GET'])
@login_required
def get_timer_sessions():
    """Get all timer sessions for the current user"""
    try:
        conn = get_db_connection()
        user_id = session.get('user_id')
        
        sessions = conn.execute(
            '''SELECT ts.*, s.subjectName, tp.presetName 
               FROM timer_sessions ts
               LEFT JOIN subjects s ON ts.subjectID = s.subjectID
               LEFT JOIN timer_presets tp ON ts.presetID = tp.presetID
               WHERE ts.userID = ? 
               ORDER BY ts.startTime DESC''',
            (user_id,)
        ).fetchall()
        
        conn.close()
        return jsonify({
            'sessions': [dict(s) for s in sessions]
        })
    except Exception as e:
        print(f'[GET_TIMER_SESSIONS] Error: {e}')
        return jsonify({'error': 'Could not fetch sessions'}), 500


@app.route('/api/progress')
@login_required
def get_progress():
    user_id = session.get('user_id')
    try:
        conn = get_db_connection()
 
        task_stats = conn.execute(
            '''SELECT status,
                      COUNT(*)        AS count,
                      AVG(progress)   AS avg_progress
               FROM tasks
               WHERE userID = ?
               GROUP BY status''',
            (user_id,)
        ).fetchall()
 
        tasks_by_subject = conn.execute(
            '''SELECT s.subjectName,
                      s.colourScheme,
                      COUNT(*)            AS count,
                      AVG(t.progress)     AS avg_progress,
                      SUM(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) AS completed
               FROM tasks t
               JOIN subjects s ON t.subjectID = s.subjectID
               WHERE t.userID = ?
               GROUP BY s.subjectName, s.colourScheme
               ORDER BY count DESC''',
            (user_id,)
        ).fetchall()
 
        # ── FIX: include taskID, subjectID, colourScheme ──────────────
        upcoming_tasks = conn.execute(
            '''SELECT t.taskID,
                      t.title,
                      t.dueDate,
                      t.progress,
                      t.status,
                      s.subjectName,
                      s.colourScheme,
                      s.subjectID
               FROM tasks t
               LEFT JOIN subjects s ON t.subjectID = s.subjectID
               WHERE t.userID = ?
                 AND COALESCE(t.status, 'pending') != 'completed'
                 AND t.dueDate IS NOT NULL
               ORDER BY t.dueDate ASC
               LIMIT 10''',
            (user_id,)
        ).fetchall()
 
        session_stats = conn.execute(
            '''SELECT
                 COUNT(*)                                                        AS total_sessions,
                 COALESCE(SUM(durationSeconds),  0)                             AS total_duration_seconds,
                 COALESCE(SUM(timeSpentSeconds), 0)                             AS total_time_spent_seconds,
                 SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END)          AS completed_sessions,
                 SUM(CASE WHEN status = 'paused'    THEN 1 ELSE 0 END)          AS paused_sessions,
                 SUM(CASE WHEN status = 'abandoned' THEN 1 ELSE 0 END)          AS abandoned_sessions
               FROM timer_sessions
               WHERE userID = ?''',
            (user_id,)
        ).fetchone()
 
        # ── Flashcard accuracy per subject ────────────────────────────
        flashcard_by_subject = conn.execute(
            '''SELECT
                 d.subject,
                 COUNT(r.resultID)                                              AS sessions,
                 COALESCE(SUM(r.knew),       0)                                AS total_knew,
                 COALESCE(SUM(r.unsure),     0)                                AS total_unsure,
                 COALESCE(SUM(r.missed),     0)                                AS total_missed,
                 COALESCE(SUM(r.totalCards), 0)                                AS total_cards,
                 ROUND(
                     AVG(CAST(r.knew AS REAL) / MAX(r.totalCards, 1) * 100),
                 1)                                                             AS avg_accuracy_pct
               FROM flashcard_results r
               JOIN flashcard_decks d ON r.deckID = d.deckID
               WHERE r.userID = ?
               GROUP BY d.subject
               ORDER BY sessions DESC''',
            (user_id,)
        ).fetchall()
 
        # ── Time on task per subject ──────────────────────────────────
        time_by_subject = conn.execute(
            '''SELECT
                 s.subjectName,
                 s.colourScheme,
                 COALESCE(SUM(ts.timeSpentSeconds), 0) AS total_seconds,
                 COUNT(ts.sessionID)                    AS session_count
               FROM timer_sessions ts
               JOIN subjects s ON ts.subjectID = s.subjectID
               WHERE ts.userID = ?
               GROUP BY s.subjectName, s.colourScheme
               ORDER BY total_seconds DESC''',
            (user_id,)
        ).fetchall()
 
        conn.close()
 
        return jsonify({
            'tasks': {
                'stats':      [dict(r) for r in task_stats],
                'by_subject': [dict(r) for r in tasks_by_subject],
                'upcoming':   [dict(r) for r in upcoming_tasks],
            },
            'sessions':        dict(session_stats),
            'flashcard_stats': [dict(r) for r in flashcard_by_subject],
            'time_by_subject': [dict(r) for r in time_by_subject],
        })
    except Exception as e:
        print(f'[GET_PROGRESS] Error: {e}')
        traceback.print_exc()
        return jsonify({'error': 'Could not fetch progress'}), 500

@app.route('/api/resources')
@login_required
def get_resources():
    """Return the resource library tree, including the user's own uploads."""
    user_id = session.get('user_id')
    try:
        libraries = []
        from RAG.paths import SUBJECT_RESOURCE_DIRS, CHAT_DATABASE_SUBJECT_DIRS

        # ── Chat-DB library ──
        chat_db_library = {
            'title': 'Chat Database',
            'source_key': 'chat_db',
            'subjects': [],
        }
        for subject_name, subject_dir in CHAT_DATABASE_SUBJECT_DIRS.items():
            if os.path.isdir(subject_dir):
                chat_db_library['subjects'].append({
                    'name': subject_name,
                    'tree': _build_directory_tree(subject_dir),
                })

        if chat_db_library['subjects']:
            libraries.append(chat_db_library)

        # ── User uploads library ──
        user_upload_dir = os.path.join(USER_UPLOADS_DIR, str(user_id))
        if os.path.isdir(user_upload_dir):
            upload_files = []
            for filename in sorted(os.listdir(user_upload_dir)):
                if filename.startswith('.'):
                    continue
                filepath = os.path.join(user_upload_dir, filename)
                if os.path.isfile(filepath):
                    upload_files.append({
                        'name':      filename,
                        'type':      'file',
                        'path':      filename,
                        'extension': os.path.splitext(filename)[1].lower(),
                    })

            if upload_files:
                libraries.append({
                    'title':      'My Uploads',
                    'source_key': 'user_uploads',
                    'subjects':   [{'name': 'My Files', 'tree': upload_files}],
                })

        return jsonify({'libraries': libraries})

    except Exception as e:
        print(f'[GET_RESOURCES] Error: {e}')
        return jsonify({'error': 'Could not list resources'}), 500


@app.route('/resource')
@login_required
def view_resource():
    source = request.args.get('source', '').strip()
    path   = request.args.get('path',   '').strip()
    if not source or not path:
        abort(400)
 
    from RAG.paths import SUBJECT_RESOURCE_DIRS, CHAT_DATABASE_SUBJECT_DIRS
 
    normalized = _normalize_relative_path(path)
    if not normalized:
        abort(400)
 
    # ── Decide which root directories to search ───────────────────
    if source == 'resources':
        search_roots = list(SUBJECT_RESOURCE_DIRS.values())
    elif source == 'chat_db':
        search_roots = list(CHAT_DATABASE_SUBJECT_DIRS.values())
    elif source == 'user_uploads':
        # user-upload files have their own dedicated route
        abort(400, 'Use /resource/upload/<filename> for user uploads')
    else:
        abort(400, f'Unknown source: {source}')
 
    for root_dir in search_roots:
        resolved = _safe_join(root_dir, normalized)
        if resolved and os.path.isfile(resolved):
            directory = os.path.dirname(resolved)
            filename  = os.path.basename(resolved)
            mime_type, _ = __import__('mimetypes').guess_type(filename)
            as_attachment = False  # open inline in browser
            return send_from_directory(
                directory, filename,
                mimetype=mime_type or 'application/octet-stream',
                as_attachment=as_attachment,
            )
 
    # Nothing found — return a proper 404 (NOT the SPA shell)
    abort(404)


@app.route('/resource/upload/<path:filename>')
@login_required
def view_user_upload(filename):
    """Serve a user-uploaded file securely."""
    user_id    = session.get('user_id')
    user_dir   = os.path.join(USER_UPLOADS_DIR, str(user_id))
    safe_name  = secure_filename(filename)
    if not safe_name:
        abort(400)
    resolved = _safe_join(user_dir, safe_name)
    if not resolved or not os.path.isfile(resolved):
        abort(404)
    return send_from_directory(user_dir, safe_name)


@app.route('/api/resources/upload', methods=['POST'])
@login_required
def upload_resource():
    """Upload a resource file to the user's secure uploads folder."""
    user_id = session.get('user_id')
    file    = request.files.get('file')

    if not file or not file.filename:
        return jsonify({'error': 'No file provided'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        return jsonify({'error': f'File type .{ext} is not allowed'}), 400

    user_dir = os.path.join(USER_UPLOADS_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    base_name  = secure_filename(file.filename)
    name, dext = os.path.splitext(base_name)
    timestamp  = int(datetime.now().timestamp())
    safe_name  = f"{name}_{timestamp}{dext}"
    filepath   = os.path.join(user_dir, safe_name)

    file.save(filepath)

    return jsonify({
        'success':       True,
        'filename':      safe_name,
        'original_name': base_name,
        'size':          os.path.getsize(filepath),
    }), 201


@app.route('/api/resources/user-uploads', methods=['GET'])
@login_required
def get_user_uploads():
    """List all files the current user has uploaded."""
    user_id  = session.get('user_id')
    user_dir = os.path.join(USER_UPLOADS_DIR, str(user_id))

    if not os.path.isdir(user_dir):
        return jsonify({'files': []})

    files = []
    for filename in sorted(os.listdir(user_dir)):
        if filename.startswith('.'):
            continue
        filepath = os.path.join(user_dir, filename)
        if os.path.isfile(filepath):
            files.append({
                'name':      filename,
                'size':      os.path.getsize(filepath),
                'extension': os.path.splitext(filename)[1].lower(),
            })

    return jsonify({'files': files})


@app.route('/api/resources/user-uploads/<path:filename>', methods=['DELETE'])
@login_required
def delete_user_upload(filename):
    """Permanently delete a user-uploaded file."""
    user_id   = session.get('user_id')
    user_dir  = os.path.join(USER_UPLOADS_DIR, str(user_id))
    safe_name = secure_filename(filename)
    resolved  = _safe_join(user_dir, safe_name)

    if not resolved or not os.path.isfile(resolved):
        return jsonify({'error': 'File not found'}), 404

    os.remove(resolved)
    return jsonify({'success': True})


@app.route('/api/flashcards', methods=['POST'])
@login_required
def generate_flashcards():
    data = request.get_json() or {}
    subject = data.get('subject', 'General').strip() or 'General'
    module  = data.get('module', '').strip()  or 'General'
    count   = min(max(int(data.get('count', 5) or 5), 3), 12)

    # ── Syllabus validation ───────────────────────────────────────
    try:
        from RAG.syllabus_topics import SYLLABUS_TOPICS
        if subject in SYLLABUS_TOPICS and module not in ('General', ''):
            subject_data = SYLLABUS_TOPICS[subject]
            known_modules = [m['module'] for m in subject_data]
            known_topics  = [t for m in subject_data for t in m.get('topics', [])]
            all_known     = known_modules + known_topics

            # Fuzzy check: does the input overlap with any known module/topic?
            mod_lower = module.lower()
            matched = any(
                mod_lower in k.lower() or k.lower() in mod_lower
                for k in all_known
            )
            if not matched:
                suggestions = ', '.join(f'"{m}"' for m in known_modules[:4])
                return jsonify({
                    'error': (
                        f'"{module}" is not a recognised NSW HSC {subject} module or topic. '
                        f'Try one of: {suggestions}. '
                        f'You can also browse modules in the Quiz generator.'
                    )
                }), 400
    except ImportError:
        pass  # Syllabus topics not available — proceed without validation

    try:
        from RAG.retriever    import retrieve, format_chunks_for_prompt
        from Chat.prompt_builder import build_flashcards_prompt
        from Chat.gemini_client  import ask_gemini_json

        chunks   = retrieve(f'NSW HSC {subject} {module} flashcards', subject=subject, n_results=5)
        context  = format_chunks_for_prompt(chunks)
        prompt   = build_flashcards_prompt(subject, module, count, context)
        response = ask_gemini_json(prompt)

        if not isinstance(response, dict) or not response.get('flashcards'):
            return jsonify({'error': 'Flashcard generator returned invalid data. Please try again.'}), 500

        return jsonify({
            'title':      response.get('title', f'{subject} — {module} flashcards'),
            'subject':    response.get('subject', subject),
            'module':     response.get('module',  module),
            'flashcards': response.get('flashcards', [])
        })
    except Exception as e:
        print(f'[GENERATE_FLASHCARDS] Error: {e}')
        return jsonify({'error': f'Could not generate flashcards: {str(e)}'}), 500


# ── FLASHCARD DECKS ──────────────────────────────────────────────

@app.route('/api/flashcards/decks', methods=['GET'])
@login_required
def get_flashcard_decks():
    try:
        user_id = session.get('user_id')
        conn = get_db_connection()

        decks = conn.execute(
            '''SELECT deckID, title, subject, module, cardCount, createdAt, updatedAt
               FROM flashcard_decks
               WHERE userID = ?
               ORDER BY updatedAt DESC''',
            (user_id,)
        ).fetchall()

        result = []
        for d in decks:
            deck = dict(d)
            cards = conn.execute(
                '''SELECT cardID, question, answer, hint, sortOrder
                   FROM flashcards
                   WHERE deckID = ? AND userID = ?
                   ORDER BY sortOrder ASC''',
                (d['deckID'], user_id)
            ).fetchall()
            deck['flashcards'] = [dict(c) for c in cards]
            result.append(deck)

        conn.close()
        return jsonify({'decks': result})

    except Exception as e:
        print(f'[GET_DECKS] Error: {e}')
        return jsonify({'error': 'Could not fetch decks'}), 500


@app.route('/api/flashcards/decks', methods=['POST'])
@login_required
def save_flashcard_deck():
    try:
        user_id = session.get('user_id')
        data = request.get_json() or {}

        title     = (data.get('title') or '').strip()
        subject   = (data.get('subject') or 'General').strip()
        module    = (data.get('module') or 'General').strip()
        cards     = data.get('flashcards', [])

        if not title:
            return jsonify({'error': 'Deck title is required'}), 400
        if not isinstance(cards, list) or len(cards) == 0:
            return jsonify({'error': 'At least one flashcard is required'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            '''INSERT INTO flashcard_decks (userID, title, subject, module, cardCount)
               VALUES (?, ?, ?, ?, ?)''',
            (user_id, title, subject, module, len(cards))
        )
        deck_id = cursor.lastrowid

        for i, card in enumerate(cards):
            question = str(card.get('question') or card.get('prompt') or '').strip()
            answer   = str(card.get('answer')   or card.get('definition') or '').strip()
            hint     = str(card.get('hint')     or card.get('tip') or '').strip() or None

            if not question or not answer:
                continue

            cursor.execute(
                '''INSERT INTO flashcards (deckID, userID, question, answer, hint, sortOrder)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (deck_id, user_id, question, answer, hint, i)
            )

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'deckID':  deck_id,
            'message': f'Deck "{title}" saved with {len(cards)} cards.'
        }), 201

    except Exception as e:
        print(f'[SAVE_DECK] Error: {e}')
        return jsonify({'error': 'Could not save deck'}), 500


@app.route('/api/flashcards/decks/<int:deck_id>', methods=['DELETE'])
@login_required
def delete_flashcard_deck(deck_id):
    try:
        user_id = session.get('user_id')
        conn = get_db_connection()

        deck = conn.execute(
            'SELECT userID FROM flashcard_decks WHERE deckID = ?', (deck_id,)
        ).fetchone()

        if not deck:
            conn.close()
            return jsonify({'error': 'Deck not found'}), 404
        if deck['userID'] != user_id:
            conn.close()
            return jsonify({'error': 'Unauthorized'}), 403

        conn.execute('DELETE FROM flashcard_decks WHERE deckID = ?', (deck_id,))
        conn.commit()
        conn.close()

        return jsonify({'success': True})

    except Exception as e:
        print(f'[DELETE_DECK] Error: {e}')
        return jsonify({'error': 'Could not delete deck'}), 500


@app.route('/api/flashcards/decks/<int:deck_id>', methods=['PUT'])
@login_required
def rename_flashcard_deck(deck_id):
    try:
        user_id = session.get('user_id')
        data    = request.get_json() or {}
        title   = (data.get('title') or '').strip()

        if not title:
            return jsonify({'error': 'Title is required'}), 400

        conn = get_db_connection()
        deck = conn.execute(
            'SELECT userID FROM flashcard_decks WHERE deckID = ?', (deck_id,)
        ).fetchone()

        if not deck or deck['userID'] != user_id:
            conn.close()
            return jsonify({'error': 'Deck not found or unauthorized'}), 403

        conn.execute(
            "UPDATE flashcard_decks SET title = ?, updatedAt = datetime('now') WHERE deckID = ?",
            (title, deck_id)
        )
        conn.commit()
        conn.close()
        return jsonify({'success': True})

    except Exception as e:
        print(f'[RENAME_DECK] Error: {e}')
        return jsonify({'error': 'Could not rename deck'}), 500


# ── FLASHCARD STUDY RESULTS ───────────────────────────────────────

@app.route('/api/flashcards/results', methods=['POST'])
@login_required
def save_flashcard_result():
    try:
        user_id = session.get('user_id')
        data    = request.get_json() or {}

        deck_id    = data.get('deckID')
        knew       = int(data.get('knew',       0))
        unsure     = int(data.get('unsure',     0))
        missed     = int(data.get('missed',     0))
        total      = int(data.get('totalCards', knew + unsure + missed))

        if not deck_id:
            return jsonify({'error': 'deckID is required'}), 400

        conn = get_db_connection()

        deck = conn.execute(
            'SELECT userID FROM flashcard_decks WHERE deckID = ?', (deck_id,)
        ).fetchone()
        if not deck or deck['userID'] != user_id:
            conn.close()
            return jsonify({'error': 'Deck not found or unauthorized'}), 403

        conn.execute(
            '''INSERT INTO flashcard_results (deckID, userID, knew, unsure, missed, totalCards)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (deck_id, user_id, knew, unsure, missed, total)
        )

        conn.execute(
            "UPDATE flashcard_decks SET updatedAt = datetime('now') WHERE deckID = ?",
            (deck_id,)
        )

        conn.commit()
        conn.close()
        return jsonify({'success': True})

    except Exception as e:
        print(f'[SAVE_RESULT] Error: {e}')
        return jsonify({'error': 'Could not save result'}), 500


@app.route('/api/flashcards/results', methods=['GET'])
@login_required
def get_flashcard_results():
    try:
        user_id = session.get('user_id')
        deck_id = request.args.get('deckID', type=int)

        conn = get_db_connection()

        if deck_id:
            rows = conn.execute(
                '''SELECT r.*, d.title, d.subject
                   FROM flashcard_results r
                   JOIN flashcard_decks d ON r.deckID = d.deckID
                   WHERE r.userID = ? AND r.deckID = ?
                   ORDER BY r.studiedAt DESC LIMIT 20''',
                (user_id, deck_id)
            ).fetchall()
        else:
            rows = conn.execute(
                '''SELECT r.*, d.title, d.subject
                   FROM flashcard_results r
                   JOIN flashcard_decks d ON r.deckID = d.deckID
                   WHERE r.userID = ?
                   ORDER BY r.studiedAt DESC LIMIT 50''',
                (user_id,)
            ).fetchall()

        conn.close()
        return jsonify({'results': [dict(r) for r in rows]})

    except Exception as e:
        print(f'[GET_RESULTS] Error: {e}')
        return jsonify({'error': 'Could not fetch results'}), 500


@app.route('/api/progress/extended', methods=['GET'])
@login_required
def get_extended_progress():
    try:
        user_id = session.get('user_id')
        conn    = get_db_connection()

        sessions_by_subject = conn.execute(
            '''SELECT
                   s.subjectName,
                   COUNT(ts.sessionID)                                  AS totalSessions,
                   SUM(COALESCE(ts.timeSpentSeconds, 0))                AS totalSeconds,
                   SUM(CASE WHEN ts.status = 'completed' THEN 1 ELSE 0 END) AS completedSessions
               FROM timer_sessions ts
               JOIN subjects s ON ts.subjectID = s.subjectID
               WHERE ts.userID = ?
               GROUP BY s.subjectName
               ORDER BY totalSeconds DESC''',
            (user_id,)
        ).fetchall()

        daily_activity = conn.execute(
            '''SELECT
                   DATE(startTime) AS date,
                   SUM(COALESCE(timeSpentSeconds, 0)) AS totalSeconds
               FROM timer_sessions
               WHERE userID = ?
                 AND startTime >= DATE('now', '-30 days')
               GROUP BY DATE(startTime)
               ORDER BY date ASC''',
            (user_id,)
        ).fetchall()

        flashcard_stats = conn.execute(
            '''SELECT
                   d.subject,
                   COUNT(r.resultID)                            AS totalSessions,
                   AVG(CAST(r.knew   AS REAL) / MAX(r.totalCards, 1) * 100) AS avgKnewPct,
                   AVG(CAST(r.missed AS REAL) / MAX(r.totalCards, 1) * 100) AS avgMissedPct
               FROM flashcard_results r
               JOIN flashcard_decks d ON r.deckID = d.deckID
               WHERE r.userID = ?
               GROUP BY d.subject
               ORDER BY totalSessions DESC''',
            (user_id,)
        ).fetchall()

        task_completion = conn.execute(
            '''SELECT
                   s.subjectName,
                   COUNT(t.taskID)                                           AS total,
                   SUM(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END)  AS completed,
                   AVG(CAST(t.progress AS REAL))                             AS avgProgress
               FROM tasks t
               JOIN subjects s ON t.subjectID = s.subjectID
               WHERE t.userID = ?
               GROUP BY s.subjectName
               ORDER BY total DESC''',
            (user_id,)
        ).fetchall()

        conn.close()

        return jsonify({
            'sessions_by_subject': [dict(r) for r in sessions_by_subject],
            'daily_activity':      [dict(r) for r in daily_activity],
            'flashcard_stats':     [dict(r) for r in flashcard_stats],
            'task_completion':     [dict(r) for r in task_completion],
        })

    except Exception as e:
        print(f'[EXTENDED_PROGRESS] Error: {e}')
        return jsonify({'error': 'Could not fetch extended progress'}), 500


# AI Chat API Routes

@app.route('/api/chat_legacy_disabled', methods=['POST'])
def legacy_ai_chat_disabled():
    data = request.json
    question = data.get('question', '').strip()
    subject = data.get('subject', 'General')
    mode = data.get('mode', 'tutor')  # tutor / mark / generate
    
    if not question:
        return jsonify({"error": "No question provided"}), 400

    try:
        from RAG.retriever import retrieve, format_chunks_for_prompt
        from Chat.prompt_builder import build_essay_marking_prompt, build_question_generation_prompt, build_tutor_prompt
        from Chat.gemini_client import ask_gemini
    except Exception as exc:
        print(f'[CHAT_IMPORT] Error: {exc}')
        return jsonify({'error': 'Chat engine is unavailable'}), 500

    # Retrieve relevant chunks
    chunks = retrieve(question, subject=subject, n_results=5)
    context = format_chunks_for_prompt(chunks)
    
    # Get chat history from session
    history = session.get('chat_history', [])
    history_text = ""
    if history:
        recent = history[-4:]  # Last 4 exchanges
        history_text = "\n".join([
            f"Student: {h['q']}\nTutor: {h['a']}" for h in recent
        ])
    
    # Build prompt based on mode
    if mode == 'mark':
        prompt = build_essay_marking_prompt(question, subject, context)
    elif mode == 'generate':
        module = data.get('module', 'General')
        difficulty = data.get('difficulty', 'medium')
        prompt = build_question_generation_prompt(subject, module, difficulty, context)
    else:
        prompt = build_tutor_prompt(question, subject, context, history_text)
    
    # Call Gemini
    gemini_response = ask_gemini(prompt)
    
    # Store in session history
    history.append({"q": question, "a": gemini_response})
    session['chat_history'] = history[-10:]  # Keep last 10
    
    # Return sources too
    sources = list(set([
        f"{c['subject']} — {c['source']}" 
        for c in chunks if c['relevance'] > 0.3
    ]))
    
    return jsonify({
        "response": gemini_response,
        "sources": sources[:3],
        "mode": mode
    })

# ================================================================
# app_chat_patch.py
#
# Drop-in replacements for the chat + RAG routes in app.py.
#
# HOW TO USE:
#   Find the block starting with:
#       HSC_CHAT_SUBJECTS = [
#   and replace everything from there down to (and including):
#       @app.route('/api/status', methods=['GET'])
#       def status(): ...
#   with the code below.
#
# All other routes (timer, tasks, calendar, etc.) are unchanged.
# ================================================================

import json
import traceback

HSC_CHAT_SUBJECTS = [
    "Software Engineering",
    "English Advanced",
    "Mathematics Advanced",
    "Chemistry",
    "General",
]


# ── SHARED HELPERS ────────────────────────────────────────────────

def retrieve_hsc_context(query: str, subject: str, n_results: int = 5):
    """
    Run RAG retrieval. Always returns (chunks, context_str, error_or_None).
    Never raises — callers can always proceed with the fallback context.
    """
    try:
        from RAG.retriever import retrieve, format_chunks_for_prompt, format_source_payload
        chunks  = retrieve(query, subject=subject, n_results=n_results)
        context = format_chunks_for_prompt(chunks)
        return chunks, context, None
    except Exception as exc:
        print(f"[RETRIEVE] Failed: {exc}")
        traceback.print_exc()
        fallback = (
            "No specific resources could be retrieved. "
            "Answer from general HSC knowledge and be transparent about this."
        )
        return [], fallback, str(exc)


def build_source_payload(chunks: list) -> list:
    """Deduplicated source list for the frontend."""
    try:
        from RAG.retriever import format_source_payload
        return format_source_payload(chunks)
    except Exception:
        return []


def make_chat_title(question: str) -> str:
    """Create a compact, human-readable chat title from the first message."""
    title = ' '.join((question or '').strip().split())
    if not title:
        return 'Untitled Chat'
    title = title[:48].rstrip(' ,.;:')
    return title or 'Untitled Chat'

def _quiz_options_valid(quiz: dict) -> bool:
    """Reject quizzes where any multiple_choice question has duplicate options."""
    for q in quiz.get('questions', []):
        if q.get('type') != 'multiple_choice':
            continue
        opts = [str(o).strip().lower() for o in (q.get('options') or [])]
        if len(opts) < 2 or len(set(opts)) != len(opts):
            return False
    return True


def _fix_duplicate_options(quiz: dict) -> dict:
    """Last-resort fallback: convert any MC question with duplicate options to short_answer."""
    for q in quiz.get('questions', []):
        if q.get('type') != 'multiple_choice':
            continue
        opts = [str(o).strip().lower() for o in (q.get('options') or [])]
        if len(opts) < 2 or len(set(opts)) != len(opts):
            q['type'] = 'short_answer'
            q['options'] = []
    return quiz


# ── /api/chat ─────────────────────────────────────────────────────

@app.route('/api/chat', methods=['POST'])
@login_required
def api_chat():
    try:
        from Chat.gemini_client  import ask_gemini
        from Chat.prompt_builder import (
            build_tutor_prompt,
            build_essay_marking_prompt,
            build_question_generation_prompt,
        )
        from RAG.ingestion import extract_text, clean_text

        # ── Accept both JSON and multipart/form-data ──
        if request.content_type and 'multipart' in request.content_type:
            question   = (request.form.get('question')   or '').strip()
            subject    = (request.form.get('subject')    or 'General').strip()
            mode       = (request.form.get('mode')       or 'tutor').strip()
            module     = (request.form.get('module')     or 'General').strip()
            difficulty = (request.form.get('difficulty') or 'medium').strip()
            uploaded   = request.files.get('file')
        else:
            data       = request.get_json() or {}
            question   = (data.get('question')   or '').strip()
            subject    = (data.get('subject')    or 'General').strip()
            mode       = (data.get('mode')       or 'tutor').strip()
            module     = (data.get('module')     or 'General').strip()
            difficulty = (data.get('difficulty') or 'medium').strip()
            uploaded   = None

        if not question and not uploaded:
            return jsonify({'error': 'Please type a question or attach a file.'}), 400

        # ── Save and extract uploaded file text ──
        file_context = ''
        if uploaded and uploaded.filename:
            ext = uploaded.filename.rsplit('.', 1)[-1].lower() if '.' in uploaded.filename else ''
            if ext in ALLOWED_UPLOAD_EXTENSIONS:
                user_dir = os.path.join(USER_UPLOADS_DIR, str(session.get('user_id')))
                os.makedirs(user_dir, exist_ok=True)
                base      = secure_filename(uploaded.filename)
                name, dxt = os.path.splitext(base)
                ts        = int(datetime.now().timestamp())
                safe_name = f"{name}_{ts}{dxt}"
                filepath  = os.path.join(user_dir, safe_name)
                uploaded.save(filepath)

                try:
                    raw  = extract_text(filepath)
                    text = clean_text(raw)[:4000]
                    if text:
                        file_context = (
                            f"\n\n[ATTACHED FILE: {base}]\n"
                            f"{text}\n"
                            "[END OF ATTACHED FILE]\n"
                        )
                except Exception as fe:
                    print(f'[CHAT_UPLOAD] Text extraction failed: {fe}')

        # ── RAG retrieval ──
        chunks, context, retrieval_error = retrieve_hsc_context(
            question or (uploaded.filename if uploaded else ''), subject, n_results=5
        )
        if file_context:
            context = file_context + '\n' + context

        # ── Chat history from DB ─────────────────────────────────────
        # IMPORTANT: use the sessionID sent by the frontend, NOT the
        # Flask session cookie — the cookie can be stale (pointing at a
        # previous session that had file uploads) and causes Gemini to
        # "remember" files that were never attached to this conversation.
        history_text = ''
        frontend_session_id = None
        if request.content_type and 'multipart' in request.content_type:
            frontend_session_id = request.form.get('sessionID')
        else:
            frontend_session_id = (request.get_json() or {}).get('sessionID')
 
        # Sync Flask session to match what the frontend says is active
        if frontend_session_id:
            try:
                frontend_session_id = int(frontend_session_id)
                session['active_chat_session'] = frontend_session_id
            except (TypeError, ValueError):
                frontend_session_id = None
 
        active_sid = frontend_session_id or session.get('active_chat_session')
 
        try:
            if active_sid:
                conn_hist = get_db_connection()
                # Only load history if the session actually belongs to this user
                owns = conn_hist.execute(
                    'SELECT sessionID FROM chat_sessions WHERE sessionID=? AND userID=?',
                    (active_sid, session.get('user_id'))
                ).fetchone()
                if owns:
                    recent = conn_hist.execute('''
                        SELECT role, content, mode FROM chat_messages
                        WHERE sessionID = ?
                          AND mode NOT IN ('quiz', 'quiz_result')
                        ORDER BY createdAt DESC LIMIT 8
                    ''', (active_sid,)).fetchall()
                    conn_hist.close()
                    recent = list(reversed(recent))
                    pairs  = []
                    for i in range(0, len(recent) - 1, 2):
                        if recent[i]['role'] == 'user' and recent[i+1]['role'] == 'assistant':
                            pairs.append(
                                f"Student: {recent[i]['content']}\n"
                                f"Tutor: {recent[i+1]['content']}"
                            )
                    history_text = '\n'.join(pairs)
                else:
                    conn_hist.close()
        except Exception as hist_exc:
            print(f'[CHAT_HISTORY] {hist_exc}')
            history_text = ''

        # ── Build prompt ──
        if mode == 'feedback':
            prompt = build_essay_marking_prompt(question, subject, context)
        elif mode == 'generate':
            prompt = build_question_generation_prompt(subject, module, difficulty, context)
        else:
            mode   = 'tutor'
            prompt = build_tutor_prompt(question, subject, context, history_text)

        # ── Call Gemini ──
        gemini_response = ask_gemini(prompt)

        # ── Persist to DB ──
        session_title = 'Untitled Chat'
        try:
            user_id    = session.get('user_id')
            session_id = session.get('active_chat_session')

            if session_id:
                conn = get_db_connection()
                exists = conn.execute(
                    'SELECT sessionID FROM chat_sessions WHERE sessionID=? AND userID=?',
                    (session_id, user_id)
                ).fetchone()
                conn.close()
                if not exists:
                    session_id = None
                    session.pop('active_chat_session', None)

            if not session_id:
                conn = get_db_connection()
                cur  = conn.cursor()
                cur.execute('''
                    INSERT INTO chat_sessions (userID, title, subject, module, createdAt, updatedAt)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ''', (user_id, make_chat_title(question), subject, module))
                conn.commit()
                session_id = cur.lastrowid
                session['active_chat_session'] = session_id
                conn.close()

            conn = get_db_connection()
            cur  = conn.cursor()
            cur.execute('''
                INSERT INTO chat_messages (sessionID, userID, role, mode, content, createdAt)
                VALUES (?, ?, 'user', ?, ?, CURRENT_TIMESTAMP)
            ''', (session_id, user_id, mode, question))
            cur.execute('''
                INSERT INTO chat_messages (sessionID, userID, role, mode, content, sources, createdAt)
                VALUES (?, ?, 'assistant', ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (session_id, user_id, mode, gemini_response, json.dumps(chunks)))

            cur_sess = cur.execute(
                'SELECT title, messageCount FROM chat_sessions WHERE sessionID=? AND userID=?',
                (session_id, user_id)
            ).fetchone()
            session_title = cur_sess['title'] if cur_sess else make_chat_title(question)
            if cur_sess and cur_sess['messageCount'] in (0, None):
                session_title = make_chat_title(question)

            cur.execute('''
                UPDATE chat_sessions
                SET title=?, subject=?, module=?,
                    messageCount=(SELECT COUNT(*) FROM chat_messages WHERE sessionID=?),
                    updatedAt=CURRENT_TIMESTAMP
                WHERE sessionID=?
            ''', (session_title, subject, module, session_id, session_id))
            conn.commit()
            conn.close()
        except Exception as db_exc:
            print(f'[CHAT_DB_SAVE] {db_exc}')

        return jsonify({
            'response':        gemini_response,
            'sources':         build_source_payload(chunks),
            'mode':            mode,
            'retrieval_error': retrieval_error,
            'sessionID':       session.get('active_chat_session'),
            'title':           session_title,
        })

    except RuntimeError as exc:
        print(f'[API_CHAT] RuntimeError: {exc}')
        return jsonify({'error': str(exc)}), 500
    except Exception as exc:
        print(f'[API_CHAT] Unexpected: {exc}')
        traceback.print_exc()
        return jsonify({'error': 'An unexpected error occurred. Please try again.'}), 500


# ── /api/quiz/generate ────────────────────────────────────────────

@app.route('/api/quiz/generate', methods=['POST'])
@login_required
def api_quiz_generate():
    try:
        from Chat.gemini_client  import ask_gemini_json
        from Chat.prompt_builder import build_quiz_generation_prompt

        data           = request.get_json() or {}
        subject        = (data.get('subject')  or 'Software Engineering').strip()
        module         = (data.get('module')   or 'General').strip()
        difficulty     = (data.get('difficulty') or 'medium').strip()
        question_count = max(3, min(int(data.get('question_count') or 5), 10))

        seed = f"{subject} {module} {difficulty} HSC quiz"
        chunks, context, retrieval_error = retrieve_hsc_context(seed, subject, n_results=8)

        prompt = build_quiz_generation_prompt(
            subject, module, difficulty, question_count, context
        )

        try:
            import requests as _req
            pass
        except Exception:
            pass

        quiz = ask_gemini_json(prompt, temperature=0.2)  # lower temperature for more reliable JSON

        if not isinstance(quiz, dict) or not quiz.get('questions'):
            # Retry once with explicit JSON reminder appended
            prompt_retry = prompt + "\n\nCRITICAL: Your entire response must be only the JSON object. No text before or after it."
            quiz = ask_gemini_json(prompt_retry, temperature=0.1)

        # Guard against duplicate multiple-choice options
        if isinstance(quiz, dict) and quiz.get('questions') and not _quiz_options_valid(quiz):
            print("[QUIZ_GENERATE] Duplicate MC options detected — retrying once")
            prompt_dedup = prompt + (
                "\n\nIMPORTANT FIX: Your previous attempt produced multiple_choice "
                "questions with duplicate or near-duplicate options. Regenerate the "
                "ENTIRE quiz, ensuring every multiple_choice question has four "
                "distinct, non-overlapping options."
            )
            retry_quiz = ask_gemini_json(prompt_dedup, temperature=0.2)
            if isinstance(retry_quiz, dict) and retry_quiz.get('questions'):
                quiz = retry_quiz

        if isinstance(quiz, dict) and quiz.get('questions') and not _quiz_options_valid(quiz):
            quiz = _fix_duplicate_options(quiz)

        # Normalise questions
        questions = quiz.get('questions', [])
        for i, q in enumerate(questions, 1):
            q.setdefault('id',      f"q{i}")
            q.setdefault('options', [])
            q.setdefault('marks',   1)

        quiz['questions'] = questions[:question_count]
        quiz['subject']   = subject
        quiz['module']    = module

        # Store full quiz (with answers) server-side
        session['active_quiz'] = quiz

        # Strip answers from what we send to the browser
        public_quiz = dict(quiz)
        public_quiz['questions'] = [
            {k: v for k, v in q.items() if k not in {'answer', 'marking_guidance'}}
            for q in quiz['questions']
        ]

        # Store quiz in database for persistence (so it appears in chat history)
        quiz_message_id = None
        try:
            user_id = session.get('user_id')
            session_id = session.get('active_chat_session')

            # If no active session, create one
            if not session_id:
                conn_new = get_db_connection()
                cur_new = conn_new.cursor()
                cur_new.execute('''
                    INSERT INTO chat_sessions (userID, title, subject, module, createdAt, updatedAt)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ''', (user_id, make_chat_title(f"Quiz: {module}"), subject, module))
                conn_new.commit()
                session_id = cur_new.lastrowid
                session['active_chat_session'] = session_id
                conn_new.close()

            # Store the quiz as a message (JSON encoded)
            if session_id:
                conn_msg = get_db_connection()
                cur_msg = conn_msg.cursor()
                quiz_content = json.dumps(public_quiz)
                cur_msg.execute('''
                    INSERT INTO chat_messages (sessionID, userID, role, mode, content, createdAt)
                    VALUES (?, ?, 'assistant', 'quiz', ?, CURRENT_TIMESTAMP)
                ''', (session_id, user_id, quiz_content))
                quiz_message_id = cur_msg.lastrowid

                # Update session message count
                cur_msg.execute('''
                    UPDATE chat_sessions
                    SET messageCount=(SELECT COUNT(*) FROM chat_messages WHERE sessionID=?),
                        updatedAt=CURRENT_TIMESTAMP
                    WHERE sessionID=?
                ''', (session_id, session_id))
                conn_msg.commit()
                conn_msg.close()
        except Exception as db_exc:
            print(f"[QUIZ_DB_SAVE] {db_exc}")

        return jsonify({
            "quiz":            public_quiz,
            "sources":         build_source_payload(chunks),
            "retrieval_error": retrieval_error,
            "quizMessageID":   quiz_message_id,
        })

    except RuntimeError as exc:
        print(f"[QUIZ_GENERATE] {exc}")
        return jsonify({"error": str(exc)}), 500
    except Exception as exc:
        print(f"[QUIZ_GENERATE] Unexpected: {exc}")
        traceback.print_exc()
        return jsonify({"error": "Could not generate quiz. Please try again."}), 500


# ── /api/quiz/mark ────────────────────────────────────────────────

@app.route('/api/quiz/mark', methods=['POST'])
@login_required
def api_quiz_mark():
    try:
        from Chat.gemini_client  import ask_gemini_json
        from Chat.prompt_builder import build_quiz_marking_prompt

        data    = request.get_json() or {}
        # Prefer the server-stored quiz (has answers) over the browser copy
        quiz    = session.get('active_quiz') or data.get('quiz')
        answers = data.get('answers') or {}
        quiz_message_id = data.get('quizMessageID')

        if not quiz:
            return jsonify({"error": "No active quiz found. Please generate a new quiz."}), 400
        if not answers:
            return jsonify({"error": "No answers were submitted."}), 400

        subject = quiz.get('subject', 'General')
        module  = quiz.get('module',  'General')
        chunks, context, retrieval_error = retrieve_hsc_context(
            f"{subject} {module} marking", subject, n_results=5
        )

        prompt = build_quiz_marking_prompt(
            json.dumps(quiz,    ensure_ascii=False),
            json.dumps(answers, ensure_ascii=False),
            context,
        )
        result = ask_gemini_json(prompt)

        # Validate and normalize the marking result
        if isinstance(result, list):
            # If Gemini returned an array of feedback items, wrap it
            print(f"[DEBUG] Marking returned a list instead of dict. Converting…")
            result = {
                "score": 0,
                "total": 0,
                "summary": "See feedback below",
                "feedback": result,
                "next_steps": []
            }
        elif not isinstance(result, dict):
            print(f"[DEBUG] Marking returned unexpected type: {type(result)}")
            return jsonify({"error": "Marking service returned invalid data. Please try again."}), 500

        # Ensure required fields exist with defaults
        result.setdefault("score", 0)
        result.setdefault("total", 0)
        result.setdefault("summary", "")
        result.setdefault("feedback", [])
        result.setdefault("next_steps", [])

        # Validate that score and total are numeric
        try:
            result["score"] = int(result.get("score", 0))
            result["total"] = int(result.get("total", 0))
        except (ValueError, TypeError):
            print(f"[DEBUG] Marking score/total not numeric. Got: score={result.get('score')}, total={result.get('total')}")
            result["score"] = 0
            result["total"] = 0

        # ── Persist answers + feedback so the quiz survives a chat reload ──
        try:
            if quiz_message_id:
                user_id = session.get('user_id')
                conn_q = get_db_connection()
                owner = conn_q.execute(
                    'SELECT userID, sessionID FROM chat_messages WHERE messageID = ?',
                    (quiz_message_id,)
                ).fetchone()

                if owner and owner['userID'] == user_id:
                    payload = json.dumps({
                        'quiz':    quiz,
                        'answers': answers,
                        'result':  result,
                    })
                    conn_q.execute('''
                        UPDATE chat_messages
                        SET mode = 'quiz_result', content = ?
                        WHERE messageID = ?
                    ''', (payload, quiz_message_id))
                    conn_q.execute('''
                        UPDATE chat_sessions
                        SET updatedAt = CURRENT_TIMESTAMP
                        WHERE sessionID = ?
                    ''', (owner['sessionID'],))
                    conn_q.commit()
                conn_q.close()
        except Exception as persist_exc:
            print(f"[QUIZ_MARK_PERSIST] {persist_exc}")

        return jsonify({
            "result":          result,
            "sources":         build_source_payload(chunks),
            "retrieval_error": retrieval_error,
        })

    except RuntimeError as exc:
        print(f"[QUIZ_MARK] {exc}")
        return jsonify({"error": str(exc)}), 500
    except Exception as exc:
        print(f"[QUIZ_MARK] Unexpected: {exc}")
        traceback.print_exc()
        return jsonify({"error": "Could not mark the quiz. Please try again."}), 500


# ── /api/clear ────────────────────────────────────────────────────

@app.route('/api/clear', methods=['POST'])
def clear_history():
    session.pop('chat_history', None)
    session.pop('active_quiz',  None)
    return jsonify({"status": "cleared"})


# ── /api/chat/sessions ────────────────────────────────────────────

@app.route('/api/chat/clear-session', methods=['POST'])
@login_required
def clear_chat_session():
    session.pop('active_chat_session', None)
    session.pop('active_quiz', None)
    return jsonify({'ok': True})

@app.route('/api/chat/sessions', methods=['GET'])
@login_required
def get_chat_sessions():
    """List all chat sessions for the current user."""
    try:
        user_id = session.get('user_id')
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT sessionID, title, subject, module, messageCount, updatedAt
            FROM chat_sessions
            WHERE userID = ?
            ORDER BY updatedAt DESC
        ''', (user_id,))
        sessions = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        return jsonify({"sessions": sessions})
    except Exception as exc:
        print(f"[CHAT_SESSIONS] {exc}")
        return jsonify({"error": "Could not load chat history."}), 500


@app.route('/api/chat/session', methods=['POST'])
@login_required
def create_chat_session():
    """Create a new chat session."""
    try:
        user_id = session.get('user_id')
        data = request.get_json() or {}
        title = data.get('title', 'Untitled Chat').strip()
        subject = data.get('subject', 'General').strip()
        module = data.get('module', 'General').strip()

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO chat_sessions (userID, title, subject, module, createdAt, updatedAt)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ''', (user_id, title, subject, module))
        conn.commit()
        
        session_id = cursor.lastrowid
        session['active_chat_session'] = session_id
        session['chat_history'] = []

        return jsonify({"sessionID": session_id, "title": title})
    except Exception as exc:
        print(f"[CREATE_CHAT] {exc}")
        return jsonify({"error": "Could not create new chat."}), 500


@app.route('/api/chat/session/<int:session_id>', methods=['GET'])
@login_required
def load_chat_session(session_id):
    """Load a specific chat session and its messages."""
    try:
        user_id = session.get('user_id')
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get session info
        cursor.execute('''
            SELECT sessionID, title, subject, module, messageCount
            FROM chat_sessions
            WHERE sessionID = ? AND userID = ?
        ''', (session_id, user_id))
        chat_session = cursor.fetchone()
        if not chat_session:
            return jsonify({"error": "Chat session not found."}), 404

        # Get messages
        cursor.execute('''
            SELECT messageID, role, content, mode, sources, createdAt
            FROM chat_messages
            WHERE sessionID = ?
            ORDER BY createdAt ASC
        ''', (session_id,))
        messages = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]

        # Reconstruct chat_history for the session
        history = []
        for msg in messages:
            if msg['role'] == 'user':
                history.append({"q": msg['content'], "subject": msg['mode']})
            elif msg['role'] == 'assistant' and history:
                history[-1]["a"] = msg['content']

        session['active_chat_session'] = session_id
        session['chat_history'] = history

        return jsonify({
            "sessionID": session_id,
            "title": chat_session[1],
            "subject": chat_session[2],
            "module": chat_session[3],
            "messages": messages,
            "history": history
        })
    except Exception as exc:
        print(f"[LOAD_CHAT] {exc}")
        return jsonify({"error": "Could not load chat session."}), 500


@app.route('/api/chat/session/<int:session_id>', methods=['PATCH'])
@login_required
def rename_chat_session(session_id):
    """Rename a chat session owned by the current user."""
    try:
        user_id = session.get('user_id')
        data = request.get_json() or {}
        title = (data.get('title') or '').strip()
        if not title:
            return jsonify({"error": "Chat title is required."}), 400
        title = title[:80]

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE chat_sessions
            SET title = ?, updatedAt = CURRENT_TIMESTAMP
            WHERE sessionID = ? AND userID = ?
        ''', (title, session_id, user_id))
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({"error": "Chat session not found."}), 404
        conn.commit()
        conn.close()
        return jsonify({"success": True, "sessionID": session_id, "title": title})
    except Exception as exc:
        print(f"[RENAME_CHAT] {exc}")
        return jsonify({"error": "Could not rename chat."}), 500


@app.route('/api/chat/session/<int:session_id>', methods=['DELETE'])
@login_required
def delete_chat_session(session_id):
    """Delete a chat session and all its messages."""
    try:
        user_id = session.get('user_id')
        conn = get_db_connection()
        cursor = conn.cursor()

        # Verify ownership
        cursor.execute('SELECT userID FROM chat_sessions WHERE sessionID = ?', (session_id,))
        result = cursor.fetchone()
        if not result or result[0] != user_id:
            return jsonify({"error": "Unauthorized."}), 403

        cursor.execute('DELETE FROM chat_sessions WHERE sessionID = ?', (session_id,))
        conn.commit()

        if session.get('active_chat_session') == session_id:
            session.pop('active_chat_session', None)

        return jsonify({"status": "Session deleted"})
    except Exception as exc:
        print(f"[DELETE_CHAT] {exc}")
        return jsonify({"error": "Could not delete chat session."}), 500


# ── /api/ingest ───────────────────────────────────────────────────

@app.route('/api/ingest', methods=['POST'])
def trigger_ingestion():
    try:
        from RAG.agent import run_full_ingestion
        import threading
        thread = threading.Thread(target=run_full_ingestion, daemon=True)
        thread.start()
        return jsonify({"status": "Ingestion started in background. This may take a few minutes."})
    except Exception as exc:
        print(f"[INGEST] {exc}")
        return jsonify({"error": str(exc)}), 500


# ── /api/status ───────────────────────────────────────────────────

@app.route('/api/status', methods=['GET'])
def api_status():
    try:
        from RAG.embedder import get_or_create_collection
        from RAG.paths    import CHROMA_DIR, SUBJECT_RESOURCE_DIRS

        collection = get_or_create_collection()
        count      = collection.count()

        return jsonify({
            "chunks_in_database": count,
            "chroma_path":        CHROMA_DIR,
            "subjects":           HSC_CHAT_SUBJECTS,
            "resource_folders":   {k: str(v) for k, v in SUBJECT_RESOURCE_DIRS.items()},
        })
    except Exception as exc:
        print(f"[STATUS] {exc}")
        return jsonify({"error": str(exc), "chunks_in_database": 0}), 500

# timer ambience upload and management routes

def _ambience_dir(user_id, category):
    """Return (and create) the per-user ambience sub-directory."""
    d = os.path.join(AMBIENCE_DIR, str(user_id), category)
    os.makedirs(d, exist_ok=True)
    return d


@app.route('/api/timer/ambience/upload', methods=['POST'])
@login_required
def upload_ambience():
    """Upload a custom background or sound for the ambient timer."""
    user_id  = session.get('user_id')
    file     = request.files.get('file')
    category = request.form.get('category', 'background')   # 'background' | 'sound'

    if not file or not file.filename:
        return jsonify({'error': 'No file provided'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''

    if category == 'background':
        if ext not in ALLOWED_AMBIENCE_BG:
            return jsonify({'error': f'File type .{ext} is not allowed for backgrounds'}), 400
        max_bytes = 40 * 1024 * 1024   # 40 MB
        media_type = 'video' if ext in {'mp4', 'webm'} else 'image'
    elif category == 'sound':
        if ext not in ALLOWED_AMBIENCE_SOUND:
            return jsonify({'error': f'File type .{ext} is not allowed for sounds'}), 400
        max_bytes  = 20 * 1024 * 1024  # 20 MB
        media_type = 'audio'
    else:
        return jsonify({'error': 'Invalid category'}), 400

    # Read and size-check
    data = file.read()
    if len(data) > max_bytes:
        return jsonify({'error': f'File exceeds {max_bytes // (1024*1024)} MB limit'}), 400

    target_dir = _ambience_dir(user_id, category)
    base_name  = secure_filename(file.filename)
    name, dext = os.path.splitext(base_name)
    ts         = int(datetime.now().timestamp())
    safe_name  = f"{name}_{ts}{dext}"
    filepath   = os.path.join(target_dir, safe_name)

    with open(filepath, 'wb') as fh:
        fh.write(data)

    return jsonify({
        'success':    True,
        'id':         safe_name,
        'filename':   safe_name,
        'media_type': media_type,
        'category':   category,
        'url':        f'/api/timer/ambience/serve/{category}/{safe_name}',
    }), 201


@app.route('/api/timer/ambience/uploads', methods=['GET'])
@login_required
def list_ambience_uploads():
    """List all custom backgrounds and sounds for the current user."""
    user_id     = session.get('user_id')
    backgrounds = []
    sounds      = []

    bg_dir = os.path.join(AMBIENCE_DIR, str(user_id), 'background')
    if os.path.isdir(bg_dir):
        for fn in sorted(os.listdir(bg_dir)):
            if fn.startswith('.'):
                continue
            ext  = fn.rsplit('.', 1)[-1].lower() if '.' in fn else ''
            mtype = 'video' if ext in {'mp4', 'webm'} else 'image'
            backgrounds.append({
                'id':    fn,
                'label': os.path.splitext(fn)[0].replace('_', ' '),
                'type':  mtype,
                'value': f'/api/timer/ambience/serve/background/{fn}',
            })

    snd_dir = os.path.join(AMBIENCE_DIR, str(user_id), 'sound')
    if os.path.isdir(snd_dir):
        for fn in sorted(os.listdir(snd_dir)):
            if fn.startswith('.'):
                continue
            sounds.append({
                'id':    fn,
                'label': os.path.splitext(fn)[0].replace('_', ' '),
                'icon':  '🎵',
                'src':   f'/api/timer/ambience/serve/sound/{fn}',
            })

    return jsonify({'backgrounds': backgrounds, 'sounds': sounds})


@app.route('/api/timer/ambience/serve/<category>/<path:filename>')
@login_required
def serve_ambience(category, filename):
    """Serve a user-uploaded ambience file securely."""
    user_id   = session.get('user_id')
    safe_fn   = secure_filename(filename)
    serve_dir = os.path.join(AMBIENCE_DIR, str(user_id), category)
    resolved  = _safe_join(serve_dir, safe_fn)

    if not resolved or not os.path.isfile(resolved):
        abort(404)

    return send_from_directory(serve_dir, safe_fn)


@app.route('/api/timer/ambience/upload', methods=['DELETE'])
@login_required
def delete_ambience():
    """Delete a user-uploaded ambience file."""
    user_id  = session.get('user_id')
    file_id  = request.args.get('id')
    category = request.args.get('category', 'background')

    if not file_id:
        return jsonify({'error': 'Missing id parameter'}), 400

    safe_fn  = secure_filename(file_id)
    serve_dir = os.path.join(AMBIENCE_DIR, str(user_id), category)
    resolved  = _safe_join(serve_dir, safe_fn)

    if not resolved or not os.path.isfile(resolved):
        return jsonify({'error': 'File not found'}), 404

    os.remove(resolved)
    return jsonify({'success': True})


@app.route('/api/timer/ambience/prefs', methods=['POST'])
@login_required
def save_ambience_prefs():
    """
    Persist ambience preferences (background + active sounds) server-side
    so they survive across devices.  Stored as a JSON blob in userSettings.
    """
    user_id = session.get('user_id')
    data    = request.get_json() or {}

    # Strip any obviously oversized values before storing
    safe = {
        'bgId':    str(data.get('bgId',    ''))[:120],
        'bgType':  str(data.get('bgType',  ''))[:20],
        'bgValue': str(data.get('bgValue', ''))[:300],
        'sounds':  data.get('sounds', {}) if isinstance(data.get('sounds'), dict) else {},
    }

    try:
        conn     = get_db_connection()
        existing = conn.execute('SELECT userSettings FROM users WHERE userID = ?', (user_id,)).fetchone()
        prefs    = _load_user_settings(existing['userSettings'] if existing else None)
        prefs['timer_ambience'] = safe
        conn.execute('UPDATE users SET userSettings = ? WHERE userID = ?', (json.dumps(prefs), user_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as exc:
        print(f'[AMBIENCE_PREFS] {exc}')
        return jsonify({'error': 'Could not save preferences'}), 500


@app.route('/api/timer/ambience/prefs', methods=['GET'])
@login_required
def get_ambience_prefs():
    """Return saved ambience preferences for the current user."""
    user_id = session.get('user_id')
    try:
        conn     = get_db_connection()
        existing = conn.execute('SELECT userSettings FROM users WHERE userID = ?', (user_id,)).fetchone()
        conn.close()
        prefs    = _load_user_settings(existing['userSettings'] if existing else None)
        return jsonify(prefs.get('timer_ambience', {}))
    except Exception as exc:
        print(f'[AMBIENCE_PREFS_GET] {exc}')
        return jsonify({}), 500

# Known Flask-rendered frontend paths
_FRONTEND_PATHS = {
    '/', '/home', '/login', '/logout', '/signup', '/onboarding',
    '/profile', '/calendar', '/tasks', '/timer', '/chat',
    '/flashcards', '/progress', '/resources', '/offline.html',
}
 
@app.errorhandler(404)
def not_found(e):
    path = request.path
    # Only serve the SPA shell for known page routes
    if path in _FRONTEND_PATHS or path.startswith('/static/'):
        return render_template('index.html'), 404
    # API / resource / unknown paths get a plain 404 JSON response
    return jsonify({'error': 'Not found', 'path': path}), 404

if __name__ == '__main__':
    debug_db()
    print("Templates folder:", app.template_folder)
    print("Static folder:", app.static_folder)
    app.run(debug=True, port=5000)
