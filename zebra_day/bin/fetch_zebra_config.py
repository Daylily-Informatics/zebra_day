import socket
import sys

def send_zpl_to_printer(ip_address, port, zpl_string):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((ip_address, port))
        s.sendall(zpl_string.encode())
        response = s.recv(1024)
    return response.decode()

# Example usage
ip = sys.argv[1]
zpl_command = '^XA^HH^XZ'  # This command retrieves the printer's configuration. Replace as needed.
response = send_zpl_to_printer(ip, 9100, zpl_command)
print(response)
