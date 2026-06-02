"""
File Management API endpoints.
Redirected to execute remotely on Jetson Nano at 172.16.1.186 via SFTP/SSH.
"""
import os
import json
from datetime import datetime

from ninja import Router
from django.conf import settings
from django.http import HttpRequest

from .utils import (
    secure_filename_unicode,
)
from .remote_helper import (
    get_remote_home,
    run_remote_python,
    run_ssh_cmd,
    get_sftp_client,
)
from apps.core.utils import log_audit

router = Router()

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

    safe_name = secure_filename_unicode(filename)
    
    code = f"""
import os, json
HOME = '{get_remote_home()}'
dest_dir = os.path.join(HOME, '{path}')
dest_path = os.path.join(dest_dir, '{safe_name}')
print(json.dumps({{"exists": os.path.exists(dest_path)}}))
"""
    return run_remote_python(code)


# ────────────────────────────────────────────────────────────────────────────
#  2. POST /upload_chunk
# ────────────────────────────────────────────────────────────────────────────
@router.post("/upload_chunk")
def api_upload_chunk(request: HttpRequest):
    file = request.FILES.get('file')
    filename = request.POST.get('filename')
    path = request.POST.get('path') or ''
    chunk_index = int(request.POST.get('chunk_index', 0))
    auto_rename = request.POST.get('auto_rename') == 'true'

    if not file or not filename:
        return {"error": "Missing file or filename"}

    safe_filename = secure_filename_unicode(filename)
    
    sftp = get_sftp_client()
    try:
        dest_dir = os.path.join(get_remote_home(), path).replace('\\', '/')
        try:
            sftp.stat(dest_dir)
        except IOError:
            run_ssh_cmd(f"mkdir -p '{dest_dir}'")

        dest_path = os.path.join(dest_dir, safe_filename).replace('\\', '/')

        if chunk_index == 0:
            if auto_rename:
                try:
                    sftp.stat(dest_path)
                    base, ext = os.path.splitext(safe_filename)
                    counter = 1
                    while True:
                        new_name = f"{base} ({counter}){ext}"
                        new_path = os.path.join(dest_dir, new_name).replace('\\', '/')
                        try:
                            sftp.stat(new_path)
                            counter += 1
                        except IOError:
                            dest_path = new_path
                            safe_filename = new_name
                            break
                except IOError:
                    pass
            f = sftp.open(dest_path, 'wb')
        else:
            f = sftp.open(dest_path, 'ab')

        for chunk in file.chunks():
            f.write(chunk)
        f.close()
        if chunk_index == 0:
            log_audit(request, "UPLOAD_FILE", target=os.path.join(path, safe_filename).replace('\\', '/'), details=f"Uploaded file chunk 0 for {safe_filename} to {path}")
        return {"ok": True, "chunk_index": chunk_index, "final_filename": safe_filename}
    except Exception as e:
        return {"error": str(e)}
    finally:
        sftp.ssh_client.close()


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

    code = f"""
import os, datetime, shutil, json
HOME = '{get_remote_home()}'
BACKUP = os.path.join(HOME, '.backups')
rel_path = '{rel_path}'
content = {repr(content)}
client_mtime = {client_mtime if client_mtime is not None else 'None'}
force = {force}
max_size = {settings.MAX_EDIT_SIZE}

abs_path = os.path.abspath(os.path.join(HOME, rel_path))
if not abs_path.startswith(HOME):
    print(json.dumps({{"error": "invalid path"}}))
    exit()
if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
    print(json.dumps({{"error": "not found"}}))
    exit()

encoded = content.encode('utf-8', errors='replace')
if len(encoded) > max_size:
    print(json.dumps({{"error": "content too large"}}))
    exit()

current_mtime = os.path.getmtime(abs_path)
if client_mtime is not None and not force:
    if abs(float(client_mtime) - float(current_mtime)) > 0.01:
        print(json.dumps({{"error": "conflict", "code": "conflict", "current_mtime": current_mtime}}))
        exit()

# Backup
ts = datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')
try:
    rel_parts = rel_path.replace('\\\\', '/').split('/')
    file_name = rel_parts[-1] if rel_parts and rel_parts[-1] else os.path.basename(abs_path)
    subdir = os.path.join(BACKUP, *([p for p in rel_parts[:-1] if p] + [file_name]))
    os.makedirs(subdir, exist_ok=True)
    backup_path = os.path.join(subdir, f'{{ts}}.bak')
    shutil.copy2(abs_path, backup_path)
    
    names = sorted(n for n in os.listdir(subdir) if n.endswith('.bak'))
    excess = len(names) - {settings.BACKUP_RETENTION}
    if excess > 0:
        for old in names[:excess]:
            try:
                os.remove(os.path.join(subdir, old))
            except Exception:
                pass
except Exception:
    pass

with open(abs_path, 'w', encoding='utf-8', errors='replace') as f:
    f.write(content)

new_mtime = os.path.getmtime(abs_path)
print(json.dumps({{"ok": True, "mtime": new_mtime}}))
"""
    res = run_remote_python(code)
    if isinstance(res, dict) and res.get("ok"):
        log_audit(request, "SAVE_FILE", target=rel_path, details=f"Saved content to file: {rel_path}")
    return res


# ────────────────────────────────────────────────────────────────────────────
#  4. POST /delete
# ────────────────────────────────────────────────────────────────────────────
@router.post("/delete")
def api_delete(request: HttpRequest):
    data = json.loads(request.body or '{}')
    rel_path = data.get('path')
    permanent = bool(data.get('permanent'))

    if not rel_path:
        return {"error": "missing path"}

    code = f"""
import os, shutil, json, datetime
HOME = '{get_remote_home()}'
TRASH = os.path.join(HOME, '.trash')
BACKUP = os.path.join(HOME, '.backups')
rel_path = '{rel_path}'
permanent = {permanent}

src_abs = os.path.abspath(os.path.join(HOME, rel_path))
if not src_abs.startswith(HOME):
    print(json.dumps({{"error": "invalid path"}}))
    exit()

if src_abs == TRASH or src_abs.startswith(TRASH + os.sep) or src_abs == BACKUP or src_abs.startswith(BACKUP + os.sep):
    print(json.dumps({{"error": "cannot delete inside system folders"}}))
    exit()

if not os.path.exists(src_abs):
    print(json.dumps({{"error": "not found"}}))
    exit()

try:
    if permanent:
        if os.path.isdir(src_abs):
            shutil.rmtree(src_abs)
        else:
            os.remove(src_abs)
        print(json.dumps({{"ok": True, "permanent": True}}))
    else:
        ts = datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')
        dest_abs = os.path.join(TRASH, ts, rel_path)
        os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
        shutil.move(src_abs, dest_abs)
        
        index_path = os.path.join(TRASH, ts, '.index.json')
        items = []
        if os.path.exists(index_path):
            with open(index_path, 'r', encoding='utf-8') as f:
                items = json.load(f) or []
        items.append({{
            "rel": rel_path,
            "is_dir": os.path.isdir(dest_abs),
            "size": os.path.getsize(dest_abs) if os.path.isfile(dest_abs) else 0,
            "trashed_at": ts,
        }})
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False)
            
        print(json.dumps({{"ok": True, "permanent": False}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
    res = run_remote_python(code)
    if isinstance(res, dict) and res.get("ok"):
        action = "DELETE_PERMANENT" if permanent else "TRASH_FILE"
        log_audit(request, action, target=rel_path, details=f"Deleted file/folder: {rel_path} (permanent={permanent})")
    return res


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

    code = f"""
import os, shutil, json, datetime
HOME = '{get_remote_home()}'
TRASH = os.path.join(HOME, '.trash')
BACKUP = os.path.join(HOME, '.backups')
paths = {paths}
permanent = {permanent}

moved = 0
removed = 0
ts = datetime.datetime.now().strftime('%Y%m%d%H%M%S%f') if not permanent else None

for rel_path in paths:
    if not rel_path:
        continue
    src_abs = os.path.abspath(os.path.join(HOME, rel_path))
    if not src_abs.startswith(HOME):
        continue
    if src_abs == TRASH or src_abs.startswith(TRASH + os.sep) or src_abs == BACKUP or src_abs.startswith(BACKUP + os.sep):
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
        except:
            pass
    else:
        try:
            dest_abs = os.path.join(TRASH, ts, rel_path)
            os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
            shutil.move(src_abs, dest_abs)
            moved += 1
            
            index_path = os.path.join(TRASH, ts, '.index.json')
            items = []
            if os.path.exists(index_path):
                with open(index_path, 'r', encoding='utf-8') as f:
                    items = json.load(f) or []
            items.append({{
                "rel": rel_path,
                "is_dir": os.path.isdir(dest_abs),
                "size": os.path.getsize(dest_abs) if os.path.isfile(dest_abs) else 0,
                "trashed_at": ts,
            }})
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(items, f, ensure_ascii=False)
        except:
            pass

print(json.dumps({{"ok": True, "moved": moved, "removed": removed, "permanent": permanent}}))
"""
    res = run_remote_python(code)
    if isinstance(res, dict) and res.get("ok"):
        action = "DELETE_BATCH_PERMANENT" if permanent else "TRASH_BATCH"
        log_audit(request, action, target=", ".join(paths), details=f"Batch deleted/trashed: {len(paths)} items (moved={res.get('moved')}, removed={res.get('removed')}, permanent={permanent})")
    return res


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

    code = f"""
import os, zipfile, json, datetime
HOME = '{get_remote_home()}'
paths = {paths}
current_rel = '{current_rel}'

current_abs = os.path.join(HOME, current_rel)
if not current_abs.startswith(HOME):
    print(json.dumps({{"error": "Invalid path"}}))
    exit()

if len(paths) == 1:
    item_name = os.path.basename(paths[0])
    full_item_path = os.path.join(HOME, paths[0])
    if os.path.isfile(full_item_path):
        base_name, _ = os.path.splitext(item_name)
    else:
        base_name = item_name
else:
    base_name = f"archive_{{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}}"

zip_name = f"{{base_name}}.zip"
zip_path = os.path.join(current_abs, zip_name)
counter = 1
while os.path.exists(zip_path):
    zip_name = f"{{base_name}} ({{counter}}).zip"
    zip_path = os.path.join(current_abs, zip_name)
    counter += 1

try:
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for rel_item in paths:
            abs_item = os.path.join(HOME, rel_item)
            if not abs_item.startswith(HOME) or not os.path.exists(abs_item):
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
    print(json.dumps({{"ok": True, "zip_name": zip_name}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
    res = run_remote_python(code)
    if isinstance(res, dict) and res.get("ok"):
        log_audit(request, "ZIP_FILES", target=res.get("zip_name"), details=f"Zipped files: {', '.join(paths)} into {res.get('zip_name')}")
    return res


# ────────────────────────────────────────────────────────────────────────────
#  7. POST /unzip
# ────────────────────────────────────────────────────────────────────────────
@router.post("/unzip")
def api_unzip(request: HttpRequest):
    data = json.loads(request.body or '{}')
    rel_path = data.get('path')

    if not rel_path:
        return {"error": "Missing path"}

    code = f"""
import os, zipfile, tarfile, json
HOME = '{get_remote_home()}'
rel_path = '{rel_path}'

abs_path = os.path.join(HOME, rel_path)
if not abs_path.startswith(HOME) or not os.path.isfile(abs_path):
    print(json.dumps({{"error": "Invalid file"}}))
    exit()

lower_name = abs_path.lower()
extract_dir = os.path.dirname(abs_path)

try:
    if lower_name.endswith('.zip'):
        if not zipfile.is_zipfile(abs_path):
            print(json.dumps({{"error": "Invalid zip file"}}))
            exit()
        with zipfile.ZipFile(abs_path, 'r') as zipf:
            for member in zipf.namelist():
                target = os.path.join(extract_dir, member)
                if not os.path.abspath(target).startswith(extract_dir):
                    print(json.dumps({{"error": "Malicious zip entry"}}))
                    exit()
            zipf.extractall(extract_dir)

    elif lower_name.endswith(('.tar', '.tar.gz', '.tgz')):
        if not tarfile.is_tarfile(abs_path):
            print(json.dumps({{"error": "Invalid tar file"}}))
            exit()
        with tarfile.open(abs_path, 'r:*') as tar:
            for member in tar.getmembers():
                target = os.path.join(extract_dir, member.name)
                if not os.path.abspath(target).startswith(extract_dir):
                    print(json.dumps({{"error": "Malicious tar entry"}}))
                    exit()
            tar.extractall(extract_dir)
    else:
        print(json.dumps({{"error": "Unsupported archive format"}}))
        exit()

    print(json.dumps({{"ok": True}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
    res = run_remote_python(code)
    if isinstance(res, dict) and res.get("ok"):
        log_audit(request, "UNZIP_FILE", target=rel_path, details=f"Extracted archive: {rel_path}")
    return res


# ────────────────────────────────────────────────────────────────────────────
#  8. POST /trash/empty
# ────────────────────────────────────────────────────────────────────────────
@router.post("/trash/empty")
def api_trash_empty(request: HttpRequest):
    code = f"""
import os, shutil, json
HOME = '{get_remote_home()}'
TRASH = os.path.join(HOME, '.trash')
deleted = 0
if os.path.exists(TRASH):
    for name in os.listdir(TRASH):
        path = os.path.join(TRASH, name)
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            deleted += 1
        except:
            pass
print(json.dumps({{"ok": True, "deleted": deleted}}))
"""
    res = run_remote_python(code)
    if isinstance(res, dict) and res.get("ok"):
        log_audit(request, "EMPTY_TRASH", target=".trash", details=f"Successfully emptied trash, deleted {res.get('deleted')} items")
    return res


# ────────────────────────────────────────────────────────────────────────────
#  9. POST /trash/restore
# ────────────────────────────────────────────────────────────────────────────
@router.post("/trash/restore")
def api_trash_restore(request: HttpRequest):
    data = json.loads(request.body or '{}')
    trash_rel = data.get('trash_rel')

    if not trash_rel:
        return {"error": "missing path"}

    code = f"""
import os, json, shutil
HOME = '{get_remote_home()}'
TRASH = os.path.join(HOME, '.trash')
trash_rel = '{trash_rel}'

parts = trash_rel.replace('\\\\', '/').split('/')
if len(parts) < 2:
    print(json.dumps({{"error": "invalid trash path"}}))
    exit()

ts = parts[0]
rel = '/'.join(parts[1:])
src_abs = os.path.join(TRASH, ts, *rel.split('/'))

if not src_abs.startswith(TRASH) or not os.path.exists(src_abs):
    print(json.dumps({{"error": "not found"}}))
    exit()

dest_abs = os.path.join(HOME, *rel.split('/'))
if not dest_abs.startswith(HOME):
    print(json.dumps({{"error": "invalid dest"}}))
    exit()

try:
    os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
    final_dest = dest_abs
    if os.path.exists(final_dest):
        final_dest = dest_abs + f'.restored.{{ts}}'
    shutil.move(src_abs, final_dest)

    # remove from index
    index_path = os.path.join(TRASH, ts, '.index.json')
    if os.path.exists(index_path):
        with open(index_path, 'r', encoding='utf-8') as f:
            entries = json.load(f) or []
        entries = [e for e in entries if e.get('rel') != rel]
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(entries, f, ensure_ascii=False)
            
    print(json.dumps({{"ok": True, "restored_to": final_dest}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
    res = run_remote_python(code)
    if isinstance(res, dict) and res.get("ok"):
        log_audit(request, "RESTORE_FILE", target=trash_rel, details=f"Restored file/folder {trash_rel} to {res.get('restored_to')}")
    return res


# ────────────────────────────────────────────────────────────────────────────
# 10. POST /trash/delete_permanent
# ────────────────────────────────────────────────────────────────────────────
@router.post("/trash/delete_permanent")
def api_trash_delete_permanent(request: HttpRequest):
    data = json.loads(request.body or '{}')
    trash_rel = data.get('trash_rel')

    if not trash_rel:
        return {"error": "missing path"}

    code = f"""
import os, json, shutil
HOME = '{get_remote_home()}'
TRASH = os.path.join(HOME, '.trash')
trash_rel = '{trash_rel}'

parts = trash_rel.replace('\\\\', '/').split('/')
if len(parts) < 2:
    print(json.dumps({{"error": "invalid trash path"}}))
    exit()

ts = parts[0]
rel = '/'.join(parts[1:])
target_abs = os.path.join(TRASH, ts, *rel.split('/'))

if not target_abs.startswith(TRASH) or not os.path.exists(target_abs):
    print(json.dumps({{"error": "not found"}}))
    exit()

try:
    if os.path.isdir(target_abs):
        shutil.rmtree(target_abs)
    else:
        os.remove(target_abs)

    index_path = os.path.join(TRASH, ts, '.index.json')
    if os.path.exists(index_path):
        with open(index_path, 'r', encoding='utf-8') as f:
            entries = json.load(f) or []
        entries = [e for e in entries if e.get('rel') != rel]
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(entries, f, ensure_ascii=False)
            
    print(json.dumps({{"ok": True}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
    res = run_remote_python(code)
    if isinstance(res, dict) and res.get("ok"):
        log_audit(request, "DELETE_PERMANENT", target=trash_rel, details=f"Permanently deleted trash item: {trash_rel}")
    return res


# ────────────────────────────────────────────────────────────────────────────
# 11. GET /backups
# ────────────────────────────────────────────────────────────────────────────
@router.get("/backups")
def api_backups(request: HttpRequest, path: str = ''):
    code = f"""
import os, json
HOME = '{get_remote_home()}'
BACKUP = os.path.join(HOME, '.backups')
path = '{path}'

abs_path = os.path.abspath(os.path.join(HOME, path))
if not abs_path.startswith(HOME):
    print(json.dumps({{"error": "invalid path"}}))
    exit()

rel_parts = path.replace('\\\\', '/').split('/')
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
                items.append({{
                    "ts": n[:-4],
                    "size": os.path.getsize(p),
                    "mtime": os.path.getmtime(p),
                }})
            except:
                pass
    items.sort(key=lambda x: x['ts'], reverse=True)
    print(json.dumps({{"ok": True, "items": items}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
    return run_remote_python(code)


# ────────────────────────────────────────────────────────────────────────────
# 12. POST /restore_backup
# ────────────────────────────────────────────────────────────────────────────
@router.post("/restore_backup")
def api_restore_backup(request: HttpRequest):
    data = json.loads(request.body or '{}')
    rel_path = data.get('path') or ''
    ts = data.get('ts') or ''

    code = f"""
import os, json, shutil, datetime
HOME = '{get_remote_home()}'
BACKUP = os.path.join(HOME, '.backups')
rel_path = '{rel_path}'
ts = '{ts}'

abs_path = os.path.abspath(os.path.join(HOME, rel_path))
if not abs_path.startswith(HOME) or not os.path.exists(abs_path):
    print(json.dumps({{"error": "invalid path"}}))
    exit()

rel_parts = rel_path.replace('\\\\', '/').split('/')
file_name = rel_parts[-1] if rel_parts and rel_parts[-1] else os.path.basename(abs_path)
subdir = os.path.join(BACKUP, *([p for p in rel_parts[:-1] if p] + [file_name]))
backup_file = os.path.join(subdir, f'{{ts}}.bak')

if not os.path.exists(backup_file):
    print(json.dumps({{"error": "backup not found"}}))
    exit()

try:
    ts2 = datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')
    os.makedirs(subdir, exist_ok=True)
    shutil.copy2(abs_path, os.path.join(subdir, f'{{ts2}}.bak'))
    shutil.copy2(backup_file, abs_path)
    new_mtime = os.path.getmtime(abs_path)
    print(json.dumps({{"ok": True, "mtime": new_mtime}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
    res = run_remote_python(code)
    if isinstance(res, dict) and res.get("ok"):
        log_audit(request, "RESTORE_BACKUP", target=rel_path, details=f"Restored backup version {ts} for file: {rel_path}")
    return res


# ────────────────────────────────────────────────────────────────────────────
# 13. GET /backup_content
# ────────────────────────────────────────────────────────────────────────────
@router.get("/backup_content")
def api_backup_content(request: HttpRequest, path: str = '', ts: str = ''):
    code = f"""
import os, json
HOME = '{get_remote_home()}'
BACKUP = os.path.join(HOME, '.backups')
path = '{path}'
ts = '{ts}'

abs_path = os.path.abspath(os.path.join(HOME, path))
if not abs_path.startswith(HOME):
    print(json.dumps({{"error": "invalid path"}}))
    exit()

rel_parts = path.replace('\\\\', '/').split('/')
file_name = rel_parts[-1] if rel_parts and rel_parts[-1] else os.path.basename(abs_path)
subdir = os.path.join(BACKUP, *([p for p in rel_parts[:-1] if p] + [file_name]))
backup_file = os.path.join(subdir, f'{{ts}}.bak')

if not os.path.exists(backup_file):
    print(json.dumps({{"error": "not found"}}))
    exit()

if os.path.getsize(backup_file) > {settings.MAX_EDIT_SIZE}:
    print(json.dumps({{"ok": True, "binary": True}}))
    exit()

# Binary check
try:
    with open(backup_file, 'rb') as fb:
        sample = fb.read(2048)
    if b'\\x00' in sample:
        print(json.dumps({{"ok": True, "binary": True}}))
        exit()
except:
    pass

try:
    with open(backup_file, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    print(json.dumps({{"ok": True, "binary": False, "content": content}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
    return run_remote_python(code)
