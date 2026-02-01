"""
Versioned JSON API router for zebra_day.

Provides programmatic access to printer management and label printing.
All endpoints return JSON and are prefixed with /api/v1/.
"""
from __future__ import annotations

from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()


# ----- Request/Response Models -----

class PrintRequest(BaseModel):
    """Request model for printing a label."""
    lab: str = Field(..., description="Lab identifier")
    printer: str = Field(..., description="Printer name")
    label_zpl_style: Optional[str] = Field(None, description="ZPL template name")
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
    png_url: Optional[str] = None


class PrinterInfo(BaseModel):
    """Printer information model."""
    name: str
    ip_address: str
    model: str
    serial: str
    label_zpl_styles: List[str]
    print_method: str


class LabPrinters(BaseModel):
    """Lab and its printers."""
    lab: str
    printers: List[PrinterInfo]


# ----- Endpoints -----

@router.get("/labs", response_model=List[str])
async def list_labs(request: Request) -> List[str]:
    """List all available labs."""
    zp = request.app.state.zp
    return list(zp.printers.get("labs", {}).keys())


@router.get("/labs/{lab}/printers", response_model=List[PrinterInfo])
async def list_printers(request: Request, lab: str) -> List[PrinterInfo]:
    """List all printers in a lab."""
    zp = request.app.state.zp
    labs = zp.printers.get("labs", {})

    if lab not in labs:
        raise HTTPException(status_code=404, detail=f"Lab '{lab}' not found")

    printers = []
    for name, info in labs[lab].items():
        printers.append(
            PrinterInfo(
                name=name,
                ip_address=info.get("ip_address", ""),
                model=info.get("model", ""),
                serial=info.get("serial", ""),
                label_zpl_styles=info.get("label_zpl_styles", []),
                print_method=info.get("print_method", ""),
            )
        )
    return printers


@router.get("/templates", response_model=List[str])
async def list_templates(request: Request) -> List[str]:
    """List all available ZPL templates."""
    from pathlib import Path

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
        result = zp.print_zpl(
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

        # Check if result is a PNG file path
        if result and ".png" in str(result):
            png_name = str(result).split("/")[-1]
            return PrintResponse(
                success=True,
                message="PNG generated successfully",
                png_url=f"/files/{png_name}",
            )

        return PrintResponse(success=True, message="Print request sent successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        rate_limiter.release()


@router.get("/config")
async def get_config(request: Request) -> Dict[str, Any]:
    """Get the current printer configuration."""
    zp = request.app.state.zp
    return zp.printers

