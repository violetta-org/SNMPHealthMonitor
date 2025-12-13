import time
import json
import os
import sys
import socket
from datetime import datetime
from typing import Dict, Any

# Setup project root path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Collectors imports
from collectors.snmp import fetch_snmp_metrics

# Config imports - from config_prompt module
from .config_prompt import (
    get_snmp_agent, get_snmp_port, get_snmp_community, get_snmp_version, get_snmp_oids_file,
    get_pull_interval, get_notify_host, get_notify_port, get_oids_file_path
)

# Database imports
from db_service.db_config import get_connection
from db_service.db_writer import upsert_device, write_metrics_batch


def _notify_new_data(sysname: str, metric_count: int):
    """Send UDP notification to query service (fire-and-forget)."""
    try:
        timestamp = time.time()
        dt = datetime.fromtimestamp(timestamp)
        
        message = json.dumps({
            'event': 'new_data',
            'sysname': sysname,
            'metric_count': metric_count,
            'timestamp': timestamp
        }).encode('utf-8')

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.1)
        sock.sendto(message, (get_notify_host(), get_notify_port()))
        sock.close()
    except Exception:
        pass


def main():
    try:
        while True:
            try:
                # Get config values each loop (in case they change)
                snmp_agent = get_snmp_agent()
                snmp_port = get_snmp_port()
                snmp_community = get_snmp_community()
                snmp_version = get_snmp_version()
                snmp_oids_file = get_snmp_oids_file()
                pull_interval = get_pull_interval()
                
                # Resolve OIDs file path before passing to snmp collector
                oids_file_path = get_oids_file_path(snmp_oids_file)
                print(f"[DEBUG] Resolved OIDs file path: {oids_file_path}")
                
                metrics = fetch_snmp_metrics(snmp_agent, snmp_port, snmp_community, snmp_version, oids_file_path)
                
                sysname = None
                for m in metrics:
                    if m.get('name') == 'sys.name':
                        sysname = str(m.get('value', '')).strip()
                        if sysname:
                            break
                
                # Nếu không có sys.name, không thể tiếp tục
                if not sysname:
                    print(f"[ERROR] Cannot get sys.name from SNMP agent {snmp_agent}")
                    time.sleep(pull_interval)
                    continue
                
                valid_metrics = [m for m in metrics if m.get('ts') is not None]
                
                if valid_metrics:
                    conn = get_connection()
                    try:
                        upsert_device(conn, sysname=sysname, ip_address=snmp_agent)
                        write_metrics_batch(conn, sysname, valid_metrics)
                        conn.commit()
                        _notify_new_data(sysname, len(valid_metrics))
                    except Exception:
                        conn.rollback()
                    finally:
                        try:
                            conn.close()
                        except Exception:
                            pass
                
            except Exception:
                import traceback
                traceback.print_exc()
            
            time.sleep(pull_interval)
            
    except KeyboardInterrupt:
        pass
    except Exception:
        pass
    finally:
        pass
