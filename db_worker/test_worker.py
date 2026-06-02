import unittest
from unittest.mock import MagicMock, patch
import json
import logging

# We will implement these in worker.py
from worker import parse_packet, process_packet, forward_packet

class TestDBWorker(unittest.TestCase):
    def setUp(self):
        self.valid_payload = {
            "event": "new_data",
            "sysname": "nano",
            "metric_count": 2,
            "timestamp": 1685799999.0,
            "ip_address": "127.0.0.1",
            "metrics": [
                {"name": "cpu.core.percent", "value": 12.5, "labels": {"hrDeviceIndex": "1"}, "ts": 1685799999},
                {"name": "temperature.cpu", "value": 45.5, "ts": 1685799999}
            ]
        }
        self.valid_bytes = json.dumps(self.valid_payload).encode('utf-8')

    def test_parse_packet_success(self):
        """Should parse valid JSON bytes correctly."""
        result = parse_packet(self.valid_bytes)
        self.assertEqual(result, self.valid_payload)

    def test_parse_packet_invalid_json(self):
        """Should return None and log error if JSON is malformed."""
        with self.assertLogs('worker', level='ERROR') as log:
            result = parse_packet(b"{invalid-json}")
            self.assertIsNone(result)
            self.assertTrue(any("Failed to parse JSON" in line for line in log.output))

    def test_parse_packet_missing_fields(self):
        """Should return None if required fields are missing."""
        invalid_payload = {"event": "new_data"}  # missing sysname, metrics
        result = parse_packet(json.dumps(invalid_payload).encode('utf-8'))
        self.assertIsNone(result)

    @patch('worker.get_connection')
    @patch('worker.upsert_device')
    @patch('worker.write_metrics_batch')
    def test_process_packet(self, mock_write, mock_upsert, mock_get_conn):
        """Should connect to DB, upsert device, write metrics, and commit."""
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn

        process_packet(self.valid_payload)

        mock_get_conn.assert_called_once()
        mock_upsert.assert_called_once_with(mock_conn, sysname="nano", ip_address="127.0.0.1")
        mock_write.assert_called_once_with(mock_conn, "nano", self.valid_payload["metrics"])
        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch('worker.get_connection')
    @patch('worker.write_metrics_batch')
    def test_process_packet_db_error_handling(self, mock_write_metrics_batch, mock_get_conn):
        """Should rollback and log error if database operation fails."""
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_write_metrics_batch.side_effect = Exception("DB Connection Lost")

        with self.assertLogs('worker', level='ERROR') as log:
            process_packet(self.valid_payload)
            mock_conn.rollback.assert_called_once()
            mock_conn.close.assert_called_once()
            self.assertTrue(any("Database operation failed" in line for line in log.output))

    @patch('socket.socket')
    def test_forward_packet(self, mock_socket):
        """Should forward the packet to the specified host and port via UDP."""
        mock_sock_instance = MagicMock()
        mock_socket.return_value = mock_sock_instance

        forward_packet(self.valid_bytes, "127.0.0.1", 6004)

        mock_sock_instance.sendto.assert_called_once_with(self.valid_bytes, ("127.0.0.1", 6004))
        mock_sock_instance.close.assert_called_once()

if __name__ == '__main__':
    unittest.main()
