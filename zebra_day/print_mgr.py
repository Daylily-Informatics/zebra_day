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

    def __init__(self, debug=0):
        self.load_printer_json()
        self.debug = False if debug in [0,'0'] else True

        
    def load_printer_json(self, json_file="etc/printer_config.json"):
        fh = open(json_file)
        self.printers_filename = json_file
        self.printers = json.load(fh)

        
    def replace_printer_json_from_template(self):
        os.system('cp etc/printer_config.template.json etc/printer_config.json')


    def get_valid_label_styles_for_lab(self,lab=None):
        unique_labels = set()

        for printer in self.printers['labs'][lab]:
            for style in self.printers['labs'][lab][printer]['label_zpl_styles']:
                unique_labels.add(style)

        result = list(unique_labels)
        return result

    
    def formulate_zpl(self,uid_barcode=None, uid_human_readable=None, alt_a=None, alt_b=None, alt_c=None, alt_d=None, alt_e=None, alt_f=None, label_zpl_style=None):

        zpl_file = f"etc/label_styles/{label_zpl_style}.zpl"
        if not os.path.exists(zpl_file):
            raise Exception(f"ZPL File : {zpl_file} does not exist.")

        with open(zpl_file, 'r') as file:
            content = file.read()
        zpl_string = content.format(uid_barcode=uid_barcode, uid_human_readable=uid_human_readable,alt_a=alt_a, alt_b=alt_b, alt_c=alt_c, alt_d=alt_d, alt_e=alt_e, alt_f=alt_f, label_zpl_style=label_zpl_style)

        return zpl_string

            
    def print_zpl(self, lab=None, printer_name=None, uid_barcode='', uid_human_readable='', alt_a='', alt_b='', alt_c='', alt_d='', alt_e='', alt_f='', label_zpl_style=None):

        if label_zpl_style in [None,'','None']:
            label_zpl_style = self.printers['labs'][lab][printer_name]['label_zpl_styles'][0]  # If a style is not specified, assume the first
        elif label_zpl_style not in self.printers['labs'][lab][printer_name]['label_zpl_styles']:
            raise Exception(f"ZPL style: {label_zpl_style} is not valid for {lab} {printer_name} ... {self.printers['labs'][lab][printer_name]['label_zpl_styles']}")

        printer_ip = self.printers['labs'][lab][printer_name]["ip_address"]

        zpl_string = self.formulate_zpl(uid_barcode=uid_barcode, uid_human_readable=uid_human_readable, alt_a=alt_a, alt_b=alt_b, alt_c=alt_c, alt_d=alt_d, alt_e=alt_e, alt_f=alt_f, label_zpl_style=label_zpl_style)

        send_zpl_code(zpl_string, printer_ip)

        if self.debug:
            print(f"\nZPL STRING  :: {zpl_string}\n")
    
