"""Versioned JSON API router for zebra_day."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from zebra_day import paths as xdg
from zebra_day.client import PrinterRecord

router = APIRouter()


class PrintRequest(BaseModel):
    lab: str
    printer: str
    label_zpl_style: str | None = None
    zpl_content: str | None = None
    uid_barcode: str = ""
    alt_a: str = ""
    alt_b: str = ""
    alt_c: str = ""
    alt_d: str = ""
    alt_e: str = ""
    alt_f: str = ""
    copies: int = Field(1, ge=1, le=100)


class PrintResponse(BaseModel):
    success: bool
    message: str
    png_url: str | None = None


class PrinterInfo(BaseModel):
    id: str
    ip_address: str
    printer_name: str | None = None
    lab_location: str | None = None
    manufacturer: str = "zebra"
    model: str = ""
    serial: str = ""
    label_zpl_styles: list[str] = Field(default_factory=list)
    default_label_style: str | None = None
    print_method: str = "socket"
    notes: str | None = ""
    lsmc_euid: str = ""
    state: str = "Unknown"
    euid: str = ""


class LabInfo(BaseModel):
    id: str
    lab_name: str
    lab_display_name: str
    lab_description: str
    network_stub: str
    available_locations: list[str]
    printers: list[PrinterInfo]


class RenderRequest(BaseModel):
    template: str | None = None
    zpl_content: str | None = None
    uid_barcode: str = ""
    alt_a: str = ""
    alt_b: str = ""
    alt_c: str = ""
    alt_d: str = ""
    alt_e: str = ""
    alt_f: str = ""


class RenderResponse(BaseModel):
    success: bool
    message: str
    png_url: str


class TemplateSaveRequest(BaseModel):
    filename: str
    zpl_content: str


class TemplateSaveResponse(BaseModel):
    success: bool
    path: str
    filename: str


def _client(request: Request):
    return request.app.state.zebra_day


def _printer_info(record: PrinterRecord) -> PrinterInfo:
    profiles = list(record.label_profiles or [])
    return PrinterInfo(
        id=record.printer_id,
        ip_address=record.ip_address,
        printer_name=record.printer_name or None,
        lab_location=record.lab_location or None,
        manufacturer=record.manufacturer,
        model=record.model,
        serial=record.serial,
        label_zpl_styles=profiles,
        default_label_style=record.default_label_profile or (profiles[0] if profiles else None),
        print_method=record.print_method,
        notes=record.notes,
        lsmc_euid=record.lsmc_euid,
        state=record.state,
        euid=record.euid,
    )


@router.get("/labs", response_model=list[str])
async def list_labs(request: Request) -> list[str]:
    return _client(request).list_labs()


@router.get("/labs/{lab}", response_model=LabInfo)
async def get_lab(request: Request, lab: str) -> LabInfo:
    printers = _client(request).list_printers(lab)
    if not printers and lab not in _client(request).list_labs():
        raise HTTPException(status_code=404, detail=f"Lab '{lab}' not found")
    title = lab.replace("-", " ").title()
    return LabInfo(
        id=lab,
        lab_name=title,
        lab_display_name=title,
        lab_description="",
        network_stub="",
        available_locations=[],
        printers=[_printer_info(item) for item in printers],
    )


@router.get("/labs/{lab}/printers", response_model=list[PrinterInfo])
async def list_printers(request: Request, lab: str) -> list[PrinterInfo]:
    if lab not in _client(request).list_labs():
        raise HTTPException(status_code=404, detail=f"Lab '{lab}' not found")
    return [_printer_info(item) for item in _client(request).list_printers(lab)]


@router.get("/templates", response_model=list[str])
async def list_templates(request: Request) -> list[str]:
    return _client(request).list_templates()


@router.post("/templates", response_model=TemplateSaveResponse)
async def save_template(request: Request, payload: TemplateSaveRequest) -> TemplateSaveResponse:
    raw_name = payload.filename.strip()
    if not raw_name:
        raise HTTPException(status_code=400, detail="filename is required")
    if "/" in raw_name or "\\" in raw_name:
        raise HTTPException(status_code=400, detail="filename must be a simple filename")
    stem = raw_name[:-4] if raw_name.endswith(".zpl") else raw_name
    _client(request).repository.upsert_template(stem, payload.zpl_content, source="user")
    return TemplateSaveResponse(
        success=True,
        path=f"tapdb://{stem}",
        filename=f"{stem}.zpl",
    )


@router.delete("/templates/{template_name}")
async def delete_template(request: Request, template_name: str) -> dict[str, Any]:
    existing = _client(request).repository.get_template(template_name)
    if existing is None:
        raise HTTPException(status_code=404, detail="Template not found")
    _client(request).repository.upsert_template(template_name, "", source="deleted")
    return {"success": True, "message": "Template deleted"}


@router.post("/print", response_model=PrintResponse)
async def print_label(request: Request, print_req: PrintRequest) -> PrintResponse:
    rate_limiter = request.app.state.print_rate_limiter
    client_ip = request.client.host if request.client else "unknown"
    allowed, reason = await rate_limiter.acquire(client_ip)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)
    try:
        _client(request).print_label(
            lab=print_req.lab,
            printer=print_req.printer,
            label_zpl_style=print_req.label_zpl_style,
            zpl_content=print_req.zpl_content,
            uid_barcode=print_req.uid_barcode,
            alt_a=print_req.alt_a,
            alt_b=print_req.alt_b,
            alt_c=print_req.alt_c,
            alt_d=print_req.alt_d,
            alt_e=print_req.alt_e,
            alt_f=print_req.alt_f,
            copies=print_req.copies,
            client_ip=client_ip,
        )
        return PrintResponse(success=True, message="Print request sent successfully")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        rate_limiter.release()


@router.post("/render", response_model=RenderResponse)
async def render_label(request: Request, render_req: RenderRequest) -> RenderResponse:
    if not render_req.template and not render_req.zpl_content:
        raise HTTPException(status_code=400, detail="Either 'template' or 'zpl_content' must be provided")
    zpl_string, png_url = _client(request).render_label(
        template=render_req.template,
        zpl_content=render_req.zpl_content,
        uid_barcode=render_req.uid_barcode,
        alt_a=render_req.alt_a,
        alt_b=render_req.alt_b,
        alt_c=render_req.alt_c,
        alt_d=render_req.alt_d,
        alt_e=render_req.alt_e,
        alt_f=render_req.alt_f,
    )
    return RenderResponse(success=bool(zpl_string), message="PNG rendered successfully", png_url=png_url)


@router.post("/render/png")
async def render_label_png(request: Request, render_req: RenderRequest):
    _zpl_string, png_url = _client(request).render_label(
        template=render_req.template,
        zpl_content=render_req.zpl_content,
        uid_barcode=render_req.uid_barcode,
        alt_a=render_req.alt_a,
        alt_b=render_req.alt_b,
        alt_c=render_req.alt_c,
        alt_d=render_req.alt_d,
        alt_e=render_req.alt_e,
        alt_f=render_req.alt_f,
    )
    filename = png_url.rsplit("/", 1)[-1]
    path = xdg.get_generated_files_dir() / filename
    return FileResponse(path=str(path), media_type="image/png", filename=filename)


@router.get("/config")
async def get_config(request: Request) -> dict[str, Any]:
    return _client(request)._legacy_config()
