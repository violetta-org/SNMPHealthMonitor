from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from db.connection import get_db
from utils.serialize import serialize_row, serialize_rows

def get_device_info(sysname: str) -> Dict[str, Any]:
    """Get device information: online, last_seen, ip_address."""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT online, last_seen, ip_address
                    FROM devices
                    WHERE sysname = %s
                """, (sysname,))
                row = cur.fetchone()
                if row:
                    # Cursor returns dict (DictCursor), access by key name
                    last_seen = row.get('last_seen')
                    return {
                        'online': bool(row.get('online', False)),
                        'last_seen': last_seen.isoformat() if last_seen else None,
                        'ip_address': row.get('ip_address')
                    }
                print(f"[DEBUG] get_device_info: Device {sysname} not found in database")
                return {
                    'online': False,
                    'last_seen': None,
                    'ip_address': None
                }
    except Exception as e:
        print(f"[ERROR] get_device_info failed for {sysname}: {e}")
        import traceback
        traceback.print_exc()
        return {
            'online': False,
            'last_seen': None,
            'ip_address': None
        }

def get_system_metrics(sysname: str, notify_timestamp: Optional[float] = None) -> Dict[str, Any]:
    """Get system info và load averages."""
    if notify_timestamp:
        cutoff = datetime.fromtimestamp(notify_timestamp) - timedelta(seconds=30)
        print(f"[DEBUG] get_system_metrics: Using notify_timestamp cutoff {cutoff} from notification")
    else:
        cutoff = datetime.now()
        print(f"[DEBUG] get_system_metrics: Using current time cutoff {cutoff}") 
    
    with get_db() as conn:
        with conn.cursor() as cur:
            result = {}
            
            # Device info
            result['device_info'] = get_device_info(sysname)
            
            # System info
            cur.execute("""
                SELECT sysname, sys_location, sys_uptime
                FROM system_info
                WHERE sysname = %s
            """, (sysname,))
            result['system_info'] = serialize_row(cur.fetchone())
            
            # Load averages (latest only)
            cur.execute("""
                SELECT load_1m, load_5m, load_15m
                FROM load_avg
                WHERE sysname = %s AND time >= %s
                ORDER BY time DESC
                LIMIT 1
            """, (sysname, cutoff))
            result['load_avg'] = serialize_row(cur.fetchone())
            
            return result

def get_status_metrics(sysname: str, notify_timestamp: Optional[float] = None) -> Dict[str, Any]:
    """Aggregate minimal status metrics without disk usage."""
    print(f"[DEBUG] get_status_metrics: Aggregating status for {sysname}, notify_timestamp={notify_timestamp}")
    try:
        status: Dict[str, Any] = {}
        # Reuse existing queries to keep logic in one place
        system_part = get_system_metrics(sysname, notify_timestamp=notify_timestamp)
        # Include memory history only on initial load (when notify_timestamp is None)
        include_history = notify_timestamp is None
        memory_part = get_memory_metrics(sysname, notify_timestamp=notify_timestamp, include_history=include_history)
        cpu_part = get_cpu_metrics(sysname, notify_timestamp=notify_timestamp)
        temperature_part = get_temperature_metrics(sysname, notify_timestamp=notify_timestamp)
        
        # Merge parts (keys are distinct: system_info, load_avg, memory, swap, cpu_percent, temperature)
        status.update(system_part or {})
        status.update(memory_part or {})
        status.update(cpu_part or {})
        # Merge temperature (overwrite device_info if exists, but that's fine)
        if temperature_part.get('temperature'):
            status['temperature'] = temperature_part['temperature']
        
        print(f"[DEBUG] get_status_metrics: Aggregation complete with keys={list(status.keys())}")
        return status
    except Exception as e:
        print(f"[DEBUG] get_status_metrics: Error during aggregation: {e}")
        return {}

def get_cpu_metrics(sysname: str, notify_timestamp: Optional[float] = None) -> Dict[str, Any]:
    """Get latest CPU metrics per core."""
    print(f"[DEBUG] get_cpu_metrics: Getting latest CPU metrics for {sysname}")
    
    # Giới hạn data scan bằng time filter
    if notify_timestamp:
        cutoff = datetime.fromtimestamp(notify_timestamp) - timedelta(seconds=30)
    else:
        cutoff = datetime.now() - timedelta(minutes=1)  # Lấy data trong 1 phút gần nhất
    
    with get_db() as conn:
        with conn.cursor() as cur:
            result = {}
            
            # Device info
            result['device_info'] = get_device_info(sysname)
            
            # Get latest CPU metrics per core (all cores, but only recent data)
            cur.execute("""
                SELECT cpu, percent
                FROM (
                    SELECT cpu, percent, time,
                           ROW_NUMBER() OVER (PARTITION BY cpu ORDER BY time DESC) AS rn
                    FROM cpu_percent
                    WHERE sysname = %s
                ) ranked
                WHERE rn = 1 AND time >= %s
                ORDER BY cpu
            """, (sysname, cutoff))
            result['cpu_percent'] = serialize_rows(cur.fetchall())
            
            return result

def get_memory_history(sysname: str, limit: int = 60) -> List[Dict[str, Any]]:
    """Get memory history data for chart (60 points)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT time, used, cached, free, total
                FROM memory
                WHERE sysname = %s
                ORDER BY time DESC
                LIMIT %s
            """, (sysname, limit))
            rows = serialize_rows(cur.fetchall())
            # Reverse để thời gian chạy từ cũ -> mới (trái -> phải)
            return list(reversed(rows))

def get_memory_metrics(sysname: str, notify_timestamp: Optional[float] = None, include_history: bool = False) -> Dict[str, Any]:
    """Get latest memory and swap metrics."""
    print(f"[DEBUG] get_memory_metrics: Getting latest memory metrics for {sysname}, include_history={include_history}")
    
    # Giới hạn data scan bằng time filter
    if notify_timestamp:
        cutoff = datetime.fromtimestamp(notify_timestamp) - timedelta(seconds=30)
    else:
        cutoff = datetime.now() - timedelta(minutes=1)  # Lấy data trong 1 phút gần nhất
    
    with get_db() as conn:
        with conn.cursor() as cur:
            result = {}
            
            # Device info
            result['device_info'] = get_device_info(sysname)
            
            # Memory (latest only)
            cur.execute("""
                SELECT time, total, available, used, free, percent, 
                       buffers, cached, shared
                FROM memory
                WHERE sysname = %s AND time >= %s
                ORDER BY time DESC
                LIMIT 1
            """, (sysname, cutoff))
            result['memory'] = serialize_row(cur.fetchone())
            
            # Memory history for chart (only on initial load)
            if include_history:
                result['memory_history'] = get_memory_history(sysname, limit=60)
            
            # Swap (latest only)
            cur.execute("""
                SELECT total, used, free, percent
                FROM swap_memory
                WHERE sysname = %s AND time >= %s
                ORDER BY time DESC
                LIMIT 1
            """, (sysname, cutoff))
            result['swap'] = serialize_row(cur.fetchone())
            
            return result

def get_network_metrics(sysname: str, notify_timestamp: Optional[float] = None) -> Dict[str, Any]:
    """Get network I/O metrics."""
    if notify_timestamp:
        cutoff = datetime.fromtimestamp(notify_timestamp) - timedelta(seconds=30)
        print(f"[DEBUG] get_network_metrics: Using notify_timestamp cutoff {cutoff} from notification")
    else:
        cutoff = datetime.now()
        print(f"[DEBUG] get_network_metrics: Using current time cutoff {cutoff}")
    
    with get_db() as conn:
        with conn.cursor() as cur:
            result = {}
            
            # Device info
            result['device_info'] = get_device_info(sysname)
            
            # Network I/O with calculated rates
            cur.execute("""
                WITH last2 AS (
                    SELECT iface, time, bytes_sent, bytes_recv, if_admin_status, if_oper_status,
                           ROW_NUMBER() OVER (PARTITION BY iface ORDER BY time DESC) AS rn
                    FROM net_io_counters
                    WHERE sysname = %s AND time >= %s
                )
                SELECT 
                    a.iface AS interface, a.time, a.bytes_sent, a.bytes_recv, 
                    a.if_admin_status, a.if_oper_status,
                    CASE 
                        WHEN b.time IS NOT NULL AND TIMESTAMPDIFF(MICROSECOND, b.time, a.time) > 0 THEN 
                            GREATEST(0, (a.bytes_sent - b.bytes_sent) / (TIMESTAMPDIFF(MICROSECOND, b.time, a.time) / 1e6)) 
                        ELSE NULL
                    END AS send_bytes_s,
                    CASE 
                        WHEN b.time IS NOT NULL AND TIMESTAMPDIFF(MICROSECOND, b.time, a.time) > 0 THEN 
                            GREATEST(0, (a.bytes_recv - b.bytes_recv) / (TIMESTAMPDIFF(MICROSECOND, b.time, a.time) / 1e6)) 
                        ELSE NULL
                    END AS recv_bytes_s
                FROM last2 a
                LEFT JOIN last2 b ON a.iface = b.iface AND a.rn = 1 AND b.rn = 2
                WHERE a.rn = 1
                ORDER BY a.iface
            """, (sysname, cutoff))
            result['net_io'] = serialize_rows(cur.fetchall())
            
            return result

def get_disk_metrics(sysname: str, notify_timestamp: Optional[float] = None) -> Dict[str, Any]:
    """Get disk usage metrics."""
    if notify_timestamp:
        cutoff = datetime.fromtimestamp(notify_timestamp) - timedelta(seconds=30)
        print(f"[DEBUG] get_disk_metrics: Using notify_timestamp cutoff {cutoff} from notification")
    else:
        # Use 60 second buffer to ensure we get recent data even with slight timing differences
        cutoff = datetime.now() - timedelta(seconds=60)
        # cutoff = datetime.now()
        print(f"[DEBUG] get_disk_metrics: Using current time cutoff {cutoff} (60s buffer)")
    
    with get_db() as conn:
        with conn.cursor() as cur:
            result = {}
            
            # Device info
            result['device_info'] = get_device_info(sysname)
            
            # Disk usage (latest per mount - filter only / and /boot/firmware, exclude tmpfs)
            cur.execute("""
                SELECT d1.mount, d1.device_partition,
                       d1.total, d1.used, d1.free, d1.percent
                FROM disk_usage d1
                INNER JOIN (
                    SELECT mount, MAX(time) as max_time
                    FROM disk_usage
                    WHERE sysname = %s AND time >= %s
                    GROUP BY mount
                ) d2 ON d1.mount = d2.mount AND d1.time = d2.max_time
                WHERE d1.sysname = %s
                  AND d1.mount IN ('/', '/boot/firmware')
                  AND d1.device_partition NOT LIKE 'tmpfs'
                  AND d1.device_partition NOT LIKE '%%tmpfs%%'
            """, (sysname, cutoff, sysname))
            result['disk_usage'] = serialize_rows(cur.fetchall())
            
            return result

def get_temperature_metrics(sysname: str, notify_timestamp: Optional[float] = None) -> Dict[str, Any]:
    """Get latest CPU temperature."""
    print(f"[DEBUG] get_temperature_metrics: Getting latest temperature for {sysname}")
    
    # Giới hạn data scan bằng time filter
    if notify_timestamp:
        cutoff = datetime.fromtimestamp(notify_timestamp) - timedelta(seconds=30)
    else:
        cutoff = datetime.now() - timedelta(minutes=1)  # Lấy data trong 1 phút gần nhất
    
    with get_db() as conn:
        with conn.cursor() as cur:
            result = {}
            
            # Device info
            result['device_info'] = get_device_info(sysname)
            
            # Get latest temperature
            cur.execute("""
                SELECT cpu_temp
                FROM temperature
                WHERE sysname = %s AND time >= %s
                ORDER BY time DESC
                LIMIT 1
            """, (sysname, cutoff))
            row = cur.fetchone()
            if row:
                result['temperature'] = serialize_row(row)
            else:
                result['temperature'] = None
            
            return result


def get_disk_io_metrics(sysname: str, notify_timestamp: Optional[float] = None, page: int = 1, per_page: int = 10) -> Dict[str, Any]:
    """Get disk I/O metrics with calculated speeds, with pagination and filtering."""
    if notify_timestamp:
        cutoff = datetime.fromtimestamp(notify_timestamp) - timedelta(seconds=30)
        print(f"[DEBUG] get_disk_io_metrics: Using notify_timestamp cutoff {cutoff} from notification")
    else:
        cutoff = datetime.now()
        print(f"[DEBUG] get_disk_io_metrics: Using current time cutoff {cutoff}")
    offset = (page - 1) * per_page
    
    with get_db() as conn:
        with conn.cursor() as cur:
            result = {}
            
            # Device info
            result['device_info'] = get_device_info(sysname)
            
            # Disk I/O with calculated speeds (paginated and filtered) - single query
            cur.execute("""
                WITH last2 AS (
                    SELECT disk, time, read_bytes, write_bytes,
                           ROW_NUMBER() OVER (PARTITION BY disk ORDER BY time DESC) AS rn
                    FROM disk_io_counters
                    WHERE sysname = %s AND time >= %s
                ),
                active_disks AS (
                    SELECT 
                        a.disk,
                        a.time,
                        a.read_bytes,
                        a.write_bytes,
                        CASE 
                            WHEN b.time IS NOT NULL AND TIMESTAMPDIFF(MICROSECOND, b.time, a.time) > 0 THEN
                                GREATEST(0, (a.read_bytes - b.read_bytes) / 
                                    (TIMESTAMPDIFF(MICROSECOND, b.time, a.time) / 1e6))
                            ELSE NULL
                        END AS read_bytes_s,
                        CASE 
                            WHEN b.time IS NOT NULL AND TIMESTAMPDIFF(MICROSECOND, b.time, a.time) > 0 THEN
                                GREATEST(0, (a.write_bytes - b.write_bytes) / 
                                    (TIMESTAMPDIFF(MICROSECOND, b.time, a.time) / 1e6))
                            ELSE NULL
                        END AS write_bytes_s
                    FROM last2 a
                    LEFT JOIN last2 b ON a.disk = b.disk AND a.rn = 1 AND b.rn = 2
                    WHERE a.rn = 1
                ),
                filtered_disks AS (
                    SELECT 
                        disk,
                        time,
                        read_bytes,
                        write_bytes,
                        read_bytes_s,
                        write_bytes_s,
                        COUNT(*) OVER() as total_count
                    FROM active_disks
                    WHERE 
                        -- Filter out loopback devices, RAM disks, and optical drives
                        disk NOT LIKE 'loop%%' 
                        AND disk NOT LIKE 'sr%%'
                        AND disk NOT LIKE 'ram%%'
                        AND disk NOT LIKE 'zram%%'
                )
                SELECT 
                    disk,
                    read_bytes,
                    write_bytes,
                    read_bytes_s,
                    write_bytes_s,
                    total_count
                FROM filtered_disks
                ORDER BY COALESCE(read_bytes_s, 0) + COALESCE(write_bytes_s, 0) DESC, disk
                LIMIT %s OFFSET %s
            """, (sysname, cutoff, per_page, offset))
            
            rows = serialize_rows(cur.fetchall())
            total_count = rows[0]['total_count'] if rows else 0
            
            # Remove total_count from data rows
            for row in rows:
                row.pop('total_count', None)
            
            result['disk_io'] = {
                'data': rows,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total_count,
                    'total_pages': (total_count + per_page - 1) // per_page
                }
            }
            
            return result

