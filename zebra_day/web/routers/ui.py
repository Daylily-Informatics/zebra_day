"""
UI router for zebra_day web interface.

Provides HTML endpoints for the web-based management interface.
All routes use the modern UI design with responsive layouts.
"""

from __future__ import annotations

import asyncio
import json
import queue
import tempfile
import threading
import time
import uuid
from pathlib import Path

import yaml
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)

import zebra_day.cmd_mgr as zdcm
from zebra_day import paths as xdg
from zebra_day.logging_config import get_logger

_log = get_logger(__name__)

router = APIRouter()


def _get_scan_jobs(app) -> dict[str, dict]:
    """Return (and lazily initialize) the in-memory scan job registry."""
    if not hasattr(app.state, "scan_jobs") or app.state.scan_jobs is None:
        app.state.scan_jobs = {}
    return app.state.scan_jobs


def get_template_context(request: Request, **kwargs) -> dict:
    """Build common template context for templates."""
    return {
        "request": request,
        "css_theme": f"static/{request.app.state.css_theme}",
        "local_ip": request.app.state.local_ip,
        **kwargs,
    }


def get_modern_context(request: Request, active_page: str = "", **kwargs) -> dict:
    """Build common template context for modern templates."""
    return {
        "request": request,
        "active_page": active_page,
        "local_ip": request.app.state.local_ip,
        "version": getattr(request.app.state, "version", "0.7.0"),
        "cache_bust": str(int(time.time())),
        **kwargs,
    }


def get_templates_by_location(zp) -> dict[str, list[str]]:
    """Get templates categorized by location: user vs package.

    Returns dict with keys 'user' and 'package', each containing sorted lists
    of template names (stems).
    """
    user_dir = xdg.get_label_styles_dir()
    pkg_dir = zp._package_label_styles_dir()

    user_templates: list[str] = []
    package_templates: list[str] = []

    if user_dir.exists():
        for f in sorted(user_dir.iterdir()):
            if f.is_file() and f.suffix == ".zpl":
                user_templates.append(f.stem)

    if pkg_dir.exists():
        for f in sorted(pkg_dir.iterdir()):
            if f.is_file() and f.suffix == ".zpl":
                # Skip if already in user (user overrides package)
                if f.stem not in user_templates:
                    package_templates.append(f.stem)

    return {"user": user_templates, "package": package_templates}


def get_labs_meta(zp) -> dict[str, dict[str, str]]:
    """Return lab metadata mapping keyed by lab key.

    This is primarily for UI display (show lab_display_name while still using
    the stable lab key in URLs).
    """
    labs = zp.printers.get("labs", {}) if hasattr(zp, "printers") else {}
    meta: dict[str, dict[str, str]] = {}
    if not isinstance(labs, dict):
        return meta

    for lab_key, lab_obj in labs.items():
        if not isinstance(lab_obj, dict):
            continue
        lab_name = str(lab_obj.get("lab_name", lab_key))
        meta[str(lab_key)] = {
            "lab_name": lab_name,
            "lab_display_name": str(lab_obj.get("lab_display_name", lab_name)),
            "lab_description": str(lab_obj.get("lab_description", "")),
            "network_stub": str(lab_obj.get("network_stub", "")),
        }
    return meta


def get_stats(zp, pkg_path: Path) -> dict:
    """Calculate dashboard statistics."""
    labs = zp.printers.get("labs", {})
    # Count printers via nested 'printers' key (v2 schema)
    total_printers = sum(len(lab_data.get("printers", {})) for lab_data in labs.values())
    templates_by_loc = get_templates_by_location(zp)
    total_templates = len(templates_by_loc["user"]) + len(templates_by_loc["package"])

    # Count backup files
    bkup_dir = pkg_path / "etc" / "old_printer_config"
    backups = len(list(bkup_dir.iterdir())) if bkup_dir.exists() else 0

    return {
        "total_labs": len(labs),
        "total_printers": total_printers,
        "online_printers": 0,  # Would need to check each printer
        "total_templates": total_templates,
        "backups": backups,
    }


# =============================================================================
# MODERN UI ROUTES (root level)
# =============================================================================


@router.get("/", response_class=HTMLResponse)
async def modern_dashboard(request: Request):
    """Modern dashboard - home page."""
    zp = request.app.state.zp
    templates = request.app.state.templates
    pkg_path = request.app.state.pkg_path

    labs = zp.printers.get("labs", {})
    stats = get_stats(zp, pkg_path)

    context = get_modern_context(
        request,
        active_page="dashboard",
        labs=labs,
        stats=stats,
    )
    return templates.TemplateResponse("modern/dashboard.html", context)


@router.get("/printers", response_class=HTMLResponse)
async def modern_printers(request: Request):
    """Modern printers list - all labs."""
    zp = request.app.state.zp
    templates = request.app.state.templates

    labs = list(zp.printers.get("labs", {}).keys())
    labs_meta = get_labs_meta(zp)
    ip_root = ".".join(request.app.state.local_ip.split(".")[:-1])

    context = get_modern_context(
        request,
        active_page="printers",
        labs=labs,
        labs_meta=labs_meta,
        printers=None,
        lab=None,
        ip_root=ip_root,
    )
    return templates.TemplateResponse("modern/printers.html", context)


@router.get("/printers/{lab}", response_class=HTMLResponse)
async def modern_printers_by_lab(request: Request, lab: str, live: bool = True):
    """Modern printers list for a specific lab.

    Args:
        request: FastAPI request object
        lab: Lab name
        live: If True (default), query live status from each printer (may be slow)
    """
    zp = request.app.state.zp
    templates = request.app.state.templates

    if lab not in zp.printers.get("labs", {}):
        raise HTTPException(status_code=404, detail=f"Lab '{lab}' not found")

    lab_data = zp.printers["labs"][lab]
    lab_printers = lab_data.get("printers", {})
    labs_meta = get_labs_meta(zp)

    printers = []
    for name, info in lab_printers.items():
        ip_addr = info.get("ip_address", "")
        printer_data = {
            "id": name,
            "name": info.get("printer_name") or name,  # Display name or fallback to ID
            "printer_name": info.get("printer_name"),
            "ip_address": ip_addr,
            "lab_location": info.get("lab_location"),
            "manufacturer": info.get("manufacturer", "zebra"),
            "model": info.get("model", ""),
            "serial": info.get("serial", ""),
            "label_zpl_styles": info.get("label_zpl_styles", []),
            "print_method": info.get("print_method", "socket"),
            "status": info.get("status") or ("online" if ip_addr else "unknown"),
            "notes": info.get("notes", ""),
            "lsmc_euid": info.get("lsmc_euid", ""),
            "state": "Unknown",  # Operational state: Ready, Paused, Error, Offline, Unknown
            # Live status fields (populated if live=True)
            "firmware": None,
            "label_count": None,
            "paused": False,
            "paper_out": False,
            "ribbon_out": False,
            "head_up": False,
        }

        # Query live status if requested and IP is valid
        if live and ip_addr and ip_addr not in ("dl_png", "unknown"):
            try:
                live_status = zdcm.get_cached_status(ip_addr, timeout=2.0)
                if live_status.get("online"):
                    # Status = network reachability only (online/offline)
                    printer_data["status"] = "online"
                    printer_data["firmware"] = live_status.get("firmware")
                    printer_data["label_count"] = live_status.get("label_count")
                    printer_data["paused"] = live_status.get("paused", False)
                    printer_data["paper_out"] = live_status.get("paper_out", False)
                    printer_data["ribbon_out"] = live_status.get("ribbon_out", False)
                    printer_data["head_up"] = live_status.get("head_up", False)
                    # Update model/serial from live data if available
                    if live_status.get("model"):
                        printer_data["model"] = live_status["model"]
                    if live_status.get("serial"):
                        printer_data["serial"] = live_status["serial"]
                else:
                    printer_data["status"] = "offline"
            except Exception:
                printer_data["status"] = "offline"

        # Calculate operational state based on status and flags
        # State = operational status (Ready/Paused/Error/Offline/Unknown)
        if printer_data["status"] == "offline":
            printer_data["state"] = "Offline"
        elif printer_data["status"] == "online":
            # Printer is reachable, now check operational state
            if printer_data.get("paused"):
                printer_data["state"] = "Paused"
            elif (
                printer_data.get("paper_out")
                or printer_data.get("ribbon_out")
                or printer_data.get("head_up")
            ):
                printer_data["state"] = "Error"
            else:
                printer_data["state"] = "Ready"
        else:
            printer_data["state"] = "Unknown"

        printers.append(printer_data)

    ip_root = ".".join(request.app.state.local_ip.split(".")[:-1])

    context = get_modern_context(
        request,
        active_page="printers",
        labs=list(zp.printers.get("labs", {}).keys()),
        labs_meta=labs_meta,
        printers=printers,
        lab=lab,
        lab_name=lab_data.get("lab_name", lab),
        lab_display_name=lab_data.get("lab_display_name", lab_data.get("lab_name", lab)),
        lab_description=lab_data.get("lab_description", ""),
        network_stub=lab_data.get("network_stub", ""),
        available_locations=lab_data.get("available_locations", []),
        ip_root=ip_root,
        live_status=live,
    )
    return templates.TemplateResponse("modern/printers.html", context)


@router.get("/printers/{lab}/{printer_id}", response_class=HTMLResponse)
async def modern_printer_detail(request: Request, lab: str, printer_id: str, refresh: bool = False):
    """Modern printer detail page.

    Args:
        request: FastAPI request object
        lab: Lab name
        printer_id: Printer ID within the lab
        refresh: If True, force refresh the live status cache
    """
    zp = request.app.state.zp
    templates = request.app.state.templates

    if lab not in zp.printers.get("labs", {}):
        raise HTTPException(status_code=404, detail=f"Lab '{lab}' not found")

    lab_data = zp.printers["labs"][lab]
    lab_printers = lab_data.get("printers", {})
    labs_meta = get_labs_meta(zp)

    if printer_id not in lab_printers:
        raise HTTPException(status_code=404, detail=f"Printer '{printer_id}' not found")

    printer_info = dict(lab_printers[printer_id])  # Copy to avoid mutating config

    # Query live status from printer
    live_status = None
    printer_config = ""
    ip_addr = printer_info.get("ip_address", "")
    if ip_addr and ip_addr != "dl_png":
        try:
            # Get live status (cached unless refresh=True)
            live_status = zdcm.get_cached_status(ip_addr, timeout=2.0, force_refresh=refresh)
        except Exception:
            live_status = {"online": False}

        # Try to get printer configuration (only if online)
        if live_status and live_status.get("online"):
            try:
                printer_config = zdcm.ZebraPrinter(ip_addr).get_configuration() or ""
            except Exception as e:
                printer_config = f"Unable to retrieve config: {e}"
        else:
            printer_config = "Printer offline - unable to retrieve configuration"

    # Calculate operational state based on live status
    if live_status:
        if not live_status.get("online"):
            printer_info["state"] = "Offline"
        elif live_status.get("paused"):
            printer_info["state"] = "Paused"
        elif (
            live_status.get("paper_out")
            or live_status.get("ribbon_out")
            or live_status.get("head_up")
        ):
            printer_info["state"] = "Error"
        else:
            printer_info["state"] = "Ready"
    else:
        printer_info["state"] = "Unknown"

    context = get_modern_context(
        request,
        active_page="printers",
        printer_id=printer_id,
        printer_name=printer_info.get("printer_name") or printer_id,
        lab=lab,
        lab_name=lab_data.get("lab_name", lab),
        lab_display_name=lab_data.get("lab_display_name", lab_data.get("lab_name", lab)),
        lab_description=lab_data.get("lab_description", ""),
        network_stub=lab_data.get("network_stub", ""),
        labs_meta=labs_meta,
        available_locations=lab_data.get("available_locations", []),
        printer_info=printer_info,
        printer_config=printer_config,
        live_status=live_status,
    )
    return templates.TemplateResponse("modern/printer_detail.html", context)


@router.get("/print", response_class=HTMLResponse)
async def modern_print_request(
    request: Request,
    lab: str = "",
    printer: str = "",
    template: str = "",
):
    """Modern print request form."""
    zp = request.app.state.zp
    templates = request.app.state.templates

    templates_by_loc = get_templates_by_location(zp)
    labs_dict = zp.printers.get("labs", {})
    labs_meta = get_labs_meta(zp)

    context = get_modern_context(
        request,
        active_page="print",
        labs=list(labs_dict.keys()),
        labs_meta=labs_meta,
        labs_dict=json.dumps(labs_dict),
        user_templates=templates_by_loc["user"],
        package_templates=templates_by_loc["package"],
        selected_lab=lab,
        selected_printer=printer,
        selected_template=template,
    )
    return templates.TemplateResponse("modern/print_request.html", context)


@router.get("/templates", response_class=HTMLResponse)
async def modern_templates(request: Request):
    """Modern template management page."""
    zp = request.app.state.zp
    templates = request.app.state.templates

    templates_by_loc = get_templates_by_location(zp)

    context = get_modern_context(
        request,
        active_page="templates",
        user_templates=templates_by_loc["user"],
        package_templates=templates_by_loc["package"],
    )
    return templates.TemplateResponse("modern/templates.html", context)


@router.get("/templates/edit", response_class=HTMLResponse)
async def modern_template_edit(
    request: Request,
    filename: str,
    dtype: str = "",  # deprecated, ignored
):
    """Modern template editor.

    Loads template via resolve_template_path() (XDG-first resolution).
    The 'dtype' parameter is deprecated and ignored.
    """
    zp = request.app.state.zp
    templates = request.app.state.templates

    # Normalize: strip .zpl if present (resolve_template_path handles it)
    template_name = filename.replace(".zpl", "")

    try:
        filepath = zp.resolve_template_path(template_name)
        content = filepath.read_text()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Template '{template_name}' not found") from e

    # Determine source location for display
    user_dir = xdg.get_label_styles_dir()
    source_location = "user" if filepath.is_relative_to(user_dir) else "package"

    labs_dict = zp.printers.get("labs", {})

    context = get_modern_context(
        request,
        active_page="templates",
        filename=f"{template_name}.zpl",
        template_name=template_name,
        content=content,
        source_location=source_location,
        labs=list(labs_dict.keys()),
        labs_dict=json.dumps(labs_dict),
    )
    return templates.TemplateResponse("modern/template_editor.html", context)


@router.get("/templates/preview")
async def modern_template_preview(
    request: Request,
    filename: str,
    dtype: str = "",  # deprecated, ignored
):
    """Generate a PNG preview of a ZPL template.

    Resolves template via XDG-first resolution and redirects to the generated PNG.
    The 'dtype' parameter is deprecated and ignored.
    """
    zp = request.app.state.zp
    pkg_path = request.app.state.pkg_path

    # Normalize template name
    template_name = filename.replace(".zpl", "")

    try:
        filepath = zp.resolve_template_path(template_name)
        zpl_content = filepath.read_text()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Template '{template_name}' not found") from e

    try:
        # Generate PNG preview
        output_dir = pkg_path / "files"
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / f"{template_name}_preview.png"
        zp.generate_label_png(zpl_content, str(output_path), False)

        return RedirectResponse(url=f"/files/{template_name}_preview.png", status_code=303)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preview generation failed: {e}") from None


@router.get("/config", response_class=HTMLResponse)
async def modern_config(request: Request):
    """Modern configuration page."""
    zp = request.app.state.zp
    templates = request.app.state.templates
    pkg_path = request.app.state.pkg_path

    labs = list(zp.printers.get("labs", {}).keys())
    labs_meta = get_labs_meta(zp)
    ip_root = ".".join(request.app.state.local_ip.split(".")[:-1])

    # Build config summary
    stats = get_stats(zp, pkg_path)
    config_summary = {
        "labs": stats["total_labs"],
        "printers": stats["total_printers"],
        "templates": stats["total_templates"],
        "backups": stats["backups"],
    }

    # Get the config file path that was loaded
    config_file_path = getattr(zp, "printers_filename", "Unknown")

    # Build backend info for the template
    from zebra_day.web.routers.api import _get_backend_info

    backend_info = _get_backend_info(zp)

    context = get_modern_context(
        request,
        active_page="config",
        labs=labs,
        labs_meta=labs_meta,
        ip_root=ip_root,
        config_summary=config_summary,
        config_file_path=config_file_path,
        backend_info=backend_info,
    )
    return templates.TemplateResponse("modern/config.html", context)


@router.get("/config/view", response_class=HTMLResponse)
async def modern_config_view(request: Request):
    """View printer configuration as YAML."""
    zp = request.app.state.zp
    templates = request.app.state.templates

    # Convert config to YAML with header
    config_yaml = "# zebra_day Configuration File\n\n" + yaml.dump(
        zp.printers, default_flow_style=False, sort_keys=False
    )

    context = get_template_context(
        request,
        title="View Configuration",
        config_yaml=config_yaml,
        mode="view",
    )
    return templates.TemplateResponse("modern/config_editor.html", context)


@router.get("/config/edit", response_class=HTMLResponse)
async def modern_config_edit(request: Request, error_msg: str | None = None):
    """Edit printer configuration as YAML."""
    zp = request.app.state.zp
    templates = request.app.state.templates

    # Convert config to YAML with header
    config_yaml = "# zebra_day Configuration File\n\n" + yaml.dump(
        zp.printers, default_flow_style=False, sort_keys=False
    )

    context = get_template_context(
        request,
        title="Edit Configuration",
        config_yaml=config_yaml,
        mode="edit",
        error_msg=error_msg,
    )
    return templates.TemplateResponse("modern/config_editor.html", context)


@router.post("/config/save")
async def modern_config_save(request: Request, yaml_data: str = Form(...)):
    """Save edited printer configuration as YAML."""
    zp = request.app.state.zp

    try:
        # Validate YAML
        new_config = yaml.safe_load(yaml_data)

        if not isinstance(new_config, dict):
            raise ValueError("Config must be a YAML dictionary")

        # Update printers and save
        zp.printers = new_config
        zp.save_printer_config()

        return RedirectResponse(url="/config", status_code=303)

    except yaml.YAMLError as e:
        return RedirectResponse(url=f"/config/edit?error_msg=Invalid YAML: {e}", status_code=303)
    except ValueError as e:
        return RedirectResponse(url=f"/config/edit?error_msg={e}", status_code=303)


@router.get("/config/backups", response_class=HTMLResponse)
async def modern_config_backups(request: Request):
    """List prior config files (YAML and legacy JSON)."""
    templates = request.app.state.templates

    # Use XDG backup directory
    bkup_dir = xdg.get_config_backups_dir()

    backup_files = []
    if bkup_dir.exists():
        for f in sorted(bkup_dir.iterdir(), reverse=True):
            if f.is_file() and f.suffix in (".yaml", ".yml", ".json"):
                backup_files.append(f.name)

    context = get_template_context(
        request,
        title="Configuration Backups",
        backup_files=backup_files,
    )
    return templates.TemplateResponse("modern/config_backups.html", context)


@router.get("/config/new", response_class=HTMLResponse)
async def modern_config_new(request: Request):
    """Build new config page."""
    zp = request.app.state.zp
    templates = request.app.state.templates

    ip_root = ".".join(request.app.state.local_ip.split(".")[:-1])

    context = get_template_context(
        request,
        title="New Configuration",
        ip_root=ip_root,
        labs=list(zp.printers.get("labs", {}).keys()),
    )
    return templates.TemplateResponse("modern/config_new.html", context)


@router.get("/config/reset")
async def modern_config_reset(request: Request):
    """Reset printer config from template."""
    zp = request.app.state.zp
    zp.replace_printer_json_from_template()
    time.sleep(0.5)
    return RedirectResponse(url="/config", status_code=303)


@router.get("/config/clear")
async def modern_config_clear(request: Request):
    """Clear the printer configuration."""
    zp = request.app.state.zp
    zp.clear_printers_json()
    time.sleep(0.5)
    return RedirectResponse(url="/config", status_code=303)


@router.get("/config/scan", response_class=HTMLResponse)
async def modern_config_scan(
    request: Request,
    ip_stub: str = "192.168.1",
    scan_wait: str = "0.5",
    lab: str = "scan-results",
):
    """Scan network for printers."""
    zp = request.app.state.zp
    zp.probe_zebra_printers_add_to_printers_json(ip_stub=ip_stub, scan_wait=scan_wait, lab=lab)
    time.sleep(2.2)
    return RedirectResponse(url=f"/printers/{lab}", status_code=303)


@router.get("/config/scan/stream")
async def modern_config_scan_stream(
    request: Request,
    ip_stub: str = "192.168.1",
    scan_wait: str = "0.5",
    lab: str = "scan-results",
):
    """Stream network scan progress via Server-Sent Events (SSE)."""
    zp = request.app.state.zp
    scan_jobs = _get_scan_jobs(request.app)

    scan_id = uuid.uuid4().hex
    cancel_event = threading.Event()
    progress_queue: queue.Queue[dict | None] = queue.Queue()

    def progress_callback(msg: dict) -> None:
        try:
            progress_queue.put(msg)
        except Exception:
            # Never let UI progress reporting break the scan thread.
            pass

    def run_scan() -> None:
        try:
            zp.probe_zebra_printers_add_to_printers_json(
                ip_stub=ip_stub,
                scan_wait=scan_wait,
                lab=lab,
                cancel_event=cancel_event,
                progress_callback=progress_callback,
            )
        except Exception as e:
            progress_callback({"kind": "error", "message": str(e)})
        finally:
            # Sentinel to end the SSE generator.
            progress_queue.put(None)

    t = threading.Thread(
        target=run_scan,
        name=f"zebra-day-scan-{scan_id}",
        daemon=True,
    )
    scan_jobs[scan_id] = {"cancel_event": cancel_event, "thread": t}
    t.start()

    async def event_stream():
        # Initial event gives the client the scan_id to support cancellation.
        yield f"data: {json.dumps({'kind': 'init', 'scan_id': scan_id, 'lab': lab, 'total': 255})}\n\n"

        while True:
            if await request.is_disconnected():
                cancel_event.set()
                break

            try:
                msg = progress_queue.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.05)
                continue

            if msg is None:
                break

            yield f"data: {json.dumps(msg)}\n\n"

        scan_jobs.pop(scan_id, None)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/config/scan/cancel")
async def modern_config_scan_cancel(request: Request, scan_id: str):
    """Cancel an active scan (if present) and keep any discovered printers."""
    scan_jobs = _get_scan_jobs(request.app)
    job = scan_jobs.get(scan_id)
    if not job:
        raise HTTPException(status_code=404, detail="scan_id not found")

    cancel_event = job.get("cancel_event")
    if cancel_event is not None:
        try:
            cancel_event.set()
        except Exception:
            pass

    return JSONResponse({"success": True, "scan_id": scan_id})


@router.get("/_print_label", response_class=HTMLResponse)
async def modern_print_label(
    request: Request,
    lab: str | None = None,
    printer: str = "",
    printer_ip: str = "",
    label_zpl_style: str = "",
    uid_barcode: str = "",
    alt_a: str = "",
    alt_b: str = "",
    alt_c: str = "",
    alt_d: str = "",
    alt_e: str = "",
    alt_f: str = "",
    labSelect: str = "",
):
    """Execute print request - modern UI."""
    zp = request.app.state.zp
    templates = request.app.state.templates
    rate_limiter = request.app.state.print_rate_limiter

    if lab is None:
        lab = labSelect

    client_ip = request.client.host if request.client else "unknown"

    # Check rate limit
    allowed, reason = await rate_limiter.acquire(client_ip)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)

    try:
        result = zp.print_zpl(
            lab=lab,
            printer_name=printer,
            label_zpl_style=label_zpl_style,
            uid_barcode=uid_barcode,
            alt_a=alt_a,
            alt_b=alt_b,
            alt_c=alt_c,
            alt_d=alt_d,
            alt_e=alt_e,
            alt_f=alt_f,
            client_ip=client_ip,
        )
    finally:
        rate_limiter.release()

    # Build the full URL for reference
    full_url = str(request.url)

    png_url = None
    if result and ".png" in str(result):
        png_name = str(result).split("/")[-1]
        png_url = f"/generated/{png_name}"

    context = get_modern_context(
        request,
        title="Print Result",
        success=True,
        full_url=full_url,
        png_url=png_url,
    )
    return templates.TemplateResponse("modern/print_result.html", context)


@router.post("/save", response_class=HTMLResponse)
async def modern_save_template(
    request: Request,
    filename: str = Form(...),
    content: str = Form(...),
    location: str = Form("user"),
    overwrite: bool = Form(True),
    backup: bool = Form(True),
):
    """Save ZPL template to user config or package directory.

    Saves to ~/.config/zebra_day/label_styles/ by default (location='user').
    If backup=True (default), existing files are backed up before overwriting.
    """
    zp = request.app.state.zp
    templates = request.app.state.templates

    try:
        saved_path = zp.save_template(
            filename=filename,
            zpl_content=content,
            location=location,
            overwrite=overwrite,
            backup=backup,
        )
        context = get_modern_context(
            request,
            title="Template Saved",
            success=True,
            saved_path=str(saved_path),
            saved_filename=saved_path.name,
            location=location,
        )
    except (FileExistsError, ValueError, PermissionError) as e:
        context = get_modern_context(
            request,
            title="Save Failed",
            success=False,
            error_message=str(e),
        )

    return templates.TemplateResponse("modern/save_result.html", context)


@router.post("/png_renderer")
async def modern_png_renderer(
    request: Request,
    filename: str = Form(...),
    content: str = Form(...),
    lab: str = Form(""),
    printer: str = Form(""),
    ftag: str = Form(""),
):
    """Render ZPL content to PNG - modern UI."""
    zp = request.app.state.zp
    pkg_path = request.app.state.pkg_path

    files_dir = pkg_path / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    png_tmp_f = tempfile.NamedTemporaryFile(suffix=".png", dir=str(files_dir), delete=False).name

    zp.generate_label_png(content, png_fn=png_tmp_f)

    # Return just the relative path for the img src
    return Response(
        content=f"files/{Path(png_tmp_f).name}",
        media_type="text/plain",
    )
