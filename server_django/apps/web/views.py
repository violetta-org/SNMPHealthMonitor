import os
import json
import shutil
from datetime import datetime

from django.shortcuts import render, redirect
from django.urls import reverse
from django.http import HttpResponseNotFound, FileResponse, HttpResponse, Http404, StreamingHttpResponse
from django.conf import settings as django_settings
from apps.devices.models import Device
from apps.core.utils import parse_time_range
from apps.files.utils import (
    is_safe_path,
    is_archive,
    is_editable,
    detect_language,
    relpath_within_home,
)
from apps.files.remote_helper import (
    get_remote_home,
    run_remote_python,
    get_sftp_client,
    run_ssh_cmd,
)

TEMPLATE_MAP = {
    'systemstatus': 'dashboard.html',
    'network': 'network.html',
    'disk': 'disk.html',
    'diskio': 'diskio.html',
    'history': 'history.html'
}

HOME = django_settings.HOME_DIRECTORY
TRASH = django_settings.TRASH_DIRECTORY
BACKUP = django_settings.BACKUP_DIRECTORY
MAX_EDIT_SIZE = django_settings.MAX_EDIT_SIZE


def index(request):
    """Landing page or redirect to dashboard/login."""
    return render(request, 'index.html')


def login(request):
    """Login page with full authentication."""
    # Already logged in? redirect to dashboard
    if request.session.get('user_id'):
        return redirect('web:dashboard_default')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        if not username or not password:
            return render(request, 'login.html', {'error': 'Vui lòng nhập đầy đủ thông tin.'})

        try:
            from apps.core.models import User
            user = User.objects.get(username=username)
            if user.check_password(password):
                # Set session
                request.session['user_id'] = user.id
                request.session['username'] = user.username
                request.session.set_expiry(0)  # Browser-length session

                # Audit log
                _audit_log(request, user, 'LOGIN', None, 'Login successful')

                return redirect('web:dashboard_default')
            else:
                _audit_log(request, None, 'LOGIN_FAILED', None, f'Wrong password for {username}')
                return render(request, 'login.html', {'error': 'Sai mật khẩu.'})
        except User.DoesNotExist:
            _audit_log(request, None, 'LOGIN_FAILED', None, f'Unknown user: {username}')
            return render(request, 'login.html', {'error': 'Tên đăng nhập không tồn tại.'})
        except Exception as e:
            return render(request, 'login.html', {'error': f'Lỗi: {e}'})

    return render(request, 'login.html')


def dashboard_default(request):
    """Default dashboard view - dynamically resolves the first active device."""
    try:
        device = Device.objects.first()
        if device:
            return redirect('web:dashboard_sys', sysname=device.sysname)
    except Exception as e:
        print(f"Error fetching default device: {e}")

    return render(request, "dashboard.html", {
        "sysname": "osboxes",
        "topic": "systemstatus"
    })


def dashboard_sys(request, sysname):
    """Dashboard for specific system."""
    return render(request, "dashboard.html", {
        "sysname": sysname,
        "topic": "systemstatus"
    })


def dashboard_topic(request, sysname, topic):
    """Dashboard detail views."""
    template_name = TEMPLATE_MAP.get(topic, "404.html")

    if template_name == "404.html":
        return render(request, "404.html", status=404)

    context = {
        "sysname": sysname,
        "topic": topic
    }

    # Inject Device Status
    try:
        device = Device.objects.get(sysname=sysname)
        context["device_info"] = {
            "name": device.sysname,
            "status": "online" if device.online else "offline",
            "online": device.online,
            "last_seen": device.last_seen.isoformat() if device.last_seen else None
        }
    except Device.DoesNotExist:
        context["device_info"] = {"status": "unknown"}
    except Exception as e:
        print(f"Error fetching device status: {e}")

    if topic == "history":
        start_str = request.GET.get("start")
        end_str = request.GET.get("end")
        start_dt, end_dt = parse_time_range(start_str, end_str)

        context.update({
            "history_start": start_dt.isoformat(timespec="minutes"),
            "history_end": end_dt.isoformat(timespec="minutes"),
        })

    return render(request, template_name, context)


# ==========================================================================
# File Manager — full directory listing
# ==========================================================================
def files(request, req_path=None):
    """
    File Manager with dynamic path support and breadcrumb navigation.
    Interacts with Jetson Nano.
    """
    req_path = req_path or request.GET.get('req_path') or ''

    # Ensure remote home directory exists
    run_ssh_cmd(f"mkdir -p '{get_remote_home()}'")

    code = f"""
import os, stat, json, datetime
HOME = '{get_remote_home()}'
req_path = '{req_path}'

requested_dir = os.path.abspath(os.path.join(HOME, req_path))
if not requested_dir.startswith(HOME):
    print(json.dumps({{"error": "Access Denied"}}))
    exit()
if not os.path.exists(requested_dir):
    print(json.dumps({{"error": "Directory not found"}}))
    exit()
if not os.path.isdir(requested_dir):
    print(json.dumps({{"error": "Path is not a directory"}}))
    exit()

files_details = []
for item_name in os.listdir(requested_dir):
    item_path = os.path.join(requested_dir, item_name)
    if not item_path.startswith(HOME):
        continue
    item_is_dir = os.path.isdir(item_path)
    stat_info = os.stat(item_path)
    relative_path = os.path.join(req_path, item_name).replace('\\\\', '/') if req_path else item_name
    
    files_details.append({{
        'name': item_name,
        'is_dir': item_is_dir,
        'size': stat_info.st_size if not item_is_dir else 0,
        'mtime': datetime.datetime.fromtimestamp(stat_info.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
        'relative_path': relative_path,
        'is_editable': not item_is_dir,
        'is_archive': not item_is_dir and item_name.lower().endswith(('.zip', '.tar', '.tar.gz', '.tgz')),
    }})

files_details.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))

# breadcrumbs
breadcrumbs = []
if req_path:
    parts = req_path.split('/')
    current = ''
    for part in parts:
        if part:
            current = os.path.join(current, part).replace('\\\\', '/') if current else part
            breadcrumbs.append({{'name': part, 'path': current}})

parent_path = None
if req_path:
    parent = '/'.join(req_path.rstrip('/').split('/')[:-1])
    parent_path = parent if parent else ''

print(json.dumps({{
    "files": files_details,
    "breadcrumbs": breadcrumbs,
    "parent_path": parent_path,
    "home_label": os.path.basename(HOME) or "Home",
    "abs_current": requested_dir,
    "rel_current": req_path
}}))
"""
    result = run_remote_python(code)
    if "error" in result:
        return HttpResponse(result["error"], status=400)

    # Compute parent path for the "Go Up" link
    return render(request, 'files.html', {
        'files': result['files'],
        'current_path': result['rel_current'],
        'breadcrumbs': result['breadcrumbs'],
        'home_label': result['home_label'],
        'base_abs': get_remote_home(),
        'abs_current': result['abs_current'],
        'rel_current': result['rel_current'],
        'max_edit_size': MAX_EDIT_SIZE,
        'parent_path': result['parent_path'],
        'crumb': result['breadcrumbs'][-1] if result['breadcrumbs'] else {'path': '', 'name': 'Home'},
    })


# ==========================================================================
# Trash — list soft-deleted items
# ==========================================================================
def trash(request):
    """
    Trash view — reads .index.json from each trash timestamp folder on Jetson Nano.
    """
    code = f"""
import os, json
HOME = '{get_remote_home()}'
TRASH = os.path.join(HOME, '.trash')
items = []
if os.path.exists(TRASH):
    for ts in sorted(os.listdir(TRASH), reverse=True):
        ts_dir = os.path.join(TRASH, ts)
        if not os.path.isdir(ts_dir):
            continue
        index_path = os.path.join(ts_dir, '.index.json')
        if os.path.exists(index_path):
            try:
                with open(index_path, 'r', encoding='utf-8') as f:
                    entries = json.load(f) or []
                for ent in entries:
                    rel = ent.get('rel') or ''
                    trash_rel = os.path.join(ts, rel).replace('\\\\', '/')
                    abs_path = os.path.join(TRASH, trash_rel)
                    items.append({{
                        "trash_rel": trash_rel,
                        "original_rel": rel,
                        "is_dir": bool(ent.get('is_dir')),
                        "size": ent.get('size', 0),
                        "trashed_at": ts,
                        "exists": os.path.exists(abs_path),
                    }})
            except:
                pass
print(json.dumps({{
    "items": items,
    "home_label": os.path.basename(HOME) or "Home"
}}))
"""
    result = run_remote_python(code)
    return render(request, 'trash.html', {
        'items': result.get('items', []),
        'home_label': result.get('home_label', 'Home'),
    })


# ==========================================================================
# Download — secure file download
# ==========================================================================
def download(request, filename):
    """
    Download file from Jetson Nano over SFTP.
    """
    sftp = get_sftp_client()
    remote_path = os.path.join(get_remote_home(), filename).replace('\\', '/')

    def file_iterator(sftp_file, chunk_size=32768):
        try:
            while True:
                chunk = sftp_file.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            sftp_file.close()
            sftp.ssh_client.close()

    try:
        sftp_file = sftp.open(remote_path, 'rb')
    except IOError:
        sftp.ssh_client.close()
        raise Http404("File not found on remote server")

    response = StreamingHttpResponse(file_iterator(sftp_file))
    response['Content-Type'] = 'application/octet-stream'
    response['Content-Disposition'] = f'attachment; filename="{os.path.basename(remote_path)}"'
    return response


# ==========================================================================
# Edit — file editor with content loading
# ==========================================================================
def edit(request, req_path):
    """
    File editor view on Jetson Nano.
    """
    code = f"""
import os, json
HOME = '{get_remote_home()}'
req_path = '{req_path}'
abs_path = os.path.abspath(os.path.join(HOME, req_path))

if not abs_path.startswith(HOME):
    print(json.dumps({{"error": "Access Denied"}}))
    exit()
if not os.path.exists(abs_path):
    print(json.dumps({{"error": "File not found"}}))
    exit()
if not os.path.isfile(abs_path):
    print(json.dumps({{"error": "Path is not a file"}}))
    exit()

size = os.path.getsize(abs_path)
if size > {django_settings.MAX_EDIT_SIZE}:
    print(json.dumps({{"error": "File too large"}}))
    exit()

is_binary = False
try:
    with open(abs_path, 'rb') as fb:
        sample = fb.read(2048)
    if b'\\x00' in sample:
        is_binary = True
except:
    pass

content = ""
if not is_binary:
    try:
        with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception as e:
        print(json.dumps({{"error": f"Read error: {{e}}"}}))
        exit()

# parent parts
parent_parts = req_path.rstrip('/').split('/')[:-1]
parent_path = '/'.join(parent_parts) if parent_parts else ''

print(json.dumps({{
    "rel_path": req_path,
    "file_name": os.path.basename(abs_path),
    "content": content,
    "mtime": os.path.getmtime(abs_path),
    "is_binary": is_binary,
    "home_label": os.path.basename(HOME) or "Home",
    "parent_path": parent_path
}}))
"""
    result = run_remote_python(code)
    if "error" in result:
        return HttpResponse(result["error"], status=400)

    language = detect_language(result['file_name'])

    return render(request, 'edit.html', {
        'rel_path': result['rel_path'],
        'file_name': result['file_name'],
        'content': result['content'],
        'mtime': result['mtime'],
        'language': language,
        'is_binary': result['is_binary'],
        'home_label': result['home_label'],
        'parent_path': result['parent_path'],
    })


# ==========================================================================
# Download Backup
# ==========================================================================
def download_backup(request):
    """
    Download a specific backup version of a file from Jetson Nano.
    """
    rel_path = request.GET.get('path') or ''
    ts = request.GET.get('ts') or ''

    sftp = get_sftp_client()
    rel_parts = rel_path.replace('\\', '/').split('/')
    file_name = rel_parts[-1] if rel_parts and rel_parts[-1] else "file"
    subdir = os.path.join(get_remote_home(), '.backups', *([p for p in rel_parts[:-1] if p] + [file_name])).replace('\\', '/')
    backup_file = os.path.join(subdir, f"{ts}.bak").replace('\\', '/')

    def file_iterator(sftp_file, chunk_size=32768):
        try:
            while True:
                chunk = sftp_file.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            sftp_file.close()
            sftp.ssh_client.close()

    try:
        sftp_file = sftp.open(backup_file, 'rb')
    except IOError:
        sftp.ssh_client.close()
        raise Http404("Backup not found on remote server")

    response = StreamingHttpResponse(file_iterator(sftp_file))
    response['Content-Type'] = 'application/octet-stream'
    response['Content-Disposition'] = f'attachment; filename="{file_name}.{ts}.bak"'
    return response


# ==========================================================================
# Other views (unchanged)
# ==========================================================================
def system(request):
    return render(request, "system.html")


def logs_view(request):
    from apps.core.models import User
    try:
        users = User.objects.all().order_by('username')
    except Exception:
        users = []
    return render(request, "audit.html", {'users': users})


def logout(request):
    """Logout — clear session and redirect."""
    user_id = request.session.get('user_id')
    username = request.session.get('username')
    if user_id:
        try:
            from apps.core.models import User
            user = User.objects.get(id=user_id)
            _audit_log(request, user, 'LOGOUT', None, f'{username} logged out')
        except Exception:
            pass
    request.session.flush()
    return redirect('web:login')


def _audit_log(request, user, action, target, details):
    """Helper to write an audit log entry."""
    from apps.core.utils import log_audit
    user_id = user.id if user else None
    log_audit(request=request, action=action, target=target, details=details, user_id=user_id)
