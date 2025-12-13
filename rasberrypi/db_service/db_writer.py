"""Database writer helpers for component-centric schema.

Minimal API with two functions:
  - upsert_device(conn, sysname, ip_address, ...)
  - write_metrics_batch(conn, sysname, metrics)

This module avoids background threads/queues and writes a batch within
one transaction for each payload received by the manager.
"""

import pymysql as MySQLdb
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

_TEXT_WHITELIST = {
    "sys.name", "sys.location",
    "network.interface.name",
    "disk.usage.mount", "disk.usage.device",
    "disk.io.device",
}

# Cache toàn cục ánh xạ hrDeviceIndex sang số thứ tự core theo thiết bị
# Format: {sysname: {hr_index: core_num}}
_cpu_core_mapping: Dict[str, Dict[int, int]] = {}


def _to_dt(ts: Optional[int]) -> datetime:
    """Convert unix ts (s) to datetime with ms precision."""
    if ts is None:
        raise ValueError("Timestamp (ts) is required, cannot be None")
    return datetime.fromtimestamp(int(ts))


def upsert_device(
    conn,
    sysname: str,
    ip_address: Optional[str],
    last_seen: Optional[datetime] = None,
    online: bool = True,
) -> None:
    """Insert or update a device row using ON DUPLICATE KEY UPDATE."""
    last_seen = last_seen or datetime.now()
    sql = (
        "INSERT INTO devices (sysname, ip_address, last_seen, online) "
        "VALUES (%s, %s, %s, %s) "
        "ON DUPLICATE KEY UPDATE "
        "ip_address = VALUES(ip_address), "
        "last_seen = VALUES(last_seen), online = VALUES(online)"
    )
    with conn.cursor() as cur:
        cur.execute(sql, (sysname, ip_address, last_seen, online))


def _insert_load_avg_batch(cur, sysname: str, metrics_by_ts: Dict[int, Dict[str, Any]]) -> None:
    """Insert load averages grouped by timestamp (all 3 values in one INSERT)."""
    for ts, values in metrics_by_ts.items():
        load_1m = values.get("load.1m")
        load_5m = values.get("load.5m")
        load_15m = values.get("load.15m")
        
        print(f"[DEBUG] _insert_load_avg_batch: sysname={sysname}, ts={ts}, load_1m={load_1m}, load_5m={load_5m}, load_15m={load_15m}")
        cur.execute(
            "INSERT INTO load_avg (time, sysname, load_1m, load_5m, load_15m) "
            "VALUES (%s, %s, %s, %s, %s)",
            (_to_dt(ts), sysname, load_1m, load_5m, load_15m),
        )


def _insert_cpu_percent(cur, sysname: str, labels: Dict[str, Any], value: Any, ts: int) -> None:
    """Insert per-core CPU percent from hrProcessorLoad."""
    hr_index = int(labels.get("hrDeviceIndex", "0"))

    # Initialize device mapping if first time
    if sysname not in _cpu_core_mapping:
        _cpu_core_mapping[sysname] = {}

    # Assign sequential core number if this hrDeviceIndex is new
    if hr_index not in _cpu_core_mapping[sysname]:
        # Get all existing indices for this device, sort them, assign next number
        existing_indices = sorted(_cpu_core_mapping[sysname].keys())

        # Find where this index should go in sorted order
        core_num = 0
        for existing_idx in existing_indices:
            if hr_index < existing_idx:
                break
            core_num += 1

        # Shift existing mappings if needed
        for idx, num in list(_cpu_core_mapping[sysname].items()):
            if num >= core_num:
                _cpu_core_mapping[sysname][idx] = num + 1

        _cpu_core_mapping[sysname][hr_index] = core_num

    cpu_name = f"cpu{_cpu_core_mapping[sysname][hr_index]}"
    cur.execute(
        "INSERT INTO cpu_percent (time, sysname, cpu, percent) VALUES (%s, %s, %s, %s)",
        (_to_dt(ts), sysname, cpu_name, value),
    )


def _insert_memory(cur, sysname: str, metrics_by_name: Dict[str, Tuple[Any, int]]) -> None:
    # Expect names: memory.total, memory.available, memory.used, memory.free, memory.percent, memory.buffers, memory.cached, memory.shared
    ts = metrics_by_name.get("memory.total", (None, None))[1] or metrics_by_name.get("memory.available", (None, None))[1]
    if ts is None:
        return

    total = metrics_by_name.get("memory.total", (None, ts))[0]
    available = metrics_by_name.get("memory.available", (None, ts))[0]
    buffers = metrics_by_name.get("memory.buffers", (None, ts))[0]
    cached = metrics_by_name.get("memory.cached", (None, ts))[0]
    shared = metrics_by_name.get("memory.shared", (None, ts))[0]

    # Calculate derived fields
    used = None
    free = available  # Use available as free
    percent = None

    if total is not None and available is not None:
        used = total - available
        if total > 0:
            percent = (used / total) * 100

    vals = {
        "total": total,
        "available": available,
        "used": used,
        "free": free,
        "percent": percent,
        "buffers": buffers,
        "cached": cached,
        "shared": shared,
    }
    cur.execute(
        "INSERT INTO memory (time, sysname, total, available, used, free, percent, buffers, cached, shared) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (_to_dt(ts), sysname, vals["total"], vals["available"], vals["used"], vals["free"],
         vals["percent"], vals["buffers"], vals["cached"], vals["shared"]),
    )


def _insert_swap(cur, sysname: str, metrics_by_name: Dict[str, Tuple[Any, int]]) -> None:
    ts = metrics_by_name.get("swap.total", (None, None))[1] or metrics_by_name.get("swap.free", (None, None))[1]
    if ts is None:
        return

    total = metrics_by_name.get("swap.total", (None, ts))[0]
    free = metrics_by_name.get("swap.free", (None, ts))[0]

    # Calculate derived fields
    used = None
    percent = None

    if total is not None and free is not None:
        used = total - free
        if total > 0:
            percent = (used / total) * 100

    cur.execute(
        "INSERT INTO swap_memory (time, sysname, total, used, free, percent) VALUES (%s, %s, %s, %s, %s, %s)",
        (_to_dt(ts), sysname, total, used, free, percent),
    )


def _insert_disk_usage(cur, sysname: str, metrics_by_index: Dict[str, Dict[str, Any]], ts: int) -> None:
    """Insert disk usage from UCD-SNMP-MIB::dskTable.

    metrics_by_index format: {
        "31": {"mount": "/", "device": "/dev/sda1", "total": 123456, ...},
        "32": {"mount": "/home", "device": "/dev/sda2", ...}
    }
    """
    for idx, values in metrics_by_index.items():
        mount = values.get("mount")
        device = values.get("device")
        total = values.get("total")
        used = values.get("used")
        free = values.get("free")
        percent = values.get("percent")

        cur.execute(
            "INSERT INTO disk_usage (time, sysname, mount, device_partition, total, used, free, percent) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (_to_dt(ts), sysname, mount, device, total, used, free, percent),
        )


def _insert_disk_io(cur, sysname: str, metrics_by_index: Dict[str, Dict[str, Any]], ts: int) -> None:
    """Insert disk I/O from UCD-DISKIO-MIB::diskIOTable."""
    for idx, values in metrics_by_index.items():
        disk = values.get("device")
        read_count = values.get("read_count")
        write_count = values.get("write_count")
        read_bytes = values.get("read_bytes")
        write_bytes = values.get("write_bytes")

        cur.execute(
            "INSERT INTO disk_io_counters (time, sysname, disk, read_count, write_count, read_bytes, write_bytes) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (_to_dt(ts), sysname, disk, read_count, write_count, read_bytes, write_bytes),
        )


def _insert_temperature(cur, sysname: str, cpu_temp: Any, ts: int) -> None:
    """Insert CPU temperature from SNMP extend."""
    print(f"[DEBUG] _insert_temperature: sysname={sysname}, cpu_temp={cpu_temp}, ts={ts}")
    # Parse temperature value - might be string like "45.7" or already float
    temp_value = None
    if isinstance(cpu_temp, (int, float)):
        temp_value = float(cpu_temp)
    elif isinstance(cpu_temp, str):
        try:
            # Try to parse string to float (handles "45.7" or error messages)
            temp_value = float(cpu_temp.strip())
        except (ValueError, AttributeError):
            print(f"[DEBUG] _insert_temperature: Cannot parse temperature value: {cpu_temp}")
            return
    
    if temp_value is None:
        print(f"[DEBUG] _insert_temperature: Invalid temperature value, skipping")
        return
    
    cur.execute(
        "INSERT INTO temperature (time, sysname, cpu_temp) "
        "VALUES (%s, %s, %s)",
        (_to_dt(ts), sysname, temp_value),
    )


def _insert_net_io(cur, sysname: str, metrics_by_index: Dict[str, Dict[str, Any]], ts: int) -> None:
    """Insert network I/O from IF-MIB."""
    for idx, values in metrics_by_index.items():
        cur.execute(
            "INSERT INTO net_io_counters (time, sysname, if_index, iface, if_high_speed_mbps, "
            "if_admin_status, if_oper_status, bytes_sent, bytes_recv) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                _to_dt(ts),
                sysname,
                idx,
                values.get("iface"),
                values.get("if_high_speed_mbps"),
                values.get("if_admin_status"),
                values.get("if_oper_status"),
                values.get("bytes_sent"),
                values.get("bytes_recv"),
            ),
        )


def write_metrics_batch(conn, sysname: str, metrics: List[Dict[str, Any]]) -> None:
    """Write raw metrics into tables for a device in a single transaction."""
    print(f"[DEBUG] write_metrics_batch: begin sysname={sysname}, metrics={len(metrics) if metrics else 0}")
    with conn.cursor() as cur:
        # Group some families that benefit from a single insert
        load_avg_group: Dict[int, Dict[str, Any]] = {}  # {ts: {load.1m, load.5m, load.15m}}
        mem_group: Dict[str, Tuple[Any, int]] = {}
        swap_group: Dict[str, Tuple[Any, int]] = {}
        sys_info_group: Dict[str, Tuple[Any, int]] = {}  # {name: (value, ts)}
        disk_usage_group: Dict[str, Dict[str, Any]] = {}  # {dskIndex: {mount, device, total, ...}}
        disk_io_group: Dict[str, Dict[str, Any]] = {}  # {index: {device, read_count, write_count, read_bytes, write_bytes}}
        net_io_group: Dict[str, Dict[str, Any]] = {}  # {ifIndex: {iface, if_high_speed_mbps, if_admin_status, if_oper_status, bytes_sent, bytes_recv}}

        for m in metrics or []:
            name = m.get("name")
            value = m.get("value")
            ts = m.get("ts")
            labels = m.get("labels") or {}

            # Discard metrics without timestamp
            if ts is None:
                print(f"[WARN] Discarding metric {name} - no timestamp")
                continue

            # Helper to check if value is numeric
            def _is_number(x):
                return isinstance(x, (int, float))

            # Allow whitelisted text metrics, skip other non-numeric values
            allow_text = name in _TEXT_WHITELIST
            if value is not None and not _is_number(value) and not allow_text:
                print(f"[DEBUG] Skipping non-numeric metric {name}: {value} (type: {type(value).__name__})")
                continue

            try:
                if name.startswith("load."):
                    # Group load averages by timestamp
                    if ts not in load_avg_group:
                        load_avg_group[ts] = {}
                    load_avg_group[ts][name] = value
                elif name == "cpu.core.percent":
                    _insert_cpu_percent(cur, sysname, labels, value, ts)
                elif name.startswith("memory."):
                    mem_group[name] = (value, ts)
                elif name.startswith("swap."):
                    swap_group[name] = (value, ts)
                elif name.startswith("disk.usage."):
                    dsk_index = labels.get("dskIndex", "0")
                    if dsk_index not in disk_usage_group:
                        disk_usage_group[dsk_index] = {}

                    if name == "disk.usage.mount":
                        disk_usage_group[dsk_index]["mount"] = value
                    elif name == "disk.usage.device":
                        disk_usage_group[dsk_index]["device"] = value
                    elif name == "disk.usage.total_kb":
                        disk_usage_group[dsk_index]["total"] = value
                        disk_usage_group[dsk_index]["ts"] = ts
                    elif name == "disk.usage.used_kb":
                        disk_usage_group[dsk_index]["used"] = value
                    elif name == "disk.usage.avail_kb":
                        disk_usage_group[dsk_index]["free"] = value
                    elif name == "disk.usage.percent":
                        disk_usage_group[dsk_index]["percent"] = value
                elif name.startswith("disk.io."):
                    idx = labels.get("index", "0")
                    if idx not in disk_io_group:
                        disk_io_group[idx] = {}

                    if name == "disk.io.device":
                        disk_io_group[idx]["device"] = value
                    elif name == "disk.io.read_count_total":
                        disk_io_group[idx]["read_count"] = value
                    elif name == "disk.io.write_count_total":
                        disk_io_group[idx]["write_count"] = value
                    elif name == "disk.io.read_bytes_total_64":
                        disk_io_group[idx]["read_bytes"] = value
                    elif name == "disk.io.write_bytes_total_64":
                        disk_io_group[idx]["write_bytes"] = value
                        disk_io_group[idx]["ts"] = ts
                elif name.startswith("network."):
                    if_index = labels.get("ifIndex", "0")
                    if if_index not in net_io_group:
                        net_io_group[if_index] = {}

                    if name == "network.interface.name":
                        net_io_group[if_index]["iface"] = value
                    elif name == "network.interface.high_speed_mbps":
                        net_io_group[if_index]["if_high_speed_mbps"] = value
                    elif name == "network.interface.admin_status":
                        net_io_group[if_index]["if_admin_status"] = value
                    elif name == "network.interface.oper_status":
                        net_io_group[if_index]["if_oper_status"] = value
                    elif name == "network.rx_bytes_total":
                        net_io_group[if_index]["bytes_recv"] = value
                    elif name == "network.tx_bytes_total":
                        net_io_group[if_index]["bytes_sent"] = value
                        net_io_group[if_index]["ts"] = ts
                elif name.startswith("sys."):
                    sys_info_group[name] = (value, ts)
                elif name == "temperature.cpu":
                    _insert_temperature(cur, sysname, value, ts)
                else:
                    print(f"[DEBUG] Unknown metric {name}, skipping")
            except Exception as e:
                print(f"[ERROR] DBWriter route failed for {name}: {e}")

        if load_avg_group:
            _insert_load_avg_batch(cur, sysname, load_avg_group)
        if mem_group:
            _insert_memory(cur, sysname, mem_group)
        if swap_group:
            _insert_swap(cur, sysname, swap_group)
        if sys_info_group:
            _insert_system_info(cur, sysname, sys_info_group)
        if disk_usage_group:
            for idx, values in disk_usage_group.items():
                ts = values.get("ts")
                if ts:
                    _insert_disk_usage(cur, sysname, {idx: values}, ts)
        if disk_io_group:
            for idx, values in disk_io_group.items():
                ts = values.get("ts")
                if ts:
                    _insert_disk_io(cur, sysname, {idx: values}, ts)
        if net_io_group:
            for idx, values in net_io_group.items():
                ts = values.get("ts")
                if ts:
                    _insert_net_io(cur, sysname, {idx: values}, ts)

    try:
        conn.commit()
        print(f"[DEBUG] write_metrics_batch: commit OK, wrote {len(metrics)} metrics for sysname={sysname}")
    except Exception as e:
        print(f"[ERROR] write_metrics_batch: commit failed for sysname={sysname}: {e}")
        try:
            conn.rollback()
            print(f"[DEBUG] write_metrics_batch: rollback OK for sysname={sysname}")
        except Exception as re:
            print(f"[ERROR] write_metrics_batch: rollback failed for sysname={sysname}: {re}")


def _insert_system_info(cur, sysname: str, metrics_by_name: Dict[str, Tuple[Any, int]]) -> None:
    """Insert/update system info from SNMPv2-MIB (latest value only)."""
    if not metrics_by_name:
        return

    sys_location = metrics_by_name.get("sys.location", (None, 0))[0]
    sys_uptime = metrics_by_name.get("sys.uptime.seconds", (None, 0))[0]
    ts = max((v[1] for v in metrics_by_name.values()), default=0)

    print(f"[DEBUG] _insert_system_info: sysname={sysname}, sys_location={sys_location}, sys_uptime={sys_uptime}, ts={ts}")
    cur.execute(
        "INSERT INTO system_info (time, sysname, sys_location, sys_uptime) "
        "VALUES (%s, %s, %s, %s) "
        "ON DUPLICATE KEY UPDATE "
        "time = VALUES(time), "
        "sys_location = VALUES(sys_location), "
        "sys_uptime = VALUES(sys_uptime)",
        (_to_dt(ts), sysname, sys_location, sys_uptime),
    )
