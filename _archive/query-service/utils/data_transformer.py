from datetime import datetime
from typing import List, Dict, Any

class RealTimeTransformer:
    """Transforms list of flattened metrics into structured JSON for frontend.
    Now stateful to calculate rates (e.g. network throughput).
    """
    
    
    # Predefined list of excluded prefixes (Loopback, Docker, Virtual, VPN)
    EXCLUDED_PREFIXES = ['lo', 'lo0', 'docker', 'veth', 'br-', 'virbr', 'wg', 'zt']

    def __init__(self):
        # Store previous values for rate calculation
        # {sysname: {'net_rx': val, 'net_tx': val, 'time': ts}}
        self._prev_state: Dict[str, Dict] = {}

    def transform(self, topic: str, metrics: List[Dict[str, Any]], sysname: str = None) -> Dict[str, Any]:
        """
        Main entry point (instance method).
        Args:
            topic: systemstatus, network, disk, diskio
            metrics: List of metric objects {name, value, labels, ts}
            sysname: Optional system name from caller (UDP message)
        """
        if not metrics:
            return {}

        method_name = f"_transform_{topic}"
        transformer = getattr(self, method_name, None)
        
        if transformer:
            # Check if method accepts sysname
            import inspect
            sig = inspect.signature(transformer)
            if 'sysname' in sig.parameters:
                return transformer(metrics, sysname=sysname)
            return transformer(metrics)
        return {}

    @staticmethod
    def _get_metric_value(metrics: List[Dict], name_suffix: str, labels: Dict = None) -> Any:
        # Helper to find a specific metric value (static is fine here but can be instance too)
        for m in metrics:
            if m['name'].endswith(name_suffix):
                if labels:
                    # Check if all provided labels match
                    match = True
                    for k, v in labels.items():
                        if m.get('labels', {}).get(k) != v:
                            match = False
                            break
                    if match:
                        return m['value']
                else:
                    return m['value']
        return None

    def _transform_systemstatus(self, metrics: List[Dict]) -> Dict:
        # Group: system_info, load_avg, device_info
        # PLUS: cpu_percent, memory, swap (as per user requirement to map all in 4 topics)
        
        sysname = "N/A"
        location = "N/A" 
        uptime = 0
        ts = datetime.now().isoformat()
        
        # CPU, Memory, Swap containers
        cpu_map = {} # index -> {cpu, percent}
        mem_data = {}
        swap_data = {}
        
        load_1m = 0
        load_5m = 0
        load_15m = 0
        
        # Network counters per interface: ifIndex -> {rx, tx, name}
        net_counters = {}
        
        ts_val = 0
        
        for m in metrics:
            name = m['name']
            val = m['value']
            
            # Timestamp (prefer latest)
            if m.get('ts'): 
                ts_val = m['ts']
                ts = datetime.fromtimestamp(m['ts']).isoformat()
            
            # System Info - extract from individual metrics
            if name == 'sys.name':
                sysname = val
            elif name == 'sys.location':
                location = val
            elif name == 'sys.uptime.seconds':
                uptime = val
            
            # Load Avg
            elif name == 'load.1m': load_1m = val
            elif name == 'load.5m': load_5m = val
            elif name == 'load.15m': load_15m = val
            
            # CPU - convert hrDeviceIndex to sequential core numbers
            elif name == 'cpu.core.percent':
                # Get hrDeviceIndex from labels and convert to int for sorting
                hr_index = m.get('labels', {}).get('hrDeviceIndex', '0')
                cpu_map[hr_index] = {
                    'percent': val,
                    'time': ts
                }
            
            # Memory
            elif name.startswith('memory.'):
                # memory.total, memory.used, memory.free, memory.cached, memory.buffers
                field = name.split('.')[-1] # e.g. 'total'
                mem_data[field] = val
                
            # Swap
            elif name.startswith('swap.'):
                 field = name.split('.')[-1]
                 swap_data[field] = val

            # Network metrics - group by interface to calculate rates per interface
            elif name.startswith('network.'):
                if_index = m.get('labels', {}).get('ifIndex')
                if if_index:
                    # Filter logic: Match queries.py (Physical-like interfaces only)
                    # We often don't have the interface NAME yet (it comes in a separate metric).
                    # However, we build `net_counters` keyed by index.
                    # We must verify the name matches the pattern when we process `network.interface.name`.
                    # OR we can assume we only want to KEEP the entry if the name eventually matches.
                    # But `network.interface.name` is just one metric in the stream.
                    
                    # Better approach: Collect everything first, then filter the `net_counters` dictionary before processing rates.
                    
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

        # Post-process Memory
        if 'total' in mem_data:
            total = mem_data['total']
            
            # Ensure basic fields exist
            for f in ['free', 'cached', 'buffers', 'available', 'shared']:
                if f not in mem_data: mem_data[f] = 0
            
            # Validate: cap values at total (SNMP data can be invalid)
            # CRITICAL FIX: Some Linux systems report Free = Physical Free + Swap Free
            # If Free > Total, we must subtract Swap Free to get real Physical Free
            if mem_data['free'] > total:
                 swap_free = swap_data.get('free', 0)
                 mem_data['free'] = max(0, mem_data['free'] - swap_free)

            mem_data['free'] = min(mem_data['free'], total)
            mem_data['cached'] = min(mem_data['cached'], total)
            mem_data['buffers'] = min(mem_data['buffers'], total)
            mem_data['available'] = min(mem_data['available'], total)
            
            # Recalculate 'used' because raw SNMP used might be missing or wrong
            # Standard Linux calculation: used = total - free - buffers - cached
            calculated_used = total - mem_data['free'] - mem_data['buffers'] - mem_data['cached']
            mem_data['used'] = max(0, calculated_used)
            
            # Also ensure 'percent' is present
            if total > 0:
                mem_data['percent'] = (mem_data['used'] / total) * 100
                
        # Post-process Swap
        if 'total' in swap_data:
            if 'used' not in swap_data:
                 # Swap used = total - free
                 swap_data['used'] = max(0, swap_data.get('total', 0) - swap_data.get('free', 0))
            
            if 'percent' not in swap_data and swap_data.get('total', 0) > 0:
                swap_data['percent'] = (swap_data['used'] / swap_data['total']) * 100
            
            if 'free' not in swap_data: swap_data['free'] = 0

        # Rate Calculation (Per Interface)
        network_data = [] # Changed to List as per user request
        
        if sysname != "N/A":
            prev_all = self._prev_state.get(sysname, {})
            current_state = {'time': ts_val, 'interfaces': {}}
            
            dt = 0
            if 'time' in prev_all:
                 dt = ts_val - prev_all['time']

            for if_idx, counters in list(net_counters.items()):
                if_name = counters['name']
                
                # Filter logic: Match queries.py strictness
                is_excluded = any(if_name.startswith(p) for p in self.EXCLUDED_PREFIXES)
                
                if is_excluded:
                    continue

                curr_rx = counters['rx']
                curr_tx = counters['tx']
                admin_status = counters['admin_status']
                oper_status = counters['oper_status']
                
                # Store currents for next time
                current_state['interfaces'][if_idx] = {'rx': curr_rx, 'tx': curr_tx}
                
                rx_rate = 0
                tx_rate = 0
                
                if dt > 0 and 'interfaces' in prev_all and if_idx in prev_all['interfaces']:
                     prev_if = prev_all['interfaces'][if_idx]
                     rx_diff = curr_rx - prev_if['rx']
                     tx_diff = curr_tx - prev_if['tx']
                     
                     if rx_diff >= 0: rx_rate = rx_diff / dt
                     if tx_diff >= 0: tx_rate = tx_diff / dt
                
                # Push object to list
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

        # Post-process CPU: Convert hrDeviceIndex to sequential core numbers
        cpu_cores = []
        if cpu_map:
            # Sort by hrDeviceIndex to get consistent ordering
            sorted_indices = sorted(cpu_map.keys(), key=lambda x: int(x) if str(x).isdigit() else 0)
            for core_num, hr_index in enumerate(sorted_indices):
                cpu_cores.append({
                    'cpu': f'cpu{core_num}',  # cpu0, cpu1, ...
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

    def _transform_network(self, metrics: List[Dict], sysname: str = None) -> Dict:
        # Group by ifIndex (from labels)
        iface_map = {} # ifIndex -> {interface, bytes_sent, bytes_recv, ...}
        ts_val = 0
        ts = datetime.now().isoformat()
        if sysname is None:
            sysname = "N/A"
        
        # First, build index -> name mapping and find sysname
        iface_names = {}
        for m in metrics:
            if m['name'] == 'sys.name': sysname = m['value']
            if m.get('ts'): ts_val = m['ts']
            
            if m['name'] == 'network.interface.name':
                if_index = m.get('labels', {}).get('ifIndex')
                if if_index:
                    iface_names[if_index] = m['value']
        
        if ts_val == 0: ts_val = datetime.now().timestamp()
        
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
        
        # Calculate Rates
        if sysname != "N/A":
            prev_all = self._prev_state.get(sysname + '_network_page', {})
            current_state = {'time': ts_val, 'interfaces': {}}
            prev_interfaces = prev_all.get('interfaces', {})
            dt = 0
            if 'time' in prev_all: dt = ts_val - prev_all['time']
            
            # Only update state for Network Page if we have relevant data
            # But wait, shared state with systemstatus? 
            # Ideally yes, but systemstatus uses logical names often? 
            # Here we use ifIndex. Let's use ifIndex for state key to be robust.
            # Or use interface name if available.
            
            filtered_network = []
            for if_index, if_data in iface_map.items():
                if_name = if_data['interface']
                 
                # Filter logic: Match queries.py strictness
                is_excluded = any(if_name.startswith(p) for p in self.EXCLUDED_PREFIXES)
                
                if is_excluded:
                    continue

                curr_rx = if_data['bytes_recv']
                curr_tx = if_data['bytes_sent']
                
                # Store for next time
                current_state['interfaces'][if_index] = {'rx': curr_rx, 'tx': curr_tx}
                
                # Rate
                rx_rate = 0
                tx_rate = 0
                if dt > 0 and if_index in prev_interfaces:
                    prev_if = prev_interfaces[if_index]
                    rx_diff = curr_rx - prev_if['rx']
                    tx_diff = curr_tx - prev_if['tx']
                    
                    if rx_diff >= 0: rx_rate = rx_diff / dt
                    if tx_diff >= 0: tx_rate = tx_diff / dt
                
                if_data['recv_bytes_s'] = rx_rate
                if_data['send_bytes_s'] = tx_rate
                
                filtered_network.append(if_data)

            # Update state (Merge with existing? Be careful not to overwrite systemstatus state if they share 'sysname' key)
            # Strategy: Use a distinct key prefix for Network Page state?
            # Or share? "interfaces" in systemstatus state was keyed by if_index too?
            # In systemstatus transformer (lines 127), it keyed net_counters by if_index.
            # And saved state keyed by 'interfaces' (line 179).
            # So they ARE compatible if I use the same structure.
            # 'interfaces' -> ifIndex -> {rx, tx}
            
            # However, I should probably separate them to avoid race conditions or just use a different key in _prev_state map.
            # e.g. self._prev_state[sysname + '_network_page']
            
            self._prev_state[sysname + '_network_page'] = current_state

        return {
            'network': filtered_network,
            'device_info': { 'online': True, 'last_seen': ts }
        }

    @staticmethod
    def _transform_disk(metrics: List[Dict]) -> Dict:
        # Group by dskIndex first to find names
        # Map: dskIndex -> {mount, device}
        dsk_meta = {}
        ts = datetime.now().isoformat()
        
        # Pass 1: Gather Names
        for m in metrics:
            if m['name'] == 'disk.usage.mount':
                idx = m.get('labels', {}).get('dskIndex')
                if idx:
                    if idx not in dsk_meta: dsk_meta[idx] = {}
                    dsk_meta[idx]['mount'] = m['value']
            elif m['name'] == 'disk.usage.device':
                idx = m.get('labels', {}).get('dskIndex')
                if idx:
                    if idx not in dsk_meta: dsk_meta[idx] = {}
                    dsk_meta[idx]['device'] = m['value']
            if m.get('ts') and 'disk.usage' in m['name']:
                 ts = datetime.fromtimestamp(m['ts']).isoformat()

        # Pass 2: Gather Values
        disk_map = {} # dskIndex -> {total, used...}
        
        for m in metrics:
            if 'disk.usage' not in m['name']: continue
            
            idx = m.get('labels', {}).get('dskIndex')
            if not idx: continue
            
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
            # OIDs scale is 1024 according to snmp_oids_linux.json for kb fields
            # The collector applies scale! So val is already bytes if scale=1024 was defined in JSON?
            # Let's check snmp_oids_linux.json again.
            # { "name": "disk.usage.total_kb", ... "scale": 1024, "unit": "bytes" }
            # Yes, collector applies scale. So val is BYTES.
            
            if m['name'].endswith('total_kb'):
                disk_map[idx]['total'] = val
            elif m['name'].endswith('used_kb'):
                disk_map[idx]['used'] = val
            elif m['name'].endswith('free_kb'):
                disk_map[idx]['free'] = val
            elif m['name'].endswith('percent'):
                disk_map[idx]['percent'] = val

        # Calculate missing fields
        filtered_disk_usage = []
        valid_mounts = ['/', '/boot/firmware']
        
        for d in disk_map.values():
            if 'total' in d and 'used' in d and 'free' not in d:
                d['free'] = d['total'] - d['used']
            if 'total' in d and 'used' in d and 'percent' not in d and d['total'] > 0:
                d['percent'] = (d['used'] / d['total']) * 100
            
            # Filter logic matching queries.py
            # 1. Mount must be in valid_mounts
            # 2. Device must not be tmpfs
            if d['mount'] in valid_mounts and 'tmpfs' not in d['device_partition']:
                filtered_disk_usage.append(d)

        return {
            'disk_usage': filtered_disk_usage,
            'device_info': { 'online': True, 'last_seen': ts }
        }

    def _transform_diskio(self, metrics: List[Dict], sysname: str = None) -> Dict:
        # Group by index
        io_meta = {} # index -> device_name
        
        ts_val = 0
        ts = datetime.now().isoformat()
        if sysname is None:
            sysname = "N/A"
        
        # Pass 1: Gather Names
        for m in metrics:
            if m['name'] == 'sys.name': sysname = m['value']
            if m.get('ts'): ts_val = m['ts']
            
            if m['name'] == 'disk.io.device':
                idx = m.get('labels', {}).get('index')
                if idx:
                    io_meta[idx] = m['value']

        if ts_val == 0: ts_val = datetime.now().timestamp()
        
        # Pass 2: Gather Values
        io_map = {} # index -> data
        
        for m in metrics:
            if 'disk.io' not in m['name']: continue
            if m.get('ts'): ts = datetime.fromtimestamp(m['ts']).isoformat()
            
            idx = m.get('labels', {}).get('index')
            if not idx: continue
            
            if idx not in io_map:
                device = io_meta.get(idx, f"disk{idx}")
                io_map[idx] = {
                    'disk': device, 
                    'time': ts, 
                    'read_bytes': 0, 'write_bytes': 0
                }
            
            if 'read_bytes' in m['name']:
                io_map[idx]['read_bytes'] = m['value']
            elif 'write_bytes' in m['name']:
                io_map[idx]['write_bytes'] = m['value']
        
        # Calculate Rates
        filtered_data = []
        import re # Import locally to avoid top-level change if not needed, or better assume it's available? 
                  # It's better to modify top level imports but I can use import inside.
        
        if sysname != "N/A":
             prev_all = self._prev_state.get(sysname + '_diskio', {})
             current_state = {'time': ts_val, 'devices': {}}
             prev_devices = prev_all.get('devices', {})
             dt = 0
             if 'time' in prev_all: dt = ts_val - prev_all['time']
             
             # Use device name as key for state to persist across index changes (unlikely but safe)?
             # Or use index? Index might change if disks reordered. Device name is safer.
             
             for idx, d_data in io_map.items():
                  device = d_data['disk']
                  curr_read = d_data['read_bytes']
                  curr_write = d_data['write_bytes']
                  
                  current_state['devices'][device] = {'read': curr_read, 'write': curr_write}
                  
                  r_rate = 0
                  w_rate = 0
                  
                  if dt > 0 and device in prev_devices:
                       prev_d = prev_devices[device]
                       r_diff = curr_read - prev_d['read']
                       w_diff = curr_write - prev_d['write']
                       
                       if r_diff >= 0: r_rate = r_diff / dt
                       if w_diff >= 0: w_rate = w_diff / dt
                  
                  d_data['read_bytes_s'] = r_rate
                  d_data['write_bytes_s'] = w_rate

                  # Filter Logic matching queries.py
                  # SQL: (disk NOT REGEXP '[0-9]+$' OR disk LIKE 'mmcblk%') AND disk NOT LIKE '%p[0-9]%'
                  
                  # Python Regex
                  cond1 = (not re.search(r'[0-9]+$', device)) or device.startswith('mmcblk')
                  cond2 = not re.search(r'p[0-9]', device)
                  
                  if cond1 and cond2:
                      filtered_data.append(d_data)
             
             self._prev_state[sysname + '_diskio'] = current_state
        else:
             # Even if no sysname, apply filter to static data? 
             # Ideally yes, but without sysname rate calc is skipped so it's edge case.
             # Just filter io_map values.
             for d_data in io_map.values():
                  device = d_data['disk']
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
            'device_info': { 'online': True, 'last_seen': ts }
        }
