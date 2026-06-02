import os
import sys
import json
import socket
import logging
import traceback
import time
from typing import Optional

# Set up logging to console
logger = logging.getLogger('worker')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
logger.addHandler(handler)

# Project imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
if os.path.join(project_root, 'rasberrypi') not in sys.path:
    sys.path.insert(0, os.path.join(project_root, 'rasberrypi'))

try:
    from db_service.db_config import get_connection
    from db_service.db_writer import upsert_device, write_metrics_batch
except ImportError as e:
    logger.error(f"Failed to import DB services: {e}")
    # Mocking for testing if dependencies are absent
    def get_connection(): raise NotImplementedError()
    def upsert_device(*a, **kw): pass
    def write_metrics_batch(*a, **kw): pass

def parse_packet(data: bytes) -> Optional[dict]:
    """Parse incoming UDP payload and validate its format."""
    try:
        payload = json.loads(data.decode('utf-8'))
        if not isinstance(payload, dict):
            logger.error("Payload is not a JSON object")
            return None
        
        # Verify required keys
        required_keys = ["event", "sysname", "metrics"]
        for key in required_keys:
            if key not in payload:
                logger.error(f"Payload missing required key: {key}")
                return None
        return payload
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON packet: {e}. Raw data: {data}")
    except Exception as e:
        logger.error(f"Unexpected error parsing packet: {e}\n{traceback.format_exc()}")
    return None

def process_packet(payload: dict, conn) -> None:
    """Connect to database and write device and metric information."""
    try:
        sysname = payload["sysname"]
        metrics = payload["metrics"]
        ip_address = payload.get("ip_address")

        upsert_device(conn, sysname=sysname, ip_address=ip_address)
        write_metrics_batch(conn, sysname, metrics)
        conn.commit()
        # logger.info(f"Successfully wrote {len(metrics)} metrics for device '{sysname}' to database")
    except Exception as e:
        logger.error(f"Database operation failed: {e}\n{traceback.format_exc()}")
        try:
            conn.rollback()
        except Exception as re:
            logger.error(f"Failed to rollback transaction: {re}")


def forward_packet(data: bytes, host: str, port: int) -> None:
    """Forward the UDP datagram to the Django UDP listener."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(data, (host, port))
        sock.close()
        logger.info(f"Forwarded UDP packet to Django server at {host}:{port}")
    except Exception as e:
        logger.error(f"Failed to forward packet to Django server: {e}\n{traceback.format_exc()}")

def main():
    bind_host = os.environ.get("BIND_HOST", "0.0.0.0")
    bind_port = int(os.environ.get("BIND_PORT", "6003"))
    django_host = os.environ.get("DJANGO_HOST", "127.0.0.1")
    django_port = int(os.environ.get("DJANGO_PORT", "6004"))

    # Create UDP socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((bind_host, bind_port))
        logger.info(f"Database Worker UDP Listener running on {bind_host}:{bind_port}")
        logger.info(f"Configured to forward packets to Django at {django_host}:{django_port}")
    except Exception as e:
        logger.error(f"Failed to bind socket on {bind_host}:{bind_port}: {e}")
        sys.exit(1)

    # Create persistent DB connection
    db_conn = None
    
    while True:
        try:
            data, addr = sock.recvfrom(65535)
            
            # Bắt đầu bấm giờ
            start_time = time.perf_counter()
            
            # 1. Parse packet
            payload = parse_packet(data)
            if payload is None:
                continue
                
            # Keep connection alive / reconnect if needed
            if db_conn is None:
                db_conn = get_connection()
            else:
                try:
                    db_conn.ping(reconnect=True)
                except Exception:
                    db_conn = get_connection()
                
            # 2. Forward to Django (high priority for real-time frontend responsiveness)
            forward_packet(data, django_host, django_port)

            # 3. Persist to DB
            process_packet(payload, db_conn)
            
            # Kết thúc bấm giờ và ghi log
            end_time = time.perf_counter()
            exec_time = (end_time - start_time) * 1000
            logger.info(f"[Worker Perf] Processed and forwarded packet ({len(data)} bytes) in {exec_time:.2f} ms")
            
            
        except KeyboardInterrupt:
            logger.info("Worker stopped by user")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}\n{traceback.format_exc()}")

    sock.close()
    if db_conn:
        db_conn.close()

if __name__ == "__main__":
    main()
