import os
import json
import shutil
from datetime import datetime

from django.shortcuts import render, redirect
from django.urls import reverse
from django.http import HttpResponseNotFound, FileResponse, HttpResponse, Http404
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
    """Login page."""
    if request.method == 'POST':
        return redirect('web:dashboard_default')
    return render(request, 'login.html')


def dashboard_default(request):
    """Default dashboard view."""
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
    Ported from Flask app.py lines 640-758.
    """
    req_path = req_path or ''

    # Build absolute path and validate
    requested_dir = os.path.join(HOME, req_path)

    if not is_safe_path(HOME, requested_dir):
        return HttpResponse("Access Denied: Path traversal detected", status=403)

    if not os.path.exists(requested_dir):
        return HttpResponse("Directory not found", status=404)

    if not os.path.isdir(requested_dir):
        return HttpResponse("Path is not a directory", status=400)

    # Build file listing
    files_details = []
    try:
        for item_name in os.listdir(requested_dir):
            item_path = os.path.join(requested_dir, item_name)

            if not is_safe_path(HOME, item_path):
                continue

            item_is_dir = os.path.isdir(item_path)
            stat_info = os.stat(item_path)

            # Build relative path for navigation
            relative_path = os.path.join(req_path, item_name) if req_path else item_name

            files_details.append({
                'name': item_name,
                'is_dir': item_is_dir,
                'size': stat_info.st_size if not item_is_dir else 0,
                'mtime': datetime.fromtimestamp(stat_info.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                'relative_path': relative_path,
                'is_editable': not item_is_dir and is_editable(item_path),
                'is_archive': not item_is_dir and is_archive(item_name),
            })
    except Exception as e:
        print(f"Error listing directory {requested_dir}: {e}")
        return HttpResponse(f"Error reading directory: {e}", status=500)

    # Sort: directories first, then files, alphabetically
    files_details.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))

    # Build breadcrumbs
    breadcrumbs = []
    if req_path:
        parts = req_path.split('/')
        current = ''
        for part in parts:
            if part:
                current = os.path.join(current, part) if current else part
                breadcrumbs.append({'name': part, 'path': current})

    # Compute parent path for the "Go Up" link
    parent_path = None
    if req_path:
        parent = '/'.join(req_path.rstrip('/').split('/')[:-1])
        parent_path = parent if parent else ''

    return render(request, 'files.html', {
        'files': files_details,
        'current_path': req_path,
        'breadcrumbs': breadcrumbs,
        'home_label': os.path.basename(HOME) or 'Home',
        'base_abs': HOME,
        'abs_current': os.path.abspath(requested_dir),
        'rel_current': req_path,
        'max_edit_size': MAX_EDIT_SIZE,
        'parent_path': parent_path,
        'crumb': breadcrumbs[-1] if breadcrumbs else {'path': '', 'name': 'Home'},
    })


# ==========================================================================
# Trash — list soft-deleted items
# ==========================================================================
def trash(request):
    """
    Trash view — reads .index.json from each trash timestamp folder.
    Ported from Flask app.py lines 843-878.
    """
    items = []
    try:
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
                            trash_rel = os.path.join(ts, rel)
                            abs_path = os.path.join(TRASH, trash_rel)
                            items.append({
                                "trash_rel": trash_rel.replace('\\', '/'),
                                "original_rel": rel.replace('\\', '/'),
                                "is_dir": bool(ent.get('is_dir')),
                                "size": ent.get('size', 0),
                                "trashed_at": ts,
                                "exists": os.path.exists(abs_path),
                            })
                    except Exception:
                        continue
    except Exception as e:
        print(f"trash list error: {e}")

    return render(request, 'trash.html', {
        'items': items,
        'home_label': os.path.basename(HOME) or 'Home',
    })


# ==========================================================================
# Download — secure file download
# ==========================================================================
def download(request, filename):
    """
    Download file with Path Traversal protection.
    Ported from Flask app.py lines 760-788.
    """
    file_path = os.path.join(HOME, filename)

    if not is_safe_path(HOME, file_path):
        return HttpResponse("Access Denied: Path traversal detected", status=403)

    if not os.path.exists(file_path):
        raise Http404("File not found")

    if not os.path.isfile(file_path):
        return HttpResponse("Path is not a file", status=400)

    response = FileResponse(open(file_path, 'rb'), as_attachment=True)
    response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
    return response


# ==========================================================================
# Edit — file editor with content loading
# ==========================================================================
def edit(request, req_path):
    """
    File editor view.
    Ported from Flask app.py lines 808-841.
    """
    abs_path = os.path.join(HOME, req_path)

    if not is_safe_path(HOME, abs_path):
        return HttpResponse("Access Denied", status=403)
    if not os.path.exists(abs_path):
        return HttpResponse("File not found", status=404)
    if not os.path.isfile(abs_path):
        return HttpResponse("Path is not a file", status=400)

    size = os.path.getsize(abs_path)
    if size > MAX_EDIT_SIZE:
        return HttpResponse(f"File too large to edit (>{MAX_EDIT_SIZE} bytes)", status=400)

    # Detect binary
    is_binary = False
    try:
        with open(abs_path, 'rb') as fb:
            sample = fb.read(2048)
        if b'\x00' in sample:
            is_binary = True
    except Exception:
        pass

    # Read content
    try:
        with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception:
        return HttpResponse("Unable to read file", status=500)

    mtime = os.path.getmtime(abs_path)
    language = detect_language(abs_path)

    # Compute parent path for breadcrumb
    parent_parts = req_path.rstrip('/').split('/')[:-1]
    parent_path = '/'.join(parent_parts) if parent_parts else ''

    return render(request, 'edit.html', {
        'rel_path': req_path,
        'file_name': os.path.basename(abs_path),
        'content': content,
        'mtime': mtime,
        'language': language,
        'is_binary': is_binary,
        'home_label': os.path.basename(HOME) or 'Home',
        'parent_path': parent_path,
    })


# ==========================================================================
# Download Backup
# ==========================================================================
def download_backup(request):
    """
    Download a specific backup version of a file.
    Ported from Flask app.py lines 790-806.
    """
    rel_path = request.GET.get('path') or ''
    ts = request.GET.get('ts') or ''

    abs_path = os.path.abspath(os.path.join(HOME, rel_path))
    if not is_safe_path(HOME, abs_path):
        return HttpResponse("Access Denied", status=403)

    rel_parts = rel_path.replace('\\', '/').split('/')
    file_name = rel_parts[-1] if rel_parts and rel_parts[-1] else os.path.basename(abs_path)
    subdir = os.path.join(BACKUP, *([p for p in rel_parts[:-1] if p] + [file_name]))
    backup_file = os.path.join(subdir, f'{ts}.bak')

    if not os.path.exists(backup_file):
        raise Http404("Backup not found")

    response = FileResponse(open(backup_file, 'rb'), as_attachment=True)
    response['Content-Disposition'] = f'attachment; filename="{file_name}.{ts}.bak"'
    return response


# ==========================================================================
# Other views (unchanged)
# ==========================================================================
def system(request):
    return render(request, "system.html")


def logs_view(request):
    return render(request, "audit.html")


def logout(request):
    return redirect('web:index')
