from flask import Flask, render_template, session, redirect, url_for, render_template_string, request, send_from_directory, send_file, jsonify, has_request_context, has_app_context, Response, stream_with_context
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import shutil
import subprocess
import signal
import psutil
import paramiko
import threading
import unicodedata
import re
import json
import io
import csv
from datetime import timedelta, datetime, timezone
import zipfile
import tarfile
import time
import math
from urllib.parse import urlencode, parse_qsl

# ==========================================
# 1. IMPORTS & CONFIGURATION
# ==========================================
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-very-secret-key'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
db = SQLAlchemy(app)
socketio = SocketIO(app, async_mode='threading')
limiter = Limiter(get_remote_address, app=app, default_limits=["200 per day", "50 per hour"])
clients = {}
TERMINAL_SSH_HOST = os.environ.get('TERMINAL_SSH_HOST', 'localhost')
TERMINAL_SSH_USERNAME = os.environ.get('TERMINAL_SSH_USERNAME', 'khoa')
TERMINAL_SSH_PASSWORD = os.environ.get('TERMINAL_SSH_PASSWORD', 'osboxes.org')
TERMINAL_TMUX_PREFIX = os.environ.get('TERMINAL_TMUX_PREFIX', 'webterm_user')
TERMINAL_TMUX_TTL_SECONDS = int(os.environ.get('TERMINAL_TMUX_TTL_SECONDS', '1800'))
terminal_cleanup_timers = {}
pkg_task_lock = threading.Lock()
pkg_task_running = False
MAX_PROCESSES = 10  # limit number of processes sent to client (top by CPU)
PROCESS_REFRESH_INTERVAL = 2.0  # seconds; throttle psutil scans
process_cache_lock = threading.Lock()
last_process_list = []
last_process_time = 0.0

# File Manager: Secure home directory for managed files
HOME_DIRECTORY = os.path.abspath(os.path.expanduser('~/managed_files'))

# Create HOME_DIRECTORY if it doesn't exist
if not os.path.exists(HOME_DIRECTORY):
    os.makedirs(HOME_DIRECTORY)
    print(f"Created managed files directory: {HOME_DIRECTORY}")

# Trash directory for soft delete
TRASH_DIRECTORY = os.path.join(HOME_DIRECTORY, '.trash')
os.makedirs(TRASH_DIRECTORY, exist_ok=True)

# Backups: store editor backups outside working folders to avoid clutter
BACKUP_DIRECTORY = os.path.join(HOME_DIRECTORY, '.backups')
os.makedirs(BACKUP_DIRECTORY, exist_ok=True)
BACKUP_RETENTION = 10  # keep last N backups per file

# Terminal session recordings
TERMINAL_LOG_DIR = os.path.join(HOME_DIRECTORY, '.terminal_logs')
os.makedirs(TERMINAL_LOG_DIR, exist_ok=True)

# Export defaults
EXPORT_DEFAULTS = {
    'format': 'csv',
    'delimiter': ',',
    'quotechar': '"',
    'quoting': csv.QUOTE_ALL
}

# Enhanced logging
LOGGING_FORMAT = '%(asctime)s [%(levelname)s] %(message)s'
LOGGING_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# Session recording
SESSION_RECORDING_DIR = os.path.join(HOME_DIRECTORY, '.session_recordings')
os.makedirs(SESSION_RECORDING_DIR, exist_ok=True)

MAX_EDIT_SIZE = 10 * 1024 * 1024  # 10 MB

# ==========================================
# 2. HELPER FUNCTIONS (Các hàm hỗ trợ logic)
# ==========================================
def secure_filename_unicode(filename):
    r"""
    Secure filename sanitization that preserves Unicode characters (Vietnamese, Chinese, etc.)
    while removing dangerous characters that could cause Path Traversal attacks.
    
    Args:
        filename: Original filename from user upload
    
    Returns:
        Sanitized filename safe for file system operations
    
    Security measures:
    - Removes path separators: / \ (prevents directory traversal)
    - Removes parent directory references: .. (prevents traversal)
    - Removes null bytes: \x00 (prevents null byte injection)
    - Removes control characters (ASCII 0-31)
    - Removes dangerous characters: < > : " | ? * (invalid on Windows)
    - Normalizes Unicode to NFC form (consistent representation)
    - Limits filename length to 255 characters
    - Ensures filename is not empty after sanitization
    """
    if not filename:
        return 'unnamed_file'
    
    # Normalize Unicode to NFC (Canonical Decomposition, followed by Canonical Composition)
    # This ensures consistent representation of Vietnamese characters like ê, ơ, ư
    filename = unicodedata.normalize('NFC', filename)
    
    # Remove null bytes (security: null byte injection)
    filename = filename.replace('\x00', '')
    
    # Remove or replace dangerous characters
    dangerous_chars = {
        '/': '',   # Path separator (Unix)
        '\\': '',  # Path separator (Windows)
        '<': '',   # Invalid on Windows
        '>': '',   # Invalid on Windows
        ':': '',   # Drive letter separator on Windows
        '"': '',   # Quote
        '|': '',   # Pipe (invalid on Windows)
        '?': '',   # Wildcard (invalid on Windows)
        '*': '',   # Wildcard (invalid on Windows)
    }
    
    for char, replacement in dangerous_chars.items():
        filename = filename.replace(char, replacement)
    
    # Remove control characters (ASCII 0-31) except newline/tab which we'll remove anyway
    filename = ''.join(char for char in filename if ord(char) >= 32 or char in '\t\n')
    filename = filename.replace('\t', '').replace('\n', '')
    
    # Remove leading/trailing dots and spaces (Windows issue: files can't start/end with these)
    filename = filename.strip('. ')
    
    # Prevent parent directory reference (security: path traversal)
    # Remove any occurrence of '..' 
    while '..' in filename:
        filename = filename.replace('..', '.')
    
    # Limit filename length (255 is typical max for most filesystems)
    # Reserve some space for potential extensions
    max_length = 255
    if len(filename) > max_length:
        # Try to preserve extension if present
        name_parts = filename.rsplit('.', 1)
        if len(name_parts) == 2 and len(name_parts[1]) <= 10:
            # Has extension, preserve it
            name = name_parts[0][:max_length - len(name_parts[1]) - 1]
            filename = f"{name}.{name_parts[1]}"
        else:
            # No extension or very long extension, just truncate
            filename = filename[:max_length]
    
    # Final safety check: ensure filename is not empty and not reserved
    if not filename or filename in ('.', '..'):
        return 'unnamed_file'
    
    # Windows reserved names (case-insensitive)
    reserved_names = {
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    }
    
    # Check if filename (without extension) is a reserved name
    name_without_ext = filename.rsplit('.', 1)[0].upper()
    if name_without_ext in reserved_names:
        filename = f"file_{filename}"
    
    return filename

def _is_safe_path(base_dir, target_path):
    """
    Security check: Prevent Path Traversal attacks.
    Ensures target_path is within base_dir.
    """
    base_abs = os.path.abspath(base_dir)
    target_abs = os.path.abspath(target_path)
    return target_abs.startswith(base_abs)


def _relpath_within_home(abs_path):
    try:
        rel_path = os.path.relpath(abs_path, HOME_DIRECTORY)
        return rel_path.replace('\\', '/')
    except Exception:
        return abs_path


def _normalize_rel_target(rel_path):
    if not rel_path:
        return None
    target = rel_path.replace('\\', '/').lstrip('./')
    return target or None


def _audit_file_action(action, abs_path=None, rel_path=None, details=None):
    target = None
    if rel_path:
        target = _normalize_rel_target(rel_path)
    elif abs_path:
        if _is_safe_path(HOME_DIRECTORY, abs_path):
            target = _relpath_within_home(abs_path)
        else:
            target = abs_path
    log_audit_event(action, target=target, details=details)

def log_audit_event(action, target=None, details=None, user_id=None, username=None, ip_address=None):
    if not action:
        return
    ctx = None
    if not has_app_context():
        ctx = app.app_context()
        ctx.push()
    try:
        resolved_user_id = user_id
        resolved_username = username
        resolved_ip = ip_address

        if has_request_context():
            if resolved_user_id is None:
                resolved_user_id = session.get('user_id')
            if resolved_ip is None:
                resolved_ip = request.remote_addr

        if resolved_username is None and resolved_user_id:
            user_obj = User.query.get(resolved_user_id)
            if user_obj:
                resolved_username = user_obj.username

        entry = AuditLog(
            user_id=resolved_user_id,
            username=resolved_username,
            action=action,
            target=target,
            details=details,
            ip_address=resolved_ip,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        print(f"audit log error: {e}")
    finally:
        if ctx:
            ctx.pop()


def _format_audit_timestamp(dt, tz_info=None):
    if not dt:
        return ''
    tz_info = tz_info or DEFAULT_AUDIT_TIMEZONE
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(tz_info).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return dt.strftime('%Y-%m-%d %H:%M:%S')


def _parse_audit_details(details):
    items = []
    if not details:
        return items
    details = str(details).strip()
    if not details:
        return items
    # Try JSON first
    try:
        data = json.loads(details)
        if isinstance(data, dict):
            for key, value in data.items():
                items.append({'key': key, 'value': value})
            return items
        if isinstance(data, list):
            for index, value in enumerate(data, start=1):
                items.append({'key': f'item{index}', 'value': value})
            return items
    except Exception:
        pass
    # Fall back to key=value pairs separated by whitespace
    for chunk in re.split(r'\s+', details):
        if not chunk:
            continue
        if '=' in chunk:
            key, value = chunk.split('=', 1)
            items.append({'key': key, 'value': value})
        else:
            items.append({'key': '', 'value': chunk})
    if not items:
        items.append({'key': '', 'value': details})
    return items


def _classify_audit_action(action):
    action_lower = (action or '').lower()
    if any(keyword in action_lower for keyword in AUDIT_ERROR_KEYWORDS):
        return 'danger'
    if any(keyword in action_lower for keyword in AUDIT_SUCCESS_KEYWORDS):
        return 'success'
    return 'neutral'


DEFAULT_AUDIT_TZ_OFFSET = 7
DEFAULT_AUDIT_TIMEZONE = timezone(timedelta(hours=DEFAULT_AUDIT_TZ_OFFSET))
AUDIT_ERROR_KEYWORDS = ('fail', 'error', 'denied', 'unauthorized', 'killed')
AUDIT_SUCCESS_KEYWORDS = ('success', 'uploaded', 'saved', 'restored', 'created', 'opened', 'closed')
AUDIT_STATUS_KEYWORDS = {
    'danger': AUDIT_ERROR_KEYWORDS,
    'success': AUDIT_SUCCESS_KEYWORDS,
}
AUDIT_TIMEZONE_CHOICES = [offset for offset in range(-12, 15)]
DEFAULT_AUDIT_RETENTION_DAYS = 30
MIN_AUDIT_RETENTION_DAYS = 0.04  # ≈ 1 hour
MAX_AUDIT_RETENTION_DAYS = 365
DEFAULT_AUDIT_EXPORT_DAYS = 30


def _coerce_tz_offset(raw):
    try:
        offset = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_AUDIT_TZ_OFFSET
    return max(-12, min(14, offset))


def _parse_datetime_param(value, tz_offset_hours, is_end=False):
    if not value:
        return None
    formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d']
    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            if fmt == '%Y-%m-%d':
                if is_end:
                    dt = dt.replace(hour=23, minute=59, second=59)
                else:
                    dt = dt.replace(hour=0, minute=0, second=0)
            local_tz = timezone(timedelta(hours=tz_offset_hours))
            dt = dt.replace(tzinfo=local_tz)
            return dt.astimezone(timezone.utc)
        except Exception:
            continue
    return None


def _as_naive_utc(dt):
    if not dt:
        return None
    if dt.tzinfo:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _extract_audit_filters(args):
    tz_offset = _coerce_tz_offset(args.get('tz', DEFAULT_AUDIT_TZ_OFFSET))
    filters = {
        'search': (args.get('q') or '').strip(),
        'action': (args.get('action') or '').strip(),
        'user': (args.get('user') or '').strip(),
        'ip': (args.get('ip') or '').strip(),
        'status': (args.get('status') or '').strip(),
        'start_raw': (args.get('start') or '').strip(),
        'end_raw': (args.get('end') or '').strip(),
        'tz_offset': tz_offset,
    }
    if filters['status'] not in AUDIT_STATUS_KEYWORDS:
        filters['status'] = ''
    filters['start'] = _parse_datetime_param(filters['start_raw'], tz_offset, is_end=False)
    filters['end'] = _parse_datetime_param(filters['end_raw'], tz_offset, is_end=True)
    return filters


def _apply_audit_filters(query, filters):
    if filters['action']:
        query = query.filter(AuditLog.action == filters['action'])
    if filters['search']:
        like = f"%{filters['search']}%"
        query = query.filter(or_(
            AuditLog.username.ilike(like),
            AuditLog.action.ilike(like),
            AuditLog.target.ilike(like),
            AuditLog.details.ilike(like),
        ))
    if filters['user']:
        query = query.filter(AuditLog.username.ilike(f"%{filters['user']}%"))
    if filters['ip']:
        query = query.filter(AuditLog.ip_address.ilike(f"%{filters['ip']}%"))
    start = _as_naive_utc(filters.get('start'))
    end = _as_naive_utc(filters.get('end'))
    if start:
        query = query.filter(AuditLog.created_at >= start)
    if end:
        query = query.filter(AuditLog.created_at <= end)
    if filters['status']:
        keywords = AUDIT_STATUS_KEYWORDS.get(filters['status'], ())
        if keywords:
            keyword_filters = [AuditLog.action.ilike(f"%{kw}%") for kw in keywords]
            query = query.filter(or_(*keyword_filters))
    return query


def _build_timezone_options():
    options = []
    for offset in AUDIT_TIMEZONE_CHOICES:
        label = f"UTC{offset:+g}"
        options.append({'value': offset, 'label': label})
    return options


def _filter_query_params(filters):
    params = {
        'q': filters['search'],
        'action': filters['action'],
        'user': filters['user'],
        'ip': filters['ip'],
        'status': filters['status'],
        'start': filters['start_raw'],
        'end': filters['end_raw'],
        'tz': filters['tz_offset'],
    }
    return {k: v for k, v in params.items() if v not in (None, '', [])}

def _run_pkg_action(action, package, sid, audit_user_id=None, audit_username=None):
    log_details = f"action={action} package={package}"
    log_audit_event('system_pkg_action_started', details=log_details, user_id=audit_user_id, username=audit_username)
    try:
        # Build command: sudo apt-get {action} -y {package}
        cmd = ['sudo', 'apt-get', action, '-y', package]
        
        # Start process with output streaming
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        # Stream output line by line
        for line in iter(process.stdout.readline, ''):
            if line:
                socketio.emit('pkg_status', {'output': line.strip()}, to=sid)
        
        # Wait for process to complete and get return code
        return_code = process.wait()
        
        # Emit final status
        if return_code == 0:
            socketio.emit('pkg_status', {
                'output': f'✓ Successfully {action}ed {package}',
                'status': 'success'
            }, to=sid)
            log_audit_event('system_pkg_action_success', details=log_details, user_id=audit_user_id, username=audit_username)
        else:
            socketio.emit('pkg_status', {
                'output': f'✗ Failed to {action} {package} (exit code: {return_code})',
                'status': 'error'
            }, to=sid)
            log_audit_event('system_pkg_action_failed', details=f"{log_details} exit={return_code}", user_id=audit_user_id, username=audit_username)

    except Exception as e:
        socketio.emit('pkg_status', {
            'output': f'Exception: {str(e)}',
            'status': 'error'
        }, to=sid)
        print(f"_run_pkg_action error: {e}")
        log_audit_event('system_pkg_action_failed', details=f"{log_details} exception={e}", user_id=audit_user_id, username=audit_username)
    finally:
        global pkg_task_running
        try:
            with pkg_task_lock:
                pkg_task_running = False
        except Exception:
            pass

def _is_protected_process(pid, name=None):
    """Best-effort check to avoid killing critical system processes."""
    try:
        if pid in (0, 1, os.getpid()):
            return True
        if name is None:
            try:
                name = psutil.Process(pid).name()
            except Exception:
                name = None
        name_lower = (name or '').lower()
        if name_lower in {'systemd', 'init', 'sshd'}:
            return True
    except Exception:
        pass
    return False


def _get_and_emit_processes(sid):
    """Helper function to retrieve process list and emit to client (sorted by CPU).

    Uses a simple cache so that expensive psutil scans are performed at most
    once every PROCESS_REFRESH_INTERVAL seconds; intermediate requests reuse
    the last snapshot. This keeps the UI near real-time while reducing load.
    """
    global last_process_list, last_process_time

    now = time.time()

    # Check if we can reuse cached snapshot
    with process_cache_lock:
        use_cache = (
            last_process_list
            and (now - last_process_time) < PROCESS_REFRESH_INTERVAL
        )
        cached = list(last_process_list) if use_cache else None

    if use_cache:
        socketio.emit('process_list', cached, to=sid)
        return

    # Need to build a fresh snapshot
    processes = []
    try:
        for p in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent']):
            info = p.info
            pid = info.get('pid')
            name = info.get('name')
            username = info.get('username')
            cpu = info.get('cpu_percent')
            is_protected = _is_protected_process(pid, name)
            processes.append({
                'pid': pid,
                'name': name,
                'username': username,
                'cpu_percent': cpu,
                'protected': is_protected,
            })
    except Exception as e:
        print(f"_get_and_emit_processes error: {e}")

    try:
        processes.sort(key=lambda p: (p.get('cpu_percent') is None, -(p.get('cpu_percent') or 0)))
        # Only send top N to client to keep UI responsive
        if MAX_PROCESSES and len(processes) > MAX_PROCESSES:
            processes = processes[:MAX_PROCESSES]
    except Exception:
        pass

    # Update cache
    with process_cache_lock:
        last_process_list = list(processes)
        last_process_time = time.time()

    socketio.emit('process_list', processes, to=sid)

# ==========================================
# 3. DATABASE MODELS (Mô hình dữ liệu)
# ==========================================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String, unique=True, nullable=False)
    password_hash = db.Column(db.String, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    username = db.Column(db.String, nullable=True)
    action = db.Column(db.String, nullable=False)
    target = db.Column(db.String, nullable=True)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

# ==========================================
# 4. WEB ROUTES (Controllers - Xử lý request)
# ==========================================
@app.route('/')
def index():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    return render_template('index.html')

@limiter.limit("5 per minute")
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user is None or not user.check_password(password):
            error = 'Invalid username or password'
            log_audit_event(
                'login_failed',
                target=username or None,
                details='Invalid credentials'
            )
            return render_template('login.html', error=error)
        session['user_id'] = user.id
        session.permanent = True
        log_audit_event('login_success', target=user.username)
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    if session.get('user_id'):
        log_audit_event('logout')
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/system')
def system():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    return render_template('system.html')

@limiter.limit("30 per minute")
@app.route('/files', methods=['GET', 'POST'])
@app.route('/files/<path:req_path>', methods=['GET', 'POST'])
def files(req_path=''):
    """
    File Manager with dynamic path support and breadcrumb navigation.
    Implements comprehensive Path Traversal protection.
    """
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    # Build absolute path and validate it's within HOME_DIRECTORY
    requested_dir = os.path.join(HOME_DIRECTORY, req_path)
    
    # Security check: Path Traversal protection
    if not _is_safe_path(HOME_DIRECTORY, requested_dir):
        return "Access Denied: Path traversal detected", 403
    
    # Ensure the path exists and is a directory
    if not os.path.exists(requested_dir):
        return "Directory not found", 404
    
    if not os.path.isdir(requested_dir):
        return "Path is not a directory", 400
    
    # Handle file upload (POST)
    if request.method == 'POST':
        uploaded_file = request.files.get('file')
        if uploaded_file and uploaded_file.filename:
            filename = secure_filename_unicode(uploaded_file.filename)
            save_path = os.path.join(requested_dir, filename)
            
            # Double-check save path is safe
            if not _is_safe_path(HOME_DIRECTORY, save_path):
                return "Access Denied: Invalid upload path", 403
            
            uploaded_file.save(save_path)
            rel_target = os.path.join(req_path, filename) if req_path else filename
            _audit_file_action('file_uploaded', rel_path=rel_target)
        
        # Redirect to same path after upload
        if req_path:
            return redirect(url_for('files', req_path=req_path))
        return redirect(url_for('files'))
    
    # Handle directory listing (GET)
    files_details = []
    
    try:
        for item_name in os.listdir(requested_dir):
            item_path = os.path.join(requested_dir, item_name)
            
            # Skip if path is unsafe (shouldn't happen, but extra safety)
            if not _is_safe_path(HOME_DIRECTORY, item_path):
                continue
            
            # Get file/dir stats
            is_dir = os.path.isdir(item_path)
            stat_info = os.stat(item_path)
            
            # Check if editable (Smart Check)
            is_editable = False
            if not is_dir and stat_info.st_size <= MAX_EDIT_SIZE:
                # Heuristic: Read first 1024 bytes to check for NUL byte
                try:
                    with open(item_path, 'rb') as f:
                        chunk = f.read(1024)
                        if b'\x00' not in chunk:
                            is_editable = True
                except Exception:
                    pass # Cannot read, assume not editable

            # Build relative path for navigation
            if req_path:
                relative_path = os.path.join(req_path, item_name)
            else:
                relative_path = item_name
            
            files_details.append({
                'name': item_name,
                'is_dir': is_dir,
                'size': stat_info.st_size if not is_dir else 0,
                'mtime': datetime.fromtimestamp(stat_info.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                'relative_path': relative_path,
                'is_editable': is_editable
            })
    except Exception as e:
        print(f"Error listing directory {requested_dir}: {e}")
        log_audit_event('directory_view_failed', details=f"path={requested_dir} err={e}")
        return f"Error reading directory: {e}", 500

    # Sort: directories first, then files, alphabetically
    files_details.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
    
    # Build breadcrumbs for navigation
    breadcrumbs = []
    if req_path:
        parts = req_path.split('/')
        current = ''
        for part in parts:
            if part:  # Skip empty parts
                current = os.path.join(current, part) if current else part
                breadcrumbs.append({
                    'name': part,
                    'path': current
                })
    
    _audit_file_action('directory_viewed', rel_path=req_path or '/', details=f"items={len(files_details)}")

    return render_template(
        'files.html',
        files=files_details,
        current_path=req_path,
        breadcrumbs=breadcrumbs,
        home_label=os.path.basename(HOME_DIRECTORY) or 'Home',
        base_abs=HOME_DIRECTORY,
        abs_current=os.path.abspath(requested_dir),
        rel_current=req_path,
        max_edit_size=MAX_EDIT_SIZE
    )

@app.route('/download/<path:filename>')
def download(filename):
    """
    Download file with Path Traversal protection.
    """
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    # Build absolute path
    file_path = os.path.join(HOME_DIRECTORY, filename)
    
    # Security check: Path Traversal protection
    if not _is_safe_path(HOME_DIRECTORY, file_path):
        return "Access Denied: Path traversal detected", 403
    
    # Check file exists
    if not os.path.exists(file_path):
        return "File not found", 404
    
    # Check it's actually a file, not a directory
    if not os.path.isfile(file_path):
        return "Path is not a file", 400
    
    # Extract directory and filename for send_from_directory
    directory = os.path.dirname(file_path)
    file_name = os.path.basename(file_path)
    _audit_file_action('file_downloaded', rel_path=filename)
    
    return send_from_directory(directory, file_name, as_attachment=True)

@app.route('/download_backup')
def download_backup():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    rel_path = request.args.get('path') or ''
    ts = request.args.get('ts') or ''
    abs_path = os.path.abspath(os.path.join(HOME_DIRECTORY, rel_path))
    if not _is_safe_path(HOME_DIRECTORY, abs_path):
        return "Access Denied", 403
    rel_parts = (rel_path or '').replace('\\','/').split('/')
    file_name = rel_parts[-1] if rel_parts and rel_parts[-1] else os.path.basename(abs_path)
    subdir = os.path.join(BACKUP_DIRECTORY, *([p for p in rel_parts[:-1] if p] + [file_name]))
    backup_file = os.path.join(subdir, f'{ts}.bak')
    if not os.path.exists(backup_file):
        return "Not found", 404
    _audit_file_action('backup_downloaded', rel_path=rel_path, details=f"ts={ts}")
    return send_from_directory(os.path.dirname(backup_file), os.path.basename(backup_file), as_attachment=True)

@app.route('/edit/<path:req_path>')
def edit(req_path):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    abs_path = os.path.join(HOME_DIRECTORY, req_path)
    if not _is_safe_path(HOME_DIRECTORY, abs_path):
        return "Access Denied", 403
    if not os.path.exists(abs_path):
        return "File not found", 404
    if not os.path.isfile(abs_path):
        return "Path is not a file", 400
    size = os.path.getsize(abs_path)
    if size > MAX_EDIT_SIZE:
        return f"File too large to edit (>{MAX_EDIT_SIZE} bytes)", 400
    ext = os.path.splitext(abs_path)[1].lower().lstrip('.')
    # detect binary (simple heuristic: contains NUL in first 2048 bytes)
    is_binary = False
    try:
        with open(abs_path, 'rb') as fb:
            sample = fb.read(2048)
        if b'\x00' in sample:
            is_binary = True
    except Exception:
        pass
    try:
        with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception:
        return "Unable to read file", 500
    mtime = os.path.getmtime(abs_path)
    lang_map = {'py':'python','js':'javascript','json':'json','md':'markdown','yaml':'yaml','yml':'yaml','html':'html','css':'css','c':'c','h':'c','cpp':'cpp','sh':'shell'}
    language = lang_map.get(ext, 'plaintext')
    _audit_file_action('file_viewed', rel_path=req_path)
    return render_template('edit.html', rel_path=req_path, file_name=os.path.basename(abs_path), content=content, mtime=mtime, language=language, is_binary=is_binary, home_label=os.path.basename(HOME_DIRECTORY) or 'Home')

@app.route('/trash')
def trash():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    items = []
    try:
        import json
        if os.path.exists(TRASH_DIRECTORY):
            for ts in sorted(os.listdir(TRASH_DIRECTORY), reverse=True):
                ts_dir = os.path.join(TRASH_DIRECTORY, ts)
                if not os.path.isdir(ts_dir):
                    continue
                index_path = os.path.join(ts_dir, '.index.json')
                if os.path.exists(index_path):
                    try:
                        with open(index_path, 'r', encoding='utf-8') as f:
                            entries = json.load(f) or []
                        for ent in entries:
                            rel = ent.get('rel') or ''
                            trash_rel = os.path.join(ts, rel)
                            abs_path = os.path.join(TRASH_DIRECTORY, trash_rel)
                            items.append({
                                "trash_rel": trash_rel.replace('\\', '/'),
                                "original_rel": rel.replace('\\', '/'),
                                "is_dir": bool(ent.get('is_dir')),
                                "size": ent.get('size', 0),
                                "trashed_at": ts,
                                "exists": os.path.exists(abs_path)
                            })
                    except Exception:
                        continue
    except Exception as e:
        print(f"trash list error: {e}")
        log_audit_event('trash_list_failed', details=str(e))
    log_audit_event('trash_viewed', details=f"items={len(items)}")
    return render_template('trash.html', items=items, home_label=os.path.basename(HOME_DIRECTORY) or 'Home')


@app.route('/audit')
def audit():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    page = request.args.get('page', 1, type=int)
    per_page = 50
    page = max(page, 1)

    filters = _extract_audit_filters(request.args)
    tz = timezone(timedelta(hours=filters['tz_offset']))

    query = AuditLog.query
    query = _apply_audit_filters(query, filters)

    total = query.count()
    total_pages = max(1, math.ceil(total / per_page)) if total else 1
    page = min(page, total_pages)
    logs_raw = query.order_by(AuditLog.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

    actions = [row[0] for row in db.session.query(AuditLog.action).distinct().order_by(AuditLog.action).all()]
    timezone_options = _build_timezone_options()

    logs = []
    for entry in logs_raw:
        logs.append({
            'timestamp': _format_audit_timestamp(entry.created_at, tz),
            'user': entry.username or 'N/A',
            'user_id': entry.user_id,
            'action': entry.action,
            'action_class': _classify_audit_action(entry.action),
            'target': entry.target,
            'ip': entry.ip_address,
            'details': _parse_audit_details(entry.details),
        })

    query_params = _filter_query_params(filters)
    query_string = urlencode(query_params)
    export_url = url_for('audit_export', **query_params)
    prune_summary = {
        'deleted': request.args.get('prune_deleted', type=int),
        'retention': request.args.get('prune_retention', type=int),
    }

    return render_template(
        'audit.html',
        logs=logs,
        page=page,
        total_pages=total_pages,
        total=total,
        filters=filters,
        per_page=per_page,
        actions=actions,
        timezone_options=timezone_options,
        export_url=export_url,
        status_choices=list(AUDIT_STATUS_KEYWORDS.keys()),
        query_params=query_params,
        query_string=query_string,
        prune_summary=prune_summary,
        default_prune_days=DEFAULT_AUDIT_RETENTION_DAYS,
        max_prune_days=MAX_AUDIT_RETENTION_DAYS,
        min_prune_days=MIN_AUDIT_RETENTION_DAYS,
        export_limit_days=DEFAULT_AUDIT_EXPORT_DAYS,
    )


@app.route('/audit/export')
def audit_export():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    filters = _extract_audit_filters(request.args)
    tz = timezone(timedelta(hours=filters['tz_offset']))

    query = AuditLog.query
    enforce_default_range = False
    if not filters['start'] and not filters['end']:
        filters['end'] = datetime.now(timezone.utc)
        filters['start'] = filters['end'] - timedelta(days=DEFAULT_AUDIT_EXPORT_DAYS)
        enforce_default_range = True
    elif not filters['end']:
        filters['end'] = datetime.now(timezone.utc)

    query = _apply_audit_filters(query, filters)
    query = query.order_by(AuditLog.created_at.desc())

    def generate():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(['Timestamp', 'User', 'User ID', 'Action', 'Target', 'IP', 'Details'])
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)

        for entry in query.yield_per(200):
            parsed_details = _parse_audit_details(entry.details)
            if parsed_details:
                details_text = '; '.join(
                    [f"{item['key']}: {item['value']}" if item.get('key') else str(item.get('value')) for item in parsed_details]
                )
            else:
                details_text = entry.details or ''

            writer.writerow([
                _format_audit_timestamp(entry.created_at, tz),
                entry.username or 'N/A',
                entry.user_id or '',
                entry.action,
                entry.target or '',
                entry.ip_address or '',
                details_text,
            ])

            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)

    timestamp_for_name = datetime.now(timezone.utc)
    if enforce_default_range:
        timestamp_for_name = filters['end']
    filename = f"audit-export-{_format_audit_timestamp(timestamp_for_name, tz).replace(' ', '_')}.csv"
    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"'
    }
    return Response(stream_with_context(generate()), mimetype='text/csv', headers=headers)


@app.route('/audit/prune', methods=['POST'])
def audit_prune():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    retention = request.form.get('retention', type=float)
    if retention is None:
        retention = DEFAULT_AUDIT_RETENTION_DAYS
    retention = max(MIN_AUDIT_RETENTION_DAYS, min(retention, MAX_AUDIT_RETENTION_DAYS))
    cutoff = datetime.utcnow() - timedelta(days=retention)

    try:
        deleted = AuditLog.query.filter(AuditLog.created_at < cutoff).delete(synchronize_session=False)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        deleted = 0
        log_audit_event('audit_log_prune_failed', details=f'retention_days={retention} error={exc}')
        return redirect(url_for('audit', prune_deleted=deleted, prune_retention=retention))

    log_audit_event('audit_log_pruned', details=f'retention_days={retention} deleted={deleted}')

    return_query = request.form.get('return_query', '') or ''
    redirect_params = dict(parse_qsl(return_query, keep_blank_values=True))
    redirect_params['prune_deleted'] = deleted
    redirect_params['prune_retention'] = retention
    return redirect(url_for('audit', **redirect_params))

# ==========================================
# 5. API ENDPOINTS (Xử lý JSON cho Ajax)
# ==========================================
@app.route('/api/check_exists', methods=['POST'])
def api_check_exists():
    if not session.get('user_id'):
        return {"error": "unauthorized"}, 401
    
    data = request.get_json(silent=True) or {}
    filename = data.get('filename')
    path = data.get('path') or ''
    
    if not filename:
        return {"error": "missing filename"}, 400
        
    dest_dir = os.path.join(HOME_DIRECTORY, path)
    if not _is_safe_path(HOME_DIRECTORY, dest_dir):
        return {"error": "invalid path"}, 403
        
    safe_filename = secure_filename_unicode(filename)
    dest_path = os.path.join(dest_dir, safe_filename)
    rel_dest = os.path.join(path, safe_filename) if path else safe_filename
    
    return {"exists": os.path.exists(dest_path)}

@app.route('/api/upload_chunk', methods=['POST'])
@limiter.exempt
def api_upload_chunk():
    """
    Handle chunked file uploads.
    """
    if not session.get('user_id'):
        return {"error": "unauthorized"}, 401
    
    file = request.files.get('file')
    filename = request.form.get('filename')
    path = request.form.get('path') or ''
    chunk_index = int(request.form.get('chunk_index', 0))
    total_chunks = int(request.form.get('total_chunks', 1))
    auto_rename = request.form.get('auto_rename') == 'true'

    if not file or not filename:
        return {"error": "Missing file or filename"}, 400

    # Validate path
    dest_dir = os.path.join(HOME_DIRECTORY, path)
    if not _is_safe_path(HOME_DIRECTORY, dest_dir):
        return {"error": "Invalid path"}, 403
    
    # Ensure directory exists
    if not os.path.exists(dest_dir):
        return {"error": "Directory not found"}, 404

    # Sanitize filename
    safe_filename = secure_filename_unicode(filename)
    dest_path = os.path.join(dest_dir, safe_filename)
    rel_dest = os.path.join(path, safe_filename) if path else safe_filename

    # Security check on final path
    if not _is_safe_path(HOME_DIRECTORY, dest_path):
        return {"error": "Invalid destination"}, 403

    try:
        # If it's the first chunk
        if chunk_index == 0:
            # Auto-rename logic if requested
            if auto_rename and os.path.exists(dest_path):
                base, ext = os.path.splitext(safe_filename)
                counter = 1
                while os.path.exists(dest_path):
                    new_name = f"{base} ({counter}){ext}"
                    dest_path = os.path.join(dest_dir, new_name)
                    counter += 1
                safe_filename = os.path.basename(dest_path) # Update for return
                rel_dest = os.path.join(path, safe_filename) if path else safe_filename

            # Create new file
            with open(dest_path, 'wb') as f:
                f.write(file.read())
        else:
            # Append to existing
            with open(dest_path, 'ab') as f:
                f.write(file.read())

        if total_chunks <= 1 or chunk_index == total_chunks - 1:
            size = None
            try:
                size = os.path.getsize(dest_path)
            except Exception:
                pass
            details = f"size={size}" if size is not None else None
            _audit_file_action('file_uploaded_chunked', rel_path=rel_dest, details=details)
            
        return {"ok": True, "chunk_index": chunk_index, "final_filename": safe_filename}
    except Exception as e:
        print(f"Upload chunk error: {e}")
        return {"error": str(e)}, 500

@app.route('/api/zip', methods=['POST'])
def api_zip():
    if not session.get('user_id'):
        return {"error": "unauthorized"}, 401
    
    data = request.get_json(silent=True) or {}
    paths = data.get('paths') or []
    current_rel = data.get('current_path') or ''
    
    if not paths:
        return {"error": "No files selected"}, 400
        
    current_abs = os.path.join(HOME_DIRECTORY, current_rel)
    if not _is_safe_path(HOME_DIRECTORY, current_abs):
        return {"error": "Invalid path"}, 403
        
    # Smart Naming Logic
    if len(paths) == 1:
        # If single item, use its name
        item_name = os.path.basename(paths[0])
        # If it's a file, strip extension? Usually yes for "folder.zip", but "file.txt.zip" is also common.
        # Let's strip extension if it's a file to make "file.zip" instead of "file.txt.zip"
        # BUT if it's a folder, keep name.
        # Check if it is file or dir? We only have relative path.
        full_item_path = os.path.join(HOME_DIRECTORY, paths[0])
        if os.path.isfile(full_item_path):
            base_name, _ = os.path.splitext(item_name)
        else:
            base_name = item_name
    else:
        # Multiple items
        base_name = f"archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Auto-rename output zip
    zip_name = f"{base_name}.zip"
    zip_path = os.path.join(current_abs, zip_name)
    counter = 1
    while os.path.exists(zip_path):
        zip_name = f"{base_name} ({counter}).zip"
        zip_path = os.path.join(current_abs, zip_name)
        counter += 1
    
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for rel_item in paths:
                abs_item = os.path.join(HOME_DIRECTORY, rel_item)
                if not _is_safe_path(HOME_DIRECTORY, abs_item) or not os.path.exists(abs_item):
                    continue
                
                if os.path.isfile(abs_item):
                    # Entry in zip should be relative to current dir
                    arcname = os.path.relpath(abs_item, current_abs)
                    zipf.write(abs_item, arcname)
                else:
                    # Folder recursion
                    for root, dirs, files in os.walk(abs_item):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, current_abs) # Keep folder structure relative to current view
                            zipf.write(file_path, arcname)
                            
        rel_zip = os.path.join(current_rel, zip_name) if current_rel else zip_name
        _audit_file_action('zip_created', rel_path=rel_zip, details=f"items={len(paths)}")
        return {"ok": True, "zip_name": zip_name}
    except Exception as e:
        print(f"Zip error: {e}")
        return {"error": str(e)}, 500

@app.route('/api/unzip', methods=['POST'])
def api_unzip():
    if not session.get('user_id'):
        return {"error": "unauthorized"}, 401
    
    data = request.get_json(silent=True) or {}
    rel_path = data.get('path')
    
    if not rel_path:
        return {"error": "Missing path"}, 400
        
    abs_path = os.path.join(HOME_DIRECTORY, rel_path)
    if not _is_safe_path(HOME_DIRECTORY, abs_path):
        return {"error": "Invalid path"}, 403
    
    if not os.path.isfile(abs_path):
        return {"error": "File not found"}, 404

    # Determine type
    lower_name = abs_path.lower()
    extract_dir = os.path.dirname(abs_path)
    
    try:
        if lower_name.endswith('.zip'):
            if not zipfile.is_zipfile(abs_path):
                return {"error": "Invalid zip file"}, 400
            
            with zipfile.ZipFile(abs_path, 'r') as zipf:
                # Security: Zip Slip protection
                for member in zipf.namelist():
                    target_path = os.path.join(extract_dir, member)
                    if not _is_safe_path(extract_dir, target_path):
                        raise Exception(f"Malicious zip file (Zip Slip): {member}")
                zipf.extractall(extract_dir)

        elif lower_name.endswith(('.tar', '.tar.gz', '.tgz')):
            if not tarfile.is_tarfile(abs_path):
                 return {"error": "Invalid tar file"}, 400
            
            with tarfile.open(abs_path, 'r:*') as tar:
                # Security: Tar Slip protection
                for member in tar.getmembers():
                    target_path = os.path.join(extract_dir, member.name)
                    if not _is_safe_path(extract_dir, target_path):
                        raise Exception(f"Malicious tar file (Tar Slip): {member.name}")
                    # Filter: don't extract absolute paths or smart filtering
                    if member.name.startswith('/') or '..' in member.name:
                         raise Exception(f"Malicious tar path: {member.name}")
                
                tar.extractall(extract_dir) # safe after check
        else:
            return {"error": "Unsupported archive format"}, 400
            
        _audit_file_action('archive_extracted', rel_path=_relpath_within_home(abs_path), details=f"dest={_relpath_within_home(extract_dir)}")
        return {"ok": True}
    except Exception as e:
        print(f"Unzip error: {e}")
        return {"error": str(e)}, 500

@limiter.limit("60 per minute")
@app.route('/api/save', methods=['POST'])
def api_save():
    if not session.get('user_id'):
        return {"error":"unauthorized"}, 401
    data = request.get_json(silent=True) or {}
    rel_path = data.get('path') or ''
    content = data.get('content') or ''
    client_mtime = data.get('mtime')
    force = bool(data.get('force'))
    abs_path = os.path.join(HOME_DIRECTORY, rel_path)
    abs_path = os.path.abspath(abs_path)
    if not _is_safe_path(HOME_DIRECTORY, abs_path):
        return {"error":"invalid path"}, 400
    if not os.path.exists(abs_path):
        return {"error":"not found"}, 404
    if not os.path.isfile(abs_path):
        return {"error":"not a file"}, 400
    # allow saving any type; still enforce size limit below
    encoded = content.encode('utf-8', errors='replace')
    if len(encoded) > MAX_EDIT_SIZE:
        return {"error":"content too large"}, 400
    current_mtime = os.path.getmtime(abs_path)
    try:
        if client_mtime is not None and not force:
            try:
                if float(client_mtime) != float(current_mtime):
                    return {"error":"conflict","code":"conflict","current_mtime":current_mtime}, 409
            except Exception:
                pass
        ts = datetime.now().strftime('%Y%m%d%H%M%S%f')
        # Write backup into .backups/<rel_dir>/<file_name>/<ts>.bak
        try:
            rel_parts = (rel_path or '').replace('\\','/').split('/')
            file_name = rel_parts[-1] if rel_parts and rel_parts[-1] else os.path.basename(abs_path)
            subdir = os.path.join(BACKUP_DIRECTORY, *([p for p in rel_parts[:-1] if p] + [file_name]))
            os.makedirs(subdir, exist_ok=True)
            backup_path = os.path.join(subdir, f'{ts}.bak')
            shutil.copy2(abs_path, backup_path)
            # Enforce retention
            try:
                names = [n for n in os.listdir(subdir) if n.endswith('.bak')]
                names.sort()  # ts in name => lexicographic equals chronological
                excess = len(names) - BACKUP_RETENTION
                if excess > 0:
                    for old in names[:excess]:
                        try:
                            os.remove(os.path.join(subdir, old))
                        except Exception:
                            pass
            except Exception:
                pass
        except Exception:
            pass
        with open(abs_path, 'w', encoding='utf-8', errors='replace') as f:
            f.write(content)
        new_mtime = os.path.getmtime(abs_path)
        details = f"bytes={len(encoded)} force={force}"
        _audit_file_action('file_saved', rel_path=rel_path, details=details)
        return {"ok":True, "mtime": new_mtime}
    except Exception as e:
        return {"error": str(e)}, 500

@limiter.limit("30 per minute")
@app.route('/api/delete_batch', methods=['POST'])
def api_delete_batch():
    if not session.get('user_id'):
        return {"error": "unauthorized"}, 401
    data = request.get_json(silent=True) or {}
    paths = data.get('paths') or []
    permanent = bool(data.get('permanent'))
    if not isinstance(paths, list) or not paths:
        return {"error": "missing paths"}, 400
    moved = 0
    removed = 0
    ts = None
    try:
        if not permanent:
            ts = datetime.now().strftime('%Y%m%d%H%M%S%f')
        for rel_path in paths:
            if not rel_path:
                continue
            src_abs = os.path.abspath(os.path.join(HOME_DIRECTORY, rel_path))
            if not _is_safe_path(HOME_DIRECTORY, src_abs):
                continue
            # skip system folders
            if (src_abs == TRASH_DIRECTORY or src_abs.startswith(TRASH_DIRECTORY + os.sep) or
                src_abs == BACKUP_DIRECTORY or src_abs.startswith(BACKUP_DIRECTORY + os.sep)):
                continue
            if not os.path.exists(src_abs):
                continue
            if permanent:
                try:
                    if os.path.isdir(src_abs):
                        shutil.rmtree(src_abs)
                    else:
                        os.remove(src_abs)
                    removed += 1
                except Exception:
                    pass
            else:
                try:
                    dest_abs = os.path.join(TRASH_DIRECTORY, ts, rel_path)
                    os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
                    shutil.move(src_abs, dest_abs)
                    moved += 1
                    # update index
                    try:
                        import json
                        index_path = os.path.join(TRASH_DIRECTORY, ts, '.index.json')
                        items = []
                        if os.path.exists(index_path):
                            with open(index_path, 'r', encoding='utf-8') as f:
                                items = json.load(f) or []
                        items.append({
                            "rel": rel_path,
                            "is_dir": os.path.isdir(dest_abs),
                            "size": (os.path.getsize(dest_abs) if os.path.isfile(dest_abs) else 0),
                            "trashed_at": ts
                        })
                        with open(index_path, 'w', encoding='utf-8') as f:
                            json.dump(items, f, ensure_ascii=False)
                    except Exception:
                        pass
                except Exception:
                    pass
        log_audit_event(
            'batch_delete',
            details=f"permanent={permanent} moved={moved} removed={removed} total={len(paths)}",
        )
        return {"ok": True, "moved": moved, "removed": removed, "permanent": permanent}
    except Exception as e:
        return {"error": str(e)}, 500

@limiter.limit("15 per minute")
@app.route('/api/trash_empty', methods=['POST'])
def api_trash_empty():
    if not session.get('user_id'):
        return {"error": "unauthorized"}, 401
    deleted = 0
    try:
        if os.path.exists(TRASH_DIRECTORY):
            for name in os.listdir(TRASH_DIRECTORY):
                path = os.path.join(TRASH_DIRECTORY, name)
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                    deleted += 1
                except Exception:
                    pass
        log_audit_event('trash_emptied', details=f"deleted={deleted}")
        return {"ok": True, "deleted": deleted}
    except Exception as e:
        return {"error": str(e)}, 500

@limiter.limit("60 per minute")
@app.route('/api/backups')
def api_backups():
    if not session.get('user_id'):
        return {"error": "unauthorized"}, 401
    rel_path = request.args.get('path') or ''
    abs_path = os.path.abspath(os.path.join(HOME_DIRECTORY, rel_path))
    if not _is_safe_path(HOME_DIRECTORY, abs_path):
        return {"error": "invalid path"}, 400
    rel_parts = (rel_path or '').replace('\\','/').split('/')
    file_name = rel_parts[-1] if rel_parts and rel_parts[-1] else os.path.basename(abs_path)
    subdir = os.path.join(BACKUP_DIRECTORY, *([p for p in rel_parts[:-1] if p] + [file_name]))
    items = []
    try:
        if os.path.exists(subdir):
            for n in os.listdir(subdir):
                if not n.endswith('.bak'):
                    continue
                p = os.path.join(subdir, n)
                try:
                    items.append({
                        "ts": n[:-4],
                        "size": os.path.getsize(p),
                        "mtime": os.path.getmtime(p)
                    })
                except Exception:
                    pass
        # sort desc by ts
        items.sort(key=lambda x: x['ts'], reverse=True)
        return {"ok": True, "items": items}
    except Exception as e:
        return {"error": str(e)}, 500

@limiter.limit("60 per minute")
@app.route('/api/restore_backup', methods=['POST'])
def api_restore_backup():
    if not session.get('user_id'):
        return {"error": "unauthorized"}, 401
    data = request.get_json(silent=True) or {}
    rel_path = data.get('path') or ''
    ts = data.get('ts') or ''
    abs_path = os.path.abspath(os.path.join(HOME_DIRECTORY, rel_path))
    if not _is_safe_path(HOME_DIRECTORY, abs_path):
        return {"error": "invalid path"}, 400
    if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
        return {"error": "not found"}, 404
    rel_parts = (rel_path or '').replace('\\','/').split('/')
    file_name = rel_parts[-1] if rel_parts and rel_parts[-1] else os.path.basename(abs_path)
    subdir = os.path.join(BACKUP_DIRECTORY, *([p for p in rel_parts[:-1] if p] + [file_name]))
    backup_file = os.path.join(subdir, f'{ts}.bak')
    if not os.path.exists(backup_file):
        return {"error": "backup not found"}, 404
    try:
        # create a backup of current before restoring
        ts2 = datetime.now().strftime('%Y%m%d%H%M%S%f')
        try:
            os.makedirs(subdir, exist_ok=True)
            shutil.copy2(abs_path, os.path.join(subdir, f'{ts2}.bak'))
        except Exception:
            pass
        shutil.copy2(backup_file, abs_path)
        new_mtime = os.path.getmtime(abs_path)
        _audit_file_action('file_restored_backup', rel_path=rel_path, details=f"ts={ts}")
        return {"ok": True, "mtime": new_mtime}
    except Exception as e:
        return {"error": str(e)}, 500

@limiter.limit("60 per minute")
@app.route('/api/backup_content')
def api_backup_content():
    if not session.get('user_id'):
        return {"error": "unauthorized"}, 401
    rel_path = request.args.get('path') or ''
    ts = request.args.get('ts') or ''
    abs_path = os.path.abspath(os.path.join(HOME_DIRECTORY, rel_path))
    if not _is_safe_path(HOME_DIRECTORY, abs_path):
        return {"error": "invalid path"}, 400
    rel_parts = (rel_path or '').replace('\\','/').split('/')
    file_name = rel_parts[-1] if rel_parts and rel_parts[-1] else os.path.basename(abs_path)
    subdir = os.path.join(BACKUP_DIRECTORY, *([p for p in rel_parts[:-1] if p] + [file_name]))
    backup_file = os.path.join(subdir, f'{ts}.bak')
    if not os.path.exists(backup_file):
        return {"error": "not found"}, 404
    if os.path.getsize(backup_file) > MAX_EDIT_SIZE:
        return {"ok": True, "binary": True}
    # heuristic binary check
    try:
        with open(backup_file, 'rb') as fb:
            sample = fb.read(2048)
        if b'\x00' in sample:
            return {"ok": True, "binary": True}
    except Exception:
        pass
    try:
        with open(backup_file, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        return {"ok": True, "binary": False, "content": content}
    except Exception as e:
        return {"error": str(e)}, 500

@limiter.limit("30 per minute")
@app.route('/api/delete', methods=['POST'])
def api_delete():
    if not session.get('user_id'):
        return {"error": "unauthorized"}, 401
    data = request.get_json(silent=True) or {}
    rel_path = data.get('path')
    permanent = bool(data.get('permanent'))
    if not rel_path:
        return {"error": "missing path"}, 400
    src_abs = os.path.join(HOME_DIRECTORY, rel_path)
    src_abs = os.path.abspath(src_abs)
    if not _is_safe_path(HOME_DIRECTORY, src_abs):
        return {"error": "invalid path"}, 400
    # Prevent deleting items inside system folders (.trash, .backups) from File Manager
    if (src_abs == TRASH_DIRECTORY or src_abs.startswith(TRASH_DIRECTORY + os.sep) or
        src_abs == BACKUP_DIRECTORY or src_abs.startswith(BACKUP_DIRECTORY + os.sep)):
        return {"error": "cannot delete inside system folders (.trash/.backups) here; use proper pages"}, 400
    if not os.path.exists(src_abs):
        return {"error": "not found"}, 404
    try:
        if permanent:
            if os.path.isdir(src_abs):
                shutil.rmtree(src_abs)
            else:
                os.remove(src_abs)
            _audit_file_action('file_deleted_permanent', rel_path=rel_path)
            return {"ok": True, "permanent": True}
        ts = datetime.now().strftime('%Y%m%d%H%M%S%f')
        dest_abs = os.path.join(TRASH_DIRECTORY, ts, rel_path)
        os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
        shutil.move(src_abs, dest_abs)
        # maintain simple index for the batch
        try:
            import json
            index_path = os.path.join(TRASH_DIRECTORY, ts, '.index.json')
            items = []
            if os.path.exists(index_path):
                with open(index_path, 'r', encoding='utf-8') as f:
                    items = json.load(f) or []
            items.append({
                "rel": rel_path,
                "is_dir": os.path.isdir(dest_abs),
                "size": (os.path.getsize(dest_abs) if os.path.isfile(dest_abs) else 0),
                "trashed_at": ts
            })
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(items, f, ensure_ascii=False)
        except Exception:
            pass
        _audit_file_action('file_deleted_soft', rel_path=rel_path, details=f"trash_ts={ts}")
        return {"ok": True, "permanent": False}
    except Exception as e:
        return {"error": str(e)}, 500

@limiter.limit("30 per minute")
@app.route('/api/restore', methods=['POST'])
def api_restore():
    if not session.get('user_id'):
        return {"error": "unauthorized"}, 401
    data = request.get_json(silent=True) or {}
    trash_rel = data.get('trash_rel')
    if not trash_rel:
        return {"error": "missing path"}, 400
    parts = trash_rel.replace('\\', '/').split('/')
    if len(parts) < 2:
        return {"error": "invalid trash path"}, 400
    ts = parts[0]
    rel = '/'.join(parts[1:])
    src_abs = os.path.join(TRASH_DIRECTORY, ts, *rel.split('/'))
    if not _is_safe_path(TRASH_DIRECTORY, src_abs):
        return {"error": "invalid path"}, 400
    if not os.path.exists(src_abs):
        return {"error": "not found"}, 404
    dest_abs = os.path.join(HOME_DIRECTORY, *rel.split('/'))
    if not _is_safe_path(HOME_DIRECTORY, dest_abs):
        return {"error": "invalid dest"}, 400
    try:
        os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
        final_dest = dest_abs
        if os.path.exists(final_dest):
            final_dest = dest_abs + f'.restored.{ts}'
        shutil.move(src_abs, final_dest)
        # update index
        try:
            import json
            index_path = os.path.join(TRASH_DIRECTORY, ts, '.index.json')
            if os.path.exists(index_path):
                with open(index_path, 'r', encoding='utf-8') as f:
                    entries = json.load(f) or []
                entries = [e for e in entries if (e.get('rel') or '') != rel]
                with open(index_path, 'w', encoding='utf-8') as f:
                    json.dump(entries, f, ensure_ascii=False)
        except Exception:
            pass
        _audit_file_action('file_restored_from_trash', rel_path=rel, details=f"ts={ts}")
        return {"ok": True, "restored_to": final_dest}
    except Exception as e:
        return {"error": str(e)}, 500

@limiter.limit("30 per minute")
@app.route('/api/delete_permanent', methods=['POST'])
def api_delete_permanent():
    if not session.get('user_id'):
        return {"error": "unauthorized"}, 401
    data = request.get_json(silent=True) or {}
    trash_rel = data.get('trash_rel')
    if not trash_rel:
        return {"error": "missing path"}, 400
    parts = trash_rel.replace('\\', '/').split('/')
    if len(parts) < 2:
        return {"error": "invalid trash path"}, 400
    ts = parts[0]
    rel = '/'.join(parts[1:])
    target_abs = os.path.join(TRASH_DIRECTORY, ts, *rel.split('/'))
    if not _is_safe_path(TRASH_DIRECTORY, target_abs):
        return {"error": "invalid path"}, 400
    if not os.path.exists(target_abs):
        return {"error": "not found"}, 404
    try:
        if os.path.isdir(target_abs):
            shutil.rmtree(target_abs)
        else:
            os.remove(target_abs)
        # update index
        try:
            import json
            index_path = os.path.join(TRASH_DIRECTORY, ts, '.index.json')
            if os.path.exists(index_path):
                with open(index_path, 'r', encoding='utf-8') as f:
                    entries = json.load(f) or []
                entries = [e for e in entries if (e.get('rel') or '') != rel]
                with open(index_path, 'w', encoding='utf-8') as f:
                    json.dump(entries, f, ensure_ascii=False)
        except Exception:
            pass
        _audit_file_action('trash_deleted_permanent', rel_path=rel, details=f"ts={ts}")
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}, 500

# ==========================================
# 6. SOCKETIO EVENTS (Xử lý thời gian thực)
# ==========================================
def _get_tmux_session_name(user_id):
    safe_uid = str(user_id).replace('-', '')[:8]
    return f"{TERMINAL_TMUX_PREFIX}_{safe_uid}"


def _attach_tmux_session(channel, tmux_session, window_name=None):
    if not tmux_session:
        return
    safe_win = None
    if window_name:
        try:
            safe_win = re.sub(r'[^A-Za-z0-9_\-]', '_', str(window_name))
        except Exception:
            safe_win = None
    if not safe_win:
        safe_win = "win0"
    cmd = (
        f"tmux has-session -t {tmux_session} 2>/dev/null || "
        f"tmux new-session -d -s {tmux_session}; "
        f"tmux select-window -t {tmux_session}:{safe_win} 2>/dev/null || "
        f"tmux new-window -t {tmux_session} -n {safe_win} -d; "
        f"tmux set-option -t {tmux_session} status off; "
        f"tmux attach-session -t {tmux_session}\n"
    )
    try:
        channel.send(cmd)
    except Exception as e:
        print(f"tmux attach error for {tmux_session}:{safe_win}: {e}")


def _schedule_tmux_cleanup(tmux_session):
    if not tmux_session:
        return
    for info in clients.values():
        if info.get('tmux_session') == tmux_session:
            return
    existing = terminal_cleanup_timers.get(tmux_session)
    if existing is not None:
        try:
            existing.cancel()
        except Exception:
            pass
    timer = threading.Timer(TERMINAL_TMUX_TTL_SECONDS, _cleanup_tmux_session, args=(tmux_session,))
    timer.daemon = True
    terminal_cleanup_timers[tmux_session] = timer
    timer.start()


def _cleanup_tmux_session(tmux_session):
    if not tmux_session:
        return
    if any(info.get('tmux_session') == tmux_session for info in clients.values()):
        return
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(TERMINAL_SSH_HOST, username=TERMINAL_SSH_USERNAME, password=TERMINAL_SSH_PASSWORD, timeout=5)
        ssh.exec_command(f"tmux has-session -t {tmux_session} && tmux kill-session -t {tmux_session} || true")
        ssh.close()
    except Exception as e:
        print(f"tmux cleanup error for {tmux_session}: {e}")
    finally:
        terminal_cleanup_timers.pop(tmux_session, None)


@socketio.on('terminal_input')
def handle_terminal_input(data):
    sid = request.sid
    if sid in clients:
        channel = clients[sid]['channel']
        channel.send(data)


@socketio.on('connect')
def handle_connect(auth=None):
    if not session.get('user_id'):
        return False
    sid = request.sid
    user_id = session.get('user_id')
    user_obj = User.query.get(user_id) if user_id else None
    username = user_obj.username if user_obj else None

    window_name = None
    if isinstance(auth, dict):
        window_name = auth.get('window_name') or auth.get('window') or auth.get('tab_id')

    safe_window_name = None
    if window_name:
        try:
            safe_window_name = re.sub(r'[^A-Za-z0-9_\-]', '_', str(window_name))
        except Exception:
            safe_window_name = None
    if not safe_window_name:
        safe_window_name = 'win0'

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_password = 'osboxes.org'
    client.connect('localhost', username='osboxes', password=ssh_password)
    channel = client.invoke_shell()

    base_session = _get_tmux_session_name(user_id)
    tmux_session = f"{base_session}_{safe_window_name}"
    _attach_tmux_session(channel, tmux_session, window_name=safe_window_name)
    if tmux_session in terminal_cleanup_timers:
        try:
            terminal_cleanup_timers[tmux_session].cancel()
        except Exception:
            pass
        terminal_cleanup_timers.pop(tmux_session, None)

    log_filename = f"{tmux_session}_{int(time.time())}.log"
    log_path = os.path.join(TERMINAL_LOG_DIR, log_filename)

    clients[sid] = {
        'client': client,
        'channel': channel,
        'password': ssh_password,
        'user_id': user_id,
        'username': username,
        'tmux_session': tmux_session,
        'window_name': safe_window_name,
        'log_path': log_path,
        'log_file': log_filename,
    }

    def read_from_channel(sid, channel, log_path):
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
        except Exception:
            pass
        try:
            with open(log_path, 'ab') as log_file:
                while True:
                    try:
                        data = channel.recv(1024)
                        if not data:
                            break
                        try:
                            text = data.decode('utf-8')
                        except UnicodeDecodeError:
                            text = data.decode('utf-8', errors='ignore')
                        socketio.emit('terminal_output', text, to=sid)
                        log_file.write(data)
                        log_file.flush()
                    except Exception as e:
                        print(f"read_from_channel error: {e}")
                        break
        except Exception as e:
            print(f"terminal log write error: {e}")

    socketio.start_background_task(target=read_from_channel, sid=sid, channel=channel, log_path=log_path)
    log_details = f"sid={sid} tmux={tmux_session} window={safe_window_name} record={log_filename}"
    log_audit_event('terminal_session_opened', details=log_details, user_id=user_id, username=username)


@socketio.on('resize')
def handle_resize(data):
    sid = request.sid
    if sid in clients and isinstance(data, dict):
        cols = data.get('cols') or 80
        rows = data.get('rows') or 24
        try:
            channel = clients[sid]['channel']
            channel.resize_pty(width=int(cols), height=int(rows))
        except Exception as e:
            print(f"resize_pty error: {e}")


@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    info = clients.pop(sid, None)
    if info:
        client = info['client']
        channel = info['channel']
        tmux_session = info.get('tmux_session')
        try:
            channel.close()
        except Exception:
            pass
        try:
            client.close()
        except Exception:
            pass
        if tmux_session:
            _schedule_tmux_cleanup(tmux_session)
        log_details = f"sid={sid} tmux={tmux_session} window={info.get('window_name')} record={info.get('log_file')}"
        log_audit_event('terminal_session_closed', details=log_details, user_id=info.get('user_id'), username=info.get('username'))

@socketio.on('system_action')
def handle_system_action(data):
    """
    Handle package installation/removal requests.
    Validates input and starts background task to run apt-get command.
    """
    if not session.get('user_id'):
        return
    
    action = data.get('action') if isinstance(data, dict) else None
    package = data.get('package') if isinstance(data, dict) else None
    
    # Validate action and package
    if not action or not package:
        log_audit_event('system_action_invalid', details='missing action/package')
        return

    # Validate action is one of the allowed operations
    if action not in ['install', 'remove', 'purge']:
        socketio.emit('pkg_status', {
            'output': f'Invalid action: {action}',
            'status': 'error'
        }, to=request.sid)
        log_audit_event('system_action_invalid', details=f'action={action} package={package}')
        return

    # Ensure only one apt-get job runs at a time (per server)
    global pkg_task_running
    with pkg_task_lock:
        if pkg_task_running:
            socketio.emit('pkg_status', {
                'output': 'Another package operation is already running. Please wait until it finishes.',
                'status': 'error'
            }, to=request.sid)
            return
        pkg_task_running = True

    sid = request.sid
    user_id = session.get('user_id')
    user_obj = User.query.get(user_id) if user_id else None
    username = user_obj.username if user_obj else None
    log_audit_event('system_action_requested', details=f'action={action} package={package}', user_id=user_id, username=username)

    # Start background task to run the command
    socketio.start_background_task(
        target=_run_pkg_action,
        action=action,
        package=package,
        sid=sid,
        audit_user_id=user_id,
        audit_username=username,
    )

@socketio.on('list_processes')
def handle_list_processes():
    """
    Handle request to list processes.
    Starts background task to avoid blocking the main thread.
    """
    if not session.get('user_id'):
        return
    
    socketio.start_background_task(target=_get_and_emit_processes, sid=request.sid)

@socketio.on('kill_process')
def handle_kill_process(data):
    """
    Handle request to kill a process.
    Uses subprocess.run with sudo kill instead of os.kill for better control.
    Automatically refreshes process list after successful kill.
    """
    if not session.get('user_id'):
        return

    # Use module-level cache timestamp
    global last_process_time

    pid = data.get('pid') if isinstance(data, dict) else None
    if not pid:
        return

    try:
        pid_int = int(pid)
    except (TypeError, ValueError):
        return

    # Extra safety: do not allow killing protected processes
    if _is_protected_process(pid_int):
        socketio.emit('process_error', {
            'message': f'Cannot kill protected system process {pid_int}',
            'error': ''
        }, to=request.sid)
        return
    
    sid = request.sid
    
    try:
        # Use sudo kill to terminate the process
        subprocess.run(
            ['sudo', 'kill', str(pid_int)],
            check=True,
            capture_output=True,
            text=True
        )
        
        print(f"Successfully killed process {pid}")
        log_audit_event('process_killed', details=f"pid={pid_int}")
        
        # Invalidate cache so next refresh recomputes list
        with process_cache_lock:
            last_process_time = 0.0

        # Automatically refresh process list after kill
        socketio.start_background_task(target=_get_and_emit_processes, sid=sid)
        
    except subprocess.CalledProcessError as e:
        # Process doesn't exist or permission denied
        err = (e.stderr or '').strip()
        # If process no longer exists, treat as success (already dead)
        if 'no such process' in err.lower():
            print(f"Process {pid_int} already terminated")
            with process_cache_lock:
                last_process_time = 0.0
            socketio.start_background_task(target=_get_and_emit_processes, sid=sid)
        else:
            print(f"Failed to kill process {pid_int}: {err}")
            socketio.emit('process_error', {
                'message': f'Failed to kill process {pid_int}',
                'error': err
            }, to=sid)
            log_audit_event('process_kill_failed', details=f"pid={pid_int} err={err}")
    except Exception as e:
        print(f"kill_process error: {e}")
        socketio.emit('process_error', {
            'message': f'Error killing process {pid}',
            'error': str(e)
        }, to=sid)
        log_audit_event('process_kill_failed', details=f"pid={pid_int} err={e}")

# ==========================================
# 7. MAIN EXECUTION
# ==========================================
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
