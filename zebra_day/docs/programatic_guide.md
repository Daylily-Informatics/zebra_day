# Library Usage

## Quickstart

```python
import zebra_day.print_mgr as zdpm

zlab = zdpm.zplo()  ## !!! NOTE (see note below) NOTE !!!
## !!! NOTE !!! due to something I have not yet sorted out with my pypy packaging, instantiating the print_mgr.zpl() class directly does not allow the class to see its package data files.  This hack solves the problem and returns you the same behaving object.


zlab.probe_zebra_printers_add_to_printers_json('192.168.1')  # REPLACE the IP stub with the correct value for your network. This may take a few min to run.  !! This command is not required if you've sucessuflly run the quickstart already, also, won't hurt.

print(zlab.printers)  # This should print out the json dict of all detected zebra printers. An empty dict, {}, is a failure of autodetection, and manual creation of the json file may be needed. If successful, the lab name assigned is 'scan-results', this may be edited latter.
# The json will loook something like this
## {'labs': {'scan-results': {'192.168.1.7': {'ip_address': '192.168.1.7', 'label_zpl_styles': ['test_2inX1in'], 'print_method': 'unk'}}}
##               'lab' name     'printer' name(can be edited latter)                              label_zpl_style

# Assuming a printer was detected, send a test print request.  Using the 'lab', 'printer' and 'label_zpl_style' above (you'd have your own IP/Name, other values should remain the same for now.  There are multiple label ZPL formats available, the test_2inX1in is for quick testing & only formats in the two UID values specified.

zlab.print_zpl(lab='scan-results', printer_name='192.168.1.7', label_zpl_style='test_2inX1in', uid_barcode="123aUID")
# ZPL code sent successfully to the printer!
# Out[13]: '^XA\n^FO235,20\n^BY1\n^B3N,N,40,N,N\n^FD123aUID^FS\n^FO235,70\n^ADN,30,20\n^FD123aUID^FS\n^FO235,115\n^ADN,25,12\n^FDalt_a^FS\n^FO235,145\n^ADN,25,12\n^FDalt_b^FS\n^FO70,180\n^FO235,170\n^ADN,30,20\n^FDalt_c^FS\n^FO490,180\n^ADN,25,12\n^FDalt_d^FS\n^XZ'
```

## Primary Operations

### Init Object
> def zplo():

> __init__(self, debug=0,json_config='zebra_day/etc/printer_config.json'):


  ```python
  import zebra_day.print_mgr as zdpm
  
  zlab = zdpm.zplo()
  ```

  The IP of the machine creating the obj is determined, and the default printer config.json is read.

  * a packaging bug has made a slight hack necessary to get this to work. The expected/normal way to instantiate this object should be `zlab = zdpm.zpl()`, however, this presently does not work.* 

### Load/Save/Clear Printer Config json
>  def save_printer_json(self, json_filename="zebra_day/etc/printer_config.json"):

>  def load_printer_json(self, json_file="zebra_day/etc/printer_config.json"):

>  def clear_printers_json(self, json_file="zebra_day/etc/printer_config.json"):

>  def replace_printer_json_from_template(self):

When clearing or writing a new config.json, the existing one is saved to a backup location. Users can open these and effectively rollback if errors are made. Replace from template means overwriting the active one with the json example file which accompanies the repo.


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

### Printer json
This is the file which describes the printer fleet. It may be manually edited or edited via the GUI.

```json
  {
    "labs": {
        "scan-results": {
            "Download-Label-png": {
                "ip_address": "dl_png",
                "label_zpl_styles": [
                    "test_2inX1in"
                ],
                "print_method": "generate png",
                "model": "na",
                "serial": "na"
              }
          }
      }
   }
```

  `labs` keys to a dict where each key can be a lab or IP block more likely, each termed a `lab` presently. The `lab` key in this example is `scan-results`, 
  this is the lab name assigned from scratch when the autodetect runs the first time. These names are editable via the GUI.
  The dictionary each lab points to have all keys being `printer_names` which then key to the printer specifics we need to know. The example here is the entry for the virtual PNG producing printer. When autodetection runs, detected printers are automatically added to the active printer.json.

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
