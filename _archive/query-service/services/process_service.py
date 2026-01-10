import time
import os
import psutil
import threading

from extensions import socketio

process_cache_lock = threading.Lock()
last_process_list = []
last_process_time = 0.0
PROCESS_REFRESH_INTERVAL = 2.0  # seconds; throttle psutil scans
MAX_PROCESSES = 10  # limit number of processes sent to client (top by CPU)

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

def invalidate_process_cache():
    global last_process_time
    with process_cache_lock:
        last_process_time = 0.0


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
