import sys
import os
import json
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../query-service')))
from utils.data_transformer import RealTimeTransformer

class TestTransformation(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(os.path.dirname(__file__), 'mock_valid_metrics.json'), 'r') as f:
            self.metrics = json.load(f)

    def test_systemstatus(self):
        result = RealTimeTransformer.transform('systemstatus', self.metrics)
        print("\n--- systemstatus ---")
        print(json.dumps(result, indent=2))
        self.assertIn('system_info', result)
        self.assertEqual(result['system_info']['sysname'], 'raspi-vm')
        self.assertEqual(result['load_avg']['load_1m'], 0.5)
        # CPU checks
        self.assertTrue(len(result['cpu_percent']) >= 2)
        self.assertEqual(result['cpu_percent'][0]['percent'], 45.5)
        # Memory checks
        self.assertIn('memory', result)
        self.assertEqual(result['memory']['total'], 8000000000)
        self.assertEqual(result['memory']['percent'], 50.0)

    def test_network(self):
        result = RealTimeTransformer.transform('network', self.metrics)
        print("\n--- network ---")
        print(json.dumps(result, indent=2))
        self.assertIn('net_io', result)
        self.assertTrue(len(result['net_io']) > 0)
        self.assertEqual(result['net_io'][0]['interface'], 'eth0')
        self.assertEqual(result['net_io'][0]['bytes_recv'], 102400)

    def test_disk(self):
        result = RealTimeTransformer.transform('disk', self.metrics)
        print("\n--- disk ---")
        print(json.dumps(result, indent=2))
        self.assertIn('disk_usage', result)
        self.assertEqual(result['disk_usage'][0]['mount'], '/')
        self.assertEqual(result['disk_usage'][0]['total'], 1000000 * 1024) # KB to Bytes check

    def test_diskio(self):
        result = RealTimeTransformer.transform('diskio', self.metrics)
        print("\n--- diskio ---")
        print(json.dumps(result, indent=2))
        self.assertIn('disk_io', result)
        self.assertEqual(result['disk_io']['data'][0]['disk'], 'sda')
        self.assertEqual(result['disk_io']['data'][0]['read_bytes'], 5000000)

if __name__ == '__main__':
    unittest.main()
