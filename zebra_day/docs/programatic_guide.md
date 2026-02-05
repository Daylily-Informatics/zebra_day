# Library Usage
<a href=../../README.md ><img src="http://flux.glass/format_gh_text?txt=back+home&bg_color=%23443636&txt_color=%232eecef&font=Monoid-Regular-HalfTight-Dollar-0-1-l&font_size=12&width=95&ret_type=img" /></a>
## Quickstart

```python
import zebra_day.print_mgr as zdpm

zlab = zdpm.zpl()

zlab.probe_zebra_printers_add_to_printers_json('192.168.1')  # REPLACE the IP stub with the correct value for your network. This may take a few min to run.  !! This command is not required if you've sucessuflly run the quickstart already, also, won't hurt.

print(zlab.printers)  # This should print out the config dict of all detected zebra printers. An empty dict, {}, is a failure of autodetection, and manual creation of the config file may be needed. If successful, the lab name assigned is 'default', this may be edited later.
# The config will look something like this (v2.0.0 schema with nested printers)
## {'schema_version': '2.0.0', 'labs': {'default': {'lab_name': 'Default', 'printers': {'192.168.1.7': {'ip_address': '192.168.1.7', ...}}}}}

# Assuming a printer was detected, send a test print request. Using the 'lab', 'printer' and 'label_zpl_style' above (you'd have your own IP/Name, other values should remain the same for now. There are multiple label ZPL formats available, the test_2inX1in is for quick testing & only formats in the two UID values specified.

zlab.print_zpl(lab='default', printer_name='192.168.1.7', label_zpl_style='test_2inX1in', uid_barcode="123aUID")
# ZPL code sent successfully to the printer!
# Out[13]: '^XA\n^FO235,20\n^BY1\n^B3N,N,40,N,N\n^FD123aUID^FS\n^FO235,70\n^ADN,30,20\n^FD123aUID^FS\n^FO235,115\n^ADN,25,12\n^FDalt_a^FS\n^FO235,145\n^ADN,25,12\n^FDalt_b^FS\n^FO70,180\n^FO235,170\n^ADN,30,20\n^FDalt_c^FS\n^FO490,180\n^ADN,25,12\n^FDalt_d^FS\n^XZ'
```

## Primary Operations

### Init Object
> def zpl():


  ```python
  import zebra_day.print_mgr as zdpm
  
  zlab = zdpm.zpl()
  ```

  The IP of the machine creating the obj is determined, and the default printer config is read.


### Load/Save/Clear Printer Config

> As of 2.2.0, printer configuration uses YAML format and is stored in XDG-compliant locations:
> - **Linux**: `~/.config/zebra_day/zebra-day-config.yaml`
> - **macOS**: `~/.config/zebra_day/zebra-day-config.yaml`
>
> Legacy note (macOS): older installs may still have config at
> `~/Library/Preferences/zebra_day/`; zebra_day will copy that forward into
> `~/.config/zebra_day/` the first time it loads config.
>
> Use `zday config path` or `zday info` to see the exact path on your system.
>
> Legacy JSON configuration files are automatically migrated to YAML on first load.

```python
# These methods now use the XDG paths automatically (YAML format)
zlab.save_printer_config()  # New method (saves YAML)
zlab.save_printer_json()    # Legacy method (redirects to save_printer_config)
zlab.load_printer_json()    # Legacy method (loads YAML or JSON)
zlab.clear_printers_json()
zlab.replace_printer_json_from_template()
```

When clearing or writing a new config, the existing one is saved to a backup location. Users can open these and effectively rollback if errors are made. Replace from template means overwriting the active one with the template file which accompanies the repo.


### Scan Local Network For Zebra Printers
  >  def probe_zebra_printers_add_to_printers_json(self, ip_stub="192.168.1", scan_wait="0.25",lab="scan-results"):
  
### Check label styles allowed for a lab    
> def get_valid_label_styles_for_lab(self,lab=None):

A never quite implemented idea.

### Produce a ZPL string which will be sent to a printer

>  def formulate_zpl(self,uid_barcode=None, alt_a=None, alt_b=None, alt_c=None, alt_d=None, alt_e=None, alt_f=None, label_zpl_style=None):

  * The `lab` & `printer_name` are used to resolve the IP address for the printer this tuple identify.
  * `label_zpl_style` is used to find the `zpl` template file the remaining values passed in are templated in to.
  * `uid_barcode` is the value which is encoded as a barcode and presented in human readable form. The way this value is displayed will vary by template.
  * `alt_[a-f]` these are used diferently, or not at all, depending on the zpl template.  

### Send ZPL To Zebra To Print A Label
> def print_zpl(self, lab=None, printer_name=None, uid_barcode='', alt_a='', alt_b='', alt_c='', alt_d='', alt_e='', alt_f='', label_zpl_style=None, client_ip='pkg', print_n=1):

With the ZPL string produced, determine the printer IP and send the string to it.

### Send ZPL To PDF Generation Service
>  def generate_label_png(self,zpl_string=None, png_fn=None):

Rather than print a physical label, produce a `png`... this is most helpful when we get to the UI.

## Data Structures

### Printer Configuration (v2.0.0 Schema, YAML Format)
This is the file which describes the printer fleet. It may be manually edited or edited via the GUI.

```yaml
# zebra-day-config.yaml
schema_version: "2.0.0"

labs:
  default:
    lab_name: Default
    available_locations:
      - Bench A
      - Bench B
    printers:
      "192.168.1.7":
        ip_address: "192.168.1.7"
        printer_name: Main Lab Printer
        lab_location: Bench A
        manufacturer: zebra
        model: ZD620
        serial: "12345"
        label_zpl_styles:
          - tube_2inX1in
          - plate_1inX0.25in
        default_label_style: tube_2inX1in
        print_method: socket
        arp_data: ""
        notes: Primary sample printer
```

**Schema v2.0.0 Changes:**
- `labs` now contains nested `printers` object (not flat printer entries)
- Added `lab_name` and `available_locations` at lab level
- Added `printer_name`, `lab_location`, `manufacturer`, `default_label_style`, `notes` at printer level
- Added `schema_version` at root level

The `lab` key in this example is `default`, which is the lab name assigned when autodetect runs. These names are editable via the GUI. Printers are nested under the `printers` key within each lab.

### Rendering ZPL to PNG (without printing)

To generate a PNG preview of a label without sending to a printer, use the `/api/v1/render` endpoint:

```bash
# Render using a template
curl -X POST "https://localhost:8118/api/v1/render" \
  -H "Content-Type: application/json" \
  -d '{
    "template_name": "tube_2inX1in",
    "uid_barcode": "SAMPLE123",
    "alt_a": "Field A",
    "alt_b": "Field B"
  }' \
  --output label.png

# Render raw ZPL content
curl -X POST "https://localhost:8118/api/v1/render" \
  -H "Content-Type: application/json" \
  -d '{
    "zpl_content": "^XA^FO50,50^ADN,36,20^FDHello World^FS^XZ"
  }' \
  --output label.png
```

The render endpoint returns a PNG image directly. This is useful for:
- Previewing labels before printing
- Generating label images for documentation
- Testing ZPL templates without physical printers

### ZPL Template Files
These are template files for various different label styles. These may be manually edited (but its a nicer expereience using the UI)

* Template files are easiest to design via the UI. The ZPL format is very old school word processor vibes.

```text
^XA
^FO200,20
^BY1
^B3N,N,40,N,N
^FD{uid_barcode}^FS
^FO200,70
^ADN,30,20
^FD{uid_barcode}^FS
^FO460,18
^ADN,24,14
^FD{alt_a}^FS
^FO515,62
^ADN,40,26
^FD{alt_b}^FS
^XZ    
```

* The `{}` format keys match those from above in the zpl string formulation call.
* [ZPL docs](https://labelary.com/zpl.html)
* This ZPL creates this label:<ul>

    <img width="312" alt="zpl_exa" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/9d2b53b3-03d0-4095-9622-64273734ff76">
