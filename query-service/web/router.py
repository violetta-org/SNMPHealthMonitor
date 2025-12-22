from flask import Blueprint, render_template, redirect, url_for, request
from utils.time_range import get_default_range


web_bp = Blueprint("web", __name__)

template_map = {
    'systemstatus': 'dashboard.html',
    'network': 'network.html',
    'disk': 'disk.html',
    'diskio': 'diskio.html',
    'history': 'history.html'
}

@web_bp.route("/")
def index():
    # If using authentication:
    if not session.get('user_id'):
        return redirect(url_for('web.login'))
    return render_template('index.html')

# Imports for File Manager Web
import os
import json
from datetime import datetime
from flask import session, send_from_directory, request
from services.file_service import HOME_DIRECTORY, TRASH_DIRECTORY, BACKUP_DIRECTORY, MAX_EDIT_SIZE
from utils.security import _is_safe_path, secure_filename_unicode
from extensions import limiter
from db.models import User

@web_bp.route("/dashboard")
def dashboard_default():
    return render_template(
        "dashboard.html",
        sysname="raspi-pbl",
        topic="systemstatus"
    )

@web_bp.route("/dashboard/<sysname>")
def dashboard_sys(sysname: str):
    return render_template(
        "dashboard.html",
        sysname=sysname,
        topic="systemstatus"
    )

@web_bp.route("/dashboard/<sysname>/<topic>")
def dashboard_topic(sysname: str, topic: str):
    # Lấy template từ map hoặc fallback
    template_name = template_map.get(topic, "404.html")
    context = {
        "sysname": sysname,
        "topic": topic
    }

    # Inject Device Status (Online/Offline, Last Update)
    try:
        from services.device_service import DeviceService
        device_info = DeviceService.get_device_status(sysname)
        if device_info:
            context["device_info"] = device_info
    except Exception as e:
        print(f"Error fetching device status for header: {e}")

    if topic == "history":
        default_start, default_end = get_default_range()
        start_value = request.args.get("start") or default_start.isoformat(timespec="minutes")
        end_value = request.args.get("end") or default_end.isoformat(timespec="minutes")

        context.update({
            "history_start": start_value,
            "history_end": end_value,
        })
    
    return render_template(
        template_name,  # THÊM tên template
        **context
    )


# ==========================================
# FILE MANAGER WEB ROUTES
# ==========================================

# NOTE: Login/Auth checks are commented/simplified because User model is not fully migrated.
# To enable AUTH: uncomment User import and session checks.

@limiter.limit("5 per minute")
@web_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user is None or not user.check_password(password):
            error = 'Invalid username or password'
            return render_template('login.html', error=error)
        session['user_id'] = user.id
        session.permanent = True
        return redirect(url_for('web.index'))
    return render_template('login.html')

@web_bp.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('web.login'))

@web_bp.route('/system')
def system():
    if not session.get('user_id'):
        return redirect(url_for('web.login'))
    return render_template('system.html')

@web_bp.route('/logs-view')
def logs_view():
    if not session.get('user_id'):
        return redirect(url_for('web.login'))
    
    # Pass user list for filter dropdown
    users = User.query.with_entities(User.id, User.username).all()
    users_list = [{"id": u.id, "username": u.username} for u in users]
    
    return render_template('audit.html', sysname="raspi-pbl", topic="audit", users=users_list)

@limiter.limit("30 per minute")
@web_bp.route('/files', methods=['GET', 'POST'])
@web_bp.route('/files/<path:req_path>', methods=['GET', 'POST'])
def files(req_path=''):
    """
    File Manager with dynamic path support and breadcrumb navigation.
    Implements comprehensive Path Traversal protection.
    """
    if not session.get('user_id'):
        return redirect(url_for('web.login'))
    
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
            
            # Double check save path is safe
            if not _is_safe_path(HOME_DIRECTORY, save_path):
                return "Access Denied: Invalid upload path", 403
            
            uploaded_file.save(save_path)
        
        # Redirect to same path after upload
        if req_path:
            return redirect(url_for('web.files', req_path=req_path))
        return redirect(url_for('web.files'))
    
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

@web_bp.route('/download/<path:filename>')
def download(filename):
    """
    Download file with Path Traversal protection.
    """
    if not session.get('user_id'):
        return redirect(url_for('web.login'))
    
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
    
    return send_from_directory(directory, file_name, as_attachment=True)

@web_bp.route('/download_backup')
def download_backup():
    if not session.get('user_id'):
        return redirect(url_for('web.login'))
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
    return send_from_directory(os.path.dirname(backup_file), os.path.basename(backup_file), as_attachment=True)

@web_bp.route('/edit/<path:req_path>')
def edit(req_path):
    if not session.get('user_id'):
        return redirect(url_for('web.login'))
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
    return render_template('edit.html', rel_path=req_path, file_name=os.path.basename(abs_path), content=content, mtime=mtime, language=language, is_binary=is_binary, home_label=os.path.basename(HOME_DIRECTORY) or 'Home')

@web_bp.route('/trash')
def trash():
    if not session.get('user_id'):
        return redirect(url_for('web.login'))
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
    return render_template('trash.html', items=items, home_label=os.path.basename(HOME_DIRECTORY) or 'Home')