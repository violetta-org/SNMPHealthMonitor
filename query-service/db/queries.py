from datetime import datetime, timedelta
import os
import logging
from typing import List, Dict, Any, Optional
from db.connection import get_db
from utils.serialize import serialize_row, serialize_rows
from utils.logging import configure_logger

logger = configure_logger(__name__)
logger.setLevel(logging.CRITICAL)


def calculate_group_interval(duration: timedelta) -> int:
    """
    Calculate aggregation interval in seconds based on time range duration.
    Target: 500-1000 data points for optimal chart rendering.
    
    Args:
        duration: Time range duration (end_time - start_time)
    
    Returns:
        interval_seconds: Aggregation interval in seconds
        - 0: Raw data (no aggregation)
        - 60: 1 minute buckets
        - 300: 5 minute buckets
        - 3600: 1 hour buckets
    """
    total_seconds = duration.total_seconds()
    
    if total_seconds < 3600:  # < 1 hour
        return 0  # Raw data
    elif total_seconds < 21600:  # < 6 hours
        return 60  # 1 minute buckets
    elif total_seconds < 86400:  # < 24 hours
        return 300  # 5 minute buckets
    else:  # >= 24 hours
        return 3600  # 1 hour buckets


def calculate_group_interval_dynamic(duration: timedelta, target_points: int = 500) -> int:
    """
    Calculate a dynamic aggregation interval in seconds targeting ~target_points.
    Returns 0 for raw data if total_seconds <= target_points.
    """
    total_seconds = max(1, int(duration.total_seconds()))
    if total_seconds <= target_points:
        return 0
    return max(1, int(round(total_seconds / float(target_points))))


 


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


def get_system_metrics(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """Get system info and load averages.
    
    Mode:
    - Snapshot (start_time=None): Latest system_info and load_avg
    - Range (start_time provided): All load_avg records in time range (with downsampling if needed)
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            result = {}
            
            # System info (static, no time range needed)
            cur.execute("""
                SELECT sysname, sys_location, sys_uptime
                FROM system_info
                WHERE sysname = %s
            """, (sysname,))
            result['system_info'] = serialize_row(cur.fetchone())
            
            # Load averages
            if start_time is None:
                # Snapshot Mode: Latest load average
                cur.execute("""
                        SELECT time, load_1m, load_5m, load_15m
                    FROM load_avg
                        WHERE sysname = %s
                    ORDER BY time DESC
                    LIMIT 1
                    """, (sysname,))
                result['load_avg'] = serialize_row(cur.fetchone())
            else:
                # Range Mode: All load averages in time range (with downsampling)
                end_time = end_time or datetime.now()
                duration = end_time - start_time
                interval = calculate_group_interval_dynamic(duration, target_points=500)
                
                if interval == 0:
                    # Raw data
                    cur.execute("""
                        SELECT time, load_1m, load_5m, load_15m
                        FROM load_avg
                        WHERE sysname = %s AND time >= %s AND time <= %s
                        ORDER BY time ASC
                    """, (sysname, start_time, end_time))
                else:
                    # Aggregated data
                    cur.execute(f"""
                        SELECT 
                            FROM_UNIXTIME((UNIX_TIMESTAMP(time) DIV {interval}) * {interval}) as time,
                            AVG(load_1m) as load_1m,
                            AVG(load_5m) as load_5m,
                            AVG(load_15m) as load_15m
                        FROM load_avg
                        WHERE sysname = %s AND time >= %s AND time <= %s
                        GROUP BY FROM_UNIXTIME((UNIX_TIMESTAMP(time) DIV {interval}) * {interval})
                        ORDER BY time ASC
                    """, (sysname, start_time, end_time))
                result['load_avg'] = serialize_rows(cur.fetchall())
            
            return result


def get_cpu_metrics(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """Get CPU metrics per core.
    
    Mode:
    - Snapshot (start_time=None): Latest CPU percent per core
    - Range (start_time provided): All CPU percent records in time range (with downsampling if needed)
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            result = {}
            
            if start_time is None:
                # Snapshot Mode: Latest CPU percent per core
                cur.execute("""
                        SELECT cpu, percent, time
                        FROM (
                            SELECT cpu, percent, time,
                            ROW_NUMBER() OVER (PARTITION BY cpu ORDER BY time DESC) AS rn
                            FROM cpu_percent
                            WHERE sysname = %s
                            ) ranked
                        WHERE rn = 1
                        ORDER BY cpu
                    """, (sysname,))
                result['cpu_percent'] = serialize_rows(cur.fetchall())
            else:
                # Range Mode: All CPU percent records in time range (with downsampling)
                end_time = end_time or datetime.now()
                duration = end_time - start_time
                interval = calculate_group_interval(duration)
                
                if interval == 0:
                    # Raw data
                    cur.execute("""
                        SELECT cpu, percent, time
                        FROM cpu_percent
                        WHERE sysname = %s AND time >= %s AND time <= %s
                        ORDER BY time ASC, cpu ASC
                    """, (sysname, start_time, end_time))
                else:
                    # Aggregated data: AVG percent per core per time bucket
                    cur.execute(f"""
                        SELECT 
                            cpu,
                            FROM_UNIXTIME((UNIX_TIMESTAMP(time) DIV {interval}) * {interval}) as time,
                            AVG(percent) as percent
                        FROM cpu_percent
                        WHERE sysname = %s AND time >= %s AND time <= %s
                        GROUP BY cpu, FROM_UNIXTIME((UNIX_TIMESTAMP(time) DIV {interval}) * {interval})
                        ORDER BY time ASC, cpu ASC
                    """, (sysname, start_time, end_time))
            result['cpu_percent'] = serialize_rows(cur.fetchall())
            
            return result


def get_memory_history(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Get memory history data for chart.
    
    If start_time is provided, returns all records in range (with downsampling if needed).
    Otherwise, returns latest N records (if limit specified).
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            if start_time is not None:
                # Range Mode: All records in time range (with dynamic downsampling ~500 points)
                end_time = end_time or datetime.now()
                duration = end_time - start_time
                interval = calculate_group_interval_dynamic(duration, target_points=500)
                
                if interval == 0:
                    # Raw data
                    cur.execute("""
                        SELECT time, used, cached, free, total
                        FROM memory
                        WHERE sysname = %s AND time >= %s AND time <= %s
                        ORDER BY time ASC
                    """, (sysname, start_time, end_time))
                else:
                    # Aggregated data: AVG values per time bucket (dynamic interval)
                    cur.execute(f"""
                        SELECT 
                            FROM_UNIXTIME((UNIX_TIMESTAMP(time) DIV {interval}) * {interval}) as time,
                            AVG(used) as used,
                            AVG(cached) as cached,
                            AVG(free) as free,
                            AVG(total) as total
                        FROM memory
                        WHERE sysname = %s AND time >= %s AND time <= %s
                        GROUP BY FROM_UNIXTIME((UNIX_TIMESTAMP(time) DIV {interval}) * {interval})
                        ORDER BY time ASC
                    """, (sysname, start_time, end_time))
                return serialize_rows(cur.fetchall())
            else:
                # Snapshot Mode: Latest N records
                if limit:
                    cur.execute("""
                        SELECT time, used, cached, free, total
                        FROM memory
                        WHERE sysname = %s
                        ORDER BY time DESC
                        LIMIT %s
                    """, (sysname, limit))
                else:
                    cur.execute("""
                        SELECT time, used, cached, free, total
                        FROM memory
                        WHERE sysname = %s
                        ORDER BY time DESC
                        LIMIT 60
                    """, (sysname,))
                rows = serialize_rows(cur.fetchall())
                return list(reversed(rows))  # Reverse để thời gian chạy từ cũ -> mới


def get_memory_percent_history(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Get memory percent history data for percentage chart.
    
    If start_time is provided, returns all records in range (with downsampling if needed).
    Otherwise, returns latest N records (if limit specified).
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            if start_time is not None:
                # Range Mode: All records in time range (with downsampling)
                end_time = end_time or datetime.now()
                duration = end_time - start_time
                interval = calculate_group_interval(duration)
                
                if interval == 0:
                    # Raw data
                    cur.execute("""
                        SELECT time, percent
                        FROM memory
                        WHERE sysname = %s AND time >= %s AND time <= %s
                        ORDER BY time ASC
                    """, (sysname, start_time, end_time))
                else:
                    # Aggregated data: AVG percent per dynamic time bucket
                    cur.execute(f"""
                        SELECT 
                            FROM_UNIXTIME((UNIX_TIMESTAMP(time) DIV {interval}) * {interval}) as time,
                            AVG(percent) as percent
                        FROM memory
                        WHERE sysname = %s AND time >= %s AND time <= %s
                        GROUP BY FROM_UNIXTIME((UNIX_TIMESTAMP(time) DIV {interval}) * {interval})
                        ORDER BY time ASC
                    """, (sysname, start_time, end_time))
                return serialize_rows(cur.fetchall())
            else:
                # Snapshot Mode: Latest N records
                if limit:
                    cur.execute("""
                        SELECT time, percent
                        FROM memory
                        WHERE sysname = %s
                        ORDER BY time DESC
                        LIMIT %s
                    """, (sysname, limit))
                else:
                    cur.execute("""
                        SELECT time, percent
                        FROM memory
                        WHERE sysname = %s
                        ORDER BY time DESC
                        LIMIT 200
                    """, (sysname,))
                rows = serialize_rows(cur.fetchall())
                return list(reversed(rows))  # Reverse để thời gian chạy từ cũ -> mới


def get_memory_metrics(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """Get memory and swap metrics.
    
    Mode:
    - Snapshot (start_time=None): Latest memory and swap records
    - Range (start_time provided): All memory and swap records in time range (with downsampling if needed)
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            result = {}
            
            if start_time is None:
                # Snapshot Mode: Latest memory record
                cur.execute("""
                        SELECT time, total, available, used, free, percent, 
                        buffers, cached, shared
                    FROM memory
                        WHERE sysname = %s
                    ORDER BY time DESC
                    LIMIT 1
                    """, (sysname,))
                result['memory'] = serialize_row(cur.fetchone())
            
                # Latest swap record
                cur.execute("""
                    SELECT time, total, used, free, percent
                FROM swap_memory
                    WHERE sysname = %s
                ORDER BY time DESC
                LIMIT 1
                """, (sysname,))
                result['swap'] = serialize_row(cur.fetchone())
            else:
                # Range Mode: All memory records in time range (with downsampling)
                end_time = end_time or datetime.now()
                duration = end_time - start_time
                interval = calculate_group_interval(duration)
                
                if interval == 0:
                    # Raw data
                    cur.execute("""
                        SELECT time, total, available, used, free, percent, 
                               buffers, cached, shared
                        FROM memory
                        WHERE sysname = %s AND time >= %s AND time <= %s
                        ORDER BY time ASC
                    """, (sysname, start_time, end_time))
                    memory_rows = serialize_rows(cur.fetchall())
                    
                    cur.execute("""
                        SELECT time, total, used, free, percent
                        FROM swap_memory
                        WHERE sysname = %s AND time >= %s AND time <= %s
                        ORDER BY time ASC
                    """, (sysname, start_time, end_time))
                    swap_rows = serialize_rows(cur.fetchall())
                else:
                    # Aggregated data: AVG values per time bucket
                    cur.execute(f"""
                        SELECT 
                            FROM_UNIXTIME((UNIX_TIMESTAMP(time) DIV {interval}) * {interval}) as time,
                            AVG(total) as total,
                            AVG(available) as available,
                            AVG(used) as used,
                            AVG(free) as free,
                            AVG(percent) as percent,
                            AVG(buffers) as buffers,
                            AVG(cached) as cached,
                            AVG(shared) as shared
                        FROM memory
                        WHERE sysname = %s AND time >= %s AND time <= %s
                        GROUP BY FROM_UNIXTIME((UNIX_TIMESTAMP(time) DIV {interval}) * {interval})
                        ORDER BY time ASC
                    """, (sysname, start_time, end_time))
                    memory_rows = serialize_rows(cur.fetchall())
                    
                    cur.execute(f"""
                        SELECT 
                            FROM_UNIXTIME((UNIX_TIMESTAMP(time) DIV {interval}) * {interval}) as time,
                            AVG(total) as total,
                            AVG(used) as used,
                            AVG(free) as free,
                            AVG(percent) as percent
                        FROM swap_memory
                        WHERE sysname = %s AND time >= %s AND time <= %s
                        GROUP BY FROM_UNIXTIME((UNIX_TIMESTAMP(time) DIV {interval}) * {interval})
                        ORDER BY time ASC
                    """, (sysname, start_time, end_time))
                    swap_rows = serialize_rows(cur.fetchall())
                
                result['memory'] = memory_rows if len(memory_rows) > 1 else (memory_rows[0] if memory_rows else None)
                result['swap'] = swap_rows if len(swap_rows) > 1 else (swap_rows[0] if swap_rows else None)
            
            return result


def get_network_metrics(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """Get network I/O metrics with calculated rates.
    
    Mode:
    - Snapshot (start_time=None): Latest network I/O with rates calculated from previous record
    - Range (start_time provided): All network I/O records with rates (with downsampling if needed)
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            result = {}
            
            if start_time is None:
                # Snapshot Mode: Latest network I/O with rates from previous record
                cur.execute("""
                    WITH last2 AS (
                        SELECT iface, time, bytes_sent, bytes_recv, if_admin_status, if_oper_status,
                            ROW_NUMBER() OVER (PARTITION BY iface ORDER BY time DESC) AS rn
                        FROM net_io_counters
                            WHERE sysname = %s
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
                    """, (sysname,))
                result['net_io'] = serialize_rows(cur.fetchall())
            else:
                # Range Mode: All network I/O records with rates (with downsampling)
                end_time = end_time or datetime.now()
                duration = end_time - start_time
                interval = calculate_group_interval(duration)
                
                if interval == 0:
                    # Raw data with LAG window function
                    cur.execute("""
                        WITH ranked AS (
                            SELECT 
                                iface AS interface,
                                time,
                                bytes_sent,
                                bytes_recv,
                                if_admin_status,
                                if_oper_status,
                                LAG(bytes_sent) OVER (PARTITION BY iface ORDER BY time) AS prev_bytes_sent,
                                LAG(bytes_recv) OVER (PARTITION BY iface ORDER BY time) AS prev_bytes_recv,
                                LAG(time) OVER (PARTITION BY iface ORDER BY time) AS prev_time
                            FROM net_io_counters
                            WHERE sysname = %s AND time >= %s AND time <= %s
                        )
                        SELECT 
                            interface,
                            time,
                            bytes_sent,
                            bytes_recv,
                            if_admin_status,
                            if_oper_status,
                            CASE 
                                WHEN prev_time IS NOT NULL AND TIMESTAMPDIFF(MICROSECOND, prev_time, time) > 0 THEN 
                                    GREATEST(0, (bytes_sent - prev_bytes_sent) / (TIMESTAMPDIFF(MICROSECOND, prev_time, time) / 1e6)) 
                                ELSE NULL
                            END AS send_bytes_s,
                            CASE 
                                WHEN prev_time IS NOT NULL AND TIMESTAMPDIFF(MICROSECOND, prev_time, time) > 0 THEN 
                                    GREATEST(0, (bytes_recv - prev_bytes_recv) / (TIMESTAMPDIFF(MICROSECOND, prev_time, time) / 1e6)) 
                                ELSE NULL
                            END AS recv_bytes_s
                        FROM ranked
                        ORDER BY time ASC, interface ASC
                    """, (sysname, start_time, end_time))
                else:
                    # Aggregated data: Calculate average rate per bucket
                    # For counters, we use (MAX - MIN) / interval to get rate per bucket
                    cur.execute(f"""
                        SELECT 
                            interface,
                            time_bucket as time,
                            MAX(bytes_sent) as bytes_sent,
                            MAX(bytes_recv) as bytes_recv,
                            MAX(if_admin_status) as if_admin_status,
                            MAX(if_oper_status) as if_oper_status,
                            CASE 
                                WHEN MIN(bytes_sent) IS NOT NULL AND MAX(bytes_sent) IS NOT NULL AND MAX(bytes_sent) >= MIN(bytes_sent) THEN
                                    GREATEST(0, (MAX(bytes_sent) - MIN(bytes_sent)) / {interval})
                                ELSE NULL
                            END AS send_bytes_s,
                            CASE 
                                WHEN MIN(bytes_recv) IS NOT NULL AND MAX(bytes_recv) IS NOT NULL AND MAX(bytes_recv) >= MIN(bytes_recv) THEN
                                    GREATEST(0, (MAX(bytes_recv) - MIN(bytes_recv)) / {interval})
                                ELSE NULL
                            END AS recv_bytes_s
                        FROM (
                            SELECT 
                                iface AS interface,
                                FROM_UNIXTIME((UNIX_TIMESTAMP(time) DIV {interval}) * {interval}) as time_bucket,
                                bytes_sent,
                                bytes_recv,
                                if_admin_status,
                                if_oper_status
                            FROM net_io_counters
                            WHERE sysname = %s AND time >= %s AND time <= %s
                        ) grouped
                        GROUP BY interface, time_bucket
                        ORDER BY time_bucket ASC, interface ASC
                    """, (sysname, start_time, end_time))
            result['net_io'] = serialize_rows(cur.fetchall())
            
            return result


def get_disk_metrics(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """Get disk usage metrics.
    
    Mode:
    - Snapshot (start_time=None): Latest disk usage per mount point
    - Range (start_time provided): All disk usage records in time range (with downsampling if needed)
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            result = {}
            
            if start_time is None:
                # Snapshot Mode: Latest disk usage per mount (filter only / and /boot/firmware, exclude tmpfs)
                cur.execute("""
                SELECT d1.mount, d1.device_partition,
                           d1.total, d1.used, d1.free, d1.percent, d1.time
                FROM disk_usage d1
                INNER JOIN (
                    SELECT mount, MAX(time) as max_time
                    FROM disk_usage
                        WHERE sysname = %s
                    GROUP BY mount
                ) d2 ON d1.mount = d2.mount AND d1.time = d2.max_time
                WHERE d1.sysname = %s
                  AND d1.mount IN ('/', '/boot/firmware')
                      AND d1.device_partition NOT LIKE 'tmpfs'
                      AND d1.device_partition NOT LIKE '%%tmpfs%%'
                """, (sysname, sysname))
                result['disk_usage'] = serialize_rows(cur.fetchall())
            else:
                # Range Mode: All disk usage records in time range (with downsampling)
                end_time = end_time or datetime.now()
                duration = end_time - start_time
                interval = calculate_group_interval(duration)
                
                if interval == 0:
                    # Raw data
                    cur.execute("""
                        SELECT mount, device_partition, time,
                               total, used, free, percent
                        FROM disk_usage
                        WHERE sysname = %s 
                          AND time >= %s AND time <= %s
                          AND mount IN ('/', '/boot/firmware')
                          AND device_partition NOT LIKE 'tmpfs'
                          AND device_partition NOT LIKE '%%tmpfs%%'
                        ORDER BY time ASC, mount ASC
                    """, (sysname, start_time, end_time))
                else:
                    # Aggregated data: MAX values per mount per time bucket (to see peaks)
                    cur.execute(f"""
                        SELECT 
                            mount,
                            device_partition,
                            FROM_UNIXTIME((UNIX_TIMESTAMP(time) DIV {interval}) * {interval}) as time,
                            MAX(total) as total,
                            MAX(used) as used,
                            MAX(free) as free,
                            MAX(percent) as percent
                        FROM disk_usage
                        WHERE sysname = %s 
                          AND time >= %s AND time <= %s
                          AND mount IN ('/', '/boot/firmware')
                          AND device_partition NOT LIKE 'tmpfs'
                          AND device_partition NOT LIKE '%%tmpfs%%'
                        GROUP BY mount, device_partition, FROM_UNIXTIME((UNIX_TIMESTAMP(time) DIV {interval}) * {interval})
                        ORDER BY time ASC, mount ASC
                    """, (sysname, start_time, end_time))
            result['disk_usage'] = serialize_rows(cur.fetchall())
            
            return result


def get_temperature_metrics(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """Get CPU temperature metrics.
    
    Mode:
    - Snapshot (start_time=None): Latest temperature
    - Range (start_time provided): All temperature records in time range (with downsampling if needed)
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            result = {}
            
            if start_time is None:
                # Snapshot Mode: Latest temperature
                cur.execute("""
                        SELECT time, cpu_temp
                    FROM temperature
                        WHERE sysname = %s
                    ORDER BY time DESC
                    LIMIT 1
                    """, (sysname,))
                row = cur.fetchone()
                result['temperature'] = serialize_row(row) if row else None
            else:
                # Range Mode: All temperature records in time range (with downsampling)
                end_time = end_time or datetime.now()
                duration = end_time - start_time
                interval = calculate_group_interval(duration)
                
                if interval == 0:
                    # Raw data
                    cur.execute("""
                        SELECT time, cpu_temp
                        FROM temperature
                        WHERE sysname = %s AND time >= %s AND time <= %s
                        ORDER BY time ASC
                    """, (sysname, start_time, end_time))
                    rows = serialize_rows(cur.fetchall())
                else:
                    # Aggregated data: AVG temperature per time bucket
                    cur.execute(f"""
                        SELECT 
                            FROM_UNIXTIME((UNIX_TIMESTAMP(time) DIV {interval}) * {interval}) as time,
                            AVG(cpu_temp) as cpu_temp
                        FROM temperature
                        WHERE sysname = %s AND time >= %s AND time <= %s
                        GROUP BY FROM_UNIXTIME((UNIX_TIMESTAMP(time) DIV {interval}) * {interval})
                        ORDER BY time ASC
                    """, (sysname, start_time, end_time))
                    rows = serialize_rows(cur.fetchall())
                
                result['temperature'] = rows if len(rows) > 1 else (rows[0] if rows else None)
            
            return result


def get_disk_io_metrics(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    page: int = 1,
    per_page: int = 10
) -> Dict[str, Any]:
    """Get disk I/O metrics with calculated speeds.
    
    Mode:
    - Snapshot (start_time=None): Latest disk I/O per disk with rates from previous record (paginated)
    - Range (start_time provided): All disk I/O records with rates (with downsampling if needed)
    
    Note: Pagination only applies in Snapshot Mode.
    """
    offset = (page - 1) * per_page
    
    with get_db() as conn:
        with conn.cursor() as cur:
            result = {}
            
            if start_time is None:
                # Snapshot Mode: Latest disk I/O with rates from previous record (paginated)
                cur.execute("""
                    WITH last2 AS (
                        SELECT disk, time, read_bytes, write_bytes,
                            ROW_NUMBER() OVER (PARTITION BY disk ORDER BY time DESC) AS rn
                        FROM disk_io_counters
                            WHERE sysname = %s
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
                    """, (sysname, per_page, offset))
                
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
            else:
                # Range Mode: All disk I/O records with rates (with downsampling)
                end_time = end_time or datetime.now()
                duration = end_time - start_time
                interval = calculate_group_interval(duration)
                
                if interval == 0:
                    # Raw data with LAG window function
                    cur.execute("""
                        WITH ranked AS (
                            SELECT 
                                disk,
                                time,
                                read_bytes,
                                write_bytes,
                                LAG(read_bytes) OVER (PARTITION BY disk ORDER BY time) AS prev_read_bytes,
                                LAG(write_bytes) OVER (PARTITION BY disk ORDER BY time) AS prev_write_bytes,
                                LAG(time) OVER (PARTITION BY disk ORDER BY time) AS prev_time
                            FROM disk_io_counters
                            WHERE sysname = %s 
                              AND time >= %s AND time <= %s
                              AND disk NOT LIKE 'loop%%' 
                              AND disk NOT LIKE 'sr%%'
                              AND disk NOT LIKE 'ram%%'
                              AND disk NOT LIKE 'zram%%'
                        )
                        SELECT 
                            disk,
                            time,
                            read_bytes,
                            write_bytes,
                            CASE 
                                WHEN prev_time IS NOT NULL AND TIMESTAMPDIFF(MICROSECOND, prev_time, time) > 0 THEN
                                    GREATEST(0, (read_bytes - prev_read_bytes) / 
                                        (TIMESTAMPDIFF(MICROSECOND, prev_time, time) / 1e6))
                                ELSE NULL
                            END AS read_bytes_s,
                            CASE 
                                WHEN prev_time IS NOT NULL AND TIMESTAMPDIFF(MICROSECOND, prev_time, time) > 0 THEN
                                    GREATEST(0, (write_bytes - prev_write_bytes) / 
                                        (TIMESTAMPDIFF(MICROSECOND, prev_time, time) / 1e6))
                                ELSE NULL
                            END AS write_bytes_s
                        FROM ranked
                        ORDER BY time ASC, disk ASC
                    """, (sysname, start_time, end_time))
                else:
                    # Aggregated data: Calculate average rate per bucket
                    # For counters, we use (MAX - MIN) / interval to get rate per bucket
                    cur.execute(f"""
                        SELECT 
                            disk,
                            time_bucket as time,
                            MAX(read_bytes) as read_bytes,
                            MAX(write_bytes) as write_bytes,
                            CASE 
                                WHEN MIN(read_bytes) IS NOT NULL AND MAX(read_bytes) IS NOT NULL AND MAX(read_bytes) >= MIN(read_bytes) THEN
                                    GREATEST(0, (MAX(read_bytes) - MIN(read_bytes)) / {interval})
                                ELSE NULL
                            END AS read_bytes_s,
                            CASE 
                                WHEN MIN(write_bytes) IS NOT NULL AND MAX(write_bytes) IS NOT NULL AND MAX(write_bytes) >= MIN(write_bytes) THEN
                                    GREATEST(0, (MAX(write_bytes) - MIN(write_bytes)) / {interval})
                                ELSE NULL
                            END AS write_bytes_s
                        FROM (
                            SELECT 
                                disk,
                                FROM_UNIXTIME((UNIX_TIMESTAMP(time) DIV {interval}) * {interval}) as time_bucket,
                                read_bytes,
                                write_bytes
                            FROM disk_io_counters
                            WHERE sysname = %s 
                              AND time >= %s AND time <= %s
                              AND disk NOT LIKE 'loop%%' 
                              AND disk NOT LIKE 'sr%%'
                              AND disk NOT LIKE 'ram%%'
                              AND disk NOT LIKE 'zram%%'
                        ) grouped
                        GROUP BY disk, time_bucket
                        ORDER BY time_bucket ASC, disk ASC
                    """, (sysname, start_time, end_time))
                
                rows = serialize_rows(cur.fetchall())
                result['disk_io'] = {
                    'data': rows,
                    'pagination': {
                        'page': 1,
                        'per_page': len(rows),
                        'total': len(rows),
                        'total_pages': 1
                    }
                }
            
            return result


def get_status_metrics(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """Aggregate minimal status metrics without disk usage.
    
    This is the main aggregator function that:
    1. Fetches device_info once (optimized)
    2. Calls individual metric functions
    3. Returns combined dictionary
    
    Mode:
    - Snapshot (start_time=None): Latest metrics for dashboard
    - Range (start_time provided): Historical metrics for charts (with automatic downsampling)
    """
    print(f"[DEBUG] get_status_metrics: Aggregating status for {sysname}, start_time={start_time}, end_time={end_time}")
    
    try:
        status: Dict[str, Any] = {}
        
        # Fetch device_info once at aggregation level (optimized)
        status['device_info'] = get_device_info(sysname)
        
        # Fetch individual metrics
        system_part = get_system_metrics(sysname, start_time=start_time, end_time=end_time)
        memory_part = get_memory_metrics(sysname, start_time=start_time, end_time=end_time)
        cpu_part = get_cpu_metrics(sysname, start_time=start_time, end_time=end_time)
        temperature_part = get_temperature_metrics(sysname, start_time=start_time, end_time=end_time)
        memory_history = get_memory_history(sysname, start_time=start_time, end_time=end_time)
        memory_percent_history = get_memory_percent_history(sysname, start_time=start_time, end_time=end_time)

        # History: return DB results as-is. Do not generate or backfill dummy points.
        # Merge parts (keys are distinct: system_info, load_avg, memory, swap, cpu_percent, temperature)
        status.update(system_part or {})
        status.update(memory_part or {})
        status.update(cpu_part or {})
        status['memory_history'] = memory_history
        status['memory_percent_history'] = memory_percent_history
        
        # Merge temperature (overwrite device_info if exists, but that's fine)
        if temperature_part.get('temperature'):
            status['temperature'] = temperature_part['temperature']
        
        print(f"[DEBUG] get_status_metrics: Aggregation complete with keys={list(status.keys())}")
        #print the whole data to check if null
        logger.debug(status)
        return status
    except Exception as e:
        print(f"[DEBUG] get_status_metrics: Error during aggregation: {e}")
        import traceback
        traceback.print_exc()
        return {}
