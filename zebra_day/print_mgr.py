"""
  Primary zebra_day module. Primary functions: consistent and clear management
  of 1+ networked zebra printers, automated discovery of printers on a
  network. Clear formulation and delivery of ZPL strings to destination
  printers. Management of zpl template files, which may have format value
  components for inserting data on the fly. (elsewhere, a simple ui on
  top of this).

  This module is primarily focused on print request and package config mgmt.
  See 'cmd_mgr' for interacting with zebras printer config capabilities.
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from importlib.resources import files

from zebra_day.logging_config import get_logger
from zebra_day import paths as xdg

_log = get_logger(__name__)



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
            _log.info("ZPL code sent successfully to printer %s:%d", printer_ip, printer_port)
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
    
    def __init__(self, json_config: str | None = None):
        """
        Initialize the class.

        Args:
            json_config: Path to printer config JSON. If not specified,
                uses XDG config path or falls back to package path.
        """
        # Ensure label styles directories exist
        xdg.get_label_drafts_dir()  # Creates tmps/ too

        # Determine config file location (XDG first, then package fallback)
        xdg_config = xdg.get_printer_config_path()
        pkg_config = Path(str(files('zebra_day'))) / "etc" / "printer_config.json"

        if json_config:
            jcfg = Path(json_config) if not json_config.startswith('/') else Path(json_config)
        elif xdg_config.exists():
            jcfg = xdg_config
        elif pkg_config.exists():
            jcfg = pkg_config
        else:
            jcfg = xdg_config  # Will create new config here

        if jcfg.exists():
            self.load_printer_json(str(jcfg), relative=False)
        else:
            self.create_new_printers_json_with_single_test_printer(str(jcfg))


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

        self.printers['labs'][lab]["Download-Label-png"] = {
            "ip_address": "dl_png",
            "label_zpl_styles": ["tube_2inX1in"],
            "print_method": "generate png",
            "model": "na",
            "serial": "na",
            "arp_data": ""
        }

        # Run scanner script using subprocess instead of os.popen
        script_path = Path(str(files('zebra_day'))) / "bin" / "scan_for_networed_zebra_printers_curl.sh"
        result = subprocess.run(
            [str(script_path), ip_stub, scan_wait],
            capture_output=True,
            text=True,
            check=False
        )

        for line in result.stdout.splitlines():
            line = line.rstrip()
            sl = line.split('|')
            if len(sl) > 1:
                zp = sl[0]
                ip = sl[1]
                model = sl[2]
                serial = sl[3]
                status = sl[4]
                arp_response = sl[5]

                if ip not in self.printers['labs'][lab]:
                    # The label formats set here are the installed defaults
                    self.printers['labs'][lab][ip] = {
                        "ip_address": ip,
                        "label_zpl_styles": ["tube_2inX1in", "plate_1inX0.25in", "tube_2inX0.3in"],
                        "print_method": "unk",
                        "model": model,
                        "serial": serial,
                        "arp_data": arp_response
                    }

        self.save_printer_json(self.printers_filename, relative=False)


    def save_printer_json(self, json_filename: str = "/etc/printer_config.json", relative: bool = True) -> None:
        """
        Save the current self.printers to the specified JSON file.

        Creates a backup of the previous config in the backups directory.

        Args:
            json_filename: Path to save the config to
            relative: If True, path is relative to package directory
        """
        # Resolve the target path
        if relative:
            json_path = Path(str(files('zebra_day'))) / json_filename.lstrip('/')
        else:
            json_path = Path(json_filename)

        # Create backup if file exists
        if hasattr(self, 'printers_filename') and Path(self.printers_filename).exists():
            backup_dir = xdg.get_config_backups_dir()
            rec_date = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_path = backup_dir / f"{rec_date}_printer_config.json"
            try:
                shutil.copy2(self.printers_filename, backup_path)
                _log.debug("Backup created: %s", backup_path)
            except OSError as e:
                _log.warning("Failed to create backup: %s", e)

        # Save the config
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, 'w') as json_file:
            json.dump(self.printers, json_file, indent=4)

        self.load_printer_json(str(json_path), relative=False)


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
            
        _log.debug("Loading printer config from: %s", json_file)

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


    def clear_printers_json(self, json_file: str = "/etc/printer_config.json") -> None:
        """
        Reset printers JSON to empty minimal structure.

        Args:
            json_file: Path to the config file (relative to package)
        """
        json_path = Path(str(files('zebra_day'))) / json_file.lstrip('/')

        # Write empty config using pathlib
        empty_config = {"labs": {}}
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, 'w') as f:
            json.dump(empty_config, f, indent=4)

        self.printers_filename = str(json_path)
        self.printers = empty_config

        self.save_printer_json(str(json_path), relative=False)

    def replace_printer_json_from_template(self) -> None:
        """
        Replace the active printer config with the default template.

        Copies the template JSON to the active config location.
        """
        pkg_path = Path(str(files('zebra_day')))
        template_path = pkg_path / "etc" / "printer_config.template.json"
        target_path = pkg_path / "etc" / "printer_config.json"

        # Copy template to active config using shutil
        shutil.copy2(template_path, target_path)

        with open(target_path) as fh:
            self.printers = json.load(fh)
        self.printers_filename = str(target_path)

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


    
    def generate_label_png(self, zpl_string=None, png_fn=None, relative=False):
        """
        Generate a PNG image from ZPL string using local renderer.

        This uses a local ZPL renderer (Pillow + zint-bindings) instead of
        the external Labelary API, enabling offline operation and avoiding
        rate limits.

        Args:
            zpl_string: The ZPL code to render
            png_fn: Output filename for the PNG
            relative: If True, treat png_fn as relative to package directory

        Returns:
            Path to the generated PNG file
        """
        from zebra_day.zpl_renderer import render_zpl_to_png

        if relative:
            png_fn = str(files('zebra_day')) + '/' + png_fn

        if zpl_string is None or png_fn is None:
            raise ValueError('ERROR: zpl_string and png_fn may not be None.')

        try:
            result = render_zpl_to_png(zpl_string, png_fn)
            _log.info("Label image saved as %s", result)
            return result
        except Exception as e:
            _log.error("Failed to convert ZPL to image: %s", e)
            raise
                     

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
            _log.warning(
                "ZPL style '%s' is not valid for %s/%s. Valid styles: %s",
                label_zpl_style, lab, printer_name,
                self.printers['labs'][lab][printer_name]['label_zpl_styles']
            )

        printer_ip = self.printers['labs'][lab][printer_name]["ip_address"]

        zpl_string = ''
        if zpl_content in [None]:
            zpl_string = self.formulate_zpl(uid_barcode=uid_barcode, alt_a=alt_a, alt_b=alt_b, alt_c=alt_c, alt_d=alt_d, alt_e=alt_e, alt_f=alt_f, label_zpl_style=label_zpl_style)
        else:
            zpl_string = zpl_content

        # Log print request to file (using pathlib, not shell)
        log_file = xdg.get_logs_dir() / "print_requests.log"
        log_entry = f"{lab}\t{printer_name}\t{uid_barcode}\t{label_zpl_style}\t{printer_ip}\t{print_n}\t{client_ip}\t{zpl_content}\n"
        with open(log_file, 'a') as f:
            f.write(log_entry)

        ret_s = None
        if printer_ip in ['dl_png']:
            png_fn = str(xdg.get_generated_files_dir() / f"zpl_label_{label_zpl_style}_{rec_date}.png")
            ret_s = self.generate_label_png(zpl_string, png_fn, False)

        else:
            pn = 1
            while pn <= print_n:
                send_zpl_code(zpl_string, printer_ip)
                pn += 1

            ret_s = zpl_string

        return ret_s


def _get_local_ip() -> str:
    """Get the local IP address of this machine."""
    ipcmd = r"""(ip addr show | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1' || ifconfig | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1') 2>/dev/null"""
    result = subprocess.run(ipcmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip().split('\n')[0] if result.stdout.strip() else "127.0.0.1"


def _parse_auth_args() -> str:
    """Parse --auth CLI argument.

    Returns:
        Auth mode: "none" or "cognito"
    """
    import argparse

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--auth",
        type=str,
        choices=["none", "cognito"],
        default="none",
        help="Authentication mode: 'none' (public, default) or 'cognito' (AWS Cognito)",
    )
    args, _ = parser.parse_known_args()
    return args.auth


def zday_start() -> None:
    """
    Start the zebra_day web UI on 0.0.0.0:8118.

    .. deprecated::
        Use ``zday gui start`` instead. This command will be removed in v1.0.

    This offers package utilities in a UI, mostly intended for
    template design, testing, and printer fleet maintenance.

    Usage:
        zday_start                  # Start with no authentication
        zday_start --auth none      # Explicit no authentication
        zday_start --auth cognito   # Enable Cognito authentication
    """
    import warnings
    warnings.warn(
        "zday_start is deprecated. Use 'zday gui start' instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    _log.warning(
        "DEPRECATED: zday_start is deprecated. Use 'zday gui start' instead."
    )

    from zebra_day.web.app import run_server

    auth_mode = _parse_auth_args()
    _log.info("Starting zebra_day FastAPI server on 0.0.0.0:8118 (auth=%s)...", auth_mode)
    run_server(host="0.0.0.0", port=8118, reload=False, auth=auth_mode)


def main() -> None:
    """
    Quick start: scan for printers and start the web GUI.

    .. deprecated::
        Use ``zday bootstrap`` followed by ``zday gui start`` instead.
        This command will be removed in v1.0.

    If zebra_day has been pip installed, running zday_quickstart
    will first attempt a zebra printer discovery scan of your network,
    create a new printers JSON for what is found, and start
    the zebra_day UI on 0.0.0.0:8118.

    Usage:
        zday_quickstart                  # Start with no authentication
        zday_quickstart --auth none      # Explicit no authentication
        zday_quickstart --auth cognito   # Enable Cognito authentication
    """
    import warnings
    warnings.warn(
        "zday_quickstart is deprecated. Use 'zday bootstrap' then 'zday gui start' instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    _log.warning(
        "DEPRECATED: zday_quickstart is deprecated. Use 'zday bootstrap' then 'zday gui start' instead."
    )

    import zebra_day.print_mgr as zdpm
    from zebra_day.web.app import run_server

    auth_mode = _parse_auth_args()

    ip = _get_local_ip()
    ip_root = ".".join(ip.split('.')[:-1])

    _log.info("IP detected: %s ... using IP root: %s", ip, ip_root)
    _log.info("Scanning for zebra printers on this network (may take a few minutes)...")
    time.sleep(2.2)

    zp = zdpm.zpl()
    zp.probe_zebra_printers_add_to_printers_json(ip_stub=ip_root)

    _log.info("Zebra Printer Scan Complete. Results: %s", zp.printers)
    _log.info(
        "Starting zebra_day web GUI at %s:8118 (auth=%s). "
        "Press Ctrl+C to shut down.",
        ip,
        auth_mode,
    )
    time.sleep(1.3)

    run_server(host="0.0.0.0", port=8118, reload=False, auth=auth_mode)

    _log.info("EXITING ZDAY QUICKSTART")
    _log.info(
        "If the web GUI did not run, check if a service is already running at %s:8118",
        ip
    )


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
