import time
from flask import request, session
from datetime import datetime
from typing import Optional
from utils.time_range import parse_time_range
from utils.logging import configure_logger

# Ionized-Astro Imports
from flask_socketio import emit
import services.package_service as package_service
import services.process_service as process_service
import services.terminal_service as terminal_service
import paramiko
import subprocess

def register_socketio_events(socketio, ws_manager, get_topic_data, clients):
    """
    Đăng ký tất cả Socket.IO event handlers cho query-service (Merged with Ionized-Astro features).

    socketio: Flask-SocketIO instance
    ws_manager: WebSocketManager instance
    get_topic_data: function để lấy dữ liệu metrics theo topic
    clients: dict để quản lý SSH clients (từ ionized-astro)
    """
    logger = configure_logger(__name__)

    # --- Ionized-Astro Handlers ---

    @socketio.on('terminal_input')
    def handle_terminal_input(data):
        sid = request.sid
        if sid in clients:
            channel = clients[sid]['channel']
            channel.send(data)

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

    @socketio.on('system_action')
    def handle_system_action(data):
        """Handle package installation/removal requests."""
        if not session.get('user_id'):
            return
        
        action = data.get('action') if isinstance(data, dict) else None
        package = data.get('package') if isinstance(data, dict) else None
        
        if not action or not package:
            return

        if action not in ['install', 'remove', 'purge']:
            socketio.emit('pkg_status', {
                'output': f'Invalid action: {action}',
                'status': 'error'
            }, to=request.sid)
            return

        # Use module-level lock and variable to ensure shared state
        with package_service.pkg_task_lock:
            if package_service.pkg_task_running:
                socketio.emit('pkg_status', {
                    'output': 'Another package operation is already running. Please wait until it finishes.',
                    'status': 'error'
                }, to=request.sid)
                return
            package_service.pkg_task_running = True

        sid = request.sid
        socketio.start_background_task(target=package_service._run_pkg_action, action=action, package=package, sid=sid)

    @socketio.on('list_processes')
    def handle_list_processes():
        if not session.get('user_id'):
            return
        socketio.start_background_task(target=process_service._get_and_emit_processes, sid=request.sid)

    @socketio.on('kill_process')
    def handle_kill_process(data):
        if not session.get('user_id'):
            return

        pid = data.get('pid') if isinstance(data, dict) else None
        if not pid:
            return

        try:
            pid_int = int(pid)
        except (TypeError, ValueError):
            return

        if process_service._is_protected_process(pid_int):
            socketio.emit('process_error', {
                'message': f'Cannot kill protected system process {pid_int}',
                'error': ''
            }, to=request.sid)
            return
        
        sid = request.sid
        try:
            subprocess.run(['sudo', 'kill', str(pid_int)], check=True, capture_output=True, text=True)
            print(f"Successfully killed process {pid}")
            # Invalidate cache so next refresh recomputes list
            process_service.invalidate_process_cache()
            socketio.start_background_task(target=process_service._get_and_emit_processes, sid=sid)
        except subprocess.CalledProcessError as e:
            err = (e.stderr or '').strip()
            if 'no such process' in err.lower():
                print(f"Process {pid_int} already terminated")
                socketio.start_background_task(target=process_service._get_and_emit_processes, sid=sid)
            else:
                print(f"Failed to kill process {pid_int}: {err}")
                socketio.emit('process_error', {'message': f'Failed to kill process {pid_int}', 'error': err}, to=sid)
        except Exception as e:
            print(f"kill_process error: {e}")
            socketio.emit('process_error', {'message': f'Error killing process {pid}', 'error': str(e)}, to=sid)

    # --- Unified Connect/Disconnect Handlers ---

    @socketio.on("connect")
    def handle_connect(auth=None):
        sid = request.sid
        logger.info(f"Client connected, sid={sid}")
        
        # 1. Ionized-Astro SSH Init Logic
        # Try to initialize SSH/Terminal session if user is logged in
        # If user is NOT logged in, we do NOT return False (reject), because existing Dashboard might not require it for read-only?
        # WAIT: Query Service routes now require login. So session['user_id'] SHOULD be present.
        # If it's missing, maybe we SHOULD reject?
        # But to be safe and avoid breaking "public" views if they exist, we just skip SSH.
        
        user_id = session.get('user_id')
        if user_id:
            window_name = None
            if isinstance(auth, dict):
                window_name = auth.get('window_name') or auth.get('window') or auth.get('tab_id')
            
            # Mocking SSH for localhost
            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh_password ='osboxes.org'
                client.connect('localhost', username='osboxes', password=ssh_password)
                channel = client.invoke_shell()
                tmux_session = terminal_service._get_tmux_session_name(user_id)
                terminal_service._attach_tmux_session(channel, tmux_session, window_name=window_name)
                
                # Cancel cleanup timer if exists
                if tmux_session in terminal_service.terminal_cleanup_timers:
                    try:
                        terminal_service.terminal_cleanup_timers[tmux_session].cancel()
                    except Exception:
                        pass
                    terminal_service.terminal_cleanup_timers.pop(tmux_session, None)
                
                clients[sid] = {
                    'client': client,
                    'channel': channel,
                    'password': ssh_password,
                    'user_id': user_id,
                    'tmux_session': tmux_session,
                    'window_name': window_name,
                }

                def read_from_channel(sid, channel):
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
                        except Exception as e:
                            print(f"read_from_channel error: {e}")
                            break

                socketio.start_background_task(target=read_from_channel, sid=sid, channel=channel)
            except Exception as e:
                print(f"Terminal connect error: {e}")
                # We do NOT return False here, to allow connection to proceed for other features (like simple dashboard stats)
                pass

    @socketio.on("disconnect")
    def handle_disconnect():
        sid = request.sid
        logger.info(f"Client disconnected, sid={sid}")
        ws_manager.disconnect(sid)
        
        # Ionized Cleanup
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
                terminal_service._schedule_tmux_cleanup(tmux_session, clients)

    # --- Existing Query Service Handlers ---

    @socketio.on("subscribe")
    def handle_subscribe(data):
        sid = request.sid
        sysname = data.get("sysname")
        topic = data.get("topic") or "systemstatus"
        logger.info(f"Subscribe requested: sid={sid}, sysname={sysname}, topic={topic}")

        if not sysname:
            logger.warning(f"Missing sysname in subscribe payload: {data}")
            return

        ws_manager.connect(sid, sysname, topic)

        try:
            payload = get_topic_data(sysname, topic)
            socketio.emit("data", {"type": "data", "topic": topic, "sysname": sysname, "data": payload}, to=sid)
            logger.info(f"Sent initial {topic} data to sid={sid}")
        except Exception as e:
            logger.error(f"Error sending initial data for {sysname}/{topic}: {e}", exc_info=True)

    @socketio.on("ping")
    def handle_ping(data=None):
        sid = request.sid
        logger.debug(f"Ping from sid={sid}, data={data}")
        socketio.emit("pong", {"ts": time.time()}, to=sid)

    @socketio.on("paginate")
    def handle_paginate(data):
        sid = request.sid
        sysname = data.get("sysname")
        topic = data.get("topic", "diskio")
        page = int(data.get("page", 1))
        per_page = int(data.get("per_page", 10))

        logger.info(f"Paginate requested: sid={sid}, sysname={sysname}, topic={topic}, page={page}")

        if not sysname: return
        if topic != "diskio": return

        try:
            payload = get_topic_data(sysname, topic, page=page, per_page=per_page)
            socketio.emit("data", {"type": "data", "topic": topic, "sysname": sysname, "data": payload}, to=sid)
        except Exception as e:
            logger.error(f"Error sending paginated data: {e}", exc_info=True)

    @socketio.on("query_range")
    def handle_query_range(data):
        sid = request.sid
        sysname = data.get("sysname")
        topic = data.get("topic", "systemstatus")
        start_time_str = data.get("start_time")
        end_time_str = data.get("end_time")
        page = int(data.get("page", 1))
        per_page = int(data.get("per_page", 10))

        if not sysname or not start_time_str:
            socketio.emit("error", {"message": "Missing required fields"}, to=sid)
            return

        try:
            start_time, end_time = parse_time_range(start_time_str, end_time_str)
            payload = get_topic_data(sysname, topic, start_time=start_time, end_time=end_time, page=page, per_page=per_page)
            socketio.emit("data", {
                "type": "data", 
                "topic": topic, 
                "sysname": sysname, 
                "data": payload,
                "range": {"start_time": start_time.isoformat(), "end_time": end_time.isoformat()}
            }, to=sid)
        except ValueError as e:
            socketio.emit("error", {"message": f"Invalid datetime format: {e}"}, to=sid)
        except Exception as e:
            logger.error(f"Error query_range: {e}", exc_info=True)
            socketio.emit("error", {"message": str(e)}, to=sid)
