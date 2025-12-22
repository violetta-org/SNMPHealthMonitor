from flask import Blueprint, request, jsonify, Response
from datetime import datetime, timedelta
from typing import Optional
from services.topic_service import get_topic_data
from services.plot_service import generate_history_plot_base64
from services.pdf_service import generate_history_pdf
from utils.time_range import parse_time_range


api_bp = Blueprint("api", __name__, url_prefix="/api")

# Imports for File Manager API
import os
import shutil
import json
import zipfile
import tarfile
from flask import request, session  # Ensure session is imported
from services.file_service import HOME_DIRECTORY, TRASH_DIRECTORY, BACKUP_DIRECTORY, MAX_EDIT_SIZE, BACKUP_RETENTION, create_backup_if_needed, move_to_trash
from utils.security import _is_safe_path, secure_filename_unicode
from extensions import limiter
from services.audit_service import log_action, get_recent_logs

@api_bp.route("/data/<sysname>/<topic>")
def get_topic_data_api(sysname: str, topic: str):
    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 10))
        start_time, end_time = parse_time_range(
            request.args.get("start_time"),
            request.args.get("end_time"),
        )
        data = get_topic_data(
            sysname=sysname,
            topic=topic,
            page=page,
            per_page=per_page,
            start_time=start_time,
            end_time=end_time,
        )
        return jsonify(data)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/history/plot/<sysname>")
def history_plot(sysname: str):
    """
    Generate a static PNG (base64) for historical CPU percent.
    Params:
      start_time (ISO8601, required)
      end_time   (ISO8601, optional)
      metric     (only 'cpu' supported for now)
    """
    try:
        start_time, end_time = parse_time_range(
            request.args.get("start_time"),
            request.args.get("end_time"),
        )
        if not start_time:
            return jsonify({"error": "start_time is required"}), 400
        
        # end_time defaults to datetime.now() in parse_time_range if not provided

        metric = request.args.get("metric", "cpu")
        
        from db.queries import (
            get_cpu_metrics,
            get_memory_metrics,
            get_disk_metrics,
            get_network_metrics,
            get_temperature_metrics
        )
        from services.plot_service import (
            generate_history_plot_base64, # CPU default
            generate_memory_plot,
            generate_disk_plot,
            generate_network_plot,
            generate_temp_plot
        )

        result = None
        if metric == 'cpu':
            res = get_cpu_metrics(sysname, start_time, end_time)
            cpu = res.get("cpu_percent")
            result = generate_history_plot_base64(cpu, sysname)
        elif metric == 'memory':
            res = get_memory_metrics(sysname, start_time, end_time)
            mem = res.get("memory")
            result = generate_memory_plot(mem, sysname)
        elif metric == 'disk':
            res = get_disk_metrics(sysname, start_time, end_time)
            disk = res.get("disk_usage")
            result = generate_disk_plot(disk, sysname)
        elif metric == 'network':
            res = get_network_metrics(sysname, start_time, end_time)
            net = res.get("net_io")
            result = generate_network_plot(net, sysname)
        elif metric == 'temp':
            res = get_temperature_metrics(sysname, start_time, end_time)
            temp = res.get("temperature")
            result = generate_temp_plot(temp, sysname)
        else:
            return jsonify({"error": f"Unknown metric: {metric}"}), 400

        if not result:
             return jsonify({"error": f"No data available for {metric}"}), 404

        return jsonify(result)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/history/metrics/<sysname>")
def history_metrics(sysname: str):
    """
    Get generic history metrics (JSON) for ApexCharts.
    Query Params:
      start_time: ISO8601
      end_time: ISO8601
      metrics: comma-separated list of metrics (cpu,memory,disk,network,temp). Default: all.
    """
    try:
        start_time, end_time = parse_time_range(
            request.args.get("start_time"),
            request.args.get("end_time"),
        )
        if not start_time:
             # Default to last 1 hour if not specified (Local Time)
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=1)


        metrics_param = request.args.get("metrics", "cpu,memory,disk,network,temp")
        requested_metrics = [m.strip().lower() for m in metrics_param.split(",")]
        
        from db.queries import (
            get_cpu_metrics, 
            get_memory_metrics, 
            get_disk_metrics, 
            get_network_metrics, 
            get_temperature_metrics
        )

        data = {}
        
        from utils.serialize import normalize_list

        if 'cpu' in requested_metrics:
            res = get_cpu_metrics(sysname, start_time, end_time)
            data['cpu'] = normalize_list(res.get('cpu_percent'))

        if 'memory' in requested_metrics:
            res = get_memory_metrics(sysname, start_time, end_time)
            data['memory'] = normalize_list(res.get('memory'))
            if 'swap' in res:
                data['swap'] = normalize_list(res.get('swap'))

        if 'disk' in requested_metrics:
            res = get_disk_metrics(sysname, start_time, end_time)
            data['disk_usage'] = normalize_list(res.get('disk_usage'))

        if 'network' in requested_metrics:
            res = get_network_metrics(sysname, start_time, end_time)
            data['network'] = normalize_list(res.get('net_io'))

        if 'temp' in requested_metrics:
            res = get_temperature_metrics(sysname, start_time, end_time)
            data['temperature'] = normalize_list(res.get('temperature'))
        
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/history/export/pdf/<sysname>")
def history_export_pdf(sysname: str):
    """
    Export history report as PDF.
    """
    try:
        start_time, end_time = parse_time_range(
            request.args.get("start_time"),
            request.args.get("end_time"),
        )
        if not start_time:
             # Default to last 24h for report
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=24)


        # 1. Fetch Data
        data = get_topic_data(
            sysname=sysname,
            topic="systemstatus", 
            start_time=start_time,
            end_time=end_time,
        )
        
        # 2. Generate PDF
        pdf_bytes = generate_history_pdf(sysname, data, start_time, end_time)
        
        if not pdf_bytes:
            return Response("Failed to generate PDF (no data?)", status=404)

        # 3. Return File
        filename = f"report-{sysname}-{start_time.strftime('%Y%m%d%H%M')}.pdf"
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/logs")
def get_audit_logs():
    if not session.get('user_id'):
        return jsonify({"error": "unauthorized"}), 401
    
    try:
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 20, type=int)
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        action = request.args.get('action')
        user_id = request.args.get('user_id', type=int)
        target = request.args.get('target')

        result = get_recent_logs(
            page=page, 
            per_page=limit,
            start_date=start_date,
            end_date=end_date,
            action=action,
            user_id=user_id,
            target=target
        )
        
        data = []
        for log in result['items']:
            data.append({
                "id": log.id,
                "user": log.user.username if log.user else "Unknown",
                "action": log.action,
                "target": log.target,
                "details": log.details,
                "ip_address": log.ip_address,
                "timestamp": log.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            })
            
        return jsonify({
            "logs": data,
            "total": result['total'],
            "pages": result['pages'],
            "current_page": result['current_page']
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==========================================
# FILE MANAGER API ENDPOINTS
# ==========================================
@api_bp.route('/check_exists', methods=['POST'])
def api_check_exists():
    # If using authentication, check session here
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
    
    return {"exists": os.path.exists(dest_path)}

@api_bp.route('/upload_chunk', methods=['POST'])
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

            # Create new file
            with open(dest_path, 'wb') as f:
                f.write(file.read())
        else:
            # Append to existing
            with open(dest_path, 'ab') as f:
                f.write(file.read())
            
        if chunk_index == total_chunks - 1:
            log_action(
                user_id=session.get('user_id'),
                action="UPLOAD_FILE",
                target=safe_filename,
                details=f"Uploaded to {path or '/'}",
                ip_address=request.remote_addr
            )
            
        return {"ok": True, "chunk_index": chunk_index, "final_filename": safe_filename}
    except Exception as e:
        print(f"Upload chunk error: {e}")
        return {"error": str(e)}, 500

@api_bp.route('/zip', methods=['POST'])
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
                            
        return {"ok": True, "zip_name": zip_name}
    except Exception as e:
        print(f"Zip error: {e}")
        return {"error": str(e)}, 500

@api_bp.route('/unzip', methods=['POST'])
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
            
        return {"ok": True}
    except Exception as e:
        print(f"Unzip error: {e}")
        return {"error": str(e)}, 500

@limiter.limit("60 per minute")
@api_bp.route('/save', methods=['POST'])
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
    
    # Log SAVE action
    log_action(
        user_id=session.get('user_id'),
        action="SAVE_FILE",
        target=rel_path,
        details=f"Modified file size {len(content)} bytes",
        ip_address=request.remote_addr
    )

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
        return {"ok":True, "mtime": new_mtime}
    except Exception as e:
        return {"error": str(e)}, 500

@limiter.limit("30 per minute")
@api_bp.route('/delete_batch', methods=['POST'])
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
        if moved > 0 or removed > 0:
            log_action(
                user_id=session.get('user_id'),
                action="DELETE_BATCH",
                target=f"{len(paths)} items",
                details=f"Moved: {moved}, Removed: {removed}, Permanent: {permanent}",
                ip_address=request.remote_addr
            )
        return {"ok": True, "moved": moved, "removed": removed, "permanent": permanent}
    except Exception as e:
        return {"error": str(e)}, 500

@limiter.limit("15 per minute")
@api_bp.route('/trash_empty', methods=['POST'])
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
        if deleted > 0:
            log_action(
                user_id=session.get('user_id'),
                action="EMPTY_TRASH",
                target="Trash",
                details=f"Deleted {deleted} items",
                ip_address=request.remote_addr
            )
        return {"ok": True, "deleted": deleted}
    except Exception as e:
        return {"error": str(e)}, 500

@limiter.limit("60 per minute")
@api_bp.route('/backups')
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
@api_bp.route('/restore_backup', methods=['POST'])
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
        return {"ok": True, "mtime": new_mtime}
    except Exception as e:
        return {"error": str(e)}, 500

@limiter.limit("60 per minute")
@api_bp.route('/backup_content')
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
@api_bp.route('/delete', methods=['POST'])
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
        log_action(
            user_id=session.get('user_id'),
            action="DELETE_FILE",
            target=rel_path,
            details=f"Permanent: {permanent}",
            ip_address=request.remote_addr
        )
        return {"ok": True, "permanent": False}
    except Exception as e:
        return {"error": str(e)}, 500

@limiter.limit("30 per minute")
@api_bp.route('/restore', methods=['POST'])
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
        log_action(
            user_id=session.get('user_id'),
            action="RESTORE_FILE",
            target=trash_rel,
            details=f"Restored to {final_dest}",
            ip_address=request.remote_addr
        )
        return {"ok": True, "restored_to": final_dest}
    except Exception as e:
        return {"error": str(e)}, 500

@limiter.limit("30 per minute")
@api_bp.route('/delete_permanent', methods=['POST'])
def api_delete_permanent():
    # if not session.get('user_id'): return {"error": "unauthorized"}, 401
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
        log_action(
            user_id=session.get('user_id'),
            action="DELETE_PERMANENT",
            target=trash_rel,
            details="Deleted from trash",
            ip_address=request.remote_addr
        )
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}, 500
