"""
Tools to manage a zebra printer fleet and expose an API for routing print requests.
"""

import socket
import time

# Module-level cache for printer status: {ip: (status_dict, timestamp)}
_printer_status_cache: dict[str, tuple[dict, float]] = {}
CACHE_TTL = 60  # seconds


def clear_printer_cache(ip: str | None = None) -> None:
    """Clear cached printer status. If ip is None, clear all."""
    if ip is None:
        _printer_status_cache.clear()
    elif ip in _printer_status_cache:
        del _printer_status_cache[ip]


class ZebraPrinter:
    """Interface for querying and sending commands to a Zebra printer via TCP."""

    DEFAULT_TIMEOUT = 2.0

    def __init__(self, ip_address: str, port: int = 9100, buffer_size: int = 4096):
        self.ip_address = ip_address
        self.port = port
        self.buffer_size = buffer_size

    def send_command(self, command: str, timeout: float = DEFAULT_TIMEOUT) -> str | None:
        """Send a command and return the response. Returns None on error."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                s.connect((self.ip_address, self.port))
                s.sendall(command.encode())
                response = s.recv(self.buffer_size)
            return response.decode(errors="ignore")
        except (TimeoutError, ConnectionRefusedError, OSError):
            return None

    def get_configuration(self) -> str | None:
        """Retrieve printer configuration using ^HH command."""
        return self.send_command("^XA^HH^XZ", timeout=5.0)

    def set_configuration(self, config: str) -> str | None:
        """
        Set printer configuration.
        The `config` parameter should contain the necessary ZPL commands to adjust the configuration.
        After sending the configuration commands, the ^JUS command saves the configuration.
        """
        self.send_command(config)
        return self.send_command("^XA^JUS^XZ")

    # -------------------------------------------------------------------------
    # ZPL Host Query Methods
    # -------------------------------------------------------------------------

    def get_host_identification(self, timeout: float = DEFAULT_TIMEOUT) -> dict | None:
        """Query printer with ~HI command.

        Returns dict with: model, firmware, dpi, memory, options
        Returns None if printer unreachable or timeout.
        """
        response = self.send_command("~HI", timeout=timeout)
        if not response:
            return None

        # Response format: "ZD420-203dpi ZPL,V84.20.21Z,8,8192KB,..."
        # Strip any leading/trailing whitespace and STX/ETX chars
        response = response.strip().strip("\x02\x03")
        parts = [p.strip() for p in response.split(",")]
        if len(parts) >= 4:
            return {
                "model": parts[0],
                "firmware": parts[1],
                "dpi": parts[2],
                "memory": parts[3],
                "options": parts[4] if len(parts) > 4 else "",
            }
        return None

    def get_serial_number(self, timeout: float = DEFAULT_TIMEOUT) -> str | None:
        """Query printer serial number with ~HQSN command."""
        response = self.send_command("~HQSN", timeout=timeout)
        if not response:
            return None

        # Response format varies, often: "SERIAL NUMBER\r\nXXXXXXXX\r\n"
        response = response.strip().strip("\x02\x03")
        lines = [ln.strip() for ln in response.replace("\r", "\n").split("\n") if ln.strip()]
        for line in lines:
            # Skip header lines
            if "SERIAL" in line.upper():
                continue
            # Return first non-header line
            if line:
                return line
        return response if response else None

    def get_error_status(self, timeout: float = DEFAULT_TIMEOUT) -> dict | None:
        """Query error/warning status with ~HQES command.

        Returns dict with: errors (list), warnings (list), raw (str)
        """
        response = self.send_command("~HQES", timeout=timeout)
        if not response:
            return None

        response = response.strip().strip("\x02\x03")
        # Parse error flags (format varies by printer model)
        # Common format: "ERROR STATUS\r\nXXXX XXXX XXXX XXXX"
        # Each hex digit represents status flags
        errors: list[str] = []
        warnings: list[str] = []

        # Note: Full error flag parsing would require model-specific logic.
        # For now, we return the raw response for display purposes.

        lines = [ln.strip() for ln in response.replace("\r", "\n").split("\n") if ln.strip()]
        flag_line = ""
        for line in lines:
            if "ERROR" in line.upper() or "STATUS" in line.upper():
                continue
            flag_line = line
            break

        return {
            "errors": errors,
            "warnings": warnings,
            "raw": flag_line or response,
        }

    def get_odometer(self, timeout: float = DEFAULT_TIMEOUT) -> dict | None:
        """Query odometer with ~HQOD command.

        Returns dict with distance counters in inches/centimeters.
        """
        response = self.send_command("~HQOD", timeout=timeout)
        if not response:
            return None

        response = response.strip().strip("\x02\x03")
        # Response format: "ODOMETER\r\nLABEL: XXXXX\r\n..." or numeric values
        result = {
            "raw": response,
            "label_count": None,
            "total_inches": None,
        }

        lines = [ln.strip() for ln in response.replace("\r", "\n").split("\n") if ln.strip()]
        for line in lines:
            if "LABEL" in line.upper() and ":" in line:
                try:
                    val = line.split(":")[-1].strip().split()[0]
                    result["label_count"] = int(val.replace(",", ""))
                except (ValueError, IndexError):
                    pass
            elif "INCH" in line.upper() or "TOTAL" in line.upper():
                try:
                    # Extract numeric value
                    parts = line.split(":")
                    if len(parts) > 1:
                        val = parts[-1].strip().split()[0]
                        result["total_inches"] = int(val.replace(",", ""))
                except (ValueError, IndexError):
                    pass

        return result

    def get_host_status(self, timeout: float = DEFAULT_TIMEOUT) -> dict | None:
        """Query host status with ~HS command.

        Returns dict with status flags: paused, paper_out, ribbon_out, head_up, etc.
        """
        response = self.send_command("~HS", timeout=timeout)
        if not response:
            return None

        response = response.strip().strip("\x02\x03")
        # Response format (3 lines):
        # Line 1: aaaa,b,c,dddd,eee,f,g,h,iii,j,k,l
        # Line 2: mmm,n,o,p,q,r,s,t,uuuu,v
        # Line 3: www,x
        # See ZPL manual for full field definitions

        result = {
            "raw": response,
            "paused": False,
            "paper_out": False,
            "ribbon_out": False,
            "head_up": False,
            "buffer_full": False,
        }

        lines = [ln.strip() for ln in response.replace("\r", "\n").split("\n") if ln.strip()]
        if lines:
            # Parse first line
            parts = lines[0].split(",")
            if len(parts) >= 8:
                try:
                    result["paused"] = parts[1].strip() == "1"
                    result["paper_out"] = parts[5].strip() == "1"
                    result["head_up"] = parts[6].strip() == "1"
                    result["ribbon_out"] = parts[7].strip() == "1"
                except (ValueError, IndexError):
                    pass

        return result

    def get_full_status(self, timeout: float = DEFAULT_TIMEOUT) -> dict:
        """Query all status information and return a combined dict.

        This method queries all status commands and combines results.
        Use get_cached_status() for cached access.
        """
        status = {
            "ip": self.ip_address,
            "online": False,
            "host_id": None,
            "serial": None,
            "firmware": None,
            "model": None,
            "dpi": None,
            "error_status": None,
            "odometer": None,
            "host_status": None,
            "errors": [],
            "warnings": [],
            "paused": False,
            "paper_out": False,
            "ribbon_out": False,
            "head_up": False,
            "label_count": None,
            "timestamp": time.time(),
        }

        # Query host identification first (fastest way to check if online)
        host_id = self.get_host_identification(timeout=timeout)
        if host_id:
            status["online"] = True
            status["host_id"] = host_id
            status["model"] = host_id.get("model")
            status["firmware"] = host_id.get("firmware")
            status["dpi"] = host_id.get("dpi")

            # Query serial number
            serial = self.get_serial_number(timeout=timeout)
            if serial:
                status["serial"] = serial

            # Query error status
            error_status = self.get_error_status(timeout=timeout)
            if error_status:
                status["error_status"] = error_status
                status["errors"] = error_status.get("errors", [])
                status["warnings"] = error_status.get("warnings", [])

            # Query odometer
            odometer = self.get_odometer(timeout=timeout)
            if odometer:
                status["odometer"] = odometer
                status["label_count"] = odometer.get("label_count")

            # Query host status for operational flags
            host_status = self.get_host_status(timeout=timeout)
            if host_status:
                status["host_status"] = host_status
                status["paused"] = host_status.get("paused", False)
                status["paper_out"] = host_status.get("paper_out", False)
                status["ribbon_out"] = host_status.get("ribbon_out", False)
                status["head_up"] = host_status.get("head_up", False)

        return status


def get_cached_status(
    ip: str, timeout: float = ZebraPrinter.DEFAULT_TIMEOUT, force_refresh: bool = False
) -> dict:
    """Get printer status with caching.

    Args:
        ip: Printer IP address
        timeout: Query timeout in seconds
        force_refresh: If True, bypass cache and query fresh

    Returns:
        Status dict (see ZebraPrinter.get_full_status for fields)
    """
    now = time.time()

    # Check cache
    if not force_refresh and ip in _printer_status_cache:
        cached_data, cached_time = _printer_status_cache[ip]
        if now - cached_time < CACHE_TTL:
            return cached_data

    # Query printer
    printer = ZebraPrinter(ip)
    status = printer.get_full_status(timeout=timeout)

    # Cache result
    _printer_status_cache[ip] = (status, now)

    return status
