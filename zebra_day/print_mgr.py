import os
import sys
import socket
import datetime
import json


def get_current_date():
    current_date = datetime.date.today()
    formatted_date = current_date.strftime("%Y-%m-%d")
    return formatted_date

def send_zpl_code(zpl_code, printer_ip, printer_port=9100):
    # Create a socket object
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    timeout = 5
    sock.settimeout(timeout)

    try:
        # Connect to the printer
        sock.connect((printer_ip, printer_port))

        # Send the ZPL code as raw bytes
        sock.sendall(zpl_code.encode())
        print("ZPL code sent successfully to the printer!")

    except ConnectionError as e:
        print(f"Error connecting to the printer: {e}")

    finally:
        # Close the socket connection
        sock.close()

class zpl:

    def __init__(self):
        pass


    def print_zpl(self, station_name=None, ip_addr=None, lab=None, label_zpl_style=None):
        rec_date = get_current_date()

        zpl_string = "ZPL NOT CREATED"
        send_zpl_code(zpl_string, ip_addr)

    
