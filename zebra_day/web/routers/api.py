"""
Versioned JSON API router for zebra_day.

Provides programmatic access to printer management and label printing.
All endpoints return JSON and are prefixed with /api/v1/.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from zebra_day import paths as xdg
from zebra_day.logging_config import get_logger

_log = get_logger(__name__)

router = APIRouter()


# ----- Request/Response Models -----


class PrintRequest(BaseModel):
    """Request model for printing a label."""

    lab: str = Field(..., description="Lab identifier")
    printer: str = Field(..., description="Printer name")
    label_zpl_style: str | None = Field(None, description="ZPL template name")
    zpl_content: str | None = Field(
        None,
        description=("Raw ZPL content to print directly (takes precedence over label_zpl_style)."),
    )
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
    lsmc_euid: str = Field("", description="Lab Sample Management Container Enterprise Unique ID")
    state: str = Field(
        "Unknown",
        description="Operational state: Ready, Paused, Error, Offline, Unknown",
    )


class LabInfo(BaseModel):
    """Lab information model (v2.1.0 schema)."""

    id: str = Field(..., description="Lab identifier/key in JSON")
    lab_name: str = Field(..., description="Human-readable lab name")
    lab_display_name: str = Field(..., description="Short user-friendly display name")
    lab_description: str = Field(..., description="Human-readable lab description")
    network_stub: str = Field(
        ..., description="IP stub last scanned for this lab (e.g. '192.168.1')"
    )
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


class TemplateSaveRequest(BaseModel):
    """Request model for saving a ZPL template."""

    filename: str = Field(..., description="Template filename (e.g., 'my_label.zpl' or 'my_label')")
    zpl_content: str = Field(..., description="ZPL template content")
    location: Literal["user", "package"] = Field(
        "user", description="Save location: 'user' (XDG config) or 'package'"
    )
    overwrite: bool = Field(True, description="Overwrite existing file if present")
    backup: bool = Field(True, description="Create backup before overwriting")


class TemplateSaveResponse(BaseModel):
    """Response model for template save."""

    success: bool
    path: str = Field(..., description="Full path where template was saved")
    filename: str = Field(..., description="Template filename")


class TemplateDeleteResponse(BaseModel):
    """Response model for template deletion."""

    success: bool
    message: str


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
                lsmc_euid=info.get("lsmc_euid", ""),
                state="Unknown",
            )
        )

    return LabInfo(
        id=lab,
        lab_name=lab_data.get("lab_name", lab),
        lab_display_name=lab_data.get("lab_display_name", lab_data.get("lab_name", lab)),
        lab_description=lab_data.get("lab_description", ""),
        network_stub=lab_data.get("network_stub", ""),
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
                lsmc_euid=info.get("lsmc_euid", ""),
                state="Unknown",
            )
        )
    return printers


@router.get("/templates", response_model=list[str])
async def list_templates(request: Request) -> list[str]:
    """List all available ZPL templates.

    Returns template names (stems) from:
    1. User config dir (~/.config/zebra_day/label_styles/)
    2. Package dir (zebra_day/etc/label_styles/)
    """
    zp = request.app.state.zp
    return zp.list_template_names(include_legacy_drafts=False)


@router.post("/templates", response_model=TemplateSaveResponse)
async def save_template(request: Request, data: TemplateSaveRequest) -> TemplateSaveResponse:
    """Save a ZPL template.

    Default save location is the user's XDG config dir (~/.config/zebra_day/label_styles/).
    If backup=True (default), existing files are backed up before overwriting.
    """
    zp = request.app.state.zp

    try:
        path = zp.save_template(
            filename=data.filename,
            zpl_content=data.zpl_content,
            location=data.location,
            overwrite=data.overwrite,
            backup=data.backup,
        )
        return TemplateSaveResponse(success=True, path=str(path), filename=path.name)
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@router.delete("/templates/{template_name}", response_model=TemplateDeleteResponse)
async def delete_template(
    request: Request,
    template_name: str,
    location: Literal["user", "package"] = "user",
) -> TemplateDeleteResponse:
    """Delete a ZPL template by name.

    By default, deletes from user config dir. Use location='package' to delete from package dir.
    """
    zp = request.app.state.zp

    try:
        zp.delete_template(template_name, location=location)
        return TemplateDeleteResponse(success=True, message=f"Template '{template_name}' deleted")
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


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
            zpl_content=print_req.zpl_content,
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
    lab_display_name: str | None = Field(None, description="Short user-friendly display name")
    lab_description: str | None = Field(None, description="Human-readable lab description")
    network_stub: str | None = Field(None, description="IP stub last scanned for this lab")
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
    lsmc_euid: str | None = Field(
        None, description="Lab Sample Management Container EUID (no leading zeros)"
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
    if update.lab_display_name is not None:
        lab_data["lab_display_name"] = update.lab_display_name
    if update.lab_description is not None:
        lab_data["lab_description"] = update.lab_description
    if update.network_stub is not None:
        lab_data["network_stub"] = update.network_stub
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
    if update.lsmc_euid is not None:
        printer_data["lsmc_euid"] = update.lsmc_euid

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
        lsmc_euid=printer_data.get("lsmc_euid", ""),
        state="Unknown",
    )


# ----- Backend / AWS Configuration Endpoints -----


def _get_backend_info(zp) -> dict[str, Any]:
    """Build a backend status dict from the active zpl() instance."""
    from zebra_day.backends.dynamo import DynamoBackend
    from zebra_day.backends.local import LocalBackend

    backend = zp._backend
    backend_type = "dynamodb" if isinstance(backend, DynamoBackend) else "local"

    info: dict[str, Any] = {
        "backend_type": backend_type,
    }

    if backend_type == "dynamodb":
        info["aws_profile"] = os.environ.get("AWS_PROFILE") or "default credential chain"
        info["dynamo_table"] = backend.table_name
        info["aws_region"] = backend.region
        info["s3_bucket"] = backend.s3_bucket or ""
        info["s3_prefix"] = backend.s3_prefix
        try:
            status = backend.get_status()
            info["table_status"] = status.get("table_status", "UNKNOWN")
            info["item_count"] = status.get("item_count", 0)
            info["last_backup"] = status.get("last_backup_at", "")
            info["last_backup_s3_key"] = status.get("last_backup_s3_key", "")
            info["backup_count"] = status.get("backup_count", 0)
            info["config_version"] = status.get("config_version", 0)
            info["config_updated_at"] = status.get("config_updated_at", "")
            info["config_updated_by"] = status.get("config_updated_by", "")
            info["error"] = None
        except Exception as exc:
            _log.warning("Failed to fetch DynamoDB status: %s", exc)
            info["error"] = str(exc)
    else:
        na = "N/A - using local file backend"
        info["aws_profile"] = na
        info["dynamo_table"] = na
        info["aws_region"] = na
        info["s3_bucket"] = na
        info["s3_prefix"] = na
        info["last_backup"] = na
        info["config_version"] = na
        info["error"] = None

    return info


@router.get("/config/backend-status")
async def config_backend_status(request: Request) -> dict[str, Any]:
    """Return the current backend type and AWS configuration details."""
    zp = request.app.state.zp
    return _get_backend_info(zp)


@router.post("/config/refresh")
async def config_refresh(request: Request) -> dict[str, Any]:
    """Reload configuration from the active backend.

    For DynamoDB backend this re-reads from the table.
    For local backend this re-reads the config file.
    """
    zp = request.app.state.zp
    try:
        zp.printers = zp._backend.load_config()
        zp._maybe_migrate_schema()
        return {"success": True, "message": "Configuration reloaded from backend."}
    except Exception as exc:
        _log.error("Config refresh failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/config/detect-tables")
async def config_detect_tables(
    request: Request,
    region: str | None = None,
) -> dict[str, Any]:
    """Scan an AWS region for compatible zebra-day DynamoDB tables.

    Parameters:
        region: AWS region to scan. Defaults to ZEBRA_DAY_DYNAMO_REGION,
                then AWS_DEFAULT_REGION, then us-west-2.
    """
    scan_region = region or os.environ.get(
        "ZEBRA_DAY_DYNAMO_REGION",
        os.environ.get("AWS_DEFAULT_REGION", "us-west-2"),
    )

    try:
        import boto3

        profile = os.environ.get("AWS_PROFILE") or None
        session = boto3.Session(region_name=scan_region, profile_name=profile)
        ddb = session.client("dynamodb")
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="boto3 is not installed. Install with: pip install zebra_day[aws]",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to create AWS session: {exc}",
        )

    try:
        # List all tables (paginate)
        all_tables: list[str] = []
        paginator = ddb.get_paginator("list_tables")
        for page in paginator.paginate():
            all_tables.extend(page.get("TableNames", []))

        # Filter for tables that look like zebra-day config tables
        keywords = {"zebra", "config"}
        matches: list[dict[str, Any]] = []
        for tname in all_tables:
            lower = tname.lower()
            if lower == "zebra-day-config" or all(kw in lower for kw in keywords):
                # Describe each match for details
                try:
                    desc = ddb.describe_table(TableName=tname)["Table"]
                    matches.append({
                        "table_name": tname,
                        "region": scan_region,
                        "item_count": desc.get("ItemCount", 0),
                        "status": desc.get("TableStatus", "UNKNOWN"),
                        "size_bytes": desc.get("TableSizeBytes", 0),
                    })
                except Exception as desc_exc:
                    matches.append({
                        "table_name": tname,
                        "region": scan_region,
                        "item_count": -1,
                        "status": f"Error: {desc_exc}",
                        "size_bytes": 0,
                    })

        return {
            "region": scan_region,
            "total_tables": len(all_tables),
            "matches": matches,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to scan DynamoDB tables in {scan_region}: {exc}",
        )


class CheckS3BucketRequest(BaseModel):
    """Request model for checking S3 bucket existence."""

    bucket: str = Field(description="S3 bucket name to check")
    region: str = Field(default="us-west-2", description="AWS region")
    profile: str = Field(default="", description="AWS profile name (optional)")


class CreateS3BucketRequest(BaseModel):
    """Request model for creating an S3 bucket with tags."""

    bucket: str = Field(description="S3 bucket name to create")
    region: str = Field(default="us-west-2", description="AWS region")
    profile: str = Field(default="", description="AWS profile name (optional)")
    cost_center: str = Field(default="", description="lsmc-cost-center tag value")
    project: str = Field(default="", description="lsmc-project tag value")


@router.post("/config/check-s3-bucket")
async def config_check_s3_bucket(body: CheckS3BucketRequest) -> dict[str, Any]:
    """Check whether an S3 bucket exists and is accessible."""
    if not body.bucket:
        raise HTTPException(status_code=400, detail="bucket is required.")
    profile = body.profile.strip() or None
    if profile and profile.lower() == "default":
        raise HTTPException(
            status_code=400,
            detail="AWS profile 'default' is not allowed. Use a named profile.",
        )
    try:
        import boto3

        session_kwargs: dict[str, Any] = {"region_name": body.region}
        if profile:
            session_kwargs["profile_name"] = profile
        s3 = boto3.Session(**session_kwargs).client("s3")
        s3.head_bucket(Bucket=body.bucket)
        return {"exists": True, "bucket": body.bucket}
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="boto3 is not installed. Install with: pip install zebra_day[aws]",
        )
    except Exception:
        return {"exists": False, "bucket": body.bucket}


@router.post("/config/create-s3-bucket")
async def config_create_s3_bucket(body: CreateS3BucketRequest) -> dict[str, Any]:
    """Create an S3 bucket with lsmc cost-center and project tags."""
    if not body.bucket:
        raise HTTPException(status_code=400, detail="bucket is required.")
    profile = body.profile.strip() or None
    if profile and profile.lower() == "default":
        raise HTTPException(
            status_code=400,
            detail="AWS profile 'default' is not allowed. Use a named profile.",
        )
    try:
        from zebra_day.backends.dynamo import DynamoBackend

        backend = DynamoBackend(
            table_name="zebra-day-config",
            region=body.region,
            s3_bucket=body.bucket,
            profile=profile,
            cost_center=body.cost_center or None,
            project=body.project or None,
        )
        backend.create_s3_bucket()
        return {
            "success": True,
            "bucket": body.bucket,
            "region": body.region,
            "tags": {
                "lsmc-cost-center": backend.cost_center,
                "lsmc-project": backend.project,
            },
        }
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="boto3 is not installed. Install with: pip install zebra_day[aws]",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to create S3 bucket '{body.bucket}': {exc}",
        )


class SwitchBackendRequest(BaseModel):
    """Request model for switching the active config backend."""

    backend_type: Literal["local", "dynamodb"]
    table_name: str = Field(default="zebra-day-config", description="DynamoDB table name")
    region: str = Field(default="us-west-2", description="AWS region")
    s3_bucket: str = Field(default="", description="S3 backup bucket (required for dynamodb)")
    s3_prefix: str = Field(default="zebra-day/", description="S3 key prefix")
    profile: str = Field(default="", description="AWS profile name (optional)")


@router.post("/config/switch-backend")
async def config_switch_backend(
    request: Request,
    body: SwitchBackendRequest,
) -> dict[str, Any]:
    """Switch the running server's config backend.

    **Session-only**: This affects the running process. To persist, set the
    corresponding environment variables before restarting the server.
    """
    zp = request.app.state.zp

    if body.backend_type == "dynamodb":
        # Reject profile="default" explicitly
        if body.profile.strip().lower() == "default":
            raise HTTPException(
                status_code=400,
                detail="AWS profile 'default' is not allowed. Please create and use a named profile (e.g., 'zebra-dev', 'lab-profile').",
            )

        # Validate required fields
        if not body.s3_bucket:
            raise HTTPException(
                status_code=400,
                detail="s3_bucket is required when switching to DynamoDB backend.",
            )

        try:
            from zebra_day.backends.dynamo import DynamoBackend

            profile = body.profile.strip() or None
            new_backend = DynamoBackend(
                table_name=body.table_name,
                region=body.region,
                s3_bucket=body.s3_bucket,
                s3_prefix=body.s3_prefix,
                profile=profile,
            )

            # Validate connection by describing the table
            new_backend._ddb_client.describe_table(TableName=body.table_name)

        except ImportError:
            raise HTTPException(
                status_code=501,
                detail="boto3 is not installed. Install with: pip install zebra_day[aws]",
            )
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Cannot connect to DynamoDB table '{body.table_name}' "
                f"in {body.region}: {exc}",
            )

    else:
        # Switch to local backend
        from zebra_day.backends.local import LocalBackend

        new_backend = LocalBackend()

    # Swap the backend on the live zpl instance
    try:
        zp._backend = new_backend
        zp.printers = new_backend.load_config()
        if hasattr(new_backend, "config_path_str"):
            zp.printers_filename = new_backend.config_path_str
        else:
            zp.printers_filename = ""
        zp._maybe_migrate_schema()
    except Exception as exc:
        _log.error("Backend switch failed during config reload: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Backend switch failed during config reload: {exc}",
        )

    _log.info("Backend switched to %s", body.backend_type)
    return {
        "success": True,
        "message": f"Backend switched to {body.backend_type}. This is session-only.",
        "backend": _get_backend_info(zp),
    }