from datetime import datetime, timedelta
import logging
from typing import List, Dict, Any, Optional
from db.connection import get_db
from utils.serialize import serialize_row, serialize_rows
from utils.logging import configure_logger


logger = configure_logger(__name__)
logger.setLevel(logging.CRITICAL)

# ===============================
# Canonical helpers
# ===============================

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



def local_now():
    return datetime.now()


def calculate_group_interval_dynamic(duration: timedelta, target_points: int = 500) -> int:
    total_seconds = max(1, int(duration.total_seconds()))
    if total_seconds <= target_points:
        return 0
    return max(1, int(round(total_seconds / float(target_points))))


def resolve_time_range(start_time, end_time, target_points=500):
    if start_time is None:
        return None, 0
    end_time = end_time or local_now()
    interval = calculate_group_interval_dynamic(end_time - start_time, target_points)
    return end_time, interval


 

# -----------------------------
# Device info
# -----------------------------
def get_device_info(sysname: str) -> Dict[str, Any]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT online, last_seen, ip_address
                FROM devices
                WHERE sysname = %s
            """, (sysname,))
            row = cur.fetchone()
            if not row:
                return {'online': False, 'last_seen': None, 'ip_address': None}

            return {
                'online': bool(row['online']),
                'last_seen': row['last_seen'].isoformat() if row['last_seen'] else None,
                'ip_address': row['ip_address']
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
                end_time = end_time or local_now()
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
                            FROM_UNIXTIME(
                            UNIX_TIMESTAMP(CONVERT_TZ(time,'+00:00','+00:00')) DIV {interval} * {interval}) as time,
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


# -----------------------------
# CPU metrics (FIXED)
# -----------------------------
def get_cpu_metrics(sysname, start_time=None, end_time=None):
    with get_db() as conn:
        with conn.cursor() as cur:
            if start_time is None:
                cur.execute("""
                    SELECT cpu, percent, time
                    FROM (
                      SELECT cpu, percent, time,
                             ROW_NUMBER() OVER (PARTITION BY cpu ORDER BY time DESC) rn
                      FROM cpu_percent
                      WHERE sysname = %s
                    ) x WHERE rn = 1
                    ORDER BY cpu
                """, (sysname,))
                return {'cpu_percent': serialize_rows(cur.fetchall())}

            end_time, interval = resolve_time_range(start_time, end_time)

            if interval == 0:
                cur.execute("""
                    SELECT cpu, time, percent
                    FROM cpu_percent
                    WHERE sysname=%s AND time BETWEEN %s AND %s
                    ORDER BY time, cpu
                """, (sysname, start_time, end_time))
            else:
                # FIX: CPU is GAUGE → AVG, not MAX
                cur.execute(f"""
                    SELECT
                      cpu,
                      FROM_UNIXTIME(UNIX_TIMESTAMP(time) DIV {interval} * {interval}) time,
                      AVG(percent) AS percent
                    FROM cpu_percent
                    WHERE sysname=%s AND time BETWEEN %s AND %s
                    GROUP BY cpu, time
                    ORDER BY time, cpu
                """, (sysname, start_time, end_time))

            return {'cpu_percent': serialize_rows(cur.fetchall())}


def get_cpu_avg_history(sysname: str, start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
    """Fetch averaged CPU usage over time (across all cores)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT time, AVG(percent) AS percent
                FROM cpu_percent
                WHERE sysname = %s
                  AND time BETWEEN %s AND %s
                GROUP BY time
                ORDER BY time
            """, (sysname, start_time, end_time))
            return serialize_rows(cur.fetchall())




def get_memory_timeseries(
    sysname: str,
    fields: List[str],
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: Optional[int] = None,
    target_points: int = 500
) -> List[Dict[str, Any]]:
    """Generic memory timeseries query.
    
    Args:
        sysname: System name
        fields: List of fields to select (e.g., ['used', 'cached', 'free', 'total'] or ['percent'])
        start_time: Start time for range query (None for snapshot mode)
        end_time: End time for range query
        limit: Max records for snapshot mode (default 60)
        target_points: Target data points for downsampling
    
    Returns:
        List of records with time and requested fields
    """
    fields_str = ', '.join(fields)
    avg_fields_str = ', '.join([f'AVG({f}) as {f}' for f in fields])
    default_limit = limit or 60
    
    with get_db() as conn:
        with conn.cursor() as cur:
            end_time, interval = resolve_time_range(start_time, end_time, target_points)
            
            if start_time is not None:
                if interval == 0:
                    cur.execute(f"""
                        SELECT time, {fields_str}
                        FROM memory
                        WHERE sysname = %s AND time >= %s AND time <= %s
                        ORDER BY time ASC
                    """, (sysname, start_time, end_time))
                else:
                    cur.execute(f"""
                        SELECT 
                            FROM_UNIXTIME((UNIX_TIMESTAMP(time) DIV {interval}) * {interval}) as time,
                            {avg_fields_str}
                        FROM memory
                        WHERE sysname = %s AND time >= %s AND time <= %s
                        GROUP BY FROM_UNIXTIME((UNIX_TIMESTAMP(time) DIV {interval}) * {interval})
                        ORDER BY time ASC
                    """, (sysname, start_time, end_time))
                return serialize_rows(cur.fetchall())
            else:
                cur.execute(f"""
                    SELECT time, {fields_str}
                    FROM memory
                    WHERE sysname = %s
                    ORDER BY time DESC
                    LIMIT %s
                """, (sysname, default_limit))
                rows = serialize_rows(cur.fetchall())
                return list(reversed(rows))


def get_memory_history(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Get memory history data for chart (wrapper for backward compatibility)."""
    return get_memory_timeseries(sysname, ['used', 'cached', 'free', 'total'], start_time, end_time, limit)


def get_memory_percent_history(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Get memory percent history data (wrapper for backward compatibility)."""
    return get_memory_timeseries(sysname, ['percent'], start_time, end_time, limit or 200)


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
                end_time = end_time or local_now()
                duration = end_time - start_time
                interval = calculate_group_interval_dynamic(duration)
                
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


# -----------------------------
# Network metrics (FIXED)
# -----------------------------
def get_network_metrics(sysname, start_time=None, end_time=None):
    with get_db() as conn:
        with conn.cursor() as cur:

            # SNAPSHOT MODE
            if start_time is None:
                cur.execute(f"""
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
                    WHERE sysname=%s AND {NON_LOOPBACK_IFACE_SQL}
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
                """, (sysname,))
                return {'net_io': serialize_rows(cur.fetchall())}

            # RANGE MODE
            end_time, interval = resolve_time_range(start_time, end_time)

            if interval == 0:
                cur.execute(f"""
                    WITH r AS (
                      SELECT
                        iface,
                        time,
                        bytes_sent curr_val,
                        LAG(bytes_sent) OVER (PARTITION BY iface ORDER BY time) prev_val,
                        TIMESTAMPDIFF(
                          MICROSECOND,
                          LAG(time) OVER (PARTITION BY iface ORDER BY time),
                          time
                        ) dt_us
                      FROM net_io_counters
                      WHERE sysname=%s AND time BETWEEN %s AND %s
                        AND {NON_LOOPBACK_IFACE_SQL}
                    )
                    SELECT iface, time, {RATE_SQL} AS send_bytes_s
                    FROM r
                    ORDER BY time, iface
                """, (sysname, start_time, end_time))
            else:
                # Prometheus-style: sum(rate per iface)
                cur.execute(f"""
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
                      WHERE sysname=%s AND time BETWEEN %s AND %s
                        AND {NON_LOOPBACK_IFACE_SQL}
                      GROUP BY iface, bucket
                    ) x
                    GROUP BY bucket
                    ORDER BY bucket
                """, (sysname, start_time, end_time))

            return {'net_io': serialize_rows(cur.fetchall())}



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
                rows = cur.fetchall()
                result['disk_usage'] = serialize_rows(rows)
            else:
                # Range Mode: All disk usage records in time range (with downsampling)
                end_time = end_time or local_now()
                duration = end_time - start_time
                interval = calculate_group_interval_dynamic(duration)
                
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
                rows = cur.fetchall()
                result['disk_usage'] = serialize_rows(rows)
            
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
                end_time = end_time or local_now()
                duration = end_time - start_time
                interval = calculate_group_interval_dynamic(duration)
                
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


# -----------------------------
# Disk IO metrics (FIXED)
# -----------------------------
def get_disk_io_metrics(
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    page: int = 1,
    per_page: int = 10
):
    offset = (page - 1) * per_page

    with get_db() as conn:
        with conn.cursor() as cur:

            # SNAPSHOT MODE
            if start_time is None:
                cur.execute("""
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
                            disk NOT REGEXP '[0-9]+$'  -- Giữ logic cũ cho ổ USB (sda, sdb...)
                        OR 
                        disk LIKE 'mmcblk%%'       -- Cho phép thẻ nhớ (mmcblk0)
                      )
                      AND disk NOT LIKE '%%p[0-9]%%' -- Vẫn chặn partition (loại bỏ mmcblk0p1, mmcblk0p2...)
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
                """, (sysname, per_page, offset))

                rows = serialize_rows(cur.fetchall())
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
                            "total_pages": (total + per_page - 1) // per_page
                        }
                    }
                }

            # RANGE MODE
            end_time, interval = resolve_time_range(start_time, end_time)
            if interval == 0:
                cur.execute("""
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
                    WHERE sysname=%s
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
                """, (sysname, start_time, end_time))
            else:
                cur.execute(f"""
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
                """, (sysname, start_time, end_time))

            rows = serialize_rows(cur.fetchall())
            return {
                "disk_io": {
                    "data": rows,
                    "pagination": {
                        "page": 1,
                        "per_page": len(rows),
                        "total": len(rows),
                        "total_pages": 1
                    }
                }
            }


# -----------------------------
# CPU + Network combined
# -----------------------------
def get_cpu_network_combined(
    sysname,
    iface=None,
    start_time=None,
    end_time=None,
    limit=60
):
    with get_db() as conn:
        with conn.cursor() as cur:
            result = {
                'cpu': [],
                'network': {},  # Changed to dict for per-interface data
                'interfaces': []
            }

            # ----------------------------------
            # List non-loopback interfaces
            # ----------------------------------
            cur.execute(f"""
                SELECT DISTINCT iface
                FROM net_io_counters
                WHERE sysname=%s AND {NON_LOOPBACK_IFACE_SQL}
                ORDER BY iface
            """, (sysname,))
            result['interfaces'] = [r['iface'] for r in cur.fetchall()]

            # =====================================================
            # SNAPSHOT MODE
            # =====================================================
            if start_time is None:
                # -----------------
                # CPU (AVG over cores per timestamp)
                # -----------------
                cur.execute("""
                    SELECT time, AVG(percent) AS percent
                    FROM cpu_percent
                    WHERE sysname=%s
                    GROUP BY time
                    ORDER BY time DESC
                    LIMIT %s
                """, (sysname, limit))
                result['cpu'] = list(reversed(serialize_rows(cur.fetchall())))

                # -----------------
                # Network (per-interface, rate via LAG)
                # -----------------
                for iface in result['interfaces']:
                    cur.execute(f"""
                        WITH r AS (
                          SELECT
                            time,
                            bytes_sent AS curr_sent,
                            bytes_recv AS curr_recv,
                            LAG(bytes_sent) OVER (ORDER BY time) AS prev_sent,
                            LAG(bytes_recv) OVER (ORDER BY time) AS prev_recv,
                            TIMESTAMPDIFF(
                              MICROSECOND,
                              LAG(time) OVER (ORDER BY time),
                              time
                            ) AS dt_us
                          FROM net_io_counters
                          WHERE sysname=%s
                            AND iface=%s
                            AND {NON_LOOPBACK_IFACE_SQL}
                        )
                        SELECT
                          time,
                          CASE
                            WHEN prev_sent IS NULL
                              OR curr_sent < prev_sent
                              OR dt_us <= 0
                            THEN NULL
                            ELSE (curr_sent - prev_sent) / (dt_us / 1e6)
                          END AS send_rate,
                          CASE
                            WHEN prev_recv IS NULL
                              OR curr_recv < prev_recv
                              OR dt_us <= 0
                            THEN NULL
                            ELSE (curr_recv - prev_recv) / (dt_us / 1e6)
                          END AS recv_rate
                        FROM r
                        ORDER BY time DESC
                        LIMIT %s
                    """, (sysname, iface, limit))
                    result['network'][iface] = list(reversed(serialize_rows(cur.fetchall())))

                return result

            # =====================================================
            # RANGE MODE
            # =====================================================
            end_time, interval = resolve_time_range(start_time, end_time)

            # -----------------
            # CPU
            # -----------------
            if interval == 0:
                cur.execute("""
                    SELECT time, AVG(percent) AS percent
                    FROM cpu_percent
                    WHERE sysname=%s
                      AND time BETWEEN %s AND %s
                    GROUP BY time
                    ORDER BY time
                """, (sysname, start_time, end_time))
            else:
                cur.execute(f"""
                    SELECT
                      FROM_UNIXTIME(
                        UNIX_TIMESTAMP(time) DIV {interval} * {interval}
                      ) AS time,
                      AVG(percent) AS percent
                    FROM cpu_percent
                    WHERE sysname=%s
                      AND time BETWEEN %s AND %s
                    GROUP BY time
                    ORDER BY time
                """, (sysname, start_time, end_time))

            result['cpu'] = serialize_rows(cur.fetchall())

            # -----------------
            # Network (Prometheus-style sum(rate))
            # -----------------
            if interval == 0:
                cur.execute(f"""
                    WITH r AS (
                      SELECT
                        iface,
                        time,
                        bytes_sent AS curr_sent,
                        bytes_recv AS curr_recv,
                        LAG(bytes_sent) OVER (PARTITION BY iface ORDER BY time) AS prev_sent,
                        LAG(bytes_recv) OVER (PARTITION BY iface ORDER BY time) AS prev_recv,
                        TIMESTAMPDIFF(
                          MICROSECOND,
                          LAG(time) OVER (PARTITION BY iface ORDER BY time),
                          time
                        ) AS dt_us
                      FROM net_io_counters
                      WHERE sysname=%s
                        AND time BETWEEN %s AND %s
                        AND {NON_LOOPBACK_IFACE_SQL}
                    )
                    SELECT
                      time,
                      SUM(
                        CASE
                          WHEN prev_sent IS NULL
                            OR curr_sent < prev_sent
                            OR dt_us <= 0
                          THEN NULL
                          ELSE (curr_sent - prev_sent) / (dt_us / 1e6)
                        END
                      ) AS send_rate,
                      SUM(
                        CASE
                          WHEN prev_recv IS NULL
                            OR curr_recv < prev_recv
                            OR dt_us <= 0
                          THEN NULL
                          ELSE (curr_recv - prev_recv) / (dt_us / 1e6)
                        END
                      ) AS recv_rate
                    FROM r
                    GROUP BY time
                    ORDER BY time
                """, (sysname, start_time, end_time))
            else:
                cur.execute(f"""
                    SELECT
                      bucket AS time,
                      SUM(delta_sent / {interval}) AS send_rate,
                      SUM(delta_recv / {interval}) AS recv_rate
                    FROM (
                      SELECT
                        iface,
                        FROM_UNIXTIME(
                          UNIX_TIMESTAMP(time) DIV {interval} * {interval}
                        ) AS bucket,
                        CASE
                          WHEN MAX(bytes_sent) < MIN(bytes_sent)
                          THEN NULL
                          ELSE MAX(bytes_sent) - MIN(bytes_sent)
                        END AS delta_sent,
                        CASE
                          WHEN MAX(bytes_recv) < MIN(bytes_recv)
                          THEN NULL
                          ELSE MAX(bytes_recv) - MIN(bytes_recv)
                        END AS delta_recv
                      FROM net_io_counters
                      WHERE sysname=%s
                        AND time BETWEEN %s AND %s
                        AND {NON_LOOPBACK_IFACE_SQL}
                      GROUP BY iface, bucket
                    ) x
                    GROUP BY bucket
                    ORDER BY bucket
                """, (sysname, start_time, end_time))

            result['network'] = serialize_rows(cur.fetchall())
            return result

# -----------------------------
# Status aggregator
# -----------------------------
def get_status_metrics(sysname, start_time=None, end_time=None):
    return {
        'device_info': get_device_info(sysname),
        **get_system_metrics(sysname, start_time, end_time),
        **get_cpu_metrics(sysname, start_time, end_time),
        **get_network_metrics(sysname, start_time, end_time),
        **get_memory_metrics(sysname, start_time, end_time),
        **get_temperature_metrics(sysname, start_time, end_time),
        **get_cpu_network_combined(sysname, None, start_time, end_time),
    }
