# ZDAY UI GUIDE

## Modern Web UI (2.0.0+)

zebra_day 2.0.0+ features a modern, responsive web interface with HTTPS support:

| Interface | URL | Description |
|-----------|-----|-------------|
| **Dashboard** | `https://localhost:8118/` | Printer fleet stats, quick actions, navigation |
| **Printers** | `https://localhost:8118/printers` | Printer status and management by lab |
| **Print** | `https://localhost:8118/print` | Send print requests with template selection |
| **Templates** | `https://localhost:8118/templates` | ZPL template editor with live PNG preview |
| **Config** | `https://localhost:8118/config` | Printer configuration management |
| **API Docs** | `https://localhost:8118/docs` | Interactive OpenAPI/Swagger documentation |
| **ReDoc** | `https://localhost:8118/redoc` | Alternative API documentation |

> **Note:** Use `http://` instead of `https://` if running without certificates (`--no-https`).

### Printer Status vs State (v2.2.0+)

The Printers page displays two distinct health indicators for each printer:

| Field | Purpose | Values |
|-------|---------|--------|
| **Status** | Network reachability | `Online` (green), `Offline` (red), `N/A`, `Unknown` |
| **State** | Operational status | `Ready` (green), `Paused` (yellow), `Error` (red with details), `Offline`, `Unknown` |

- **Status** answers: "Can I reach this printer on the network?"
- **State** answers: "Is this printer ready to print right now?"

The **State** column shows additional details when errors are detected:
- `Error (Paper)` — Paper out
- `Error (Ribbon)` — Ribbon out
- `Error (Head)` — Print head is up

---

## UI Documentation

> The screenshots below show the UI. Everything which can be accomplished via this UI can also be achieved with the library code directly (more so in fact).

### Home, 4 Primary Tool Clusters Available

#### _1_ Automated Zebra Printer Discovery & Centralized Management /// _2_ Zebra Printer Status And Activity Reports /// _3_ ZPL Label Template Design + Preview + Deployment of New Styles /// _4_ Manual Print Request Formulation For Any Printer + ZPL Combination Desired

<img width="1016" alt="home" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/8960686a-8444-4b17-8cf2-a27dfe0432eb">

  > the link to change ZDAY style can be found in the lower right of the home page

### Printer Fleet Status Report & Scan For New Printers Tool

<img width="1024" alt="fleetreport" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/3620b38b-88ac-4c22-8c36-76e427d91a27">

### Example of Printer Config JSON 

> ( this is fully user editable (modify the atomatically added entries, delete or add )

<img width="667" alt="editconf" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/0f6b04d7-0d98-491c-815f-ef157c6c5af8">
  > links to clear the current json file, refresh from the default template, or save current edits to become active.

####  List Of All Archived Printer Config JSON Files, 

> these can be restored if desired

<img width="999" alt="bkupconf" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/31970151-2015-40c5-a75e-8f3a694d5a78">

### List Of Available ZPL Template Files

> ( the top list are uneditable defaults, the bottom are user created )

<img width="834" alt="chooseZPL" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/c3a03dd6-2d04-47fc-9aa3-a3dc1c6b4677">

#### View of ZPL Preview/Editor
> ( changes to the ZPL on this page produce a preview PNG of what the printer will print  )
<img width="953" alt="zpl_editing" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/025851d2-813e-43d7-80af-f66a71a45bf4">
  * Drafts can be saved, previewed as PNG, or sent to an available printer

### Form To Send Manual Formulated ZPL Print Jobs To Specific Printers

<img width="895" alt="printmanual" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/9a0d7b4d-a808-4008-bd74-f4a3e8e1b670">

#### Manual Print Request Success (including presenting link which can be used by other systems to print)

<img width="312" alt="zpl_exa" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/62afc4d8-dbec-43f8-817e-a30e620aeb51">

#### Example Of Manually Printed Label Showing Zebra Printer Details

<img width="909" alt="print_success" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/5da259f3-0ed4-4c18-953d-c091690e703c">

<img width="411" alt="zplab" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/024a49b8-b86f-4950-abe4-93eedc62101c">

---

## API Reference (curl examples)

All API endpoints are documented at `/docs` (Swagger UI) and `/redoc`. Here are common operations:

### Health Checks

```bash
# Basic health check
curl https://localhost:8118/healthz

# Readiness check (printer manager initialized)
curl https://localhost:8118/readyz
```

### Printer Operations

```bash
# List all printers
curl https://localhost:8118/api/v1/printers

# Get printer status
curl "https://localhost:8118/api/v1/printers/default/192.168.1.7/status"

# Scan for new printers
curl -X POST "https://localhost:8118/api/v1/printers/scan?ip_stub=192.168.1"
```

### Print Labels

```bash
# Print a label using a template
curl -X POST "https://localhost:8118/api/v1/print" \
  -H "Content-Type: application/json" \
  -d '{
    "lab": "default",
    "printer_name": "192.168.1.7",
    "label_zpl_style": "tube_2inX1in",
    "uid_barcode": "SAMPLE123",
    "alt_a": "Field A",
    "alt_b": "Field B"
  }'

# Legacy query-string format (still supported)
curl "https://localhost:8118/_print_label?lab=default&printer=192.168.1.7&label_zpl_style=tube_2inX1in&uid_barcode=SAMPLE123"
```

### Render Labels (PNG preview without printing)

```bash
# Render using a template
curl -X POST "https://localhost:8118/api/v1/render" \
  -H "Content-Type: application/json" \
  -d '{
    "template_name": "tube_2inX1in",
    "uid_barcode": "SAMPLE123",
    "alt_a": "Field A"
  }' \
  --output label.png

# Render raw ZPL
curl -X POST "https://localhost:8118/api/v1/render" \
  -H "Content-Type: application/json" \
  -d '{"zpl_content": "^XA^FO50,50^ADN,36,20^FDHello^FS^XZ"}' \
  --output label.png
```

### Template Operations

```bash
# List all templates
curl https://localhost:8118/api/v1/templates

# Get template content
curl https://localhost:8118/api/v1/templates/tube_2inX1in
```

### Configuration

```bash
# Get current configuration
curl https://localhost:8118/api/v1/config

# Update configuration (PATCH)
curl -X PATCH "https://localhost:8118/api/v1/config" \
  -H "Content-Type: application/json" \
  -d '{"labs": {"default": {"lab_name": "Main Lab"}}}'
```

---

## Zebra Printer Web Admin UI
Often, I find these pages valuable in triaging a poorly behaving printer.  I compare a well behaved printer to a problem one and see which settings are not in agreement.

### Main Page (these links are presented in the printer status report towards the top of the ZDAY home)
<img width="430" alt="z1" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/c5f55ef4-1a69-491a-8f58-b733768d2e7b">

### General Setup Page
<img width="586" alt="z2" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/84ecc09f-05b1-4414-a38a-b83ad803f51d">
  * Darkness, Print Speed and Label Top often need editing.

### Media Setup
<img width="445" alt="z3" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/433e426e-7cff-4fcf-962c-2b8a3b80fc66">
  * Media Type Must Be Set For Label Stock
  * Almost always sensor=Web.
  * Width and length should be edited if labels are printing off the label stock (auto calibration is not working in these cases)
  * !! When you save changes to these pages, they are temporarily saved... you must go to the main setting page and apply all saved changes for them to take effect.
  
### Calibration Page
<img width="441" alt="z4" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/7843d86c-1a95-4bcd-b98a-b80ea6b93654">

### Network Settings: Wired
<img width="472" alt="z5" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/01784778-1665-46b5-8089-93db478f300e">
  * Get MAC address here.
  * Set static IP assignment here if needed, else DHCP

### Network Settings: Wireless
<img width="484" alt="z6" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/a1a55e92-5a29-4d30-89a1-baa0f4b0837f">
  * Generally not a smooth thing to setup.  It is quite hard to fuss with these settings remotely.
