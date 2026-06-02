import asyncio
import logging
import threading
from django.conf import settings
from channels.generic.websocket import AsyncJsonWebsocketConsumer
import paramiko
import re

logger = logging.getLogger(__name__)

class TerminalConsumer(AsyncJsonWebsocketConsumer):
    """
    Handles terminal connections to Jetson Nano over SSH and tmux.
    """
    async def connect(self):
        # Initialize attributes immediately to prevent clean-up exceptions
        self.ssh_client = None
        self.ssh_channel = None
        self.connected = False
        self.user_id = None

        # Only logged in users can use the terminal
        self.user_id = self.scope.get('session', {}).get('user_id')
        if not self.user_id:
            logger.warning("Unauthenticated terminal attempt rejected")
            await self.close()
            return

        await self.accept()
        self.loop = asyncio.get_running_loop()

        # Start SSH connection in a background thread to avoid blocking ASGI loop
        threading.Thread(target=self._ssh_connect_and_loop, daemon=True).start()

    def _ssh_connect_and_loop(self):
        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            logger.info(f"Connecting SSH to Jetson at {settings.JETSON_SSH_HOST}...")
            self.ssh_client.connect(
                hostname=settings.JETSON_SSH_HOST,
                username=settings.JETSON_SSH_USERNAME,
                password=settings.JETSON_SSH_PASSWORD,
                timeout=10
            )
            
            self.ssh_channel = self.ssh_client.invoke_shell()
            self.connected = True

            # Log audit
            from apps.core.utils import log_audit
            log_audit(action="SSH_CONNECT", target="Jetson Nano (172.16.1.186)", details="Established Web SSH shell session", user_id=self.user_id)

            # Get user window name or tab ID if specified, default to win0
            window_name = "win0"
            
            # Setup tmux session on Jetson Nano
            safe_uid = str(self.user_id).replace('-', '')[:8]
            tmux_session = f"webterm_user_{safe_uid}"
            
            cmd = (
                f"tmux has-session -t {tmux_session} 2>/dev/null || "
                f"tmux new-session -d -s {tmux_session}; "
                f"tmux select-window -t {tmux_session}:{window_name} 2>/dev/null || "
                f"tmux new-window -t {tmux_session} -n {window_name} -d; "
                f"tmux set-option -t {tmux_session} status off; "
                f"tmux attach-session -t {tmux_session}\n"
            )
            self.ssh_channel.send(cmd)

            # Read thread
            while self.connected:
                data = self.ssh_channel.recv(1024)
                if not data:
                    break
                try:
                    text = data.decode('utf-8')
                except UnicodeDecodeError:
                    text = data.decode('utf-8', errors='ignore')
                
                # Send to websocket client
                asyncio.run_coroutine_threadsafe(
                    self.send_json({"event": "terminal_output", "data": text}),
                    self.loop
                )
        except Exception as e:
            logger.error(f"SSH Terminal thread error: {e}", exc_info=True)
            asyncio.run_coroutine_threadsafe(
                self.send_json({"event": "terminal_output", "data": f"\r\n[SSH Connection Error: {e}]\r\n"}),
                self.loop
            )
        finally:
            self._cleanup()
            asyncio.run_coroutine_threadsafe(self.close(), self.loop)

    async def receive_json(self, content):
        event = content.get('event')
        if not getattr(self, 'connected', False) or not getattr(self, 'ssh_channel', None):
            return

        if event == 'terminal_input':
            data = content.get('data', '')
            try:
                self.ssh_channel.send(data)
            except Exception as e:
                logger.error(f"Failed to send input: {e}")
        
        elif event == 'resize':
            cols = content.get('cols', 80)
            rows = content.get('rows', 24)
            try:
                self.ssh_channel.resize_pty(width=int(cols), height=int(rows))
            except Exception as e:
                logger.error(f"resize_pty error: {e}")

    async def disconnect(self, close_code):
        self._cleanup()

    def _cleanup(self):
        self.connected = False
        ssh_channel = getattr(self, 'ssh_channel', None)
        if ssh_channel:
            try:
                ssh_channel.close()
            except Exception:
                pass
            self.ssh_channel = None
        
        ssh_client = getattr(self, 'ssh_client', None)
        if ssh_client:
            try:
                ssh_client.close()
            except Exception:
                pass
            self.ssh_client = None


class SystemConsumer(AsyncJsonWebsocketConsumer):
    """
    Handles process listing, package installs/removals, and kill actions remotely on Jetson Nano.
    """
    async def connect(self):
        self.user_id = self.scope.get('session', {}).get('user_id')
        if not self.user_id:
            await self.close()
            return
        await self.accept()

    async def receive_json(self, content):
        event = content.get('event')
        
        if event == 'list_processes':
            # Retrieve process list from Jetson Nano asynchronously
            asyncio.create_task(self._list_processes())
            
        elif event == 'kill_process':
            pid = content.get('pid')
            if pid:
                asyncio.create_task(self._kill_process(pid))
                
        elif event == 'system_action':
            action = content.get('action')
            package = content.get('package')
            if action and package:
                asyncio.create_task(self._system_action(action, package))

    def _get_ssh_connection(self):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=settings.JETSON_SSH_HOST,
            username=settings.JETSON_SSH_USERNAME,
            password=settings.JETSON_SSH_PASSWORD,
            timeout=5
        )
        return client

    async def _list_processes(self):
        try:
            # We run the command via SSH to retrieve Linux processes
            # Format: PID, COMMAND, USER, %CPU
            cmd = "ps -eo pid,comm,user,%cpu --sort=-%cpu | head -n 11"
            client = await asyncio.to_thread(self._get_ssh_connection)
            stdin, stdout, stderr = await asyncio.to_thread(client.exec_command, cmd)
            
            lines = await asyncio.to_thread(stdout.readlines)
            await asyncio.to_thread(client.close)

            processes = []
            # Skip header line
            for line in lines[1:]:
                parts = line.strip().split()
                if len(parts) >= 4:
                    pid_val = parts[0]
                    name_val = parts[1]
                    user_val = parts[2]
                    cpu_val = parts[3]
                    
                    try:
                        pid = int(pid_val)
                        cpu = float(cpu_val)
                    except ValueError:
                        continue

                    # Mark protected processes
                    is_protected = pid in (0, 1) or name_val.lower() in ('systemd', 'init', 'sshd')
                    processes.append({
                        'pid': pid,
                        'name': name_val,
                        'username': user_val,
                        'cpu_percent': cpu,
                        'protected': is_protected
                    })

            await self.send_json({
                "event": "process_list",
                "data": processes
            })
        except Exception as e:
            logger.error(f"Failed to list processes: {e}")
            await self.send_json({
                "event": "process_error",
                "message": "Không thể lấy danh sách tiến trình từ Jetson Nano",
                "error": str(e)
            })

    async def _kill_process(self, pid):
        try:
            cmd = f"sudo kill {pid}"
            client = await asyncio.to_thread(self._get_ssh_connection)
            
            # Since sudo might require a password or prompt, we use an interactive shell/exec_command
            # On standard Jetson setup, we can try running exec_command
            # If sudo is passwordless for 'jetson' user, this works instantly.
            stdin, stdout, stderr = await asyncio.to_thread(client.exec_command, cmd)
            # If it asks for sudo password, we send it
            stdin.write(settings.JETSON_SSH_PASSWORD + '\n')
            stdin.flush()
            
            err = await asyncio.to_thread(stderr.read)
            await asyncio.to_thread(client.close)

            from apps.core.utils import log_audit
            from channels.db import database_sync_to_async
            if err and b"no such process" not in err.lower():
                await database_sync_to_async(log_audit)(action="PROCESS_KILL_FAILED", target=f"PID {pid}", details=f"Failed to kill process: {err.decode('utf-8', errors='ignore')}", user_id=self.user_id)
                await self.send_json({
                    "event": "process_error",
                    "message": f"Lỗi khi kill process {pid}",
                    "error": err.decode('utf-8', errors='ignore')
                })
            else:
                await database_sync_to_async(log_audit)(action="PROCESS_KILL", target=f"PID {pid}", details=f"Successfully killed process with PID {pid} via remote control", user_id=self.user_id)
                # Refresh process list
                await self._list_processes()
        except Exception as e:
            logger.error(f"Failed to kill process: {e}")
            await self.send_json({
                "event": "process_error",
                "message": f"Không thể thực thi lệnh kill process {pid}",
                "error": str(e)
            })

    async def _system_action(self, action, package):
        if action not in ['install', 'remove']:
            return

        try:
            cmd = f"sudo apt-get {action} -y {package}"
            client = await asyncio.to_thread(self._get_ssh_connection)
            
            transport = client.get_transport()
            channel = transport.open_session()
            channel.get_pty()
            channel.exec_command(cmd)

            # Sudo password handling if prompt appears
            # Wait a small bit and read channel to see if it prompts for sudo password
            await asyncio.sleep(0.5)
            if channel.recv_ready():
                output = channel.recv(1024).decode('utf-8', errors='ignore')
                if "password" in output.lower():
                    channel.send(settings.JETSON_SSH_PASSWORD + '\n')

            # Stream output back to client line-by-line
            while True:
                if channel.recv_ready():
                    data = channel.recv(1024)
                    if not data:
                        break
                    text = data.decode('utf-8', errors='ignore')
                    await self.send_json({
                        "event": "pkg_status",
                        "output": text
                    })
                elif channel.exit_status_ready():
                    break
                else:
                    await asyncio.sleep(0.1)

            exit_code = channel.recv_exit_status()
            await asyncio.to_thread(client.close)

            from apps.core.utils import log_audit
            from channels.db import database_sync_to_async
            if exit_code == 0:
                await database_sync_to_async(log_audit)(action="PACKAGE_MANAGE", target=package, details=f"Successfully ran apt-get {action} for package: {package}", user_id=self.user_id)
                await self.send_json({
                    "event": "pkg_status",
                    "output": f"✓ Thành công: {action} {package}",
                    "status": "success"
                })
            else:
                await database_sync_to_async(log_audit)(action="PACKAGE_MANAGE_FAILED", target=package, details=f"Failed to run apt-get {action} for package: {package} (Exit code: {exit_code})", user_id=self.user_id)
                await self.send_json({
                    "event": "pkg_status",
                    "output": f"✗ Thất bại khi {action} {package} (Exit code: {exit_code})",
                    "status": "error"
                })

        except Exception as e:
            logger.error(f"System action failed: {e}")
            await self.send_json({
                "event": "pkg_status",
                "output": f"Lỗi hệ thống: {e}",
                "status": "error"
            })
