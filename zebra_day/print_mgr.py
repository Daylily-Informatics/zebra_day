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
import time
from importlib.resources import files
from pathlib import Path
from typing import Literal

import yaml

import zebra_day.cmd_mgr as zdcm
from zebra_day import paths as xdg
from zebra_day.logging_config import get_logger

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
        if return_code in [None]:
            _log.info("ZPL code sent successfully to printer %s:%d", printer_ip, printer_port)
        else:
            raise Exception(
                f"\n\nPrint request to {printer_ip}:{printer_port} did not return None, but instead: {return_code} ... zpl: {zpl_code}\n"
            )

    except ConnectionError as e:
        raise Exception(
            f"Error connecting to the printer: {printer_ip} on port {printer_port} \n\n\t" + str(e)
        ) from e

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

    def __init__(self, config_path: str | None = None):
        """
        Initialize the class.

        Args:
            config_path: Path to printer config file (YAML or JSON). If not specified,
                uses XDG config path with YAML preference and JSON fallback.
        """
        # Ensure label styles directories exist
        xdg.get_label_drafts_dir()  # Creates tmps/ too

        # Config file search order:
        # 1. Explicit path provided
        # 2. XDG YAML config
        # 3. XDG legacy JSON config (auto-migrates to YAML)
        # 4. Package template (copies to XDG YAML)
        yaml_config = xdg.get_config_file_path()
        json_config = xdg.get_legacy_json_config_path()
        pkg_template = Path(str(files("zebra_day"))) / "etc" / "zebra-day-config-template.yaml"

        if config_path:
            cfg_path = Path(config_path)
            if cfg_path.exists():
                self._load_config_file(cfg_path)
            else:
                self._create_config_from_template(cfg_path)
        elif yaml_config.exists():
            self._load_config_file(yaml_config)
        elif json_config.exists():
            # Migrate JSON to YAML
            self._migrate_json_to_yaml(json_config, yaml_config)
        elif pkg_template.exists():
            # Create config from template
            self._create_config_from_template(yaml_config)
        else:
            # Fallback: create minimal config
            self._create_minimal_config(yaml_config)

    def _load_config_file(self, config_path: Path) -> None:
        """Load configuration from a YAML or JSON file.

        Args:
            config_path: Path to the config file
        """
        _log.debug("Loading config from: %s", config_path)
        self.printers_filename = str(config_path)

        with open(config_path) as f:
            content = f.read()

        # Detect format and parse
        if config_path.suffix in (".yaml", ".yml"):
            self.printers = yaml.safe_load(content) or {}
        else:
            self.printers = json.loads(content)

        # Ensure schema version exists
        if "schema_version" not in self.printers:
            self.printers["schema_version"] = "2.0.0"
        if "labs" not in self.printers:
            self.printers["labs"] = {}

    def _migrate_json_to_yaml(self, json_path: Path, yaml_path: Path) -> None:
        """Migrate a JSON config file to YAML format.

        The JSON file is preserved as a backup.

        Args:
            json_path: Path to the existing JSON config
            yaml_path: Path where the YAML config will be created
        """
        _log.info("Migrating config from JSON to YAML: %s -> %s", json_path, yaml_path)

        # Load JSON config
        with open(json_path) as f:
            config = json.load(f)

        # Save as YAML
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        with open(yaml_path, "w") as f:
            f.write("# zebra_day Configuration File\n")
            f.write("# Migrated from JSON format\n\n")
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        # Backup the JSON file
        backup_dir = xdg.get_config_backups_dir()
        backup_name = f"{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_migrated_from.json"
        shutil.copy2(json_path, backup_dir / backup_name)
        _log.info("JSON backup saved to: %s", backup_dir / backup_name)

        # Load the new YAML config
        self._load_config_file(yaml_path)

    def _create_config_from_template(self, target_path: Path) -> None:
        """Create a new config file from the template.

        Args:
            target_path: Path where the config will be created
        """
        template_path = Path(str(files("zebra_day"))) / "etc" / "zebra-day-config-template.yaml"
        _log.info("Creating config from template: %s", target_path)

        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template_path, target_path)

        self._load_config_file(target_path)

    def _create_minimal_config(self, target_path: Path) -> None:
        """Create a minimal empty config file.

        Args:
            target_path: Path where the config will be created
        """
        _log.info("Creating minimal config: %s", target_path)

        minimal_config = {
            "schema_version": "2.0.0",
            "labs": {"default": {"lab_name": "Default", "available_locations": [], "printers": {}}},
        }

        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w") as f:
            f.write("# zebra_day Configuration File\n\n")
            yaml.dump(minimal_config, f, default_flow_style=False, sort_keys=False)

        self._load_config_file(target_path)

    def save_printer_config(self, config_path: str | None = None) -> None:
        """Save the current printer configuration to YAML file.

        Creates a backup of the previous config in the backups directory.

        Args:
            config_path: Optional path to save to. If not specified, uses current config path.
        """
        if config_path:
            target_path = Path(config_path)
        elif hasattr(self, "printers_filename"):
            target_path = Path(self.printers_filename)
        else:
            target_path = xdg.get_config_file_path()

        # Ensure target is YAML
        if target_path.suffix not in (".yaml", ".yml"):
            target_path = target_path.with_suffix(".yaml")

        # Create backup if file exists
        if target_path.exists():
            backup_dir = xdg.get_config_backups_dir()
            rec_date = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_path = backup_dir / f"{rec_date}_config_backup.yaml"
            try:
                shutil.copy2(target_path, backup_path)
                _log.debug("Backup created: %s", backup_path)
            except OSError as e:
                _log.warning("Failed to create backup: %s", e)

        # Save config as YAML
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w") as f:
            f.write("# zebra_day Configuration File\n\n")
            yaml.dump(self.printers, f, default_flow_style=False, sort_keys=False)

        self.printers_filename = str(target_path)
        _log.debug("Config saved to: %s", target_path)

    def probe_zebra_printers_add_to_printers_json(
        self, ip_stub="192.168.1", scan_wait="0.25", lab="default", relative=False
    ):
        """
        Scan the network for zebra printers.

        NOTE! this should work with no dependencies on a MAC
        UBUNTU requires system wide net-tools (for arp)
        Others... well, this may not work

        ---
        Requires:
          curl is pretty standard, arp seems less so
          arp
        ---

        ip_stub = all 255 possibilities will be probed beneath this stub provided
        scan_wait = seconds to re-try probing until moving on. 0.25 default may be too quick
        lab = code for the lab key to add/update to given finding new printers
        """
        # Ensure schema version is set
        if "schema_version" not in self.printers:
            self.printers["schema_version"] = "2.0.0"

        # Initialize lab with v2 structure if not exists
        if lab not in self.printers["labs"]:
            self.printers["labs"][lab] = {
                "lab_name": lab.replace("-", " ").title(),
                "available_locations": [],
                "printers": {},
            }

        # Ensure lab has printers sub-object (migration from v1)
        if "printers" not in self.printers["labs"][lab]:
            self.printers["labs"][lab]["printers"] = {}
            self.printers["labs"][lab].setdefault("lab_name", lab.replace("-", " ").title())
            self.printers["labs"][lab].setdefault("available_locations", [])

        # Scan network for Zebra printers using pure Python
        wait_time = float(scan_wait) if scan_wait else 0.25

        for i in range(1, 255):
            ip = f"{ip_stub}.{i}"
            try:
                # Try to connect to ZPL port (9100)
                import socket

                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(wait_time)
                result = sock.connect_ex((ip, 9100))
                sock.close()

                if result == 0:
                    # Port is open, try to get printer info
                    model = "Unknown"
                    serial = "Unknown"

                    try:
                        # Query printer for model and serial
                        printer = zdcm.ZebraPrinter(ip)
                        config = printer.get_configuration()

                        # Parse model from config
                        if "MODEL" in config:
                            for line in config.split("\n"):
                                if "MODEL" in line.upper():
                                    parts = line.split(":")
                                    if len(parts) > 1:
                                        model = parts[1].strip()
                                        break

                        # Parse serial from config
                        if "SERIAL" in config.upper():
                            for line in config.split("\n"):
                                if "SERIAL" in line.upper():
                                    parts = line.split(":")
                                    if len(parts) > 1:
                                        serial = parts[1].strip()
                                        break
                    except Exception:
                        pass  # Use defaults if we can't query printer

                    if ip not in self.printers["labs"][lab]["printers"]:
                        # The label formats set here are the installed defaults
                        self.printers["labs"][lab]["printers"][ip] = {
                            "ip_address": ip,
                            "printer_name": None,  # User can set friendly name later
                            "lab_location": None,  # User can set location later
                            "manufacturer": "zebra",
                            "model": model,
                            "serial": serial,
                            "label_zpl_styles": [
                                "tube_2inX1in",
                                "plate_1inX0.25in",
                                "tube_2inX0.3in",
                            ],
                            "default_label_style": "tube_2inX1in",  # Default to first style
                            "print_method": "socket",
                            "arp_data": "",
                            "notes": "",
                        }
            except Exception:
                pass  # Skip unreachable IPs

        self.save_printer_config()

    def save_printer_json(
        self, json_filename: str = "/etc/printer_config.json", relative: bool = True
    ) -> None:
        """Save the current config.

        .. deprecated:: 2.2.0
            Use :meth:`save_printer_config` instead.
        """
        # Redirect to YAML save
        self.save_printer_config()

    def load_printer_json(
        self, json_file: str = "etc/printer_config.json", relative: bool = True
    ) -> None:
        """Load a config file (JSON or YAML).

        .. deprecated:: 2.2.0
            Use :meth:`_load_config_file` instead.

        Args:
            json_file: Path to config file
            relative: If True, path is relative to package directory
        """
        if relative:
            config_path = Path(str(files("zebra_day"))) / json_file
        else:
            config_path = Path(json_file)

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        self._load_config_file(config_path)

    def create_new_printers_json_with_single_test_printer(self, fn: str | None = None) -> None:
        """Create a new config from the template.

        .. deprecated:: 2.2.0
            Use :meth:`_create_config_from_template` instead.
        """
        if fn is None:
            target_path = xdg.get_config_file_path()
        else:
            target_path = Path(fn)

        self._create_config_from_template(target_path)

    def clear_printers_json(self, config_file: str | None = None) -> None:
        """Reset config to empty minimal v2.0.0 structure.

        Args:
            config_file: Path to the config file (ignored, uses XDG path)
        """
        target_path = xdg.get_config_file_path()

        # Write empty config with v2 schema
        empty_config = {"schema_version": "2.0.0", "labs": {}}
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w") as f:
            f.write("# zebra_day Configuration File\n\n")
            yaml.dump(empty_config, f, default_flow_style=False, sort_keys=False)

        self.printers_filename = str(target_path)
        self.printers = empty_config

    def replace_printer_json_from_template(self) -> None:
        """Replace the active printer config with the default template."""
        target_path = xdg.get_config_file_path()
        self._create_config_from_template(target_path)

    def get_valid_label_styles_for_lab(self, lab=None):
        """
        Get all unique label styles available for printers in a lab.

        The intention for this method was to confirm a template
        being requested for use in printing to some printer
        was 'allowed' by checking with that printers printer json
        for the array of valid templates.

        This was a huge PITA in testing, could be re-enabled at some point.
        It is used once, but prints a warning only.
        """
        unique_labels = set()

        # Access printers via nested 'printers' key (v2 schema)
        lab_printers = self.printers["labs"][lab].get("printers", {})
        for _printer_id, printer_data in lab_printers.items():
            for style in printer_data.get("label_zpl_styles", []):
                unique_labels.add(style)

        result = list(unique_labels)
        return result

    # Given these inputs, format them in to the specified zpl template and
    # prepare a string to send to a printer
    def formulate_zpl(
        self,
        uid_barcode=None,
        alt_a=None,
        alt_b=None,
        alt_c=None,
        alt_d=None,
        alt_e=None,
        alt_f=None,
        label_zpl_style=None,
    ):
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

        zpl_file = str(files("zebra_day")) + f"/etc/label_styles/{label_zpl_style}.zpl"
        if not os.path.exists(zpl_file):
            zpl_file = str(files("zebra_day")) + f"/etc/label_styles/tmps/{label_zpl_style}.zpl"
            if not os.path.exists(zpl_file):
                raise Exception(
                    f"ZPL File : {zpl_file} does not exist in the TOPLEVEL or TMPS zebra_day/etc/label_styles dir."
                )

        with open(zpl_file) as file:
            content = file.read()
        zpl_string = content.format(
            uid_barcode=uid_barcode,
            alt_a=alt_a,
            alt_b=alt_b,
            alt_c=alt_c,
            alt_d=alt_d,
            alt_e=alt_e,
            alt_f=alt_f,
            label_zpl_style=label_zpl_style,
        )

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
            png_fn = str(files("zebra_day")) + "/" + png_fn

        if zpl_string is None or png_fn is None:
            raise ValueError("ERROR: zpl_string and png_fn may not be None.")

        try:
            result = render_zpl_to_png(zpl_string, png_fn)
            _log.info("Label image saved as %s", result)
            return result
        except Exception as e:
            _log.error("Failed to convert ZPL to image: %s", e)
            raise

    def print_raw_zpl(self, zpl_content, printer_ip, port=9100):
        """
        For use when no use of the printer mapping config json is needed.  This assumes you know which IP is your desired printer. The spcified zpl_content will be sent to that IP+port.
        """
        send_zpl_code(zpl_content, printer_ip, printer_port=port)

    def print_zpl(
        self,
        lab=None,
        printer_name=None,
        uid_barcode="",
        alt_a="",
        alt_b="",
        alt_c="",
        alt_d="",
        alt_e="",
        alt_f="",
        label_zpl_style=None,
        client_ip="pkg",
        print_n=1,
        zpl_content=None,
    ):
        """
        The main print method. Accepts info to determine the desired
        printer IP and to request the desired ZPL string to be sent
        to the printer.

        Args:
            lab: top level key in self.printers['labs']
            printer_name: key for printer info (ie: ip_address) needed
                to satisfy print requests.
            label_zpl_style: template code, see above for addl deets
            client_ip: optional, this is logged with print request info
            print_n: integer, > 0
            zpl_content: DO NOT USE -- hacky way to directly pass a zpl
                string to a printer. to do: write a cleaner
                string+ip method of printing.
        """
        if print_n < 1:
            raise Exception(f"\n\nprint_n < 1 , specified {print_n}")

        print_n = int(print_n)

        if printer_name in ["", "None", None] and lab in [None, "", "None"]:
            raise Exception(
                f"lab and printer_name are both required to route a zebra print request, the following was what was received: lab:{lab} & printer_name:{printer_name}"
            )

        # Access printer via nested 'printers' key (v2 schema)
        printer_data = self.printers["labs"][lab]["printers"][printer_name]

        if label_zpl_style in [None, "", "None"]:
            # Use default_label_style if set, otherwise fall back to first in list
            label_zpl_style = (
                printer_data.get("default_label_style") or printer_data["label_zpl_styles"][0]
            )
        elif label_zpl_style not in printer_data["label_zpl_styles"]:
            _log.warning(
                "ZPL style '%s' is not valid for %s/%s. Valid styles: %s",
                label_zpl_style,
                lab,
                printer_name,
                printer_data["label_zpl_styles"],
            )

        printer_ip = printer_data["ip_address"]

        zpl_string = ""
        if zpl_content in [None]:
            zpl_string = self.formulate_zpl(
                uid_barcode=uid_barcode,
                alt_a=alt_a,
                alt_b=alt_b,
                alt_c=alt_c,
                alt_d=alt_d,
                alt_e=alt_e,
                alt_f=alt_f,
                label_zpl_style=label_zpl_style,
            )
        else:
            zpl_string = zpl_content

        # Log print request to file (using pathlib, not shell)
        log_file = xdg.get_logs_dir() / "print_requests.log"
        log_entry = f"{lab}\t{printer_name}\t{uid_barcode}\t{label_zpl_style}\t{printer_ip}\t{print_n}\t{client_ip}\t{zpl_content}\n"
        with open(log_file, "a") as f:
            f.write(log_entry)

        # Send to printer
        for _ in range(print_n):
            send_zpl_code(zpl_string, printer_ip)

        return zpl_string


def _get_local_ip() -> str:
    """Get the local IP address of this machine."""
    ipcmd = r"""(ip addr show | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1' || ifconfig | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1') 2>/dev/null"""
    result = subprocess.run(ipcmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip().split("\n")[0] if result.stdout.strip() else "127.0.0.1"


def _parse_auth_args() -> Literal["none", "cognito"]:
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
    auth_mode: Literal["none", "cognito"] = args.auth
    return auth_mode


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
    _log.warning("DEPRECATED: zday_start is deprecated. Use 'zday gui start' instead.")

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
    ip_root = ".".join(ip.split(".")[:-1])

    _log.info("IP detected: %s ... using IP root: %s", ip, ip_root)
    _log.info("Scanning for zebra printers on this network (may take a few minutes)...")
    time.sleep(2.2)

    zp = zdpm.zpl()
    zp.probe_zebra_printers_add_to_printers_json(ip_stub=ip_root)

    _log.info("Zebra Printer Scan Complete. Results: %s", zp.printers)
    _log.info(
        "Starting zebra_day web GUI at %s:8118 (auth=%s). Press Ctrl+C to shut down.",
        ip,
        auth_mode,
    )
    time.sleep(1.3)

    run_server(host="0.0.0.0", port=8118, reload=False, auth=auth_mode)

    _log.info("EXITING ZDAY QUICKSTART")
    _log.info("If the web GUI did not run, check if a service is already running at %s:8118", ip)


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
