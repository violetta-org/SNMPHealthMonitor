"""
Metrics business logic services.
Ported from: query-service/services/topic_service.py

Provides async query functions for metric data retrieval using Django ORM.
Uses raw SQL for complex queries that require window functions and aggregations.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

from django.db import connection
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def local_now() -> datetime:
    """Get current local time."""
    return datetime.now()


def calculate_group_interval_dynamic(duration: timedelta, target_points: int = 500) -> int:
    """
    Calculate the grouping interval for downsampling.
    Returns 0 if no downsampling needed.
    """
    total_seconds = max(1, int(duration.total_seconds()))
    if total_seconds <= target_points:
        return 0
    interval = max(1, int(round(total_seconds / float(target_points))))
    if interval < 60:
        return 0
    return interval


def resolve_time_range(
    start_time: Optional[datetime],
    end_time: Optional[datetime],
    target_points: int = 500
) -> tuple[Optional[datetime], int]:
    """Resolve time range and calculate downsampling interval."""
    if start_time is None:
        return None, 0
    end_time = end_time or local_now()
    interval = calculate_group_interval_dynamic(end_time - start_time, target_points)
    return end_time, interval


def serialize_row(row: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """Convert datetime objects to ISO format strings."""
    if not row:
        return row
    result = {}
    for key, value in row.items():
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


def serialize_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert datetime objects in multiple rows to ISO format strings."""
    return [serialize_row(row) for row in rows if row]


def normalize_list(val: Union[List, Dict, None]) -> List:
    """Normalize a value to a list for ApexCharts consumption."""
    if val is None:
        return []
    if isinstance(val, dict):
        return [val]
    return val


def dictfetchall(cursor) -> List[Dict[str, Any]]:
    """Return all rows from a cursor as a list of dicts."""
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def dictfetchone(cursor) -> Optional[Dict[str, Any]]:
    """Return one row from a cursor as a dict."""
    row = cursor.fetchone()
    if row is None:
        return None
    columns = [col[0] for col in cursor.description]
    return dict(zip(columns, row))


# =============================================================================
# SQL FRAGMENTS (from query-service/db/queries.py)
# =============================================================================

NON_LOOPBACK_IFACE_SQL = """
iface NOT IN ('lo','lo0')
AND iface NOT LIKE 'docker%%'
AND iface NOT LIKE 'veth%%'
AND iface NOT LIKE 'br-%%'
AND iface NOT LIKE 'virbr%%'
AND iface NOT LIKE 'wg%%'
AND iface NOT LIKE 'zt%%'
AND (iface LIKE 'e%%' OR iface LIKE 'w%%')
"""

RATE_SQL = """
CASE
  WHEN prev_val IS NULL THEN NULL
  WHEN curr_val < prev_val THEN NULL
  WHEN dt_us <= 0 THEN NULL
  ELSE (curr_val - prev_val) / (dt_us / 1e6)
END
"""


# =============================================================================
# DEVICE INFO
# =============================================================================

def _get_device_info_sync(sysname: str) -> Dict[str, Any]:
    """Get device online status and metadata."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT online, last_seen, ip_address
            FROM devices
            WHERE sysname = %s
        """, [sysname])
        row = dictfetchone(cursor)
        if not row:
            return {'online': False, 'last_seen': None, 'ip_address': None}
        return {
            'online': bool(row['online']),
            'last_seen': row['last_seen'].isoformat() if row['last_seen'] else None,
            'ip_address': row['ip_address']
        }


async def get_device_info(sysname: str) -> Dict[str, Any]:
    """Async wrapper for device info."""
    return await sync_to_async(_get_device_info_sync)(sysname)


# =============================================================================
# SYSTEM METRICS
# =============================================================================

def _get_system_metrics_sync(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """Get system info and load averages."""
    with connection.cursor() as cursor:
        result = {}
        
        # System info (static)
        cursor.execute("""
            SELECT sysname, sys_location, sys_uptime
            FROM system_info
            WHERE sysname = %s
        """, [sysname])
        result['system_info'] = serialize_row(dictfetchone(cursor))
        
        if start_time is None:
            # Snapshot Mode
            cursor.execute("""
                SELECT time, load_1m, load_5m, load_15m
                FROM load_avg
                WHERE sysname = %s
                ORDER BY time DESC
                LIMIT 1
            """, [sysname])
            result['load_avg'] = serialize_row(dictfetchone(cursor))
        else:
            # Range Mode
            end_time = end_time or local_now()
            duration = end_time - start_time
            interval = calculate_group_interval_dynamic(duration, target_points=500)
            
            if interval == 0:
                cursor.execute("""
                    SELECT time, load_1m, load_5m, load_15m
                    FROM load_avg
                    WHERE sysname = %s AND time >= %s AND time <= %s
                    ORDER BY time ASC
                """, [sysname, start_time, end_time])
            else:
                cursor.execute(f"""
                    SELECT 
                        FROM_UNIXTIME(UNIX_TIMESTAMP(time) DIV {interval} * {interval}) as time,
                        AVG(load_1m) as load_1m,
                        AVG(load_5m) as load_5m,
                        AVG(load_15m) as load_15m
                    FROM load_avg
                    WHERE sysname = %s AND time >= %s AND time <= %s
                    GROUP BY FROM_UNIXTIME(UNIX_TIMESTAMP(time) DIV {interval} * {interval})
                    ORDER BY time ASC
                """, [sysname, start_time, end_time])
            result['load_avg'] = serialize_rows(dictfetchall(cursor))
        
        return result


async def get_system_metrics(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """Async wrapper for system metrics."""
    return await sync_to_async(_get_system_metrics_sync)(sysname, start_time, end_time)


# =============================================================================
# CPU METRICS
# =============================================================================

def _get_cpu_metrics_sync(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """Get CPU percentage metrics."""
    with connection.cursor() as cursor:
        if start_time is None:
            # Snapshot Mode
            cursor.execute("""
                SELECT cpu, percent, time
                FROM (
                    SELECT cpu, percent, time,
                           ROW_NUMBER() OVER (PARTITION BY cpu ORDER BY time DESC) rn
                    FROM cpu_percent
                    WHERE sysname = %s
                ) x WHERE rn = 1
                ORDER BY cpu
            """, [sysname])
            return {'cpu_percent': serialize_rows(dictfetchall(cursor))}
        
        # Range Mode
        end_time, interval = resolve_time_range(start_time, end_time)
        
        if interval == 0:
            cursor.execute("""
                SELECT cpu, time, percent
                FROM cpu_percent
                WHERE sysname = %s AND time BETWEEN %s AND %s
                ORDER BY time, cpu
            """, [sysname, start_time, end_time])
        else:
            cursor.execute(f"""
                SELECT
                    cpu,
                    FROM_UNIXTIME(UNIX_TIMESTAMP(time) DIV {interval} * {interval}) time,
                    AVG(percent) AS percent
                FROM cpu_percent
                WHERE sysname = %s AND time BETWEEN %s AND %s
                GROUP BY cpu, FROM_UNIXTIME(UNIX_TIMESTAMP(time) DIV {interval} * {interval})
                ORDER BY time, cpu
            """, [sysname, start_time, end_time])
        
        return {'cpu_percent': serialize_rows(dictfetchall(cursor))}


async def get_cpu_metrics(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """Async wrapper for CPU metrics."""
    return await sync_to_async(_get_cpu_metrics_sync)(sysname, start_time, end_time)


# =============================================================================
# MEMORY METRICS
# =============================================================================

def _get_memory_metrics_sync(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """Get memory and swap metrics."""
    with connection.cursor() as cursor:
        result = {}
        
        if start_time is None:
            # Snapshot Mode
            cursor.execute("""
                SELECT time, total, available, used, free, percent, 
                       buffers, cached, shared
                FROM memory
                WHERE sysname = %s
                ORDER BY time DESC
                LIMIT 1
            """, [sysname])
            result['memory'] = serialize_row(dictfetchone(cursor))
            
            cursor.execute("""
                SELECT time, total, used, free, percent
                FROM swap_memory
                WHERE sysname = %s
                ORDER BY time DESC
                LIMIT 1
            """, [sysname])
            result['swap'] = serialize_row(dictfetchone(cursor))
        else:
            # Range Mode
            end_time = end_time or local_now()
            duration = end_time - start_time
            interval = calculate_group_interval_dynamic(duration)
            
            if interval == 0:
                cursor.execute("""
                    SELECT time, total, available, used, free, percent, 
                           buffers, cached, shared
                    FROM memory
                    WHERE sysname = %s AND time >= %s AND time <= %s
                    ORDER BY time ASC
                """, [sysname, start_time, end_time])
                memory_rows = serialize_rows(dictfetchall(cursor))
                
                cursor.execute("""
                    SELECT time, total, used, free, percent
                    FROM swap_memory
                    WHERE sysname = %s AND time >= %s AND time <= %s
                    ORDER BY time ASC
                """, [sysname, start_time, end_time])
                swap_rows = serialize_rows(dictfetchall(cursor))
            else:
                cursor.execute(f"""
                    SELECT 
                        FROM_UNIXTIME(UNIX_TIMESTAMP(time) DIV {interval} * {interval}) as time,
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
                    GROUP BY FROM_UNIXTIME(UNIX_TIMESTAMP(time) DIV {interval} * {interval})
                    ORDER BY time ASC
                """, [sysname, start_time, end_time])
                memory_rows = serialize_rows(dictfetchall(cursor))
                
                cursor.execute(f"""
                    SELECT 
                        FROM_UNIXTIME(UNIX_TIMESTAMP(time) DIV {interval} * {interval}) as time,
                        AVG(total) as total,
                        AVG(used) as used,
                        AVG(free) as free,
                        AVG(percent) as percent
                    FROM swap_memory
                    WHERE sysname = %s AND time >= %s AND time <= %s
                    GROUP BY FROM_UNIXTIME(UNIX_TIMESTAMP(time) DIV {interval} * {interval})
                    ORDER BY time ASC
                """, [sysname, start_time, end_time])
                swap_rows = serialize_rows(dictfetchall(cursor))
            
            result['memory'] = memory_rows if len(memory_rows) > 1 else (memory_rows[0] if memory_rows else None)
            result['swap'] = swap_rows if len(swap_rows) > 1 else (swap_rows[0] if swap_rows else None)
        
        return result


async def get_memory_metrics(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """Async wrapper for memory metrics."""
    return await sync_to_async(_get_memory_metrics_sync)(sysname, start_time, end_time)


# =============================================================================
# NETWORK METRICS
# =============================================================================

def _get_network_metrics_sync(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """Get network I/O metrics."""
    with connection.cursor() as cursor:
        # Snapshot Mode
        if start_time is None:
            cursor.execute(f"""
                WITH ranked AS (
                    SELECT
                        iface,
                        time,
                        bytes_sent AS curr_val,
                        bytes_recv,
                        if_admin_status,
                        if_oper_status,
                        LAG(bytes_sent) OVER (PARTITION BY iface ORDER BY time) prev_val,
                        LAG(bytes_recv) OVER (PARTITION BY iface ORDER BY time) prev_recv,
                        TIMESTAMPDIFF(
                            MICROSECOND,
                            LAG(time) OVER (PARTITION BY iface ORDER BY time),
                            time
                        ) dt_us,
                        ROW_NUMBER() OVER (PARTITION BY iface ORDER BY time DESC) rn
                    FROM net_io_counters
                    WHERE sysname = %s AND {NON_LOOPBACK_IFACE_SQL}
                )
                SELECT
                    iface AS interface,
                    time,
                    curr_val AS bytes_sent,
                    bytes_recv,
                    if_admin_status,
                    if_oper_status,
                    {RATE_SQL} AS send_bytes_s,
                    CASE
                        WHEN prev_recv IS NULL
                        OR bytes_recv < prev_recv
                        OR dt_us <= 0
                        THEN NULL
                        ELSE (bytes_recv - prev_recv) / (dt_us / 1e6)
                    END AS recv_bytes_s
                FROM ranked
                WHERE rn = 1
            """, [sysname])
            return {'network': serialize_rows(dictfetchall(cursor))}
        
        # Range Mode
        end_time, interval = resolve_time_range(start_time, end_time)
        
        if interval == 0:
            cursor.execute(f"""
                WITH r AS (
                    SELECT
                        iface,
                        time,
                        bytes_sent AS curr_val,
                        bytes_recv AS curr_recv,
                        LAG(bytes_sent) OVER (PARTITION BY iface ORDER BY time) prev_val,
                        LAG(bytes_recv) OVER (PARTITION BY iface ORDER BY time) prev_recv,
                        TIMESTAMPDIFF(
                            MICROSECOND,
                            LAG(time) OVER (PARTITION BY iface ORDER BY time),
                            time
                        ) dt_us
                    FROM net_io_counters
                    WHERE sysname = %s AND time BETWEEN %s AND %s
                      AND {NON_LOOPBACK_IFACE_SQL}
                )
                SELECT 
                    iface, 
                    time, 
                    {RATE_SQL} AS send_bytes_s,
                    CASE
                        WHEN prev_recv IS NULL THEN NULL
                        WHEN curr_recv < prev_recv THEN NULL
                        WHEN dt_us <= 0 THEN NULL
                        ELSE (curr_recv - prev_recv) / (dt_us / 1e6)
                    END AS recv_bytes_s
                FROM r
                ORDER BY time, iface
            """, [sysname, start_time, end_time])
        else:
            cursor.execute(f"""
                SELECT bucket AS time,
                       SUM(send_rate) AS send_bytes_s,
                       SUM(recv_rate) AS recv_bytes_s
                FROM (
                    SELECT
                        iface,
                        FROM_UNIXTIME(UNIX_TIMESTAMP(time) DIV {interval} * {interval}) bucket,
                        CASE
                            WHEN MAX(bytes_sent) < MIN(bytes_sent) THEN NULL
                            ELSE (MAX(bytes_sent) - MIN(bytes_sent)) / {interval}
                        END AS send_rate,
                        CASE
                            WHEN MAX(bytes_recv) < MIN(bytes_recv) THEN NULL
                            ELSE (MAX(bytes_recv) - MIN(bytes_recv)) / {interval}
                        END AS recv_rate
                    FROM net_io_counters
                    WHERE sysname = %s AND time BETWEEN %s AND %s
                      AND {NON_LOOPBACK_IFACE_SQL}
                    GROUP BY iface, bucket
                ) x
                GROUP BY bucket
                ORDER BY bucket
            """, [sysname, start_time, end_time])
        
        return {'network': serialize_rows(dictfetchall(cursor))}


async def get_network_metrics(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """Async wrapper for network metrics."""
    return await sync_to_async(_get_network_metrics_sync)(sysname, start_time, end_time)


# =============================================================================
# DISK METRICS
# =============================================================================

def _get_disk_metrics_sync(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """Get disk usage metrics."""
    with connection.cursor() as cursor:
        result = {}
        
        if start_time is None:
            # Snapshot Mode
            cursor.execute("""
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
            """, [sysname, sysname])
            result['disk_usage'] = serialize_rows(dictfetchall(cursor))
        else:
            # Range Mode
            end_time = end_time or local_now()
            duration = end_time - start_time
            interval = calculate_group_interval_dynamic(duration)
            
            if interval == 0:
                cursor.execute("""
                    SELECT mount, device_partition, time,
                           total, used, free, percent
                    FROM disk_usage
                    WHERE sysname = %s 
                      AND time >= %s AND time <= %s
                      AND mount IN ('/', '/boot/firmware')
                      AND device_partition NOT LIKE 'tmpfs'
                      AND device_partition NOT LIKE '%%tmpfs%%'
                    ORDER BY time ASC, mount ASC
                """, [sysname, start_time, end_time])
            else:
                cursor.execute(f"""
                    SELECT 
                        mount,
                        device_partition,
                        FROM_UNIXTIME(UNIX_TIMESTAMP(time) DIV {interval} * {interval}) as time,
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
                    GROUP BY mount, device_partition, FROM_UNIXTIME(UNIX_TIMESTAMP(time) DIV {interval} * {interval})
                    ORDER BY time ASC, mount ASC
                """, [sysname, start_time, end_time])
            result['disk_usage'] = serialize_rows(dictfetchall(cursor))
        
        return result


async def get_disk_metrics(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """Async wrapper for disk metrics."""
    return await sync_to_async(_get_disk_metrics_sync)(sysname, start_time, end_time)


# =============================================================================
# DISK I/O METRICS
# =============================================================================

def _get_disk_io_metrics_sync(
    sysname: str,
    page: int = 1,
    per_page: int = 10,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """Get disk I/O metrics with rate calculation."""
    offset = (page - 1) * per_page
    
    with connection.cursor() as cursor:
        # Snapshot Mode
        if start_time is None:
            cursor.execute("""
                WITH ranked AS (
                    SELECT
                        disk,
                        time,
                        read_bytes,
                        write_bytes,
                        LAG(read_bytes) OVER (PARTITION BY disk ORDER BY time) prev_read,
                        LAG(write_bytes) OVER (PARTITION BY disk ORDER BY time) prev_write,
                        LAG(time) OVER (PARTITION BY disk ORDER BY time) prev_time,
                        ROW_NUMBER() OVER (PARTITION BY disk ORDER BY time DESC) rn
                    FROM disk_io_counters
                    WHERE sysname = %s
                      AND (
                            disk NOT REGEXP '[0-9]+$'
                        OR 
                            disk LIKE 'mmcblk%%'
                      )
                      AND disk NOT LIKE '%%p[0-9]%%'
                ),
                latest AS (
                    SELECT *, COUNT(*) OVER() AS total_count
                    FROM ranked
                    WHERE rn = 1
                )
                SELECT
                    disk,
                    time,
                    read_bytes,
                    write_bytes,
                    CASE
                        WHEN prev_read IS NULL
                        OR read_bytes < prev_read
                        OR TIMESTAMPDIFF(MICROSECOND, prev_time, time) <= 0
                        THEN NULL
                        ELSE (read_bytes - prev_read) /
                             (TIMESTAMPDIFF(MICROSECOND, prev_time, time) / 1e6)
                    END AS read_bytes_s,
                    CASE
                        WHEN prev_write IS NULL
                        OR write_bytes < prev_write
                        OR TIMESTAMPDIFF(MICROSECOND, prev_time, time) <= 0
                        THEN NULL
                        ELSE (write_bytes - prev_write) /
                             (TIMESTAMPDIFF(MICROSECOND, prev_time, time) / 1e6)
                    END AS write_bytes_s,
                    total_count
                FROM latest
                ORDER BY (COALESCE(read_bytes_s,0)+COALESCE(write_bytes_s,0)) DESC
                LIMIT %s OFFSET %s
            """, [sysname, per_page, offset])
            
            rows = serialize_rows(dictfetchall(cursor))
            total = rows[0]['total_count'] if rows else 0
            for r in rows:
                r.pop('total_count', None)
            
            return {
                "disk_io": {
                    "data": rows,
                    "pagination": {
                        "page": page,
                        "per_page": per_page,
                        "total": total,
                        "total_pages": (total + per_page - 1) // per_page if total > 0 else 0
                    }
                }
            }
        
        # Range Mode
        end_time, interval = resolve_time_range(start_time, end_time)
        
        if interval == 0:
            cursor.execute("""
                WITH r AS (
                    SELECT
                        disk,
                        time,
                        read_bytes,
                        write_bytes,
                        LAG(read_bytes) OVER (PARTITION BY disk ORDER BY time) prev_read,
                        LAG(write_bytes) OVER (PARTITION BY disk ORDER BY time) prev_write,
                        TIMESTAMPDIFF(
                            MICROSECOND,
                            LAG(time) OVER (PARTITION BY disk ORDER BY time),
                            time
                        ) dt_us
                    FROM disk_io_counters
                    WHERE sysname = %s
                      AND time BETWEEN %s AND %s
                      AND disk NOT REGEXP '[0-9]+$'
                      AND disk NOT LIKE '%%p[0-9]%%'
                )
                SELECT
                    disk,
                    time,
                    read_bytes,
                    write_bytes,
                    CASE
                        WHEN prev_read IS NULL OR read_bytes < prev_read OR dt_us <= 0 THEN NULL
                        ELSE (read_bytes - prev_read) / (dt_us / 1e6)
                    END read_bytes_s,
                    CASE
                        WHEN prev_write IS NULL OR write_bytes < prev_write OR dt_us <= 0 THEN NULL
                        ELSE (write_bytes - prev_write) / (dt_us / 1e6)
                    END write_bytes_s
                FROM r
                ORDER BY time, disk
            """, [sysname, start_time, end_time])
        else:
            cursor.execute(f"""
                SELECT
                    disk,
                    bucket AS time,
                    CASE
                        WHEN MAX(read_bytes) < MIN(read_bytes)
                        THEN NULL
                        ELSE (MAX(read_bytes) - MIN(read_bytes)) / {interval}
                    END AS read_bytes_s,
                    CASE
                        WHEN MAX(write_bytes) < MIN(write_bytes)
                        THEN NULL
                        ELSE (MAX(write_bytes) - MIN(write_bytes)) / {interval}
                    END AS write_bytes_s
                FROM (
                    SELECT
                        disk,
                        FROM_UNIXTIME(UNIX_TIMESTAMP(time) DIV {interval} * {interval}) bucket,
                        read_bytes,
                        write_bytes
                    FROM disk_io_counters
                    WHERE sysname = %s
                      AND time BETWEEN %s AND %s
                      AND disk NOT REGEXP '[0-9]+$'
                      AND disk NOT LIKE '%%p[0-9]%%'
                ) t
                GROUP BY disk, bucket
                ORDER BY bucket, disk
            """, [sysname, start_time, end_time])
        
        return {"disk_io": serialize_rows(dictfetchall(cursor))}


async def get_disk_io_metrics(
    sysname: str,
    page: int = 1,
    per_page: int = 10,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """Async wrapper for disk I/O metrics."""
    return await sync_to_async(_get_disk_io_metrics_sync)(
        sysname, page, per_page, start_time, end_time
    )


# =============================================================================
# TEMPERATURE METRICS
# =============================================================================

def _get_temperature_metrics_sync(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """Get CPU temperature metrics."""
    with connection.cursor() as cursor:
        result = {}
        
        if start_time is None:
            # Snapshot Mode
            cursor.execute("""
                SELECT time, cpu_temp
                FROM temperature
                WHERE sysname = %s
                ORDER BY time DESC
                LIMIT 1
            """, [sysname])
            row = dictfetchone(cursor)
            result['temperature'] = serialize_row(row) if row else None
        else:
            # Range Mode
            end_time = end_time or local_now()
            duration = end_time - start_time
            interval = calculate_group_interval_dynamic(duration)
            
            if interval == 0:
                cursor.execute("""
                    SELECT time, cpu_temp
                    FROM temperature
                    WHERE sysname = %s AND time >= %s AND time <= %s
                    ORDER BY time ASC
                """, [sysname, start_time, end_time])
                rows = serialize_rows(dictfetchall(cursor))
            else:
                cursor.execute(f"""
                    SELECT 
                        FROM_UNIXTIME(UNIX_TIMESTAMP(time) DIV {interval} * {interval}) as time,
                        AVG(cpu_temp) as cpu_temp
                    FROM temperature
                    WHERE sysname = %s AND time >= %s AND time <= %s
                    GROUP BY FROM_UNIXTIME(UNIX_TIMESTAMP(time) DIV {interval} * {interval})
                    ORDER BY time ASC
                """, [sysname, start_time, end_time])
                rows = serialize_rows(dictfetchall(cursor))
            
            result['temperature'] = rows if len(rows) > 1 else (rows[0] if rows else None)
        
        return result


async def get_temperature_metrics(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """Async wrapper for temperature metrics."""
    return await sync_to_async(_get_temperature_metrics_sync)(sysname, start_time, end_time)


# =============================================================================
# STATUS METRICS (combined system status)
# =============================================================================

def _get_status_metrics_sync(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """Get combined status metrics (system + CPU + memory + temp)."""
    result = {}
    
    # System info and load avg
    sys_data = _get_system_metrics_sync(sysname, start_time, end_time)
    result.update(sys_data)
    
    # CPU metrics
    cpu_data = _get_cpu_metrics_sync(sysname, start_time, end_time)
    result.update(cpu_data)
    
    # Memory metrics
    mem_data = _get_memory_metrics_sync(sysname, start_time, end_time)
    result.update(mem_data)
    
    # Temperature
    temp_data = _get_temperature_metrics_sync(sysname, start_time, end_time)
    result.update(temp_data)
    
    return result


async def get_status_metrics(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """Async wrapper for status metrics."""
    return await sync_to_async(_get_status_metrics_sync)(sysname, start_time, end_time)


# =============================================================================
# TOPIC SERVICE (main entry point)
# =============================================================================

async def get_topic_data(
    sysname: str,
    topic: str,
    page: int = 1,
    per_page: int = 10,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Fetch data for a specific topic with automatic downsampling.
    
    Ported from: query-service/services/topic_service.py
    
    Args:
        sysname: System name
        topic: Topic name (systemstatus, network, disk, diskio)
        page: Page number for pagination (diskio only, Snapshot Mode only)
        per_page: Items per page (diskio only, Snapshot Mode only)
        start_time: Start time for Range Mode queries
        end_time: End time for Range Mode queries
    
    Note: 
    - If start_time is provided, Range Mode is used (historical data with downsampling)
    - Otherwise, Snapshot Mode is used (latest data for real-time dashboard)
    """
    try:
        if topic == "systemstatus":
            data = await get_status_metrics(sysname, start_time, end_time)
            data['device_info'] = await get_device_info(sysname)
            return data
        elif topic == "network":
            data = await get_network_metrics(sysname, start_time, end_time)
            data['device_info'] = await get_device_info(sysname)
            return data
        elif topic == "disk":
            data = await get_disk_metrics(sysname, start_time, end_time)
            data['device_info'] = await get_device_info(sysname)
            return data
        elif topic == "diskio":
            data = await get_disk_io_metrics(
                sysname,
                page=page,
                per_page=per_page,
                start_time=start_time,
                end_time=end_time
            )
            data['device_info'] = await get_device_info(sysname)
            return data
        else:
            logger.warning(f"[TopicService] Unknown topic: {topic}")
            return {}
    except Exception as e:
        logger.error(f"[TopicService] Error fetching {topic} data: {e}", exc_info=True)
        return {}

