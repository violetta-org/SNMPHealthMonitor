import json
import logging
import paramiko
from django.conf import settings

logger = logging.getLogger(__name__)

def get_remote_home():
    username = settings.JETSON_SSH_USERNAME
    return f"/home/{username}/managed_files"

def run_ssh_cmd(cmd):
    """Executes a shell command on Jetson Nano via SSH."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=settings.JETSON_SSH_HOST,
            username=settings.JETSON_SSH_USERNAME,
            password=settings.JETSON_SSH_PASSWORD,
            timeout=10
        )
        stdin, stdout, stderr = client.exec_command(cmd)
        out = stdout.read().decode('utf-8', errors='ignore')
        err = stderr.read().decode('utf-8', errors='ignore')
        return out, err
    finally:
        client.close()

def run_remote_python(code):
    """Executes a Python snippet on Jetson Nano and returns JSON-loaded output."""
    # Escape quotes and formatting for bash execution
    escaped_code = code.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$')
    cmd = f'python3 -c "{escaped_code}"'
    out, err = run_ssh_cmd(cmd)
    if err.strip():
        logger.error(f"Remote Python Error: {err}")
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON returned", "output": out, "stderr": err}

def get_sftp_client():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=settings.JETSON_SSH_HOST,
        username=settings.JETSON_SSH_USERNAME,
        password=settings.JETSON_SSH_PASSWORD,
        timeout=10
    )
    sftp = client.open_sftp()
    # Bind the client to the sftp instance so it doesn't get garbage-collected
    sftp.ssh_client = client
    return sftp
