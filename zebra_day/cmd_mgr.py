"""
  Tools to manage a zebra printer fleet and expose an API for routing print requests.
"""

import socket

class ZebraPrinter:

    def __init__(self, ip_address, port=9100, buffer_size=1024):
        self.ip_address = ip_address
        self.port = port
        self.buffer_size = buffer_size

        
    def send_command(self, command):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((self.ip_address, self.port))
            s.sendall(command.encode())
            response = s.recv(self.buffer_size)
        return response.decode()

    
    def get_configuration(self):
        """Retrieve printer configuration using ^HH command"""
        return self.send_command("^XA^HH^XZ")

    
    def set_configuration(self, config):
        """
        Set printer configuration. 
        The `config` parameter should contain the necessary ZPL commands to adjust the configuration.
        After sending the configuration commands, the ^JUS command saves the configuration.
        """
        self.send_command(config)
        return self.send_command("^XA^JUS^XZ")
