import socket
import json
import threading
from typing import Callable
from config import NOTIFY_PORT
from utils.logging import configure_logger

class UDPNotificationListener:
    def __init__(self, port: int = NOTIFY_PORT, callback: Callable = None):
        self.port = port
        self.callback = callback
        self.running = False
        self.thread = None
        self.sock = None
        self.logger = configure_logger(__name__)
    
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._listen, daemon=True)
        self.thread.start()
        self.logger.info(f"Started on port {self.port}")
    
    def stop(self):
        self.logger.info(f"Stopping...")
        self.running = False
        
        # Close socket để unblock recvfrom() trong thread
        if self.sock:
            try:
                self.sock.close()
                self.logger.info(f"Socket closed")
            except Exception as e:
                self.logger.error(f"Error closing socket: {e}")
        
        # Wait for thread to finish (timeout 2 seconds)
        if self.thread and self.thread.is_alive():
            self.logger.info(f"Waiting for thread to finish...")
            self.thread.join(timeout=2.0)
            if self.thread.is_alive():
                self.logger.warning(f"Thread did not finish within timeout")
            else:
                self.logger.info(f"Thread finished")
    
    def _listen(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.bind(('0.0.0.0', self.port))
            self.sock.settimeout(1.0)
            self.logger.info(f"Listening on port {self.port}")
            
            while self.running:
                try:
                    data, addr = self.sock.recvfrom(65535)
                    message = json.loads(data.decode('utf-8'))
                    
                    if message.get('event') == 'new_data':
                        sysname = message.get('sysname')
                        metric_count = message.get('metric_count', 0)
                        self.logger.info(f"New data for {sysname}, metric_count: {metric_count}")
                        
                        if self.callback:
                            self.callback(message)
                except socket.timeout:
                    # Timeout is expected, continue to check self.running
                    continue
                except OSError as e:
                    # Socket closed or error - break loop
                    if not self.running:
                        self.logger.info(f"Socket closed, exiting listen loop")
                        break
                    self.logger.error(f"Socket error: {e}")
                    break
                except Exception as e:
                    if self.running:
                        self.logger.error(f"Error: {e}")
        except Exception as e:
            self.logger.error(f"Failed to start listener: {e}")
        finally:
            if self.sock:
                try:
                    self.sock.close()
                except:
                    pass
            self.logger.info(f"Listen loop ended")
