import time
import json
import os
import sys
import socket
import logging
from datetime import datetime
from typing import Dict, Any

# Setup project root path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Logging 
from utils.logging import configure_logger
logger = configure_logger(__name__)
logger.setLevel(level=logging.INFO)

# Collectors imports
from collectors.snmp import fetch_snmp_metrics

# Config imports - from config_prompt module
from .config_prompt import (
    get_snmp_agent, get_snmp_port, get_snmp_community, get_snmp_version, get_snmp_oids_file,
    get_pull_interval, get_notify_host, get_notify_port, get_oids_file_path
)




def _notify_new_data(sysname: str, metric_count: int, ip_address: str, metrics: list):
    """Send UDP notification to query service (fire-and-forget)."""
    try:
        timestamp = time.time()
        message = json.dumps({
            'event': 'new_data',
            'sysname': sysname,
            'metric_count': metric_count,
            'timestamp': timestamp,
            'ip_address': ip_address,
            'metrics': metrics
        }).encode('utf-8')

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(None)
        sock.sendto(message, (get_notify_host(), get_notify_port()))
        sock.close()
    except Exception:
        logger.error("Failed to send notification to query service")


def main():
    try:
        while True:
            start_time = time.time()
            try:
                # Get config values
                snmp_agent = get_snmp_agent()
                snmp_port = get_snmp_port()
                snmp_community = get_snmp_community()
                snmp_version = get_snmp_version()
                snmp_oids_file = get_snmp_oids_file()
                pull_interval = get_pull_interval()
                
                # Resolve OIDs path (now cached in snmp collector)
                oids_file_path = get_oids_file_path(snmp_oids_file)

                # Fetch (caching logic inside collector prevents redraw)
                metrics = fetch_snmp_metrics(snmp_agent, snmp_port, snmp_community, snmp_version, oids_file_path)
                
                sysname = None
                for m in metrics:
                    if m.get('name') == 'sys.name':
                        sysname = str(m.get('value', '')).strip()
                        if sysname:
                            break
                
                if not sysname:
                    logger.error(f"Cannot get sys.name from SNMP agent {snmp_agent}")
                    time.sleep(pull_interval)
                    continue
                
                valid_metrics = [m for m in metrics if m.get('ts') is not None]
                
                if valid_metrics:
                    _notify_new_data(sysname, len(valid_metrics), snmp_agent, valid_metrics)
                
            except Exception:
                import traceback
                traceback.print_exc()
                logger.error("Exception in main loop", exc_info=True)
            
            # Drift-corrected sleep
            elapsed = time.time() - start_time
            sleep_time = max(0, pull_interval - elapsed)
            # logger.info(f"Loop took {elapsed:.3f}s, sleeping for {sleep_time:.3f}s")
            time.sleep(sleep_time)
            
    except KeyboardInterrupt:
        pass
    except Exception:
        pass