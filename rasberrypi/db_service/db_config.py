"""Database configuration management with hardcoded defaults and environment variable overrides."""

import os
import pymysql as MySQLdb

# Database configuration - hardcoded defaults, overridable via env vars
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_PORT = int(os.environ.get('DB_PORT', '3306'))
DB_NAME = os.environ.get('DB_NAME', 'python_programming')
DB_USER = os.environ.get('DB_USER', 'root')
DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
DB_CHARSET = 'utf8mb4'

# Writer settings
DB_BATCH_SIZE = int(os.environ.get('DB_BATCH_SIZE', '500'))
DB_FLUSH_INTERVAL = float(os.environ.get('DB_FLUSH_INTERVAL', '2.0'))

# Retention policy
RETENTION_MINUTES = int(os.environ.get('RETENTION_MINUTES', '1440'))  # 24 hours default
DEVICE_OFFLINE_TIMEOUT = int(os.environ.get('DEVICE_OFFLINE_TIMEOUT', '60'))  # 60 seconds


def load_db_config():
    """
    Load database configuration.
    
    Returns:
        dict: MySQL connection parameters
    """
    config = {
        'host': DB_HOST,
        'port': DB_PORT,
        'db': DB_NAME,
        'user': DB_USER,
        'passwd': DB_PASSWORD,
        'charset': DB_CHARSET
    }
    
    print(f"[DEBUG] DB config: host={config['host']}, port={config['port']}, db={config['db']}, user={config['user']}")
    return config


def get_connection():
    """
    Establish a new database connection.
    
    Returns:
        MySQLdb.Connection: Active database connection
    """
    cfg = load_db_config()
    try:
        print(f"[DEBUG] Attempting MySQL connect to {cfg['host']}:{cfg['port']} db={cfg['db']} user={cfg['user']}")
        conn = MySQLdb.connect(**cfg)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT CONNECTION_ID()")
                cid = cur.fetchone()[0]
                print(f"[DEBUG] MySQL connected, connection_id={cid}")
        except Exception:
            # non-fatal; continue
            print("[DEBUG] MySQL connected (connection_id unavailable)")
        return conn
    except Exception as e:
        print(f"[ERROR] MySQL connect failed: {e}")
        raise RuntimeError(f"Failed to connect to MySQL: {e}") from e


def ensure_db_ready():
    """Fail fast if database is unreachable."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchall()
        # Capacity diagnostics
        try:
            cur.execute("SHOW VARIABLES LIKE 'max_connections'")
            max_conn_row = cur.fetchone()
            max_conn = max_conn_row[1] if max_conn_row else 'unknown'
            cur.execute("SHOW STATUS LIKE 'Threads_connected'")
            thr_row = cur.fetchone()
            threads_connected = thr_row[1] if thr_row else 'unknown'
            print(f"[DEBUG] MySQL capacity: max_connections={max_conn}, Threads_connected={threads_connected}")
        except Exception as diag_e:
            print(f"[DEBUG] Capacity diagnostics failed: {diag_e}")
        finally:
            cur.close()
            conn.close()
        print("[DEBUG] Database readiness check: OK")
    except Exception as e:
        cfg = load_db_config()
        raise RuntimeError(
            f"Database readiness check failed for host={cfg['host']} port={cfg['port']} db={cfg['db']} user={cfg['user']}: {e}"
        )
