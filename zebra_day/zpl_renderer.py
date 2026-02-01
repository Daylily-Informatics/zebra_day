"""
Local ZPL-to-PNG renderer using Pillow and zint-bindings.

Replaces external Labelary API dependency with offline rendering.
Supports the ZPL commands used in zebra_day templates:
- ^XA/^XZ: Label start/end
- ^FO: Field origin (positioning)
- ^FD/^FS: Field data/separator
- ^A0N/^ADN: Font selection
- ^BY: Barcode field default
- ^B3N: Code 39 barcode
- ^BCN: Code 128 barcode
- ^BQN: QR code
- ^BXN: Data Matrix
"""
from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

try:
    import zint
    ZINT_AVAILABLE = True
except ImportError:
    ZINT_AVAILABLE = False

_log = logging.getLogger(__name__)

# Default label dimensions for 4x6 inch label at 8 dpmm (203 dpi)
DEFAULT_LABEL_WIDTH_DOTS = 812   # 4 inches * 203 dpi
DEFAULT_LABEL_HEIGHT_DOTS = 1218  # 6 inches * 203 dpi

# Barcode type mappings
BARCODE_TYPES = {
    'B3N': 'CODE39',   # Code 39
    'BCN': 'CODE128',  # Code 128
    'BQN': 'QRCODE',   # QR Code
    'BXN': 'DATAMATRIX',  # Data Matrix
}


@dataclass
class FontSpec:
    """Font specification from ZPL ^A command."""
    height: int = 30
    width: int = 20


@dataclass
class BarcodeSpec:
    """Barcode specification from ZPL ^BY command."""
    module_width: int = 2
    ratio: float = 3.0
    height: int = 10


@dataclass
class RenderState:
    """Current rendering state while parsing ZPL."""
    x: int = 0
    y: int = 0
    font: FontSpec = field(default_factory=FontSpec)
    barcode: BarcodeSpec = field(default_factory=BarcodeSpec)
    current_barcode_type: str | None = None
    barcode_height: int = 40


def _get_font(height: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Get a font at the specified height. Falls back to default if unavailable."""
    try:
        # Try common monospace fonts
        for font_name in ['DejaVuSansMono.ttf', 'Menlo.ttc', 'Courier New.ttf', 'monospace']:
            try:
                return ImageFont.truetype(font_name, height)
            except OSError:
                continue
        # Fallback to default
        return ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()


def _render_barcode(barcode_type: str, data: str, height: int = 40, module_width: int = 2) -> Image.Image | None:
    """Render a barcode using zint-bindings."""
    if not ZINT_AVAILABLE:
        _log.warning("zint-bindings not available, cannot render barcode")
        return None

    import tempfile
    import os

    try:
        symbol = zint.Symbol()

        # Map barcode type to zint symbology
        if barcode_type == 'CODE39':
            symbol.symbology = zint.Symbology.CODE39
        elif barcode_type == 'CODE128':
            symbol.symbology = zint.Symbology.CODE128
        elif barcode_type == 'QRCODE':
            symbol.symbology = zint.Symbology.QRCODE
        elif barcode_type == 'DATAMATRIX':
            symbol.symbology = zint.Symbology.DATAMATRIX
        else:
            _log.warning("Unknown barcode type: %s", barcode_type)
            return None

        symbol.height = height
        symbol.scale = max(1, module_width)
        symbol.show_text = False  # ZPL typically handles text separately

        # Create temp file for output
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            temp_path = f.name

        symbol.outfile = temp_path
        symbol.encode(data)
        symbol.print()  # Write to outfile

        # Load the image
        if os.path.exists(temp_path):
            img = Image.open(temp_path).convert('RGBA')
            os.unlink(temp_path)  # Clean up temp file
            return img
        return None
    except Exception as e:
        _log.warning("Failed to render barcode: %s", e)
        return None


def _parse_font_command(cmd: str) -> FontSpec:
    """Parse ^A0N or ^ADN font command."""
    # ^A0N,height,width or ^ADN,height,width
    parts = cmd.split(',')
    height = int(parts[1]) if len(parts) > 1 and parts[1].strip() else 30
    width = int(parts[2]) if len(parts) > 2 and parts[2].strip() else height // 2
    return FontSpec(height=height, width=width)


def _parse_barcode_default(cmd: str) -> BarcodeSpec:
    """Parse ^BY command for barcode defaults."""
    # ^BY[module_width],[ratio],[height]
    parts = cmd.split(',')
    module_width = int(parts[0]) if parts[0].strip() else 2
    ratio = float(parts[1]) if len(parts) > 1 and parts[1].strip() else 3.0
    height = int(parts[2]) if len(parts) > 2 and parts[2].strip() else 10
    return BarcodeSpec(module_width=module_width, ratio=ratio, height=height)


def _parse_position(cmd: str) -> tuple[int, int]:
    """Parse ^FO command for field origin."""
    # ^FOx,y
    parts = cmd.split(',')
    x = int(parts[0]) if parts[0].strip() else 0
    y = int(parts[1]) if len(parts) > 1 and parts[1].strip() else 0
    return x, y


def _parse_barcode_command(cmd: str) -> int:
    """Parse barcode command (^B3N, ^BCN, etc.) and return height."""
    # Format: ^B3N,orientation,height,... or ^BCN,orientation,height,...
    parts = cmd.split(',')
    # Height is usually the 3rd parameter (index 2) for most barcode commands
    if len(parts) > 2 and parts[2].strip():
        try:
            return int(parts[2])
        except ValueError:
            pass
    return 40  # Default height


def render_zpl_to_png(
    zpl_string: str,
    output_path: str | Path,
    width: int = DEFAULT_LABEL_WIDTH_DOTS,
    height: int = DEFAULT_LABEL_HEIGHT_DOTS,
) -> str:
    """
    Render ZPL string to PNG image.

    Args:
        zpl_string: ZPL format string to render
        output_path: Path to save the PNG file
        width: Label width in dots (default: 812 for 4" at 203 dpi)
        height: Label height in dots (default: 1218 for 6" at 203 dpi)

    Returns:
        Path to the saved PNG file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Create white background image
    img = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(img)

    state = RenderState()

    # Parse ZPL commands - split on ^ character
    commands = re.split(r'\^', zpl_string)

    pending_text: str | None = None

    for cmd in commands:
        cmd = cmd.strip()
        if not cmd:
            continue

        # Label start/end - ignore
        if cmd.startswith('XA') or cmd.startswith('XZ'):
            continue

        # Field origin - set position
        if cmd.startswith('FO'):
            state.x, state.y = _parse_position(cmd[2:])
            continue

        # Font commands
        if cmd.startswith('A0N') or cmd.startswith('ADN'):
            state.font = _parse_font_command(cmd)
            continue

        # Barcode default
        if cmd.startswith('BY'):
            state.barcode = _parse_barcode_default(cmd[2:])
            continue

        # Barcode type commands
        for bc_cmd, bc_type in BARCODE_TYPES.items():
            if cmd.startswith(bc_cmd):
                state.current_barcode_type = bc_type
                state.barcode_height = _parse_barcode_command(cmd)
                break
        else:
            # Not a barcode command, check for field data
            if cmd.startswith('FD'):
                # Extract data between FD and FS
                data = cmd[2:]
                if data.endswith('FS'):
                    data = data[:-2]

                # If there's a pending barcode type, render barcode
                if state.current_barcode_type:
                    bc_img = _render_barcode(
                        state.current_barcode_type,
                        data,
                        height=state.barcode_height,
                        module_width=state.barcode.module_width,
                    )
                    if bc_img:
                        img.paste(bc_img, (state.x, state.y), bc_img if bc_img.mode == 'RGBA' else None)
                    state.current_barcode_type = None
                else:
                    # Render text
                    font = _get_font(state.font.height)
                    draw.text((state.x, state.y), data, fill='black', font=font)
                continue

        # Field separator - just a marker, usually handled with FD
        if cmd.startswith('FS'):
            continue

    # Save the image
    img.save(str(output_path), 'PNG')
    _log.info("Label image saved as %s", output_path)

    return str(output_path)

