import subprocess
from flask_socketio import emit
from extensions import socketio
import threading

pkg_task_lock = threading.Lock()
pkg_task_running = False

def _run_pkg_action(action, package, sid):
    """
    Worker function to run apt-get command in background and stream output to client.
    Runs with subprocess.Popen and emits each line of output via Socket.IO.
    """
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
        else:
            socketio.emit('pkg_status', {
                'output': f'✗ Failed to {action} {package} (exit code: {return_code})',
                'status': 'error'
            }, to=sid)

    except Exception as e:
        socketio.emit('pkg_status', {
            'output': f'Exception: {str(e)}',
            'status': 'error'
        }, to=sid)
        print(f"_run_pkg_action error: {e}")
    finally:
        global pkg_task_running
        try:
            with pkg_task_lock:
                pkg_task_running = False
        except Exception:
            pass
