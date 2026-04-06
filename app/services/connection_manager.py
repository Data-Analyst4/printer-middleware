import socket
import threading
import time
from app.utils.logger import log

class ConnectionManager:
    def __init__(self, printer_id, ip, port):
        self.printer_id = printer_id
        self.ip = ip
        self.port = port
        self.socket = None
        self.connected = False
        self.lock = threading.Lock()
        self.keep_alive = True
        self.thread = threading.Thread(target=self._maintain_connection, daemon=True)
        self.thread.start()

    def _maintain_connection(self):
        while self.keep_alive:
            try:
                if not self.connected:
                    self._connect()
                time.sleep(30)  # Check connection every 30 seconds
            except Exception as e:
                log(f"Connection maintenance error for {self.printer_id}: {e}")
                self.connected = False
                time.sleep(5)  # Retry after 5 seconds

    def _connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10.0)
            self.socket.connect((self.ip, self.port))
            self.connected = True
            log(f"Connected to printer {self.printer_id} at {self.ip}:{self.port}")
        except Exception as e:
            self.connected = False
            log(f"Failed to connect to printer {self.printer_id}: {e}")
            raise

    def send_command(self, command_dict):
        with self.lock:
            if not self.connected:
                self._connect()

            try:
                import json
                json_payload = json.dumps(command_dict).encode('utf-8')
                self.socket.sendall(json_payload)

                # Try to read response
                response = None
                try:
                    self.socket.settimeout(2.0)  # Short timeout for response
                    response_data = self.socket.recv(1024)
                    if response_data:
                        try:
                        response_text = response_data.decode('utf-8')
                        try:
                            import json as _json
                            response = _json.loads(response_text)
                        except Exception:
                            response = response_text
                    except Exception:

                return response

            except Exception as e:
                log(f"Send error for {self.printer_id}: {e}")
                self.connected = False
                raise

    def close(self):
        self.keep_alive = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        self.connected = False

    def update_target(self, ip, port):
        with self.lock:
            self.ip = ip
            self.port = port
            self.connected = False
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None