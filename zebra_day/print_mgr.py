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
        self.load_printer_json()

        
    def load_printer_json(self, json_file="etc/printer_config.json"):
        fh = open(json_file)
        self.printers = json.load(fh)

        
    def replace_printer_json_from_template(self):
        os.system('cp etc/printer_config.template.json etc/printer_config.json')


    def get_valid_label_styles_for_lab(self,lab=None):
        unique_labels = set()

        for printer in self.printers['labs'][lab]['printers']:
            for style in printer['label_zpl_styles']:
                unique_labels.add(style)

        result = list(unique_labels)
        return result
        
    def formulate_zpl(self,uid_barcode=None, uid_human_readable=None, alt_a=None, alt_b=None, alt_c=None, alt_d=None, alt_e=None, alt_f=None, label_zpl_style=None):
        pass

    
    def print_zpl(self, lab=None, printer_name=None, uid_barcode=None, uid_human_readable=None, alt_a=None, alt_b=None, alt_c=None, alt_d=None, alt_e=None, alt_f=None, label_zpl_style=None):

        if label_zpl_style in [None,'','None']:
            label_zpl_style = self.printers['labs'][lab][printer_name]['printers']
        zpl_string = "ZPL NOT CREATED"
        send_zpl_code(zpl_string, ip_addr)

    
