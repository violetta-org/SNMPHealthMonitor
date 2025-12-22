from datetime import datetime
from typing import List, Dict, Any

class RealTimeTransformer:
    """Transforms list of flattened metrics into structured JSON for frontend."""

    @staticmethod
    def transform(topic: str, metrics: List[Dict[str, Any]], extra_context: Dict = None) -> Dict[str, Any]:
        """
        Main entry point.
        Args:
            topic: systemstatus, network, disk, diskio
            metrics: List of metric objects {name, value, labels, ts}
            extra_context: Optional dict containing metadata like {'ip_address': ...}
        """
        if not metrics:
            return {}

        method_name = f"_transform_{topic}"
        transformer = getattr(RealTimeTransformer, method_name, None)
        
        if transformer:
            # Check if transformer accepts extra arguments or just pass it?
            # Easiest is to update all handlers to accept it.
            return transformer(metrics, extra_context=extra_context)
        return {}

    @staticmethod
    def _get_metric_value(metrics: List[Dict], name_suffix: str, labels: Dict = None) -> Any:
        # Helper to find a specific metric value
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

    @staticmethod
    def _transform_systemstatus(metrics: List[Dict], extra_context: Dict = None) -> Dict:
        # Group: system_info, load_avg, device_info
        # PLUS: cpu_percent, memory, swap (as per user requirement to map all in 4 topics)
        
        sysname = "N/A"
        location = "N/A"
        uptime = 0
        
        # Get IP directly from context (reliable)
        ip_address = extra_context.get('ip_address') if extra_context else None
        
        ts = datetime.now().isoformat()
        
        # CPU, Memory, Swap containers
        cpu_map = {} # index -> {cpu, percent}
        mem_data = {}
        swap_data = {}
        
        load_1m = 0
        load_5m = 0
        load_15m = 0
        
        for m in metrics:
            name = m['name']
            val = m['value']
            
            # Timestamp (prefer latest)
            if m.get('ts'): 
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

        # Post-process Memory
        if 'total' in mem_data:
            total = mem_data['total']
            
            # Ensure basic fields exist
            for f in ['free', 'cached', 'buffers', 'available', 'shared']:
                if f not in mem_data: mem_data[f] = 0
            
            # Validate: cap values at total (SNMP data can be invalid)
            mem_data['free'] = min(mem_data['free'], total)
            mem_data['cached'] = min(mem_data['cached'], total)
            mem_data['buffers'] = min(mem_data['buffers'], total)
            mem_data['available'] = min(mem_data['available'], total)
            
            # DON'T calculate used/percent - let frontend do it
            # Frontend xử lý: used = total - free - buffers - cached
            # Backend chỉ gửi raw data sau khi validate
                
        # Post-process Swap
        if 'total' in swap_data:
            if 'used' not in swap_data:
                 # Swap used = total - free
                 swap_data['used'] = max(0, swap_data.get('total', 0) - swap_data.get('free', 0))
            
            if 'percent' not in swap_data and swap_data.get('total', 0) > 0:
                swap_data['percent'] = (swap_data['used'] / swap_data['total']) * 100
            
            if 'free' not in swap_data: swap_data['free'] = 0

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
            'cpu_percent': cpu_cores,
            'memory': mem_data if mem_data else None,
            'swap': swap_data if swap_data else None,
            'device_info': {
                'online': True,
                'last_seen': ts,
                'ip_address': ip_address
            }
        }

    @staticmethod
    def _transform_network(metrics: List[Dict], extra_context: Dict = None) -> Dict:
        # Group by ifIndex (from labels)
        iface_map = {} # ifIndex -> {interface, bytes_sent, bytes_recv, ...}
        ts = datetime.now().isoformat()
        
        # First, build index -> name mapping
        iface_names = {}
        for m in metrics:
            if m['name'] == 'network.interface.name':
                if_index = m.get('labels', {}).get('ifIndex')
                if if_index:
                    iface_names[if_index] = m['value']
        
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
                    'if_oper_status': 1
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
        
        return {
            'net_io': list(iface_map.values()),
            'device_info': { 'online': True, 'last_seen': ts }
        }

    @staticmethod
    def _transform_disk(metrics: List[Dict], extra_context: Dict = None) -> Dict:
        # Group by mount/device
        disk_map = {} # mount -> {total, used, free...}
        ts = datetime.now().isoformat()

        for m in metrics:
            if 'disk.usage' in m['name']:
                if m.get('ts'): ts = datetime.fromtimestamp(m['ts']).isoformat()
                mount = m.get('labels', {}).get('mount')
                device = m.get('labels', {}).get('device')
                key = f"{mount}_{device}"
                
                if key not in disk_map:
                    disk_map[key] = {'mount': mount, 'device_partition': device, 'time': ts}
                
                # values usually in KB or Bytes. Frontend expects? 
                # DB stores bytes usually. If metrics are KB, might need mult.
                # Assuming raw values from node_exporter/psutil might be bytes. 
                # Manager logic valid_metrics needs checking. 
                # User sample: disk.usage.total_kb -> KB.
                
                val = m['value']
                if m['name'].endswith('total_kb'):
                    disk_map[key]['total'] = val * 1024
                elif m['name'].endswith('used_kb'):
                    disk_map[key]['used'] = val * 1024
                elif m['name'].endswith('free_kb'):
                    disk_map[key]['free'] = val * 1024
                elif m['name'].endswith('percent'):
                    disk_map[key]['percent'] = val

        # Calculate missing fields if possible
        for k, d in disk_map.items():
            if 'total' in d and 'used' in d and 'free' not in d:
                d['free'] = d['total'] - d['used']
            if 'total' in d and 'used' in d and 'percent' not in d and d['total'] > 0:
                d['percent'] = (d['used'] / d['total']) * 100

        return {
            'disk_usage': list(disk_map.values()),
            'device_info': { 'online': True, 'last_seen': ts }
        }

    @staticmethod
    def _transform_diskio(metrics: List[Dict], extra_context: Dict = None) -> Dict:
        # Group by device
        io_map = {}
        ts = datetime.now().isoformat()
        
        for m in metrics:
             if 'disk.io' in m['name']:
                if m.get('ts'): ts = datetime.fromtimestamp(m['ts']).isoformat()
                device = m.get('labels', {}).get('device') or m.get('labels', {}).get('name')
                if not device: continue
                
                if device not in io_map:
                    io_map[device] = {'disk': device, 'time': ts}
                
                if 'read_bytes' in m['name']:
                    io_map[device]['read_bytes'] = m['value']
                elif 'write_bytes' in m['name']:
                    io_map[device]['write_bytes'] = m['value']
                    
        data = list(io_map.values())
        return {
            'disk_io': {
                'data': data,
                'pagination': {
                    'page': 1,
                    'per_page': len(data),
                    'total': len(data),
                    'total_pages': 1
                }
            },
            'device_info': { 'online': True, 'last_seen': ts }
        }
