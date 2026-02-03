"""
Versioned JSON API router for zebra_day.

Provides programmatic access to printer management and label printing.
All endpoints return JSON and are prefixed with /api/v1/.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from zebra_day import paths as xdg

router = APIRouter()


# ----- Request/Response Models -----


class PrintRequest(BaseModel):
    """Request model for printing a label."""

    lab: str = Field(..., description="Lab identifier")
    printer: str = Field(..., description="Printer name")
    label_zpl_style: str | None = Field(None, description="ZPL template name")
    uid_barcode: str = Field("", description="UID for barcode")
    alt_a: str = Field("", description="Alternative field A")
    alt_b: str = Field("", description="Alternative field B")
    alt_c: str = Field("", description="Alternative field C")
    alt_d: str = Field("", description="Alternative field D")
    alt_e: str = Field("", description="Alternative field E")
    alt_f: str = Field("", description="Alternative field F")
    copies: int = Field(1, ge=1, le=100, description="Number of copies")


class PrintResponse(BaseModel):
    """Response model for print request."""

    success: bool
    message: str
    png_url: str | None = None


class PrinterInfo(BaseModel):
    """Printer information model (v2.0.0 schema)."""

    id: str = Field(..., description="Printer identifier/key in JSON")
    ip_address: str
    printer_name: str | None = Field(None, description="User-friendly display name")
    lab_location: str | None = Field(None, description="Location within the lab")
    manufacturer: str = Field("zebra", description="Printer manufacturer")
    model: str
    serial: str
    label_zpl_styles: list[str]
    default_label_style: str | None = Field(
        None, description="Default label style to use when none specified"
    )
    print_method: str
    notes: str | None = Field("", description="Optional notes")


class LabInfo(BaseModel):
    """Lab information model (v2.0.0 schema)."""

    id: str = Field(..., description="Lab identifier/key in JSON")
    lab_name: str = Field(..., description="Human-readable lab name")
    available_locations: list[str] = Field(
        default_factory=list, description="Valid location options for printers"
    )
    printers: list[PrinterInfo]


class LabPrinters(BaseModel):
    """Lab and its printers (deprecated, use LabInfo)."""

    lab: str
    printers: list[PrinterInfo]


class RenderRequest(BaseModel):
    """Request model for rendering ZPL to PNG."""

    template: str | None = Field(None, description="ZPL template name (e.g., 'tube_2inX1in')")
    zpl_content: str | None = Field(
        None, description="Raw ZPL content (takes precedence over template)"
    )
    uid_barcode: str = Field("", description="UID for barcode")
    alt_a: str = Field("", description="Alternative field A")
    alt_b: str = Field("", description="Alternative field B")
    alt_c: str = Field("", description="Alternative field C")
    alt_d: str = Field("", description="Alternative field D")
    alt_e: str = Field("", description="Alternative field E")
    alt_f: str = Field("", description="Alternative field F")


class RenderResponse(BaseModel):
    """Response model for render request (when not returning PNG directly)."""

    success: bool
    message: str
    png_url: str = Field(..., description="URL to download the generated PNG")


# ----- Endpoints -----


@router.get("/labs", response_model=list[str])
async def list_labs(request: Request) -> list[str]:
    """List all available labs."""
    zp = request.app.state.zp
    return list(zp.printers.get("labs", {}).keys())


@router.get("/labs/{lab}", response_model=LabInfo)
async def get_lab(request: Request, lab: str) -> LabInfo:
    """Get lab details including available locations and printers."""
    zp = request.app.state.zp
    labs = zp.printers.get("labs", {})

    if lab not in labs:
        raise HTTPException(status_code=404, detail=f"Lab '{lab}' not found")

    lab_data = labs[lab]
    lab_printers = lab_data.get("printers", {})

    printers = []
    for printer_id, info in lab_printers.items():
        printers.append(
            PrinterInfo(
                id=printer_id,
                ip_address=info.get("ip_address", ""),
                printer_name=info.get("printer_name"),
                lab_location=info.get("lab_location"),
                manufacturer=info.get("manufacturer", "zebra"),
                model=info.get("model", ""),
                serial=info.get("serial", ""),
                label_zpl_styles=info.get("label_zpl_styles", []),
                default_label_style=info.get("default_label_style"),
                print_method=info.get("print_method", ""),
                notes=info.get("notes", ""),
            )
        )

    return LabInfo(
        id=lab,
        lab_name=lab_data.get("lab_name", lab),
        available_locations=lab_data.get("available_locations", []),
        printers=printers,
    )


@router.get("/labs/{lab}/printers", response_model=list[PrinterInfo])
async def list_printers(request: Request, lab: str) -> list[PrinterInfo]:
    """List all printers in a lab."""
    zp = request.app.state.zp
    labs = zp.printers.get("labs", {})

    if lab not in labs:
        raise HTTPException(status_code=404, detail=f"Lab '{lab}' not found")

    # Access printers via nested 'printers' key (v2 schema)
    lab_printers = labs[lab].get("printers", {})

    printers = []
    for printer_id, info in lab_printers.items():
        printers.append(
            PrinterInfo(
                id=printer_id,
                ip_address=info.get("ip_address", ""),
                printer_name=info.get("printer_name"),
                lab_location=info.get("lab_location"),
                manufacturer=info.get("manufacturer", "zebra"),
                model=info.get("model", ""),
                serial=info.get("serial", ""),
                label_zpl_styles=info.get("label_zpl_styles", []),
                default_label_style=info.get("default_label_style"),
                print_method=info.get("print_method", ""),
                notes=info.get("notes", ""),
            )
        )
    return printers


@router.get("/templates", response_model=list[str])
async def list_templates(request: Request) -> list[str]:
    """List all available ZPL templates."""

    pkg_path = request.app.state.pkg_path
    styles_dir = pkg_path / "etc" / "label_styles"

    templates = []
    if styles_dir.exists():
        for f in styles_dir.iterdir():
            if f.is_file() and f.suffix == ".zpl":
                templates.append(f.stem)

    # Also include drafts
    tmps_dir = styles_dir / "tmps"
    if tmps_dir.exists():
        for f in tmps_dir.iterdir():
            if f.is_file() and f.suffix == ".zpl":
                templates.append(f.stem)

    return sorted(templates)


@router.post("/print", response_model=PrintResponse)
async def print_label(request: Request, print_req: PrintRequest) -> PrintResponse:
    """Send a print request to a printer."""
    zp = request.app.state.zp
    rate_limiter = request.app.state.print_rate_limiter
    client_ip = request.client.host if request.client else "unknown"

    # Check rate limit
    allowed, reason = await rate_limiter.acquire(client_ip)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)

    try:
        zp.print_zpl(
            lab=print_req.lab,
            printer_name=print_req.printer,
            label_zpl_style=print_req.label_zpl_style,
            uid_barcode=print_req.uid_barcode,
            alt_a=print_req.alt_a,
            alt_b=print_req.alt_b,
            alt_c=print_req.alt_c,
            alt_d=print_req.alt_d,
            alt_e=print_req.alt_e,
            alt_f=print_req.alt_f,
            print_n=print_req.copies,
            client_ip=client_ip,
        )
        return PrintResponse(success=True, message="Print request sent successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from None
    finally:
        rate_limiter.release()


@router.post("/render", response_model=RenderResponse)
async def render_label(request: Request, render_req: RenderRequest) -> RenderResponse:
    """
    Render ZPL to PNG image.

    This endpoint generates a PNG image from ZPL content without sending to a printer.
    You can provide either:
    - A template name (e.g., 'tube_2inX1in') with field values
    - Raw ZPL content directly

    Returns a URL to download the generated PNG.
    """
    zp = request.app.state.zp

    # Validate that we have either template or zpl_content
    if not render_req.template and not render_req.zpl_content:
        raise HTTPException(
            status_code=400, detail="Either 'template' or 'zpl_content' must be provided"
        )

    try:
        # Generate ZPL string from template if not provided directly
        if render_req.zpl_content:
            zpl_string = render_req.zpl_content
        else:
            zpl_string = zp.formulate_zpl(
                uid_barcode=render_req.uid_barcode,
                alt_a=render_req.alt_a,
                alt_b=render_req.alt_b,
                alt_c=render_req.alt_c,
                alt_d=render_req.alt_d,
                alt_e=render_req.alt_e,
                alt_f=render_req.alt_f,
                label_zpl_style=render_req.template,
            )

        # Generate unique filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H:%M:%S.%f")
        template_name = render_req.template or "custom"
        png_filename = f"zpl_render_{template_name}_{timestamp}.png"
        png_path = xdg.get_generated_files_dir() / png_filename

        # Render to PNG
        zp.generate_label_png(zpl_string, str(png_path), relative=False)

        return RenderResponse(
            success=True,
            message="PNG rendered successfully",
            png_url=f"/generated/{png_filename}",
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Template not found: {e}") from None
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Render failed: {e}") from None


@router.post("/render/png")
async def render_label_png(request: Request, render_req: RenderRequest):
    """
    Render ZPL to PNG and return the image directly.

    Same as /render but returns the PNG file directly instead of a URL.
    Useful for programmatic access where you want the image bytes.
    """
    zp = request.app.state.zp

    # Validate that we have either template or zpl_content
    if not render_req.template and not render_req.zpl_content:
        raise HTTPException(
            status_code=400, detail="Either 'template' or 'zpl_content' must be provided"
        )

    try:
        # Generate ZPL string from template if not provided directly
        if render_req.zpl_content:
            zpl_string = render_req.zpl_content
        else:
            zpl_string = zp.formulate_zpl(
                uid_barcode=render_req.uid_barcode,
                alt_a=render_req.alt_a,
                alt_b=render_req.alt_b,
                alt_c=render_req.alt_c,
                alt_d=render_req.alt_d,
                alt_e=render_req.alt_e,
                alt_f=render_req.alt_f,
                label_zpl_style=render_req.template,
            )

        # Generate unique filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H:%M:%S.%f")
        template_name = render_req.template or "custom"
        png_filename = f"zpl_render_{template_name}_{timestamp}.png"
        png_path = xdg.get_generated_files_dir() / png_filename

        # Render to PNG
        zp.generate_label_png(zpl_string, str(png_path), relative=False)

        # Return the file directly
        return FileResponse(
            path=str(png_path),
            media_type="image/png",
            filename=png_filename,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Template not found: {e}") from None
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Render failed: {e}") from None


@router.get("/config")
async def get_config(request: Request) -> dict[str, Any]:
    """Get the current printer configuration."""
    zp = request.app.state.zp
    return dict(zp.printers)


# ----- Lab Settings Endpoints -----


class LabUpdateRequest(BaseModel):
    """Request model for updating lab settings."""

    lab_name: str | None = Field(None, description="Human-readable lab name")
    available_locations: list[str] | None = Field(None, description="List of valid locations")


class PrinterUpdateRequest(BaseModel):
    """Request model for updating printer settings."""

    printer_name: str | None = Field(None, description="User-friendly display name")
    lab_location: str | None = Field(None, description="Location within the lab")
    notes: str | None = Field(None, description="Optional notes")
    label_zpl_styles: list[str] | None = Field(None, description="Allowed ZPL styles")
    default_label_style: str | None = Field(
        None, description="Default label style to use when none specified"
    )


@router.patch("/labs/{lab}", response_model=LabInfo)
async def update_lab(request: Request, lab: str, update: LabUpdateRequest) -> LabInfo:
    """Update lab settings (lab_name, available_locations)."""
    zp = request.app.state.zp
    labs = zp.printers.get("labs", {})

    if lab not in labs:
        raise HTTPException(status_code=404, detail=f"Lab '{lab}' not found")

    lab_data = labs[lab]

    if update.lab_name is not None:
        lab_data["lab_name"] = update.lab_name
    if update.available_locations is not None:
        lab_data["available_locations"] = update.available_locations

    # Save changes
    zp.save_printer_json(zp.printers_filename, relative=False)

    # Return updated lab info
    return await get_lab(request, lab)


@router.patch("/labs/{lab}/printers/{printer_id}")
async def update_printer(
    request: Request, lab: str, printer_id: str, update: PrinterUpdateRequest
) -> PrinterInfo:
    """Update printer settings (printer_name, lab_location, notes)."""
    zp = request.app.state.zp
    labs = zp.printers.get("labs", {})

    if lab not in labs:
        raise HTTPException(status_code=404, detail=f"Lab '{lab}' not found")

    lab_printers = labs[lab].get("printers", {})
    if printer_id not in lab_printers:
        raise HTTPException(
            status_code=404, detail=f"Printer '{printer_id}' not found in lab '{lab}'"
        )

    printer_data = lab_printers[printer_id]

    if update.printer_name is not None:
        printer_data["printer_name"] = update.printer_name if update.printer_name else None
    if update.lab_location is not None:
        printer_data["lab_location"] = update.lab_location if update.lab_location else None
    if update.notes is not None:
        printer_data["notes"] = update.notes
    if update.label_zpl_styles is not None:
        printer_data["label_zpl_styles"] = update.label_zpl_styles
    if update.default_label_style is not None:
        # Validate that the style exists in label_zpl_styles (if it's not empty string)
        if update.default_label_style and update.default_label_style not in printer_data.get(
            "label_zpl_styles", []
        ):
            raise HTTPException(
                status_code=400,
                detail=f"Default label style '{update.default_label_style}' must be one of: {printer_data.get('label_zpl_styles', [])}",
            )
        printer_data["default_label_style"] = (
            update.default_label_style if update.default_label_style else None
        )

    # Save changes
    zp.save_printer_json(zp.printers_filename, relative=False)

    return PrinterInfo(
        id=printer_id,
        ip_address=printer_data.get("ip_address", ""),
        printer_name=printer_data.get("printer_name"),
        lab_location=printer_data.get("lab_location"),
        manufacturer=printer_data.get("manufacturer", "zebra"),
        model=printer_data.get("model", ""),
        serial=printer_data.get("serial", ""),
        label_zpl_styles=printer_data.get("label_zpl_styles", []),
        default_label_style=printer_data.get("default_label_style"),
        print_method=printer_data.get("print_method", ""),
        notes=printer_data.get("notes", ""),
    )
