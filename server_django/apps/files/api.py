"""
File Management API endpoints.
Ported from legacy Flask app.py API section (lines 1039-1657).

All endpoints return JSON and are registered under /api/ via Django Ninja.
"""
import os
import json
import shutil
import zipfile
import tarfile
from datetime import datetime

from ninja import Router, File
from ninja.files import UploadedFile
from django.conf import settings
from django.http import HttpRequest

from .utils import (
    secure_filename_unicode,
    is_safe_path,
    relpath_within_home,
)

router = Router()

HOME = settings.HOME_DIRECTORY
TRASH = settings.TRASH_DIRECTORY
BACKUP = settings.BACKUP_DIRECTORY


# ────────────────────────────────────────────────────────────────────────────
#  1. POST /check_exists
# ────────────────────────────────────────────────────────────────────────────
@router.post("/check_exists")
def api_check_exists(request: HttpRequest):
    data = json.loads(request.body or '{}')
    filename = data.get('filename')
    path = data.get('path') or ''

    if not filename:
        return {"error": "missing filename"}

    dest_dir = os.path.join(HOME, path)
    if not is_safe_path(HOME, dest_dir):
        return {"error": "invalid path"}

    safe_name = secure_filename_unicode(filename)
    dest_path = os.path.join(dest_dir, safe_name)
    return {"exists": os.path.exists(dest_path)}


# ────────────────────────────────────────────────────────────────────────────
#  2. POST /upload_chunk
# ────────────────────────────────────────────────────────────────────────────
@router.post("/upload_chunk")
def api_upload_chunk(request: HttpRequest):
    file = request.FILES.get('file')
    filename = request.POST.get('filename')
    path = request.POST.get('path') or ''
    chunk_index = int(request.POST.get('chunk_index', 0))
    total_chunks = int(request.POST.get('total_chunks', 1))
    auto_rename = request.POST.get('auto_rename') == 'true'

    if not file or not filename:
        return {"error": "Missing file or filename"}

    dest_dir = os.path.join(HOME, path)
    if not is_safe_path(HOME, dest_dir):
        return {"error": "Invalid path"}
    if not os.path.exists(dest_dir):
        return {"error": "Directory not found"}

    safe_filename = secure_filename_unicode(filename)
    dest_path = os.path.join(dest_dir, safe_filename)

    if not is_safe_path(HOME, dest_path):
        return {"error": "Invalid destination"}

    try:
        if chunk_index == 0:
            # Auto-rename if file exists and requested
            if auto_rename and os.path.exists(dest_path):
                base, ext = os.path.splitext(safe_filename)
                counter = 1
                while os.path.exists(dest_path):
                    new_name = f"{base} ({counter}){ext}"
                    dest_path = os.path.join(dest_dir, new_name)
                    counter += 1
                safe_filename = os.path.basename(dest_path)

            with open(dest_path, 'wb') as f:
                for chunk in file.chunks():
                    f.write(chunk)
        else:
            with open(dest_path, 'ab') as f:
                for chunk in file.chunks():
                    f.write(chunk)

        return {"ok": True, "chunk_index": chunk_index, "final_filename": safe_filename}
    except Exception as e:
        return {"error": str(e)}


# ────────────────────────────────────────────────────────────────────────────
#  3. POST /save
# ────────────────────────────────────────────────────────────────────────────
@router.post("/save")
def api_save(request: HttpRequest):
    data = json.loads(request.body or '{}')
    rel_path = data.get('path') or ''
    content = data.get('content') or ''
    client_mtime = data.get('mtime')
    force = bool(data.get('force'))

    abs_path = os.path.abspath(os.path.join(HOME, rel_path))
    if not is_safe_path(HOME, abs_path):
        return {"error": "invalid path"}
    if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
        return {"error": "not found"}

    encoded = content.encode('utf-8', errors='replace')
    if len(encoded) > settings.MAX_EDIT_SIZE:
        return {"error": "content too large"}

    current_mtime = os.path.getmtime(abs_path)

    try:
        # Conflict detection
        if client_mtime is not None and not force:
            try:
                if float(client_mtime) != float(current_mtime):
                    return {"error": "conflict", "code": "conflict", "current_mtime": current_mtime}
            except Exception:
                pass

        # Create backup before saving
        ts = datetime.now().strftime('%Y%m%d%H%M%S%f')
        try:
            rel_parts = rel_path.replace('\\', '/').split('/')
            file_name = rel_parts[-1] if rel_parts and rel_parts[-1] else os.path.basename(abs_path)
            subdir = os.path.join(BACKUP, *([p for p in rel_parts[:-1] if p] + [file_name]))
            os.makedirs(subdir, exist_ok=True)
            backup_path = os.path.join(subdir, f'{ts}.bak')
            shutil.copy2(abs_path, backup_path)

            # Enforce retention
            names = sorted(n for n in os.listdir(subdir) if n.endswith('.bak'))
            excess = len(names) - settings.BACKUP_RETENTION
            if excess > 0:
                for old in names[:excess]:
                    try:
                        os.remove(os.path.join(subdir, old))
                    except Exception:
                        pass
        except Exception:
            pass

        # Write content
        with open(abs_path, 'w', encoding='utf-8', errors='replace') as f:
            f.write(content)

        new_mtime = os.path.getmtime(abs_path)
        return {"ok": True, "mtime": new_mtime}
    except Exception as e:
        return {"error": str(e)}


# ────────────────────────────────────────────────────────────────────────────
#  4. POST /delete — single file/folder (soft or hard delete)
# ────────────────────────────────────────────────────────────────────────────
@router.post("/delete")
def api_delete(request: HttpRequest):
    data = json.loads(request.body or '{}')
    rel_path = data.get('path')
    permanent = bool(data.get('permanent'))

    if not rel_path:
        return {"error": "missing path"}

    src_abs = os.path.abspath(os.path.join(HOME, rel_path))
    if not is_safe_path(HOME, src_abs):
        return {"error": "invalid path"}

    # Protect system folders
    if (src_abs == TRASH or src_abs.startswith(TRASH + os.sep) or
            src_abs == BACKUP or src_abs.startswith(BACKUP + os.sep)):
        return {"error": "cannot delete inside system folders (.trash/.backups) here"}

    if not os.path.exists(src_abs):
        return {"error": "not found"}

    try:
        if permanent:
            if os.path.isdir(src_abs):
                shutil.rmtree(src_abs)
            else:
                os.remove(src_abs)
            return {"ok": True, "permanent": True}

        # Soft delete — move to trash
        ts = datetime.now().strftime('%Y%m%d%H%M%S%f')
        dest_abs = os.path.join(TRASH, ts, rel_path)
        os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
        shutil.move(src_abs, dest_abs)

        # Write index
        _update_trash_index(ts, rel_path, dest_abs)
        return {"ok": True, "permanent": False}
    except Exception as e:
        return {"error": str(e)}


# ────────────────────────────────────────────────────────────────────────────
#  5. POST /delete_batch
# ────────────────────────────────────────────────────────────────────────────
@router.post("/delete_batch")
def api_delete_batch(request: HttpRequest):
    data = json.loads(request.body or '{}')
    paths = data.get('paths') or []
    permanent = bool(data.get('permanent'))

    if not isinstance(paths, list) or not paths:
        return {"error": "missing paths"}

    moved = 0
    removed = 0
    ts = None if permanent else datetime.now().strftime('%Y%m%d%H%M%S%f')

    try:
        for rel_path in paths:
            if not rel_path:
                continue
            src_abs = os.path.abspath(os.path.join(HOME, rel_path))
            if not is_safe_path(HOME, src_abs):
                continue
            if (src_abs == TRASH or src_abs.startswith(TRASH + os.sep) or
                    src_abs == BACKUP or src_abs.startswith(BACKUP + os.sep)):
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
                    dest_abs = os.path.join(TRASH, ts, rel_path)
                    os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
                    shutil.move(src_abs, dest_abs)
                    moved += 1
                    _update_trash_index(ts, rel_path, dest_abs)
                except Exception:
                    pass

        return {"ok": True, "moved": moved, "removed": removed, "permanent": permanent}
    except Exception as e:
        return {"error": str(e)}


# ────────────────────────────────────────────────────────────────────────────
#  6. POST /zip
# ────────────────────────────────────────────────────────────────────────────
@router.post("/zip")
def api_zip(request: HttpRequest):
    data = json.loads(request.body or '{}')
    paths = data.get('paths') or []
    current_rel = data.get('current_path') or ''

    if not paths:
        return {"error": "No files selected"}

    current_abs = os.path.join(HOME, current_rel)
    if not is_safe_path(HOME, current_abs):
        return {"error": "Invalid path"}

    # Smart naming
    if len(paths) == 1:
        item_name = os.path.basename(paths[0])
        full_item_path = os.path.join(HOME, paths[0])
        if os.path.isfile(full_item_path):
            base_name, _ = os.path.splitext(item_name)
        else:
            base_name = item_name
    else:
        base_name = f"archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

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
                abs_item = os.path.join(HOME, rel_item)
                if not is_safe_path(HOME, abs_item) or not os.path.exists(abs_item):
                    continue
                if os.path.isfile(abs_item):
                    arcname = os.path.relpath(abs_item, current_abs)
                    zipf.write(abs_item, arcname)
                else:
                    for root, dirs, files in os.walk(abs_item):
                        for f in files:
                            fpath = os.path.join(root, f)
                            arcname = os.path.relpath(fpath, current_abs)
                            zipf.write(fpath, arcname)

        return {"ok": True, "zip_name": zip_name}
    except Exception as e:
        return {"error": str(e)}


# ────────────────────────────────────────────────────────────────────────────
#  7. POST /unzip
# ────────────────────────────────────────────────────────────────────────────
@router.post("/unzip")
def api_unzip(request: HttpRequest):
    data = json.loads(request.body or '{}')
    rel_path = data.get('path')

    if not rel_path:
        return {"error": "Missing path"}

    abs_path = os.path.join(HOME, rel_path)
    if not is_safe_path(HOME, abs_path):
        return {"error": "Invalid path"}
    if not os.path.isfile(abs_path):
        return {"error": "File not found"}

    lower_name = abs_path.lower()
    extract_dir = os.path.dirname(abs_path)

    try:
        if lower_name.endswith('.zip'):
            if not zipfile.is_zipfile(abs_path):
                return {"error": "Invalid zip file"}
            with zipfile.ZipFile(abs_path, 'r') as zipf:
                # Zip Slip protection
                for member in zipf.namelist():
                    target = os.path.join(extract_dir, member)
                    if not is_safe_path(extract_dir, target):
                        return {"error": f"Malicious zip entry: {member}"}
                zipf.extractall(extract_dir)

        elif lower_name.endswith(('.tar', '.tar.gz', '.tgz')):
            if not tarfile.is_tarfile(abs_path):
                return {"error": "Invalid tar file"}
            with tarfile.open(abs_path, 'r:*') as tar:
                for member in tar.getmembers():
                    target = os.path.join(extract_dir, member.name)
                    if not is_safe_path(extract_dir, target):
                        return {"error": f"Malicious tar entry: {member.name}"}
                    if member.name.startswith('/') or '..' in member.name:
                        return {"error": f"Malicious tar path: {member.name}"}
                tar.extractall(extract_dir)
        else:
            return {"error": "Unsupported archive format"}

        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


# ────────────────────────────────────────────────────────────────────────────
#  8. POST /trash/empty
# ────────────────────────────────────────────────────────────────────────────
@router.post("/trash/empty")
def api_trash_empty(request: HttpRequest):
    deleted = 0
    try:
        if os.path.exists(TRASH):
            for name in os.listdir(TRASH):
                path = os.path.join(TRASH, name)
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                    deleted += 1
                except Exception:
                    pass
        return {"ok": True, "deleted": deleted}
    except Exception as e:
        return {"error": str(e)}


# ────────────────────────────────────────────────────────────────────────────
#  9. POST /trash/restore
# ────────────────────────────────────────────────────────────────────────────
@router.post("/trash/restore")
def api_trash_restore(request: HttpRequest):
    data = json.loads(request.body or '{}')
    trash_rel = data.get('trash_rel')

    if not trash_rel:
        return {"error": "missing path"}

    parts = trash_rel.replace('\\', '/').split('/')
    if len(parts) < 2:
        return {"error": "invalid trash path"}

    ts = parts[0]
    rel = '/'.join(parts[1:])
    src_abs = os.path.join(TRASH, ts, *rel.split('/'))

    if not is_safe_path(TRASH, src_abs):
        return {"error": "invalid path"}
    if not os.path.exists(src_abs):
        return {"error": "not found"}

    dest_abs = os.path.join(HOME, *rel.split('/'))
    if not is_safe_path(HOME, dest_abs):
        return {"error": "invalid dest"}

    try:
        os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
        final_dest = dest_abs
        if os.path.exists(final_dest):
            final_dest = dest_abs + f'.restored.{ts}'
        shutil.move(src_abs, final_dest)

        # Update index
        _remove_from_trash_index(ts, rel)
        return {"ok": True, "restored_to": final_dest}
    except Exception as e:
        return {"error": str(e)}


# ────────────────────────────────────────────────────────────────────────────
# 10. POST /trash/delete_permanent
# ────────────────────────────────────────────────────────────────────────────
@router.post("/trash/delete_permanent")
def api_trash_delete_permanent(request: HttpRequest):
    data = json.loads(request.body or '{}')
    trash_rel = data.get('trash_rel')

    if not trash_rel:
        return {"error": "missing path"}

    parts = trash_rel.replace('\\', '/').split('/')
    if len(parts) < 2:
        return {"error": "invalid trash path"}

    ts = parts[0]
    rel = '/'.join(parts[1:])
    target_abs = os.path.join(TRASH, ts, *rel.split('/'))

    if not is_safe_path(TRASH, target_abs):
        return {"error": "invalid path"}
    if not os.path.exists(target_abs):
        return {"error": "not found"}

    try:
        if os.path.isdir(target_abs):
            shutil.rmtree(target_abs)
        else:
            os.remove(target_abs)

        _remove_from_trash_index(ts, rel)
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


# ────────────────────────────────────────────────────────────────────────────
# 11. GET /backups
# ────────────────────────────────────────────────────────────────────────────
@router.get("/backups")
def api_backups(request: HttpRequest, path: str = ''):
    abs_path = os.path.abspath(os.path.join(HOME, path))
    if not is_safe_path(HOME, abs_path):
        return {"error": "invalid path"}

    rel_parts = path.replace('\\', '/').split('/')
    file_name = rel_parts[-1] if rel_parts and rel_parts[-1] else os.path.basename(abs_path)
    subdir = os.path.join(BACKUP, *([p for p in rel_parts[:-1] if p] + [file_name]))

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
                        "mtime": os.path.getmtime(p),
                    })
                except Exception:
                    pass
        items.sort(key=lambda x: x['ts'], reverse=True)
        return {"ok": True, "items": items}
    except Exception as e:
        return {"error": str(e)}


# ────────────────────────────────────────────────────────────────────────────
# 12. POST /restore_backup
# ────────────────────────────────────────────────────────────────────────────
@router.post("/restore_backup")
def api_restore_backup(request: HttpRequest):
    data = json.loads(request.body or '{}')
    rel_path = data.get('path') or ''
    ts = data.get('ts') or ''

    abs_path = os.path.abspath(os.path.join(HOME, rel_path))
    if not is_safe_path(HOME, abs_path):
        return {"error": "invalid path"}
    if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
        return {"error": "not found"}

    rel_parts = rel_path.replace('\\', '/').split('/')
    file_name = rel_parts[-1] if rel_parts and rel_parts[-1] else os.path.basename(abs_path)
    subdir = os.path.join(BACKUP, *([p for p in rel_parts[:-1] if p] + [file_name]))
    backup_file = os.path.join(subdir, f'{ts}.bak')

    if not os.path.exists(backup_file):
        return {"error": "backup not found"}

    try:
        # Auto-backup current before restoring
        ts2 = datetime.now().strftime('%Y%m%d%H%M%S%f')
        try:
            os.makedirs(subdir, exist_ok=True)
            shutil.copy2(abs_path, os.path.join(subdir, f'{ts2}.bak'))
        except Exception:
            pass

        shutil.copy2(backup_file, abs_path)
        new_mtime = os.path.getmtime(abs_path)
        return {"ok": True, "mtime": new_mtime}
    except Exception as e:
        return {"error": str(e)}


# ────────────────────────────────────────────────────────────────────────────
# 13. GET /backup_content
# ────────────────────────────────────────────────────────────────────────────
@router.get("/backup_content")
def api_backup_content(request: HttpRequest, path: str = '', ts: str = ''):
    abs_path = os.path.abspath(os.path.join(HOME, path))
    if not is_safe_path(HOME, abs_path):
        return {"error": "invalid path"}

    rel_parts = path.replace('\\', '/').split('/')
    file_name = rel_parts[-1] if rel_parts and rel_parts[-1] else os.path.basename(abs_path)
    subdir = os.path.join(BACKUP, *([p for p in rel_parts[:-1] if p] + [file_name]))
    backup_file = os.path.join(subdir, f'{ts}.bak')

    if not os.path.exists(backup_file):
        return {"error": "not found"}

    if os.path.getsize(backup_file) > settings.MAX_EDIT_SIZE:
        return {"ok": True, "binary": True}

    # Binary heuristic
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
        return {"error": str(e)}


# ────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ────────────────────────────────────────────────────────────────────────────
def _update_trash_index(ts: str, rel_path: str, dest_abs: str):
    """Add an entry to the trash timestamp's .index.json."""
    try:
        index_path = os.path.join(TRASH, ts, '.index.json')
        items = []
        if os.path.exists(index_path):
            with open(index_path, 'r', encoding='utf-8') as f:
                items = json.load(f) or []
        items.append({
            "rel": rel_path,
            "is_dir": os.path.isdir(dest_abs),
            "size": os.path.getsize(dest_abs) if os.path.isfile(dest_abs) else 0,
            "trashed_at": ts,
        })
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False)
    except Exception:
        pass


def _remove_from_trash_index(ts: str, rel: str):
    """Remove an entry from the trash timestamp's .index.json."""
    try:
        index_path = os.path.join(TRASH, ts, '.index.json')
        if os.path.exists(index_path):
            with open(index_path, 'r', encoding='utf-8') as f:
                entries = json.load(f) or []
            entries = [e for e in entries if (e.get('rel') or '') != rel]
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(entries, f, ensure_ascii=False)
    except Exception:
        pass
