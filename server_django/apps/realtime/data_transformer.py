"""
RealTimeTransformer for Django - Data transformation logic for real-time metric streaming.
Ported from: query-service/utils/data_transformer.py

This module transforms raw metric lists from the UDP listener into topic-specific
JSON formats that the frontend expects. It maintains state to calculate rates
(e.g., network throughput, disk I/O rates).

CRITICAL: Output format MUST match Flask-SocketIO version for frontend compatibility.
"""
import re
from datetime import datetime
from typing import List, Dict, Any, Optional


class RealTimeTransformer:
    """
    Transforms list of flattened metrics into structured JSON for frontend.
    Stateful to calculate rates (e.g., network throughput, disk I/O).
    
    Thread-Safety Note:
        This class is NOT thread-safe. In Django Channels (async), each UDP
        listener should use its own instance. Since we run in a single-process
        ASGI model with InMemoryChannelLayer, this is fine.
    """
    
    # Predefined list of excluded prefixes (Loopback, Docker, Virtual, VPN)
    EXCLUDED_PREFIXES = ['lo', 'lo0', 'docker', 'veth', 'br-', 'virbr', 'wg', 'zt']
    
    # Valid mount points for disk filtering
    VALID_MOUNTS = ['/', '/boot/firmware']

    def __init__(self):
        """Initialize the transformer with empty state for rate calculations."""
        # Store previous values for rate calculation
        # Structure: {sysname: {'time': ts, 'interfaces': {ifIndex: {rx, tx}}, ...}}
        self._prev_state: Dict[str, Dict] = {}

    def transform(
        self,
        topic: str,
        metrics: List[Dict[str, Any]],
        sysname: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Main entry point for transformation.
        
        Args:
            topic: One of 'systemstatus', 'network', 'disk', 'diskio'
            metrics: List of metric objects with format:
                     {name: str, value: Any, labels: Dict, ts: float}
            sysname: Optional system name from UDP message
            ip_address: Optional IP address to attach to device_info
            
        Returns:
            Transformed data dict matching Flask-SocketIO format exactly.
        """
        if not metrics:
            return {}

        method_name = f"_transform_{topic}"
        transformer = getattr(self, method_name, None)
        
        if transformer is None:
            return {}
        
        # Call the appropriate transformer
        result = transformer(metrics, sysname=sysname)
        
        # Attach IP address to device_info if provided
        if ip_address and 'device_info' in result:
            result['device_info']['ip_address'] = ip_address
        
        return result

    @staticmethod
    def _get_metric_value(
        metrics: List[Dict],
        name_suffix: str,
        labels: Optional[Dict] = None
    ) -> Any:
        """
        Helper to find a specific metric value by name suffix.
        
        Args:
            metrics: List of metric dicts
            name_suffix: The ending of the metric name to match
            labels: Optional label constraints to match
            
        Returns:
            The metric value if found, None otherwise
        """
        for m in metrics:
            if m['name'].endswith(name_suffix):
                if labels:
                    # Check if all provided labels match
                    metric_labels = m.get('labels', {})
                    if all(metric_labels.get(k) == v for k, v in labels.items()):
                        return m['value']
                else:
                    return m['value']
        return None

    def _transform_systemstatus(
        self,
        metrics: List[Dict],
        sysname: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transform metrics for the 'systemstatus' topic.
        
        Groups: system_info, load_avg, network, cpu_percent, memory, swap, device_info
        
        Output format (MUST match Flask):
        {
            'system_info': {'sysname': ..., 'sys_location': ..., 'sys_uptime': ...},
            'load_avg': {'time': ..., 'load_1m': ..., 'load_5m': ..., 'load_15m': ...},
            'network': [{'interface': ..., 'time': ..., 'bytes_sent': ..., ...}],
            'cpu_percent': [{'cpu': 'cpu0', 'percent': ..., 'time': ...}],
            'memory': {'total': ..., 'used': ..., 'free': ..., 'percent': ..., ...},
            'swap': {'total': ..., 'used': ..., 'free': ..., 'percent': ...},
            'device_info': {'online': True, 'last_seen': ...}
        }
        """
        # Initialize containers
        if sysname is None:
            sysname = "N/A"
        location = "N/A"
        uptime = 0
        ts = datetime.now().isoformat()
        ts_val = 0
        
        # CPU map: hrDeviceIndex -> {percent, time}
        cpu_map: Dict[str, Dict] = {}
        mem_data: Dict[str, Any] = {}
        swap_data: Dict[str, Any] = {}
        
        load_1m = 0
        load_5m = 0
        load_15m = 0
        
        # Network counters per interface: ifIndex -> {rx, tx, name, ...}
        net_counters: Dict[str, Dict] = {}
        
        # === Pass 1: Extract all values ===
        for m in metrics:
            name = m['name']
            val = m['value']
            
            # Timestamp (prefer latest)
            if m.get('ts'):
                ts_val = m['ts']
                ts = datetime.fromtimestamp(m['ts']).isoformat()
            
            # System Info
            if name == 'sys.name':
                sysname = val
            elif name == 'sys.location':
                location = val
            elif name == 'sys.uptime.seconds':
                uptime = val
            
            # Load Average
            elif name == 'load.1m':
                load_1m = val
            elif name == 'load.5m':
                load_5m = val
            elif name == 'load.15m':
                load_15m = val
            
            # CPU - convert hrDeviceIndex to sequential core numbers
            elif name == 'cpu.core.percent':
                hr_index = m.get('labels', {}).get('hrDeviceIndex', '0')
                cpu_map[hr_index] = {'percent': val, 'time': ts}
            
            # Memory
            elif name.startswith('memory.'):
                field = name.split('.')[-1]  # e.g. 'total'
                mem_data[field] = val
            
            # Swap
            elif name.startswith('swap.'):
                field = name.split('.')[-1]
                swap_data[field] = val
            
            # Network metrics - group by interface
            elif name.startswith('network.'):
                if_index = m.get('labels', {}).get('ifIndex')
                if if_index:
                    if if_index not in net_counters:
                        net_counters[if_index] = {
                            'rx': 0, 'tx': 0,
                            'name': f"if{if_index}",
                            'admin_status': 1,
                            'oper_status': 1
                        }
                    
                    if name == 'network.rx_bytes_total':
                        net_counters[if_index]['rx'] = val
                    elif name == 'network.tx_bytes_total':
                        net_counters[if_index]['tx'] = val
                    elif name == 'network.interface.name':
                        net_counters[if_index]['name'] = val
                    elif name == 'network.interface.admin_status':
                        net_counters[if_index]['admin_status'] = val
                    elif name == 'network.interface.oper_status':
                        net_counters[if_index]['oper_status'] = val

        # === Post-process Memory ===
        if 'total' in mem_data:
            total = mem_data['total']
            
            # Ensure basic fields exist
            for f in ['free', 'cached', 'buffers', 'available', 'shared']:
                if f not in mem_data:
                    mem_data[f] = 0
            
            # CRITICAL FIX: Some Linux systems report Free = Physical Free + Swap Free
            # If Free > Total, subtract Swap Free to get real Physical Free
            if mem_data['free'] > total:
                swap_free = swap_data.get('free', 0)
                mem_data['free'] = max(0, mem_data['free'] - swap_free)
            
            # Cap values at total (SNMP data can be invalid)
            mem_data['free'] = min(mem_data['free'], total)
            mem_data['cached'] = min(mem_data['cached'], total)
            mem_data['buffers'] = min(mem_data['buffers'], total)
            mem_data['available'] = min(mem_data['available'], total)
            
            # Recalculate 'used': used = total - free - buffers - cached
            calculated_used = total - mem_data['free'] - mem_data['buffers'] - mem_data['cached']
            mem_data['used'] = max(0, calculated_used)
            
            # Calculate percent
            if total > 0:
                mem_data['percent'] = (mem_data['used'] / total) * 100

        # === Post-process Swap ===
        if 'total' in swap_data:
            if 'used' not in swap_data:
                swap_data['used'] = max(0, swap_data.get('total', 0) - swap_data.get('free', 0))
            
            if 'percent' not in swap_data and swap_data.get('total', 0) > 0:
                swap_data['percent'] = (swap_data['used'] / swap_data['total']) * 100
            
            if 'free' not in swap_data:
                swap_data['free'] = 0

        # === Rate Calculation (Per Interface) ===
        network_data: List[Dict] = []
        
        if sysname != "N/A":
            prev_all = self._prev_state.get(sysname, {})
            current_state = {'time': ts_val, 'interfaces': {}}
            
            dt = ts_val - prev_all.get('time', ts_val) if 'time' in prev_all else 0
            
            for if_idx, counters in net_counters.items():
                if_name = counters['name']
                
                # Filter: exclude virtual interfaces
                is_excluded = any(if_name.startswith(p) for p in self.EXCLUDED_PREFIXES)
                if is_excluded:
                    continue
                
                curr_rx = counters['rx']
                curr_tx = counters['tx']
                admin_status = counters['admin_status']
                oper_status = counters['oper_status']
                
                # Store current values for next iteration
                current_state['interfaces'][if_idx] = {'rx': curr_rx, 'tx': curr_tx}
                
                # Calculate rates
                rx_rate = 0
                tx_rate = 0
                
                if dt > 0 and 'interfaces' in prev_all and if_idx in prev_all['interfaces']:
                    prev_if = prev_all['interfaces'][if_idx]
                    rx_diff = curr_rx - prev_if['rx']
                    tx_diff = curr_tx - prev_if['tx']
                    
                    if rx_diff >= 0:
                        rx_rate = rx_diff / dt
                    if tx_diff >= 0:
                        tx_rate = tx_diff / dt
                
                network_data.append({
                    "interface": if_name,
                    "time": ts,
                    "bytes_sent": curr_tx,
                    "bytes_recv": curr_rx,
                    "if_admin_status": admin_status,
                    "if_oper_status": oper_status,
                    "send_bytes_s": tx_rate,
                    "recv_bytes_s": rx_rate
                })
            
            # Update state
            self._prev_state[sysname] = current_state

        # === Post-process CPU: Convert hrDeviceIndex to sequential core numbers ===
        cpu_cores: List[Dict] = []
        if cpu_map:
            sorted_indices = sorted(cpu_map.keys(), key=lambda x: int(x) if str(x).isdigit() else 0)
            for core_num, hr_index in enumerate(sorted_indices):
                cpu_cores.append({
                    'cpu': f'cpu{core_num}',
                    'percent': cpu_map[hr_index]['percent'],
                    'time': cpu_map[hr_index]['time']
                })

        return {
            'system_info': {
                'sysname': sysname,
                'sys_location': location,
                'sys_uptime': uptime
            },
            'load_avg': {
                'time': ts,
                'load_1m': load_1m,
                'load_5m': load_5m,
                'load_15m': load_15m
            },
            'network': network_data,
            'cpu_percent': cpu_cores,
            'memory': mem_data if mem_data else None,
            'swap': swap_data if swap_data else None,
            'device_info': {
                'online': True,
                'last_seen': ts
            }
        }

    def _transform_network(
        self,
        metrics: List[Dict],
        sysname: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transform metrics for the 'network' topic (dedicated network page).
        
        Output format:
        {
            'network': [{'interface': ..., 'time': ..., 'bytes_sent': ..., ...}],
            'device_info': {'online': True, 'last_seen': ...}
        }
        """
        iface_map: Dict[str, Dict] = {}  # ifIndex -> interface data
        iface_names: Dict[str, str] = {}  # ifIndex -> name
        ts_val = 0
        ts = datetime.now().isoformat()
        
        if sysname is None:
            sysname = "N/A"
        
        # === Pass 1: Build index -> name mapping and find sysname ===
        for m in metrics:
            if m['name'] == 'sys.name':
                sysname = m['value']
            if m.get('ts'):
                ts_val = m['ts']
            if m['name'] == 'network.interface.name':
                if_index = m.get('labels', {}).get('ifIndex')
                if if_index:
                    iface_names[if_index] = m['value']
        
        if ts_val == 0:
            ts_val = datetime.now().timestamp()
        
        # === Pass 2: Gather values ===
        for m in metrics:
            name = m['name']
            if_index = m.get('labels', {}).get('ifIndex')
            
            if not if_index:
                continue
            
            if m.get('ts'):
                ts = datetime.fromtimestamp(m['ts']).isoformat()
            
            # Initialize interface entry if needed
            if if_index not in iface_map:
                iface_name = iface_names.get(if_index, f'if{if_index}')
                iface_map[if_index] = {
                    'interface': iface_name,
                    'time': ts,
                    'if_admin_status': 1,
                    'if_oper_status': 1,
                    'bytes_recv': 0,
                    'bytes_sent': 0
                }
            
            # Map metrics
            if name == 'network.rx_bytes_total':
                iface_map[if_index]['bytes_recv'] = m['value']
            elif name == 'network.tx_bytes_total':
                iface_map[if_index]['bytes_sent'] = m['value']
            elif name == 'network.interface.admin_status':
                iface_map[if_index]['if_admin_status'] = int(m['value'])
            elif name == 'network.interface.oper_status':
                iface_map[if_index]['if_oper_status'] = int(m['value'])
            elif name == 'network.interface.high_speed_mbps':
                iface_map[if_index]['if_high_speed_mbps'] = m['value']
        
        # === Calculate Rates ===
        filtered_network: List[Dict] = []
        
        if sysname != "N/A":
            # Use separate state key for network page
            state_key = f"{sysname}_network_page"
            prev_all = self._prev_state.get(state_key, {})
            current_state = {'time': ts_val, 'interfaces': {}}
            prev_interfaces = prev_all.get('interfaces', {})
            
            dt = ts_val - prev_all.get('time', ts_val) if 'time' in prev_all else 0
            
            for if_index, if_data in iface_map.items():
                if_name = if_data['interface']
                
                # Filter: exclude virtual interfaces
                is_excluded = any(if_name.startswith(p) for p in self.EXCLUDED_PREFIXES)
                if is_excluded:
                    continue
                
                curr_rx = if_data['bytes_recv']
                curr_tx = if_data['bytes_sent']
                
                # Store for next time
                current_state['interfaces'][if_index] = {'rx': curr_rx, 'tx': curr_tx}
                
                # Rate calculation
                rx_rate = 0
                tx_rate = 0
                
                if dt > 0 and if_index in prev_interfaces:
                    prev_if = prev_interfaces[if_index]
                    rx_diff = curr_rx - prev_if['rx']
                    tx_diff = curr_tx - prev_if['tx']
                    
                    if rx_diff >= 0:
                        rx_rate = rx_diff / dt
                    if tx_diff >= 0:
                        tx_rate = tx_diff / dt
                
                if_data['recv_bytes_s'] = rx_rate
                if_data['send_bytes_s'] = tx_rate
                
                filtered_network.append(if_data)
            
            self._prev_state[state_key] = current_state

        return {
            'network': filtered_network,
            'device_info': {'online': True, 'last_seen': ts}
        }

    def _transform_disk(
        self,
        metrics: List[Dict],
        sysname: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transform metrics for the 'disk' topic.
        
        Output format:
        {
            'disk_usage': [{'mount': ..., 'device_partition': ..., 'total': ..., ...}],
            'device_info': {'online': True, 'last_seen': ...}
        }
        """
        dsk_meta: Dict[str, Dict] = {}  # dskIndex -> {mount, device}
        ts = datetime.now().isoformat()
        
        # === Pass 1: Gather Names ===
        for m in metrics:
            if m['name'] == 'disk.usage.mount':
                idx = m.get('labels', {}).get('dskIndex')
                if idx:
                    if idx not in dsk_meta:
                        dsk_meta[idx] = {}
                    dsk_meta[idx]['mount'] = m['value']
            elif m['name'] == 'disk.usage.device':
                idx = m.get('labels', {}).get('dskIndex')
                if idx:
                    if idx not in dsk_meta:
                        dsk_meta[idx] = {}
                    dsk_meta[idx]['device'] = m['value']
            if m.get('ts') and 'disk.usage' in m['name']:
                ts = datetime.fromtimestamp(m['ts']).isoformat()

        # === Pass 2: Gather Values ===
        disk_map: Dict[str, Dict] = {}  # dskIndex -> disk data
        
        for m in metrics:
            if 'disk.usage' not in m['name']:
                continue
            
            idx = m.get('labels', {}).get('dskIndex')
            if not idx:
                continue
            
            if idx not in disk_map:
                meta = dsk_meta.get(idx, {})
                mount = meta.get('mount', 'Unknown')
                device = meta.get('device', 'Unknown')
                disk_map[idx] = {
                    'mount': mount,
                    'device_partition': device,
                    'total': 0, 'used': 0, 'free': 0, 'percent': 0,
                    'time': ts
                }
            
            val = m['value']
            # Note: collector applies scale, so val is already bytes
            if m['name'].endswith('total_kb'):
                disk_map[idx]['total'] = val
            elif m['name'].endswith('used_kb'):
                disk_map[idx]['used'] = val
            elif m['name'].endswith('free_kb'):
                disk_map[idx]['free'] = val
            elif m['name'].endswith('percent'):
                disk_map[idx]['percent'] = val

        # === Calculate missing fields and filter ===
        filtered_disk_usage: List[Dict] = []
        
        for d in disk_map.values():
            # Calculate missing fields
            if 'total' in d and 'used' in d and 'free' not in d:
                d['free'] = d['total'] - d['used']
            if 'total' in d and 'used' in d and 'percent' not in d and d['total'] > 0:
                d['percent'] = (d['used'] / d['total']) * 100
            
            # Filter logic matching queries.py:
            # 1. Mount must be in valid_mounts
            # 2. Device must not be tmpfs
            if d['mount'] in self.VALID_MOUNTS and 'tmpfs' not in d['device_partition']:
                filtered_disk_usage.append(d)

        return {
            'disk_usage': filtered_disk_usage,
            'device_info': {'online': True, 'last_seen': ts}
        }

    def _transform_diskio(
        self,
        metrics: List[Dict],
        sysname: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transform metrics for the 'diskio' topic.
        
        Output format:
        {
            'disk_io': {
                'data': [{'disk': ..., 'time': ..., 'read_bytes': ..., ...}],
                'pagination': {...}
            },
            'device_info': {'online': True, 'last_seen': ...}
        }
        """
        io_meta: Dict[str, str] = {}  # index -> device_name
        ts_val = 0
        ts = datetime.now().isoformat()
        
        if sysname is None:
            sysname = "N/A"
        
        # === Pass 1: Gather Names ===
        for m in metrics:
            if m['name'] == 'sys.name':
                sysname = m['value']
            if m.get('ts'):
                ts_val = m['ts']
            if m['name'] == 'disk.io.device':
                idx = m.get('labels', {}).get('index')
                if idx:
                    io_meta[idx] = m['value']
        
        if ts_val == 0:
            ts_val = datetime.now().timestamp()
        
        # === Pass 2: Gather Values ===
        io_map: Dict[str, Dict] = {}  # index -> disk IO data
        
        for m in metrics:
            if 'disk.io' not in m['name']:
                continue
            if m.get('ts'):
                ts = datetime.fromtimestamp(m['ts']).isoformat()
            
            idx = m.get('labels', {}).get('index')
            if not idx:
                continue
            
            if idx not in io_map:
                device = io_meta.get(idx, f"disk{idx}")
                io_map[idx] = {
                    'disk': device,
                    'time': ts,
                    'read_bytes': 0,
                    'write_bytes': 0
                }
            
            if 'read_bytes' in m['name']:
                io_map[idx]['read_bytes'] = m['value']
            elif 'write_bytes' in m['name']:
                io_map[idx]['write_bytes'] = m['value']
        
        # === Calculate Rates ===
        filtered_data: List[Dict] = []
        
        if sysname != "N/A":
            state_key = f"{sysname}_diskio"
            prev_all = self._prev_state.get(state_key, {})
            current_state = {'time': ts_val, 'devices': {}}
            prev_devices = prev_all.get('devices', {})
            
            dt = ts_val - prev_all.get('time', ts_val) if 'time' in prev_all else 0
            
            for idx, d_data in io_map.items():
                device = d_data['disk']
                curr_read = d_data['read_bytes']
                curr_write = d_data['write_bytes']
                
                # Store for next time
                current_state['devices'][device] = {'read': curr_read, 'write': curr_write}
                
                # Rate calculation
                r_rate = 0
                w_rate = 0
                
                if dt > 0 and device in prev_devices:
                    prev_d = prev_devices[device]
                    r_diff = curr_read - prev_d['read']
                    w_diff = curr_write - prev_d['write']
                    
                    if r_diff >= 0:
                        r_rate = r_diff / dt
                    if w_diff >= 0:
                        w_rate = w_diff / dt
                
                d_data['read_bytes_s'] = r_rate
                d_data['write_bytes_s'] = w_rate
                
                # Filter Logic matching queries.py:
                # SQL: (disk NOT REGEXP '[0-9]+$' OR disk LIKE 'mmcblk%')
                #      AND disk NOT LIKE '%p[0-9]%'
                cond1 = (not re.search(r'[0-9]+$', device)) or device.startswith('mmcblk')
                cond2 = not re.search(r'p[0-9]', device)
                
                if cond1 and cond2:
                    filtered_data.append(d_data)
            
            self._prev_state[state_key] = current_state
        else:
            # Edge case: no sysname, just filter without rate calculation
            for d_data in io_map.values():
                device = d_data['disk']
                d_data['read_bytes_s'] = 0
                d_data['write_bytes_s'] = 0
                
                cond1 = (not re.search(r'[0-9]+$', device)) or device.startswith('mmcblk')
                cond2 = not re.search(r'p[0-9]', device)
                
                if cond1 and cond2:
                    filtered_data.append(d_data)

        return {
            'disk_io': {
                'data': filtered_data,
                'pagination': {
                    'page': 1,
                    'per_page': len(filtered_data),
                    'total': len(filtered_data),
                    'total_pages': 1
                }
            },
            'device_info': {'online': True, 'last_seen': ts}
        }


# =============================================================================
# Module-level singleton instance
# =============================================================================
# This is used by the UDP listener to maintain state across packets.
# IMPORTANT: Must be accessed from the same process for InMemoryChannelLayer.
_transformer_instance: Optional[RealTimeTransformer] = None


def get_transformer() -> RealTimeTransformer:
    """
    Get the singleton transformer instance.
    Creates one if it doesn't exist.
    """
    global _transformer_instance
    if _transformer_instance is None:
        _transformer_instance = RealTimeTransformer()
    return _transformer_instance
