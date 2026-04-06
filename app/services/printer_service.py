import socket
import json

def send_printer_command(ip, port, command_dict):
    json_payload = json.dumps(command_dict).encode('utf-8')
    response = None

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(5.0)
        try:
            sock.connect((ip, port))
            sock.sendall(json_payload)

            try:
                response_data = sock.recv(1024)
                if response_data:
                    try:
                        response = response_data.decode('utf-8')
                    except:
                        response = str(response_data)
                    print(f"Printer response: {response}")
                    return response
            except socket.timeout:
                print("Socket timeout - no response from printer")
                return None
            except Exception as e:
                print(f"Error reading response: {e}")
                return None
        except Exception as e:
            print(f"Connection error: {e}")
            raise