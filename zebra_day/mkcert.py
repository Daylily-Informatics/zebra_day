"""
mkcert integration for zebra_day HTTPS certificate management.

This module provides utilities to:
- Check if mkcert is installed
- Check if the local CA is installed
- Generate locally-trusted certificates for the zebra_day server
"""

import logging
import platform
import shutil
import subprocess
from pathlib import Path

from zebra_day import paths as xdg

_log = logging.getLogger(__name__)

# Default certificate locations
CERT_DIR = xdg.get_config_dir() / "certs"
CERT_FILE = CERT_DIR / "server.crt"
KEY_FILE = CERT_DIR / "server.key"

# Hostnames to include in the certificate
DEFAULT_HOSTNAMES = ["localhost", "127.0.0.1", "::1"]


def get_platform_install_command() -> str:
    """Get the platform-specific mkcert installation command.

    Returns:
        Installation command string for the current platform.
    """
    system = platform.system()
    if system == "Darwin":
        return "brew install mkcert"
    elif system == "Linux":
        # Try to detect the distribution
        try:
            with open("/etc/os-release") as f:
                os_release = f.read().lower()
                if "ubuntu" in os_release or "debian" in os_release:
                    return "sudo apt install mkcert"
                elif "fedora" in os_release or "rhel" in os_release or "centos" in os_release:
                    return "sudo dnf install mkcert"
                elif "arch" in os_release:
                    return "sudo pacman -S mkcert"
        except FileNotFoundError:
            pass
        return "sudo apt install mkcert  # or use your distribution's package manager"
    elif system == "Windows":
        return "choco install mkcert  # or scoop install mkcert"
    else:
        return "See https://github.com/FiloSottile/mkcert#installation"


def is_mkcert_installed() -> bool:
    """Check if mkcert is available in PATH."""
    return shutil.which("mkcert") is not None


def is_ca_installed() -> bool:
    """Check if the mkcert local CA is installed.

    Returns True if mkcert reports the CA is installed, False otherwise.
    """
    if not is_mkcert_installed():
        return False

    try:
        result = subprocess.run(
            ["mkcert", "-CAROOT"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            ca_root = Path(result.stdout.strip())
            # Check if the CA files exist
            return (ca_root / "rootCA.pem").exists()
    except (subprocess.TimeoutExpired, OSError) as e:
        _log.debug("Error checking CA status: %s", e)

    return False


def install_ca() -> bool:
    """Install the mkcert local CA (requires user interaction for password).

    Returns True if successful, False otherwise.
    """
    if not is_mkcert_installed():
        _log.error("mkcert is not installed")
        return False

    try:
        result = subprocess.run(
            ["mkcert", "-install"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            _log.info("mkcert CA installed successfully")
            return True
        else:
            _log.error("Failed to install CA: %s", result.stderr)
            return False
    except subprocess.TimeoutExpired:
        _log.error("CA installation timed out")
        return False
    except OSError as e:
        _log.error("Error installing CA: %s", e)
        return False


def certificates_exist() -> bool:
    """Check if certificates already exist."""
    return CERT_FILE.exists() and KEY_FILE.exists()


def generate_certificates(
    hostnames: list[str] | None = None,
    cert_file: Path | None = None,
    key_file: Path | None = None,
    force: bool = False,
) -> bool:
    """Generate locally-trusted certificates using mkcert.

    Args:
        hostnames: List of hostnames/IPs to include. Defaults to localhost, 127.0.0.1, ::1
        cert_file: Path for certificate file. Defaults to ~/.config/zebra_day/certs/server.crt
        key_file: Path for private key file. Defaults to ~/.config/zebra_day/certs/server.key
        force: If True, regenerate even if certificates exist

    Returns:
        True if certificates were generated successfully, False otherwise.
    """
    if not is_mkcert_installed():
        _log.error(
            "mkcert is not installed. Install with: brew install mkcert (macOS) or apt install mkcert (Ubuntu)"
        )
        return False

    cert_path = cert_file or CERT_FILE
    key_path = key_file or KEY_FILE
    hosts = hostnames or DEFAULT_HOSTNAMES

    # Check if certificates already exist
    if not force and cert_path.exists() and key_path.exists():
        _log.info("Certificates already exist at %s", cert_path)
        return True

    # Ensure directory exists
    cert_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        cmd = [
            "mkcert",
            "-cert-file",
            str(cert_path),
            "-key-file",
            str(key_path),
            *hosts,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            _log.info("Certificates generated: %s", cert_path)
            return True
        else:
            _log.error("Failed to generate certificates: %s", result.stderr)
            return False
    except subprocess.TimeoutExpired:
        _log.error("Certificate generation timed out")
        return False
    except OSError as e:
        _log.error("Error generating certificates: %s", e)
        return False


def get_cert_paths() -> tuple[Path | None, Path | None]:
    """Get certificate paths if they exist."""
    if certificates_exist():
        return CERT_FILE, KEY_FILE
    return None, None


def try_auto_generate_certificates() -> tuple[bool, str, Path | None, Path | None]:
    """Attempt to automatically generate certificates with mkcert.

    This function checks if mkcert is installed and the CA is set up,
    then attempts to generate certificates automatically.

    Returns:
        Tuple of (success, message, cert_path, key_path) where:
        - success: True if certificates were generated or already exist
        - message: Human-readable status/error message
        - cert_path: Path to certificate file if successful, None otherwise
        - key_path: Path to key file if successful, None otherwise
    """
    # Check if certificates already exist
    if certificates_exist():
        _log.info("Certificates already exist at %s", CERT_FILE)
        return True, "Certificates already exist", CERT_FILE, KEY_FILE

    # Check if mkcert is installed
    if not is_mkcert_installed():
        install_cmd = get_platform_install_command()
        msg = (
            f"mkcert is not installed. Install it with:\n"
            f"  {install_cmd}\n"
            f"Then run: mkcert -install"
        )
        _log.warning("mkcert not installed - cannot auto-generate certificates")
        return False, msg, None, None

    # Check if CA is installed
    if not is_ca_installed():
        msg = (
            "mkcert is installed but the local CA is not set up.\n"
            "Run this command (requires password):\n"
            "  mkcert -install"
        )
        _log.warning("mkcert CA not installed - cannot auto-generate certificates")
        return False, msg, None, None

    # Try to generate certificates
    _log.info("Attempting to auto-generate certificates with mkcert...")
    success = generate_certificates()

    if success:
        msg = f"Successfully generated certificates at {CERT_FILE}"
        _log.info(msg)
        return True, msg, CERT_FILE, KEY_FILE
    else:
        msg = (
            "Failed to generate certificates automatically.\n"
            "Try manually with:\n"
            f"  mkdir -p {CERT_DIR}\n"
            f"  mkcert -cert-file {CERT_FILE} -key-file {KEY_FILE} localhost 127.0.0.1 ::1"
        )
        _log.error("Certificate generation failed")
        return False, msg, None, None
