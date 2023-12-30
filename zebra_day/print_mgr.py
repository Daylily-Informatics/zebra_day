"""
  Primay zebra_day module. Primary functions: consistent and clear management
  of 1+ networked zebra printers, automated discovery of printers on a
  network. Clear formulation and delivery of ZPL strings to destination
  printers. Management of zpl template files, which may have format value
  components for inserting data on the fly. (elsewhere, a simple ui on
  top of this).

  This module is primarily focused on print request and package config mgmt.
  See 'cmd_mgr' for interacting with zebras printer config capabilties.
"""

import os
import sys
import socket
import datetime
import json
import requests
from importlib.resources import files



def get_current_date():
    """
    get the current datetime
    """

    current_date = datetime.date.today()
    formatted_date = current_date.strftime("%Y-%m-%d")
    return formatted_date


def send_zpl_code(zpl_code, printer_ip, printer_port=9100, is_test=False):
    """
    The bit which passes the zpl to the specified printer.
    Port is more or less hard coded upstream from here fwiw
    """
    
    # In the case we are testing only, return None
    if is_test:
        return None
    
    # Create a socket object
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    timeout = 5
    sock.settimeout(timeout)

    try:
        # Connect to the printer
        sock.connect((printer_ip, printer_port))

        # Send the ZPL code as raw bytes
        # ... the zebra printer will not throw an error if the request
        # content is incorrect, or for any reason except to reject request to the wrong port.
        return_code = sock.sendall(zpl_code.encode())
        if return_code  in [None]:
            print("ZPL code sent successfully to the printer!", file=sys.stderr)
        else:
            raise Exception(f"\n\nPrint request to {printer_ip}:{printer_port} did not return None, but instead: {return_code} ... zpl: {zpl_code}\n")
            
    except ConnectionError as e:
        raise Exception(f"Error connecting to the printer: {printer_ip} on port {printer_port} \n\n\t"+str(e))

    finally:
        # Close the socket connection
        sock.close()

"""
The zpl.printers object is critical part of zebra_day. There is an in memory js  on which can be stored to an active use json file.  This active use file is
  used when creating a new zpl() class. If absent, a minimal viable json
  object is created in memory, which needs to be populated (via a few methods
  below, or manually if you'd like) before you can do very much.



"""


class zpl:
    """
    The primary class. Instantiate with:
    from zebra_day import print_mgr as zd
    zd_pm = zd.zpl()
    """
    
    def __init__(self, json_config='/etc/printer_config.json' ):
        """
        initialize the class
        
        json_config = if not specified, the standard active
          (which may be empty) is assumed
        """
        zpl_tmps = str(files('zebra_day'))+f"/etc/label_styles/tmps/"
        if not os.path.exists(zpl_tmps):
            os.system(f"mkdir -p {zpl_tmps}")
        
        jcfg = str(files('zebra_day'))+"/etc/printer_config.json"
        if os.path.exists(jcfg):
            self.load_printer_json(jcfg, relative=False)
        else:
            self.create_new_printers_json_with_single_test_printer(jcfg)


    def probe_zebra_printers_add_to_printers_json(self, ip_stub="192.168.1", scan_wait="0.25",lab="scan-results", relative=False):
        """
        Scan the network for zebra printers
        NOTE! this should work with no dependencies on a MAC
        UBUNTU requires system wide net-tools (for arp)
        Others... well, this may not work

        ---
        Requires:
          curl is pretty standard, arp seems less so
          arp  
        ---
        
        ip_stub = all 255 possibilities will be probed beneath this
        stub provided

        can_wait = seconds to re-try probing until moving on. 0.25
        default may be too squick

        lab = code for the lab key to add/update to given finding
        new printers. Existing printers will be over written.
        """

        if lab not in self.printers['labs']:
            self.printers['labs'][lab] = {}

        self.printers['labs'][lab]["Download-Label-png"] = { "ip_address": "dl_png", "label_zpl_styles": ["tube_2inX1in"],"print_method": "generate png", "model" : "na", "serial" : "na", "arp_data":""}

        res = os.popen(str(files('zebra_day'))+f"/bin/scan_for_networed_zebra_printers_curl.sh {ip_stub} {scan_wait}")
        for i in res.readlines():
            ii = i.rstrip()
            sl = ii.split('|')
            if len(sl) > 1:
                zp = sl[0]
                ip = sl[1]
                model = sl[2]
                serial = sl[3]
                status = sl[4]
                arp_response = sl[5]

                if ip not in self.printers['labs'][lab]:
                    self.printers['labs'][lab][ip] = {"ip_address" : ip, "label_zpl_styles" : ["tube_2inX1in", "plate_1inX0.25in", "tube_2inX0.3in"], "print_method" : "unk", "model" : model, "serial" : serial, "arp_data": arp_response}  # The label formats set here are the installed defaults

        self.save_printer_json(self.printers_filename, relative=False)


    def save_printer_json(self, json_filename="/etc/printer_config.json", relative=True):
        """
        This saves the current self.printers to the json file the active
          printers.json loads from (assuming it is present, in which case
          a minimal json is created to get started with.
        """

        rec_date = str(datetime.datetime.now()).replace(' ','_')
        os.system(f"mkdir -p {str(files('zebra_day'))}/etc/old_printer_config/")
        bkup_pconfig_fn = f"{str(files('zebra_day'))}/etc/old_printer_config/{rec_date}_printer_config.json"
        if relative:
            json_filename = str(files('zebra_day')) + '/' + json_filename
        else:
            pass
            
        os.system(f"cp {self.printers_filename} {bkup_pconfig_fn}")

        with open(json_filename, 'w') as json_file:
            json.dump(self.printers, json_file, indent=4)
        self.load_printer_json(json_filename, relative=False)


    def load_printer_json(self, json_file=f"etc/printer_config.json", relative=True):
        """
        Loads printer json from a specified file, saves it to the active json.
        If specified file does not exist, it is created with the base
          printers json
        
        json_file = path to file
        """
        if relative:
            json_file = f"{str(files('zebra_day'))}/{json_file}"
        else:
            pass
            
        print(json_file,file=sys.stderr)

        if not os.path.exists(json_file):
            raise Exception(f"""The file specified does not exist. Consider specifying the default 'etc/printer_config.json , provided: {json_file}, which had {str(files('zebra_day'))} prefixed to it', for {json_file}""")
        fh = open(json_file)
        self.printers_filename = json_file
        self.printers = json.load(fh)
        # self.save_printer_json() <---  use the save_printer_json call after calling this. Else, recursion.
        

    def create_new_printers_json_with_single_test_printer(self, fn=None):
        """
        Create a new printers json with just the png printer defined
        """


        if fn in [None]:
            fn = str(files('zebra_day'))+"/etc/printer_config.json"
        
        if not hasattr(self, 'printers'):
            self.printers = {}
            self.printers_filename = fn

        jdat = None
        with open(f"{str(files('zebra_day'))}/etc/printer_config.template.json", 'r') as file:
            jdat = json.load(file)
            
        self.printers = jdat
        
        self.save_printer_json(fn, relative=False)


    def clear_printers_json(self, json_file="/etc/printer_config.json"):
        """
        Set printers json (in memory and on file) to the minimal json object
          def clear_printers_json(self, json_file="/etc/printer_config.json"):
        """

        json_file = str(files('zebra_day'))+'/'+json_file
        os.system(f"""echo '{{"labs" : {{}} }}' > {json_file}""")
        fh = open(json_file)
        self.printers_filename = json_file
        self.printers = json.load(fh)

        self.save_printer_json(json_file, relative=False)
        

    def replace_printer_json_from_template(self):
        """
        Copy the uneditable (with this package) template json
          which just defines a png printer to the active printers.json
        
        Seems not to be working ?
        """
        
        fn = f"{str(files('zebra_day'))}/etc/printer_config.json"
        os.system(f"cp {str(files('zebra_day'))}/etc/printer_config.template.json {fn}")
        fh = open(fn)
        self.printers_filename = fn
        self.printers = json.load(fh)

        self.save_printer_json(self.printers_filename, relative=False)



    def get_valid_label_styles_for_lab(self,lab=None):
        """
        The intention for this method was to confirm a template
          being requested for use in printing to some printer
          was 'allowed' by checking with that printers printer json
          for the array of valid templates.

        This was a huge PITA in testing, could be re-enabled at some point

        It is used once, but prints a warning only.
        """
        
        unique_labels = set()

        for printer in self.printers['labs'][lab]:
            for style in self.printers['labs'][lab][printer]['label_zpl_styles']:
                unique_labels.add(style)

        result = list(unique_labels)
        return result


    # Given these inputs, format them in to the specified zpl template and
    # prepare a string to send to a printer
    def formulate_zpl(self,uid_barcode=None, alt_a=None, alt_b=None, alt_c=None, alt_d=None, alt_e=None, alt_f=None, label_zpl_style=None):
        """
        Produce a ZPL string using the specified zpl template file, and
          formatting in the values, where appropriate.

        label_zpl_style = filename, minus the .zpl which keys to the .zpl file.
          (note, NOT the full file name. This shoudlbe changed
          to full file paths at some point)

        uid_barcode and alt_a -to- alt_f, are the allowed format keys in
          the zpl templates.  They may be used in any way. uid_barcode
          just differntiates one.
        """
        
        zpl_file = str(files('zebra_day'))+f"/etc/label_styles/{label_zpl_style}.zpl"
        if not os.path.exists(zpl_file):
            zpl_file = str(files('zebra_day'))+f"/etc/label_styles/tmps/{label_zpl_style}.zpl"
            if not os.path.exists(zpl_file):
                raise Exception(f"ZPL File : {zpl_file} does not exist in the TOPLEVEL or TMPS zebra_day/etc/label_styles dir.")

        with open(zpl_file, 'r') as file:
            content = file.read()
        zpl_string = content.format(uid_barcode=uid_barcode, alt_a=alt_a, alt_b=alt_b, alt_c=alt_c, alt_d=alt_d, alt_e=alt_e, alt_f=alt_f, label_zpl_style=label_zpl_style)

        return zpl_string


    
    def generate_label_png(self,zpl_string=None, png_fn=None, relative=False):
        """
         If not sending to a printer, produce the png of what would be printed
        """

        if relative in [True]:
            png_fn = str(files('zebra_day'))+'/'+png_fn
            
        if zpl_string in [None] or png_fn in [None]:
            raise Exception('ERROR: zpl_string and png_fn may not be None.')

        # Labelary API URL
        labelary_url = "http://api.labelary.com/v1/printers/8dpmm/labels/4x6/0/"
        # Create a POST request to the Labelary API
        response = requests.post(labelary_url, data=zpl_string)

        # Check if the request was successful
        if response.status_code == 200:
            # Save the image to a file
            with open(png_fn, "wb") as f:
                f.write(response.content)
                print(f"Image saved as {png_fn}",file=sys.stderr)
        else:
            print(f"Failed to convert ZPL to image. Status code: {response.status_code}",file=sys.stderr)

        return png_fn
                     

    def print_raw_zpl(self,zpl_content,printer_ip, port=9100):
        """
        For use when no use of the printer mapping config json is needed.  This assumes you know which IP is your desired printer. The spcified zpl_content will be sent to that IP+port.
        """
        send_zpl_code(zpl_content, printer_ip, printer_port=port)

        
        

    def print_zpl(self, lab=None, printer_name=None, uid_barcode='', alt_a='', alt_b='', alt_c='', alt_d='', alt_e='', alt_f='', label_zpl_style=None, client_ip='pkg', print_n=1, zpl_content=None):
        """
        The main print method. Accepts info to determine the desired
          printer IP and to request the desired ZPL string to be sent
          to the printer.

        lab = top level key in self.printers['labs']
        printer_name = key for printer info (ie: ip_address) needed
          to satisfy print requests.
        label_zpl_style = template code, see above for addl deets
        client_ip = optional, this is logged with print request info
        print_n = integer, > 0
        zpl_content = DO NOT USE -- hacky way to directly pass a zpl
          string to a printer. to do: write a cleaner
          string+ip method of printing.
        """

        if print_n < 1:
            raise Exception(f"\n\nprint_n < 1 , specified {print_n}")

        rec_date = str(datetime.datetime.now()).replace(' ','_')
        print_n = int(print_n)

        if printer_name in ['','None',None] and lab in [None,'','None']:
            raise Exception(f"lab and printer_name are both required to route a zebra print request, the following was what was received: lab:{lab} & printer_name:{printer_name}")
        
        if label_zpl_style in [None,'','None']:
            label_zpl_style = self.printers['labs'][lab][printer_name]['label_zpl_styles'][0]  # If a style is not specified, assume the first
        elif label_zpl_style not in self.printers['labs'][lab][printer_name]['label_zpl_styles']:
            print(f"\n\nWARNING:::\nZPL style: {label_zpl_style} is not valid for {lab} {printer_name} ... {self.printers['labs'][lab][printer_name]['label_zpl_styles']}",file=sys.stderr)

        printer_ip = self.printers['labs'][lab][printer_name]["ip_address"]

        zpl_string = ''
        if zpl_content in [None]:
            zpl_string = self.formulate_zpl(uid_barcode=uid_barcode, alt_a=alt_a, alt_b=alt_b, alt_c=alt_c, alt_d=alt_d, alt_e=alt_e, alt_f=alt_f, label_zpl_style=label_zpl_style)
        else:
            zpl_string = zpl_content
            
        os.system(f"echo '{lab}\t{printer_name}\t{uid_barcode}\t{label_zpl_style}\t{printer_ip}\t{print_n}\t{client_ip}\t{zpl_content}\n' >> {str(files('zebra_day'))}/logs/print_requests.log")

        ret_s = None
        if printer_ip in ['dl_png']:
            png_fn = str(files('zebra_day'))+f"/files/zpl_label_{label_zpl_style}_{rec_date}.png"
            ret_s = self.generate_label_png(zpl_string, png_fn, False)

        else:
            pn = 1
            while pn <= print_n:
                send_zpl_code(zpl_string, printer_ip)
                pn += 1

            ret_s = zpl_string

        return ret_s


def zday_start():
    """
    If zebra_day has been pip installed, running `zday_start` will
      start the zebra_day ui on 0.0.0.0:8118 . This offers a lot
      of the package utilities in a UI. Mostly intended for
      template design and testing, as well as printer fleet
      mainainance
    """

    import zebra_day.print_mgr as zdpm

    from zebra_day.bin import zserve
    os.system(f"python {str(files('zebra_day'))}/bin/zserve.py "+os.path.dirname(zdpm.__file__))


def main():
    """
    If zebra_day has been pip installed, running zday_quickstart
      will first attempt a zebra printer discovery scan of your network
      create a new printers json for what is found and start
      the zebra_day UI on 0.0.0.0:8118
    """

    import zebra_day.print_mgr as zdpm
    
    ipcmd = """(ip addr show | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1' || ifconfig | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1') 2>/dev/null"""

    ip = os.popen(ipcmd).readline().rstrip()
    ip_root = ".".join(ip.split('.')[:-1])

    print(f"\nIP detected: {ip} ... using IP root: {ip_root}\n\n ..... now scanning for zebra printers on this network (which may take a few minutes...)")
    os.system('sleep 2.2')

    zp = zdpm.zpl()
    zp.probe_zebra_printers_add_to_printers_json(ip_stub=ip_root)

    print(f"\nZebra Printer Scan Complete.  Results:" + str(zp.printers) + "\n\n")
    print(f'\nNow starting zebra_day web GUI\n\n\n\t\t\t**** THE ZDAY WEB GUI WILL BE ACCESSIBLE VIA THE URL: {ip}:8118 \n\n\n\tThe zday web server will continue running, and not return this shell to a command prompt until it is shut down\n\t.... you may shut down this web service by hitting ctrl+c.\n\n')
    os.system('sleep 1.3')

    os.system(f"python {str(files('zebra_day'))}/bin/zserve.py "+os.path.dirname(zdpm.__file__))

    print('\n\n\n ** EXITING ZDAY QUICKSTART **\n\n\t\tif the zday web gui did not run ( if you immediately got the command prompt back, it did not run ), check and see if there is a service already running at {ip}:8118 . Otherwise, check out the zday cherrypy STDOUT emitted just above what you are reading now.  Cut&Paste that into chatgpt and see if a solution is presented!')

    print('fin')


if __name__ == "__main__":
    """
    entry point for zday_quickstart.
    """

    main()


if __name__ == "__zday_start__":
    """
    entry point for zday_start
    """
    
    zday_start()
