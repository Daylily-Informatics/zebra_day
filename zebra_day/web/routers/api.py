"""Versioned JSON API router for zebra_day."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from zebra_day import paths as xdg
from zebra_day.client import PrinterRecord

router = APIRouter()


class PrinterInfo(BaseModel):
    printer_euid: str
    lab: str
    ip_address: str
    printer_name: str = ""
    lab_location: str = ""
    manufacturer: str = "zebra"
    model: str = ""
    serial: str = ""
    label_profiles: list[str] = Field(default_factory=list)
    default_label_profile: str = ""
    print_method: str = "socket"
    notes: str = ""
    lsmc_euid: str = ""
    state: str = "Unknown"
    status: str = "active"
    discovery_source: str = ""


class LabInfo(BaseModel):
    lab: str
    display_name: str = ""
    description: str = ""


class LabCreateRequest(BaseModel):
    lab: str
    display_name: str = ""
    description: str = ""


class TemplateInfo(BaseModel):
    template_name: str
    zpl_content: str
    source: str = "user"
    euid: str = ""


class LabelProfileInfo(BaseModel):
    profile_name: str
    template_name: str = ""
    managed_by: str = ""
    euid: str = ""


class PrintRequest(BaseModel):
    lab: str
    printer_euid: str
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
    zpl_content: str = ""


class ResolvePrintResponse(BaseModel):
    lab: str
    printer_euid: str
    printer_ip: str
    printer: PrinterInfo
    template_name: str = ""
    label_style: str = ""
    zpl_content: str
    copies: int


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
    zpl_content: str
    png_url: str


class DiscoverRequest(BaseModel):
    ip_stub: str
    scan_http_port: int | None = None


class TemplateSaveRequest(BaseModel):
    filename: str
    zpl_content: str


def _client(request: Request):
    return request.app.state.zebra_day


def _printer_info(record: PrinterRecord) -> PrinterInfo:
    payload = dict(record.to_payload())
    payload["printer_euid"] = payload.pop("euid", "")
    payload.pop("printer_id", None)
    return PrinterInfo(**payload)


@router.get("/labs", response_model=list[str])
async def list_labs(request: Request) -> list[str]:
    return list(_client(request).list_labs())


@router.post("/labs", response_model=LabInfo, status_code=201)
async def create_lab(request: Request, payload: LabCreateRequest) -> LabInfo:
    lab = payload.lab.strip()
    if not lab:
        raise HTTPException(status_code=400, detail="lab is required")
    try:
        stored = _client(request).create_lab(
            lab,
            display_name=payload.display_name,
            description=payload.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LabInfo(
        lab=lab,
        display_name=str(stored.get("display_name") or lab.replace("-", " ").title()),
        description=str(stored.get("description") or ""),
    )


@router.get("/labs/{lab}/printers", response_model=list[PrinterInfo])
async def list_printers(request: Request, lab: str) -> list[PrinterInfo]:
    if lab not in _client(request).list_labs():
        raise HTTPException(
            status_code=404,
            detail=f"Lab '{lab}' not found. Create the lab before managing printers.",
        )
    return [_printer_info(item) for item in _client(request).list_printers(lab)]


@router.get("/labs/{lab}/printers/{printer_euid}", response_model=PrinterInfo)
async def get_printer(request: Request, lab: str, printer_euid: str) -> PrinterInfo:
    printer = _client(request).get_printer(printer_euid, lab=lab)
    if printer is None:
        raise HTTPException(status_code=404, detail=f"Printer not found: {lab}/{printer_euid}")
    return _printer_info(printer)


@router.patch("/labs/{lab}/printers/{printer_euid}", response_model=PrinterInfo)
async def patch_printer(
    request: Request,
    lab: str,
    printer_euid: str,
    payload: dict[str, Any],
) -> PrinterInfo:
    if "euid" in payload or "printer_euid" in payload:
        raise HTTPException(
            status_code=400,
            detail="printer_euid belongs in the URL path; do not send euid fields in the body",
        )
    try:
        updated = _client(request).update_printer_metadata(lab, printer_euid, **payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _printer_info(updated)


@router.post("/labs/{lab}/discover", response_model=list[PrinterInfo])
async def discover_lab_printers(
    request: Request,
    lab: str,
    payload: DiscoverRequest,
) -> list[PrinterInfo]:
    try:
        rows = _client(request).discover_printers(
            ip_stub=payload.ip_stub,
            lab=lab,
            scan_http_port=payload.scan_http_port,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
    return [_printer_info(item) for item in rows]


@router.post("/labs/{lab}/printers/{printer_euid}/sync", response_model=PrinterInfo)
async def sync_printer(request: Request, lab: str, printer_euid: str) -> PrinterInfo:
    try:
        updated = _client(request).sync_printer_metadata(printer_euid, lab)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _printer_info(updated)


@router.get("/templates", response_model=list[str])
async def list_templates(request: Request) -> list[str]:
    return list(_client(request).list_templates())


@router.get("/templates/{template_name}", response_model=TemplateInfo)
async def get_template(request: Request, template_name: str) -> TemplateInfo:
    template = _client(request).get_template(template_name)
    if template is None:
        raise HTTPException(status_code=404, detail=f"Template not found: {template_name}")
    return TemplateInfo(**template)


@router.post("/templates", response_model=TemplateInfo)
async def save_template(request: Request, payload: TemplateSaveRequest) -> TemplateInfo:
    raw_name = payload.filename.strip()
    if not raw_name:
        raise HTTPException(status_code=400, detail="filename is required")
    if "/" in raw_name or "\\" in raw_name:
        raise HTTPException(status_code=400, detail="filename must be a simple filename")
    stem = raw_name[:-4] if raw_name.endswith(".zpl") else raw_name
    _client(request).save_template(stem, payload.zpl_content, source="user")
    template = _client(request).get_template(stem)
    assert template is not None
    return TemplateInfo(**template)


@router.delete("/templates/{template_name}")
async def delete_template(request: Request, template_name: str) -> dict[str, Any]:
    try:
        _client(request).delete_template(template_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "message": "Template deleted"}


@router.get("/label-profiles", response_model=list[LabelProfileInfo])
async def list_label_profiles(request: Request) -> list[LabelProfileInfo]:
    return [LabelProfileInfo(**item) for item in _client(request).list_label_profiles()]


@router.get("/label-profiles/{profile_name}", response_model=LabelProfileInfo)
async def get_label_profile(request: Request, profile_name: str) -> LabelProfileInfo:
    payload = _client(request).get_label_profile(profile_name)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Label profile not found: {profile_name}")
    return LabelProfileInfo(**payload)


@router.post("/render", response_model=RenderResponse)
async def render_label(request: Request, render_req: RenderRequest) -> RenderResponse:
    if not render_req.template and not render_req.zpl_content:
        raise HTTPException(
            status_code=400, detail="Either 'template' or 'zpl_content' must be provided"
        )
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
    return RenderResponse(
        success=True,
        message="PNG rendered successfully",
        zpl_content=zpl_string,
        png_url=png_url,
    )


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


@router.post("/print/resolve", response_model=ResolvePrintResponse)
async def resolve_print(request: Request, print_req: PrintRequest) -> ResolvePrintResponse:
    try:
        resolved = _client(request).resolve_print_request(
            lab=print_req.lab,
            printer_euid=print_req.printer_euid,
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
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResolvePrintResponse(
        lab=str(resolved["lab"]),
        printer_euid=str(resolved["printer_euid"]),
        printer_ip=str(resolved["printer_ip"]),
        printer=PrinterInfo(**dict(resolved["printer"])),
        template_name=str(resolved.get("template_name") or ""),
        label_style=str(resolved.get("label_style") or ""),
        zpl_content=str(resolved["zpl_content"]),
        copies=int(resolved["copies"]),
    )


@router.post("/print", response_model=PrintResponse)
async def print_label(request: Request, print_req: PrintRequest) -> PrintResponse:
    rate_limiter = request.app.state.print_rate_limiter
    client_ip = request.client.host if request.client else "unknown"
    allowed, reason = await rate_limiter.acquire(client_ip)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)
    try:
        zpl_string = _client(request).submit_print_job(
            lab=print_req.lab,
            printer_euid=print_req.printer_euid,
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
        return PrintResponse(
            success=True, message="Print request sent successfully", zpl_content=zpl_string
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        rate_limiter.release()


@router.get("/config")
async def get_runtime_config(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    summary = dict(_client(request).runtime_summary())
    summary.update(
        {
            "version": getattr(request.app.state, "version", ""),
            "auth_mode": settings.auth_mode,
            "ui_show_environment_chrome": bool(settings.ui_show_environment_chrome),
            "internal_api_key_configured": bool(settings.internal_api_key),
            "config_path": str(settings.config_path),
        }
    )
    return summary
