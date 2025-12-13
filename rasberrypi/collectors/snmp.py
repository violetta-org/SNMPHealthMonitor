import json
import os
import sys
import asyncio
import time
from typing import Dict, Any, List

from .common import Metric

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
    
from units import UNITLESS, BYTES, COUNT, PERCENT, SECONDS, MBPS, CELSIUS

try:
    from pysnmp.hlapi.v3arch.asyncio import (
        CommunityData,
        SnmpEngine,
        UdpTransportTarget,
        ContextData,
        ObjectType,
        ObjectIdentity,
        get_cmd,
        walk_cmd,
    )
except Exception as e:
    raise



def _load_oids(oids_file_path: str) -> List[Dict[str, Any]]:
    """Load OIDs from file. Expects absolute or relative path already resolved."""
    print(f"[DEBUG] Loading OIDs from: {oids_file_path}")
    
    with open(oids_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # Expected format: [{"name": "cpu.load1", "oid": "1.3...", "unit": "unitless", "type": "gauge", "labels": {}}]
    if not isinstance(data, list):
        raise ValueError("SNMP OIDs file must contain a list of OID mappings")
    return data


_UNIT_MAP = {
    'unitless': UNITLESS,
    'bytes': BYTES,
    'count': COUNT,
    'percent': PERCENT,
    'seconds': SECONDS,
    'mbps': MBPS,
    'celsius': CELSIUS,
    'c': CELSIUS,
}


def _unit_from_string(unit_str: str) -> str:
    return _UNIT_MAP.get((unit_str or 'unitless').lower(), UNITLESS)


def _convert_value(val):
    s = str(val)
    try:
        if s.isdigit():
            return int(s)
        # float-like
        if s.replace('.', '', 1).isdigit() and s.count('.') < 2:
            return float(s)
    except Exception:
        pass
    return s


def _suffix_index(root_oid: str, full_oid: str) -> str:
    # Returns the numeric suffix after root OID, without leading dot
    if full_oid.startswith(root_oid):
        suffix = full_oid[len(root_oid):]
        return suffix.lstrip('.') or ''
    return ''


async def fetch_snmp_metrics_async(host: str, port: int, community: str, version: str, oids_file_path: str) -> List[Dict[str, Any]]:
    
    #nạp oids
    oids = _load_oids(oids_file_path)

    if version not in ('1', '2c'):
        raise ValueError("Only SNMP v1 and v2c are supported in this collector")

    # tạo engine và community data
    engine = SnmpEngine()
    community_data = CommunityData(community, mpModel=0 if version == '1' else 1)
    context = ContextData()
    
    # tạo transport target
    transport = await UdpTransportTarget.create((host, port), timeout=3.0, retries=0)

    metrics: List[Dict[str, Any]] = []

    for entry in oids:
        # Capture timestamp TRƯỚC KHI vào loop đo từng OID entry
        ts = int(time.time())
        
        name = entry.get('name')
        oid = entry.get('oid')
        unit = _unit_from_string(entry.get('unit', 'unitless'))
        mtype = entry.get('type', 'gauge')
        labels = entry.get('labels') or {}
        method = (entry.get('method') or ('walk' if entry.get('walk') else 'get')).lower()
        scale = float(entry.get('scale', 1.0))
        label_key = entry.get('label_key', 'index')

        if not name or not oid:
            continue

        print(f"[DEBUG] Processing {name} (OID: {oid}, method: {method})")

        try:
            #GETNEXT
            if method == 'walk':
                print(f"[DEBUG] Walking OID {oid}")
                
                # đảm bảo base_oid kết thúc với dấu chấm để khớp với prefix
                base_oid = oid if oid.endswith('.') else oid + '.'
                stop_walk = False
                
                async for (error_indication, error_status, error_index, var_binds) in walk_cmd(
                    engine,
                    community_data,
                    transport,
                    context,
                    ObjectType(ObjectIdentity(oid)),
                    lexicographicMode=False,  # dừng khi rời khỏi subtree được yêu cầu
                ):
                    if error_indication or error_status:
                        print(f"[DEBUG] SNMP walk error for {name}: {error_indication or error_status}")
                        # Skip this metric on error
                        break
                    
                    #print(f"[DEBUG] var_binds from walk: {var_binds}")
                    #print(f"[DEBUG] var_binds type: {type(var_binds)}")
                    #print(f"[DEBUG] var_binds repr: {repr(var_binds)}")
                    
                    for full_oid, val in var_binds:
                        # Check if we're still walking the expected OID tree
                        full_oid_str = str(full_oid)
                        if not full_oid_str.startswith(base_oid):
                            print(f"[DEBUG] Beyond subtree for {name}: {full_oid_str}")
                            stop_walk = True
                            break
                        
                        v = _convert_value(val)
                        try:
                            v = v * scale if isinstance(v, (int, float)) else v
                        except Exception:
                            pass
                        idx = _suffix_index(oid, str(full_oid))
                        try:
                            metrics.append(
                                Metric(
                                    name=name,
                                    value=v,
                                    unit=unit,
                                    type=mtype,
                                    labels={**labels, label_key: idx} if idx else labels,
                                    ts=ts,
                                ).to_dict()
                            )
                            print(f"[DEBUG] Walked {name}[{idx}] = {v}")
                        except ValueError as e:
                            print(f"[DEBUG] Error creating metric {name}[{idx}]: {e}")
                            # Discard metric if ts is invalid
                    
                    # Break out of outer async for loop if we detected OID beyond subtree
                    if stop_walk:
                        break
            else:
                print(f"[DEBUG] Getting OID {oid}")
                #GET
                error_indication, error_status, error_index, var_binds = await get_cmd(
                    engine,
                    community_data,
                    transport,
                    context,
                    ObjectType(ObjectIdentity(oid)),
                )
                
                #print(f"[DEBUG] var_binds from get: {var_binds}")
                #print(f"[DEBUG] var_binds type: {type(var_binds)}")
                #print(f"[DEBUG] var_binds repr: {repr(var_binds)}")
                
                if error_indication or error_status:
                    print(f"[DEBUG] SNMP get error for {name}: {error_indication or error_status}")
                    # Skip this metric on error
                else:
                    for _oid_obj, val in var_binds:
                        v = _convert_value(val)
                        try:
                            v = v * scale if isinstance(v, (int, float)) else v
                        except Exception:
                            pass
                        try:
                            metrics.append(
                                Metric(
                                    name=name,
                                    value=v,
                                    unit=unit,
                                    type=mtype,
                                    labels=labels,
                                    ts=ts,
                                ).to_dict()
                            )
                            print(f"[DEBUG] Got {name} = {v}")
                        except ValueError as e:
                            print(f"[DEBUG] Error creating metric {name}: {e}")
                            # Discard metric if ts is invalid
        except Exception as e:
            print(f"[DEBUG] Exception processing {name}: {e}")
            # Skip this metric on exception

    print(f"[DEBUG] Collected {len(metrics)} metrics total")
    return metrics


def fetch_snmp_metrics(host: str, port: int, community: str, version: str, oids_file_path: str) -> List[Dict[str, Any]]:
    """Sync wrapper for async SNMP metrics collector"""
    print(f"[DEBUG] Starting sync SNMP collection wrapper")
    
    try:
        # Check if we're already in an event loop
        loop = asyncio.get_running_loop()
        print(f"[DEBUG] Already in event loop, creating new thread")
        # If we're already in an event loop, we need to run in a new thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, fetch_snmp_metrics_async(host, port, community, version, oids_file_path))
            return future.result()
    except RuntimeError:
        # No event loop running, safe to use asyncio.run
        print(f"[DEBUG] No event loop running, using asyncio.run")
        return asyncio.run(fetch_snmp_metrics_async(host, port, community, version, oids_file_path))

