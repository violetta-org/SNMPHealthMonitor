import socket
import json
import threading
from typing import Callable
from config import NOTIFY_PORT

class UDPNotificationListener:
    def __init__(self, port: int = NOTIFY_PORT, callback: Callable = None):
        self.port = port
        self.callback = callback
        self.running = False
        self.thread = None
        self.sock = None
    
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._listen, daemon=True)
        self.thread.start()
        print(f"[UDPListener] Started on port {self.port}")
    
    def stop(self):
        print(f"[UDPListener] Stopping...")
        self.running = False
        
        # Close socket để unblock recvfrom() trong thread
        if self.sock:
            try:
                self.sock.close()
                print(f"[UDPListener] Socket closed")
            except Exception as e:
                print(f"[UDPListener] Error closing socket: {e}")
        
        # Wait for thread to finish (timeout 2 seconds)
        if self.thread and self.thread.is_alive():
            print(f"[UDPListener] Waiting for thread to finish...")
            self.thread.join(timeout=2.0)
            if self.thread.is_alive():
                print(f"[UDPListener] Warning: Thread did not finish within timeout")
            else:
                print(f"[UDPListener] Thread finished")
    
    def _listen(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.bind(('0.0.0.0', self.port))
            self.sock.settimeout(1.0)
            print(f"[UDPListener] Listening on port {self.port}")
            
            while self.running:
                try:
                    data, addr = self.sock.recvfrom(4096)
                    message = json.loads(data.decode('utf-8'))
                    
                    if message.get('event') == 'new_data':
                        sysname = message.get('sysname')
                        metric_count = message.get('metric_count', 0)
                        print(f"[UDPListener] New data for {sysname}, metric_count: {metric_count}")
                        
                        if self.callback:
                            self.callback(message)
                except socket.timeout:
                    # Timeout is expected, continue to check self.running
                    continue
                except OSError as e:
                    # Socket closed or error - break loop
                    if not self.running:
                        print(f"[UDPListener] Socket closed, exiting listen loop")
                        break
                    print(f"[UDPListener] Socket error: {e}")
                    break
                except Exception as e:
                    if self.running:
                        print(f"[UDPListener] Error: {e}")
        except Exception as e:
            print(f"[UDPListener] Failed to start listener: {e}")
        finally:
            if self.sock:
                try:
                    self.sock.close()
                except:
                    pass
            print(f"[UDPListener] Listen loop ended")

