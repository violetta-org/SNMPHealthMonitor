import sys
import os
import json

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../query-service')))

from utils.data_transformer import RealTimeTransformer

def test_transform():
    # Mock Payload
    mock_payload = {
        'sysname': 'raspi-vm',
        'sys_location': 'Lab 1',
        'uptime': 12345,
        'ip_address': '192.168.1.10',
        'load_avg': {'1m': 0.5, '5m': 0.8, '15m': 1.2},
        'net_io': [
            {'name': 'eth0', 'bytes_sent': 1000, 'bytes_recv': 2000, 'send_rate': 10, 'recv_rate': 20}
        ],
        'disk_usage': [
            {'mount': '/', 'device': '/dev/sda1', 'total': 100, 'used': 60, 'free': 40, 'percent': 60.0}
        ],
        'disk_io': [
            {'name': 'sda', 'read_bytes': 5000, 'write_bytes': 3000, 'read_rate': 50, 'write_rate': 30}
        ]
    }

    topics = ['systemstatus', 'network', 'disk', 'diskio']
    
    for topic in topics:
        print(f"--- Testing Topic: {topic} ---")
        result = RealTimeTransformer.transform(topic, mock_payload)
        print(json.dumps(result, indent=2))
        
        # Basic Validation
        if topic == 'systemstatus':
            assert 'system_info' in result
            assert result['system_info']['sysname'] == 'raspi-vm'
        elif topic == 'network':
            assert 'net_io' in result
            assert result['net_io'][0]['interface'] == 'eth0'
        elif topic == 'disk':
            assert 'disk_usage' in result
            assert result['disk_usage'][0]['mount'] == '/'
        elif topic == 'diskio':
            assert 'disk_io' in result
            assert 'pagination' in result['disk_io']
            assert result['disk_io']['pagination']['total'] == 1
            
    print("\n[SUCCESS] All transforms passed basic validation.")

if __name__ == "__main__":
    test_transform()
