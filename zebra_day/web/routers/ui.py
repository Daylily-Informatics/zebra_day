"""
UI router for zebra_day web interface.

Provides HTML endpoints for the web-based management interface.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from zebra_day.logging_config import get_logger
import zebra_day.cmd_mgr as zdcm

_log = get_logger(__name__)

router = APIRouter()


def get_template_context(request: Request, **kwargs) -> dict:
    """Build common template context."""
    return {
        "request": request,
        "css_theme": f"static/{request.app.state.css_theme}",
        "local_ip": request.app.state.local_ip,
        **kwargs,
    }


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Home page."""
    zp = request.app.state.zp
    templates = request.app.state.templates

    labs = list(zp.printers.get("labs", {}).keys())

    context = get_template_context(
        request,
        title="Zebra Day - Home",
        labs=labs,
    )
    return templates.TemplateResponse("index.html", context)


@router.get("/printer_status", response_class=HTMLResponse)
async def printer_status(request: Request, lab: str = "scan-results"):
    """Printer status page for a lab."""
    zp = request.app.state.zp
    templates = request.app.state.templates

    if lab not in zp.printers.get("labs", {}):
        raise HTTPException(status_code=404, detail=f"Lab '{lab}' not found")

    printers = []
    for name, info in zp.printers["labs"][lab].items():
        printer_data = {
            "name": name,
            "ip_address": info.get("ip_address", ""),
            "model": info.get("model", ""),
            "serial": info.get("serial", ""),
            "label_zpl_styles": info.get("label_zpl_styles", []),
            "arp_data": info.get("arp_data", ""),
            "status": "unknown",
        }

        # Try to get printer status (curl check)
        if info.get("ip_address") and info["ip_address"] != "dl_png":
            try:
                result = subprocess.run(
                    ["curl", "-m", "4", info["ip_address"]],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                for line in result.stdout.splitlines():
                    if "Status:" in line:
                        printer_data["status"] = line.strip()
                        break
            except Exception:
                printer_data["status"] = "Unable to connect"

        printers.append(printer_data)

    ip_root = ".".join(request.app.state.local_ip.split(".")[:-1])

    context = get_template_context(
        request,
        title=f"Printer Status - {lab}",
        lab=lab,
        printers=printers,
        ip_root=ip_root,
        labs=list(zp.printers.get("labs", {}).keys()),
    )
    return templates.TemplateResponse("printer_status.html", context)


@router.get("/simple_print_request", response_class=HTMLResponse)
async def simple_print_request(request: Request):
    """Simple print request form."""
    zp = request.app.state.zp
    templates = request.app.state.templates

    # Get available templates
    pkg_path = request.app.state.pkg_path
    styles_dir = pkg_path / "etc" / "label_styles"

    template_names = []
    if styles_dir.exists():
        for f in sorted(styles_dir.iterdir()):
            if f.is_file() and f.suffix == ".zpl":
                template_names.append(f.stem)

    labs_and_printers = {
        lab: list(printers.keys())
        for lab, printers in zp.printers.get("labs", {}).items()
    }

    context = get_template_context(
        request,
        title="Print Label",
        templates=template_names,
        labs=list(zp.printers.get("labs", {}).keys()),
        labs_and_printers=json.dumps(labs_and_printers),
    )
    return templates.TemplateResponse("simple_print.html", context)


@router.get("/edit_zpl", response_class=HTMLResponse)
async def edit_zpl(request: Request):
    """List ZPL templates for editing."""
    templates = request.app.state.templates
    pkg_path = request.app.state.pkg_path
    styles_dir = pkg_path / "etc" / "label_styles"

    stable_templates = []
    draft_templates = []

    if styles_dir.exists():
        for f in sorted(styles_dir.iterdir()):
            if f.is_file() and f.suffix == ".zpl":
                stable_templates.append(f.name)

    tmps_dir = styles_dir / "tmps"
    if tmps_dir.exists():
        for f in sorted(tmps_dir.iterdir()):
            if f.is_file() and f.suffix == ".zpl":
                draft_templates.append(f.name)

    context = get_template_context(
        request,
        title="Edit ZPL Templates",
        stable_templates=stable_templates,
        draft_templates=draft_templates,
    )
    return templates.TemplateResponse("edit_zpl.html", context)


@router.get("/chg_ui_style", response_class=HTMLResponse)
async def chg_ui_style(request: Request, css_file: Optional[str] = None):
    """Change UI style or show available styles."""
    if css_file:
        request.app.state.css_theme = css_file
        return RedirectResponse(url="/", status_code=303)

    templates = request.app.state.templates
    pkg_path = request.app.state.pkg_path
    static_dir = pkg_path / "static"

    css_files = []
    if static_dir.exists():
        for f in sorted(static_dir.iterdir()):
            if f.suffix == ".css":
                css_files.append(f.name)

    context = get_template_context(request, title="Change UI Style", css_files=css_files)
    return templates.TemplateResponse("chg_ui_style.html", context)




@router.get("/printer_details", response_class=HTMLResponse)
async def printer_details(request: Request, printer_name: str, lab: str):
    """Show detailed printer information."""
    zp = request.app.state.zp
    templates = request.app.state.templates

    if lab not in zp.printers.get("labs", {}):
        raise HTTPException(status_code=404, detail=f"Lab '{lab}' not found")
    if printer_name not in zp.printers["labs"][lab]:
        raise HTTPException(status_code=404, detail=f"Printer '{printer_name}' not found")

    printer_info = zp.printers["labs"][lab][printer_name]

    # Try to get printer configuration
    printer_config = ""
    ip_addr = printer_info.get("ip_address", "")
    if ip_addr and ip_addr != "dl_png":
        try:
            printer_config = zdcm.ZebraPrinter(ip_addr).get_configuration()
        except Exception as e:
            printer_config = f"Unable to retrieve config: {e}"

    context = get_template_context(
        request,
        title=f"Printer Details - {printer_name}",
        printer_name=printer_name,
        lab=lab,
        printer_info=printer_info,
        printer_config=printer_config,
    )
    return templates.TemplateResponse("printer_details.html", context)


@router.get("/view_pstation_json", response_class=HTMLResponse)
async def view_pstation_json(request: Request, error_msg: Optional[str] = None):
    """View and edit printer configuration JSON."""
    zp = request.app.state.zp
    templates = request.app.state.templates

    config_data = json.dumps(zp.printers, indent=4)

    context = get_template_context(
        request,
        title="View Printer Config JSON",
        config_data=config_data,
        error_msg=error_msg,
    )
    return templates.TemplateResponse("view_pstation_json.html", context)


@router.post("/save_pstation_json")
async def save_pstation_json(request: Request, json_data: str = Form(...)):
    """Save edited printer configuration JSON."""
    zp = request.app.state.zp

    try:
        data = json.loads(json_data)
    except json.JSONDecodeError as e:
        return RedirectResponse(
            url=f"/view_pstation_json?error_msg=Invalid+JSON:+{str(e)}",
            status_code=303,
        )

    try:
        # Backup and save
        zp.save_printer_json()

        # Write new config
        with open(zp.printers_filename, "w") as f:
            json.dump(data, f, indent=4)

        # Reload config
        zp.load_printer_json(json_file=zp.printers_filename, relative=False)

        return RedirectResponse(url="/", status_code=303)

    except Exception as e:
        return RedirectResponse(
            url=f"/view_pstation_json?error_msg=Error+saving:+{str(e)}",
            status_code=303,
        )


@router.get("/clear_printers_json")
async def clear_printers_json(request: Request):
    """Clear the printer configuration JSON."""
    zp = request.app.state.zp
    zp.clear_printers_json()
    time.sleep(1.2)
    return RedirectResponse(url="/", status_code=303)


@router.get("/reset_pstation_json")
async def reset_pstation_json(request: Request):
    """Reset printer config from template."""
    zp = request.app.state.zp
    zp.replace_printer_json_from_template()
    time.sleep(1.2)
    return RedirectResponse(url="/", status_code=303)


@router.get("/list_prior_printer_config_files", response_class=HTMLResponse)
async def list_prior_printer_config_files(request: Request):
    """List backed up printer config files."""
    templates = request.app.state.templates
    pkg_path = request.app.state.pkg_path
    bkup_dir = pkg_path / "etc" / "old_printer_config"

    backup_files = []
    if bkup_dir.exists():
        for f in sorted(bkup_dir.iterdir(), reverse=True):
            if f.is_file():
                backup_files.append(f.name)

    context = get_template_context(
        request,
        title="Prior Printer Config Files",
        backup_files=backup_files,
    )
    return templates.TemplateResponse("list_prior_configs.html", context)


@router.get("/build_new_printers_config_json", response_class=HTMLResponse)
async def build_new_printers_config_json(request: Request):
    """Show network scan form."""
    zp = request.app.state.zp
    templates = request.app.state.templates

    ip_root = ".".join(request.app.state.local_ip.split(".")[:-1])

    context = get_template_context(
        request,
        title="Scan Network for Printers",
        ip_root=ip_root,
        labs=list(zp.printers.get("labs", {}).keys()),
    )
    return templates.TemplateResponse("build_new_config.html", context)


@router.get("/probe_zebra_printers_add_to_printers_json")
async def probe_zebra_printers(
    request: Request,
    ip_stub: str = "192.168.1",
    scan_wait: str = "0.25",
    lab: str = "scan-results",
):
    """Probe network for Zebra printers and add to config."""
    zp = request.app.state.zp
    zp.probe_zebra_printers_add_to_printers_json(
        ip_stub=ip_stub, scan_wait=scan_wait, lab=lab
    )
    time.sleep(2.2)
    return RedirectResponse(url=f"/printer_status?lab={lab}", status_code=303)



@router.get("/bpr", response_class=HTMLResponse)
async def bpr(request: Request):
    """Build print request - select lab, printer, template."""
    zp = request.app.state.zp
    templates = request.app.state.templates
    pkg_path = request.app.state.pkg_path

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

    labs_dict = zp.printers.get("labs", {})

    context = get_template_context(
        request,
        title="Build Print Request",
        labs=list(labs_dict.keys()),
        labs_dict=json.dumps(labs_dict),
        stable_templates=stable_templates,
        draft_templates=draft_templates,
    )
    return templates.TemplateResponse("bpr.html", context)


@router.get("/send_print_request", response_class=HTMLResponse)
async def send_print_request(request: Request):
    """Send print request - stable templates only."""
    zp = request.app.state.zp
    templates = request.app.state.templates

    context = get_template_context(
        request,
        title="Send Print Request",
        labs=zp.printers.get("labs", {}),
    )
    return templates.TemplateResponse("send_print_request.html", context)


@router.get("/build_print_request", response_class=HTMLResponse)
async def build_print_request(
    request: Request,
    lab: str = "",
    printer: str = "",
    printer_ip: str = "",
    label_zpl_style: str = "",
    filename: str = "",
):
    """Show print request form with pre-filled values."""
    templates = request.app.state.templates

    if label_zpl_style in ["", "None"] and filename not in ["", "None"]:
        label_zpl_style = filename.replace(".zpl", "")

    context = get_template_context(
        request,
        title="Build Print Request",
        lab=lab,
        printer=printer,
        printer_ip=printer_ip,
        label_zpl_style=label_zpl_style,
    )
    return templates.TemplateResponse("build_print_request.html", context)


@router.get("/_print_label", response_class=HTMLResponse)
async def print_label(
    request: Request,
    lab: Optional[str] = None,
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
    """Execute print request."""
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
        png_url = f"/files/{png_name}"

    context = get_template_context(
        request,
        title="Print Result",
        success=True,
        full_url=full_url,
        png_url=png_url,
    )
    return templates.TemplateResponse("print_result.html", context)


@router.get("/edit", response_class=HTMLResponse)
async def edit_template(
    request: Request,
    filename: str,
    dtype: str = "",
):
    """Edit a ZPL template file."""
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

    context = get_template_context(
        request,
        title=f"Edit: {filename}",
        filename=filename,
        content=content,
        dtype=dtype,
        labs=list(labs_dict.keys()),
        labs_dict=json.dumps(labs_dict),
    )
    return templates.TemplateResponse("edit_template.html", context)



@router.post("/save", response_class=HTMLResponse)
async def save_template(
    request: Request,
    filename: str = Form(...),
    content: str = Form(...),
    ftag: str = Form("na"),
    lab: str = Form(""),
    printer: str = Form(""),
):
    """Save ZPL template as a new draft file."""
    templates = request.app.state.templates
    pkg_path = request.app.state.pkg_path

    rec_date = str(datetime.now()).replace(" ", "_")
    new_filename = filename.replace(".zpl", f".{ftag}.{rec_date}.zpl")

    tmps_dir = pkg_path / "etc" / "label_styles" / "tmps"
    tmps_dir.mkdir(parents=True, exist_ok=True)

    temp_filepath = tmps_dir / new_filename
    temp_filepath.write_text(content)

    context = get_template_context(
        request,
        title="Template Saved",
        new_filename=new_filename,
    )
    return templates.TemplateResponse("save_result.html", context)


@router.post("/png_renderer")
async def png_renderer(
    request: Request,
    filename: str = Form(...),
    content: str = Form(...),
    lab: str = Form(""),
    printer: str = Form(""),
    ftag: str = Form(""),
):
    """Render ZPL content to PNG."""
    zp = request.app.state.zp
    pkg_path = request.app.state.pkg_path

    files_dir = pkg_path / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    png_tmp_f = tempfile.NamedTemporaryFile(
        suffix=".png", dir=str(files_dir), delete=False
    ).name

    zp.generate_label_png(content, png_fn=png_tmp_f)

    # Return just the relative path for the img src
    return Response(
        content=f"files/{Path(png_tmp_f).name}",
        media_type="text/plain",
    )


@router.post("/build_and_send_raw_print_request")
async def build_and_send_raw_print_request(
    request: Request,
    lab: str = Form(...),
    printer: str = Form(...),
    content: str = Form(...),
    printer_ip: str = Form(""),
    label_zpl_style: str = Form(""),
    filename: str = Form(""),
    ftag: str = Form(""),
):
    """Send raw ZPL content to printer."""
    zp = request.app.state.zp
    rate_limiter = request.app.state.print_rate_limiter
    client_ip = request.client.host if request.client else "unknown"

    # Check rate limit
    allowed, reason = await rate_limiter.acquire(client_ip)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)

    try:
        zp.print_zpl(
            lab=lab,
            printer_name=printer,
            label_zpl_style=None,
            zpl_content=content,
            client_ip=client_ip,
        )
    finally:
        rate_limiter.release()

    return {"status": "sent"}
