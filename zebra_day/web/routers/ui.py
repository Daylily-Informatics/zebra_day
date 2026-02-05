"""
UI router for zebra_day web interface.

Provides HTML endpoints for the web-based management interface.
All routes use the modern UI design with responsive layouts.
"""

from __future__ import annotations

import json
import tempfile
import time
from datetime import datetime
from pathlib import Path

import yaml
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

import zebra_day.cmd_mgr as zdcm
from zebra_day import paths as xdg
from zebra_day.logging_config import get_logger

_log = get_logger(__name__)

router = APIRouter()


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


def get_templates_list(pkg_path: Path) -> tuple[list, list]:
    """Get lists of stable and draft templates."""
    styles_dir = pkg_path / "etc" / "label_styles"
    stable_templates = []
    draft_templates = []

    if styles_dir.exists():
        for f in sorted(styles_dir.iterdir()):
            if f.is_file() and f.suffix == ".zpl":
                stable_templates.append(f.stem)

    tmps_dir = styles_dir / "tmps"
    if tmps_dir.exists():
        for f in sorted(tmps_dir.iterdir()):
            if f.is_file() and f.suffix == ".zpl":
                draft_templates.append(f.stem)

    return stable_templates, draft_templates


def get_stats(zp, pkg_path: Path) -> dict:
    """Calculate dashboard statistics."""
    labs = zp.printers.get("labs", {})
    # Count printers via nested 'printers' key (v2 schema)
    total_printers = sum(len(lab_data.get("printers", {})) for lab_data in labs.values())
    stable, draft = get_templates_list(pkg_path)

    # Count backup files
    bkup_dir = pkg_path / "etc" / "old_printer_config"
    backups = len(list(bkup_dir.iterdir())) if bkup_dir.exists() else 0

    return {
        "total_labs": len(labs),
        "total_printers": total_printers,
        "online_printers": 0,  # Would need to check each printer
        "total_templates": len(stable) + len(draft),
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
    ip_root = ".".join(request.app.state.local_ip.split(".")[:-1])

    context = get_modern_context(
        request,
        active_page="printers",
        labs=labs,
        printers=None,
        lab=None,
        ip_root=ip_root,
    )
    return templates.TemplateResponse("modern/printers.html", context)


@router.get("/printers/{lab}", response_class=HTMLResponse)
async def modern_printers_by_lab(request: Request, lab: str):
    """Modern printers list for a specific lab."""
    zp = request.app.state.zp
    templates = request.app.state.templates

    if lab not in zp.printers.get("labs", {}):
        raise HTTPException(status_code=404, detail=f"Lab '{lab}' not found")

    lab_data = zp.printers["labs"][lab]
    lab_printers = lab_data.get("printers", {})

    printers = []
    for name, info in lab_printers.items():
        printers.append(
            {
                "id": name,
                "name": info.get("printer_name") or name,  # Display name or fallback to ID
                "printer_name": info.get("printer_name"),
                "ip_address": info.get("ip_address", ""),
                "lab_location": info.get("lab_location"),
                "manufacturer": info.get("manufacturer", "zebra"),
                "model": info.get("model", ""),
                "serial": info.get("serial", ""),
                "label_zpl_styles": info.get("label_zpl_styles", []),
                "status": "online" if info.get("ip_address") else "unknown",
                "notes": info.get("notes", ""),
            }
        )

    ip_root = ".".join(request.app.state.local_ip.split(".")[:-1])

    context = get_modern_context(
        request,
        active_page="printers",
        labs=list(zp.printers.get("labs", {}).keys()),
        printers=printers,
        lab=lab,
        lab_name=lab_data.get("lab_name", lab),
        available_locations=lab_data.get("available_locations", []),
        ip_root=ip_root,
    )
    return templates.TemplateResponse("modern/printers.html", context)


@router.get("/printers/{lab}/{printer_id}", response_class=HTMLResponse)
async def modern_printer_detail(request: Request, lab: str, printer_id: str):
    """Modern printer detail page."""
    zp = request.app.state.zp
    templates = request.app.state.templates

    if lab not in zp.printers.get("labs", {}):
        raise HTTPException(status_code=404, detail=f"Lab '{lab}' not found")

    lab_data = zp.printers["labs"][lab]
    lab_printers = lab_data.get("printers", {})

    if printer_id not in lab_printers:
        raise HTTPException(status_code=404, detail=f"Printer '{printer_id}' not found")

    printer_info = lab_printers[printer_id]

    # Try to get printer configuration
    printer_config = ""
    ip_addr = printer_info.get("ip_address", "")
    if ip_addr and ip_addr != "dl_png":
        try:
            printer_config = zdcm.ZebraPrinter(ip_addr).get_configuration()
        except Exception as e:
            printer_config = f"Unable to retrieve config: {e}"

    context = get_modern_context(
        request,
        active_page="printers",
        printer_id=printer_id,
        printer_name=printer_info.get("printer_name") or printer_id,
        lab=lab,
        lab_name=lab_data.get("lab_name", lab),
        available_locations=lab_data.get("available_locations", []),
        printer_info=printer_info,
        printer_config=printer_config,
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
    pkg_path = request.app.state.pkg_path

    stable_templates, draft_templates = get_templates_list(pkg_path)
    labs_dict = zp.printers.get("labs", {})

    context = get_modern_context(
        request,
        active_page="print",
        labs=list(labs_dict.keys()),
        labs_dict=json.dumps(labs_dict),
        stable_templates=stable_templates,
        draft_templates=draft_templates,
        selected_lab=lab,
        selected_printer=printer,
        selected_template=template,
    )
    return templates.TemplateResponse("modern/print_request.html", context)


@router.get("/templates", response_class=HTMLResponse)
async def modern_templates(request: Request):
    """Modern template management page."""
    templates = request.app.state.templates
    pkg_path = request.app.state.pkg_path

    stable_templates, draft_templates = get_templates_list(pkg_path)

    context = get_modern_context(
        request,
        active_page="templates",
        stable_templates=stable_templates,
        draft_templates=draft_templates,
    )
    return templates.TemplateResponse("modern/templates.html", context)


@router.get("/templates/edit", response_class=HTMLResponse)
async def modern_template_edit(
    request: Request,
    filename: str,
    dtype: str = "",
):
    """Modern template editor."""
    zp = request.app.state.zp
    templates = request.app.state.templates
    pkg_path = request.app.state.pkg_path

    if dtype:
        filepath = pkg_path / "etc" / "label_styles" / dtype / filename
    else:
        filepath = pkg_path / "etc" / "label_styles" / filename

    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Template '{filename}' not found")

    content = filepath.read_text()
    labs_dict = zp.printers.get("labs", {})

    context = get_modern_context(
        request,
        active_page="templates",
        filename=filename,
        content=content,
        dtype=dtype,
        labs=list(labs_dict.keys()),
        labs_dict=json.dumps(labs_dict),
    )
    return templates.TemplateResponse("modern/template_editor.html", context)


@router.get("/templates/preview")
async def modern_template_preview(
    request: Request,
    filename: str,
    dtype: str = "",
):
    """Generate a PNG preview of a ZPL template.

    Returns the PNG image directly or redirects to the generated file.
    """
    zp = request.app.state.zp
    pkg_path = request.app.state.pkg_path

    # Find the template file
    if dtype:
        filepath = pkg_path / "etc" / "label_styles" / dtype / filename
    else:
        # Try with .zpl extension if not provided
        if not filename.endswith(".zpl"):
            filepath = pkg_path / "etc" / "label_styles" / f"{filename}.zpl"
        else:
            filepath = pkg_path / "etc" / "label_styles" / filename

    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Template '{filename}' not found")

    try:
        # Read template content
        zpl_content = filepath.read_text()

        # Generate PNG preview
        output_dir = pkg_path / "files"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Use template name for output file
        template_name = filepath.stem
        output_path = output_dir / f"{template_name}_preview.png"

        zp.generate_label_png(zpl_content, str(output_path), False)

        # Return redirect to the generated file
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

    context = get_modern_context(
        request,
        active_page="config",
        labs=labs,
        ip_root=ip_root,
        config_summary=config_summary,
        config_file_path=config_file_path,
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
    scan_wait: str = "0.25",
    lab: str = "scan-results",
):
    """Scan network for printers."""
    zp = request.app.state.zp
    zp.probe_zebra_printers_add_to_printers_json(ip_stub=ip_stub, scan_wait=scan_wait, lab=lab)
    time.sleep(2.2)
    return RedirectResponse(url=f"/printers/{lab}", status_code=303)


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
    ftag: str = Form("na"),
    lab: str = Form(""),
    printer: str = Form(""),
):
    """Save ZPL template as a new draft file - modern UI."""
    templates = request.app.state.templates
    pkg_path = request.app.state.pkg_path

    rec_date = str(datetime.now()).replace(" ", "_")
    new_filename = filename.replace(".zpl", f".{ftag}.{rec_date}.zpl")

    tmps_dir = pkg_path / "etc" / "label_styles" / "tmps"
    tmps_dir.mkdir(parents=True, exist_ok=True)

    temp_filepath = tmps_dir / new_filename
    temp_filepath.write_text(content)

    context = get_modern_context(
        request,
        title="Template Saved",
        new_filename=new_filename,
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
