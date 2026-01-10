import os
import threading
import paramiko
import re

# Configuration
TERMINAL_SSH_HOST = os.environ.get('TERMINAL_SSH_HOST', 'localhost')
TERMINAL_SSH_USERNAME = os.environ.get('TERMINAL_SSH_USERNAME', 'khoa')
TERMINAL_SSH_PASSWORD = os.environ.get('TERMINAL_SSH_PASSWORD', 'osboxes.org')
TERMINAL_TMUX_PREFIX = os.environ.get('TERMINAL_TMUX_PREFIX', 'webterm_user')
TERMINAL_TMUX_TTL_SECONDS = int(os.environ.get('TERMINAL_TMUX_TTL_SECONDS', '1800'))

terminal_cleanup_timers = {}

def _cleanup_tmux_session(tmux_session, clients):
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

def _get_tmux_session_name(user_id):
    safe_uid = str(user_id).replace('-', '')[:8]
    return f"{TERMINAL_TMUX_PREFIX}_{safe_uid}"

def _schedule_tmux_cleanup(tmux_session, clients):
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
    timer = threading.Timer(TERMINAL_TMUX_TTL_SECONDS, _cleanup_tmux_session, args=(tmux_session, clients))
    timer.daemon = True
    terminal_cleanup_timers[tmux_session] = timer
    timer.start()

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
