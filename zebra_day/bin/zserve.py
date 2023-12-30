import cherrypy
import os
import sys
import time
from datetime import datetime, timedelta, date
import pytz
import yaml
import json
import tempfile

import zebra_day.print_mgr as zdpm
import zebra_day.cmd_mgr as zdcm

ENVCHECK = os.environ.get(
    "ZDAY", "skip"
)  # If this envvar is set when starring zday, requests to index are ignored unless accomanied by the matching ?envcheck string


class Zserve(object):
    def st(self):
        self.css_file = "static/style.css"

    def __init__(self, relpath, abpath):
        self.rel_p = relpath
        self.abs_p = abpath
        self.zp = zdpm.zpl()
        self.css_file = "static/oakland.css"
        try:
            ipcmd = "(ip addr show | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1' || ifconfig | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1') 2>/dev/null"
            print(ipcmd)
            self.ip = os.popen(ipcmd).readline().rstrip()
            self.ip_root = ".".join(self.ip.split(".")[:-1])
        except Exception as e:
            self.ip = "192.168.1.0"  # FAILS
            self.ip_root = "192.168.1"  # FAILS

    @cherrypy.expose
    def chg_ui_style(self, css_file=None):
        if css_file not in [None]:
            self.css_file = "static/" + css_file
            raise cherrypy.HTTPRedirect("/")

        ret_html = "<h1>Change The Zebra Day UI Style</h1><ul><small><a href=/>home</a></small><br><ul><hr><br><ul>Available Style CSS Files:<br><ul>"
        for i in sorted(os.listdir(self.rel_p + "/static")):
            if i.endswith(".css"):
                ret_html += f"<li><a href=chg_ui_style?css_file={i} >{i}</a>"
        ret_html += "</ul></ul></ul>"

        return self.wrap_content(ret_html)

    @cherrypy.expose
    def printer_details(self, printer_name=None, lab=None):
        
        ret_html = f"""<h1>Printer Information For {printer_name} In Lab {lab}</h1>
        <ul><small><a href=/>HOME</a> ... <a href=printer_status?lab={lab}>printer status report</a></small>
        <hr><ul>
        <ul>
        <h2>Json Stored Data</h2>
        <ul><ul>"""

        for i in sorted(self.zp.printers['labs'][lab][printer_name]):
            ret_html += f"<li>{i} :::: {self.zp.printers['labs'][lab][printer_name][i]}"
            
        ret_html += "</ul></ul><br><h2>Configuration Retrieved From The Zebra Printer</h2><ul><ul>"
        
        ret_html += "<li>".join(zdcm.ZebraPrinter(self.zp.printers['labs'][lab][printer_name]['ip_address']).get_configuration().splitlines())
        ret_html += "</pre></ul>"
        
        return self.wrap_content(ret_html)
    
    @cherrypy.expose
    def probe_network_for_zebra_printers(self, ip_stub=None, scan_wait="0.25"):
        if ip_stub in [None]:
            ip_stub = ".".join(self.ip.split(".")[:-1])
        ret_html = f"<h1>Probing {ip_stub} For Zebra Printers</h1><br><a href=printer_status>BACK TO THE NETWORK ZEBRA REPORT</a><ul><hr><ul>"
        try:
            self.detected_printer_ips = {}
        except Exception as e:
            self.detected_printer_ips = {}

        res = os.popen(
            self.rel_p
            + f"/bin/scan_for_networed_zebra_printers_curl.sh {ip_stub} {scan_wait}"
        )
        for i in res.readlines():
            ii = i.rstrip()
            sl = ii.split("|")
            if len(sl) > 1:
                zp = sl[0]
                ip = sl[1]
                model = sl[2]
                serial = sl[3]
                status = sl[4]
                arp_data = sl[5]
                self.detected_printer_ips[ip] = [model, serial, status, arp_data]
                ret_html = (
                    ret_html
                    + f"""
                <li>{zp} ::: <a href=http://{ip} target=new>{ip}</a> ::: {model} ::: {serial} ::: {status} ::: {arp_data}"""
                )

        self._restart()

        return self.wrap_content(ret_html)

    @cherrypy.expose
    def list_prior_printer_config_files(self):
        ret_html = """
        <h1> Saved Printer Config JSON Files</h1><ul><small><a href=/>home</a></small><br><ul><hr><ul>
        If you wish to restore from one of these files, download the one you'd like, open in a text editor, then copy the contents of the file into <a href=view_pstation_json>the printers json editing form</a> and save a new json file. <br><ul><i><small>note:  the existing file will have a backup created and accessible here</small></i>.<br><br><ul><hr><br>
        <ul>"""

        bkup_d = self.rel_p + "/etc/old_printer_config/"

        for i in sorted(os.listdir(bkup_d)):
            bkup_fn = f"etc/old_printer_config/{i}"
            ret_html = ret_html + f"<li><a href=etc/old_printer_config/{i} >{i}</a>"

        return self.wrap_content(ret_html)

    @cherrypy.expose
    def probe_zebra_printers_add_to_printers_json(
        self, ip_stub="192.168.1", scan_wait="0.25", lab="scan-results"
    ):
        self.zp.probe_zebra_printers_add_to_printers_json(
            ip_stub=ip_stub, scan_wait=scan_wait, lab=lab
        )

        os.system("sleep 2.2")
        raise cherrypy.HTTPRedirect(f"printer_status?lab={lab}")

    @cherrypy.expose
    def printer_status(self, lab="scan-results"):
        if lab not in self.zp.printers["labs"]:
            return f"ERROR-- there is no record for this lab, {lab} in the printers.json. Please go <a href=/>home</a> and check the printers.json record to confirm it is valid.  If necessary, you may clear the json and re-build it from a network scan."

        printer_deets = {}
        ret_html = f"""<h1>Printer Status Summary For {lab}</h1><small><a href=/>BACK HOME</a></small><ul><hr>        <br>        <ul><table border=1 ><tr><th>Printer Name</th><th>Printer IP</th><th>Label Style Available</th><th>Status on Network</th></tr>"""

        pips = {}
        try:
            pips = self.detected_printer_ips.copy()
        except Exception as e:
            self.detected_printer_ips = {}

        for pname in self.zp.printers["labs"][lab]:
            pip = self.zp.printers["labs"][lab][pname]["ip_address"]
            if pip in self.detected_printer_ips:
                del pips[pip]

            serial = self.zp.printers["labs"][lab][pname]["serial"].replace(" ", "_")
            model = self.zp.printers["labs"][lab][pname]["model"]
            lzs_links = "<small>"
            default = " >"
            for lzs in self.zp.printers["labs"][lab][pname]["label_zpl_styles"]:
                lzs_links += f"""<small>{default} <a href=edit_zpl >{lzs}</a> (<a target=pl href="_print_label?lab={lab}&printer={pname}&printer_ip={pip}&label_zpl_style={lzs}&uid_barcode={pip}&alt_a={model}&alt_b={serial}&alt_c={lab}&alt_d={lab}"  >test</a>)<br>"""
                if default in [" >"]:
                    lzs_links += "<br><ul><div style='height: 1px; background-color: pink; width:97%;' class=hrTiny >"
                default = ""
            lzs_links += "</ul></small>"

            printer_deets[pname] = [
                pip,
                lzs_links,
            ]  # "...".join(self.zp.printers['labs'][lab][pname]['label_zpl_styles'])]
            print(pname, pip)
            print(f"curl -m {pip}")
            cres = os.popen(f"curl -m 4 {pip}").readlines()
            for ci in cres:
                if len(ci.split("Status:")) > 1:
                    printer_deets[pname].append(ci)

        ptype = ""
        for pret in printer_deets:
            try:
                pip2 = printer_deets[pret][0]

                pip2a = f"<small>{self.zp.printers['labs'][lab][pret]['model']} <br>{self.zp.printers['labs'][lab][pret]['serial']}</small>"  # "" if pip2 not in self.detected_printer_ips else " / ".join(self.detected_printer_ips[pip2])
                ptype = printer_deets[pret][1]
                pconnect = printer_deets[pret][2]
                serial = self.zp.printers["labs"][lab][pret]["serial"].replace(" ", "_")
                model = self.zp.printers["labs"][lab][pret]["model"]
                arp_data = self.zp.printers["labs"][lab][pret]["arp_data"]
                ret_html = (
                    ret_html
                    + f"<tr><td>{pret}<br><small>{pip2a}</small></td><td><a href=http://{pip2} target=pcheck>{pip2}</a><br><small>{arp_data}</small><br></td><td valign=top ><br>{ptype}</td><td>{pconnect} <small>if state=PAUSED, each printer has a specific pause/unpause button, not one of the menu buttons, which is likely flashing and needs to be pressed</small><small><a target=new href=printer_details?printer_name={pret}&lab={lab} >...printer deets</a></small></td></tr>"
                )
            except Exception as e:
                print(e)
                ret_html = (
                    ret_html
                    + f"<tr><td>{pret}</td><td><a href=http://{pip2} target=pcheck>{pip2}</a></td><td>{ptype}<br></td><td>UNABLE TO CONNECT<br><small><a target=new href=printer_details?printer_name={pret}&lab={lab} >...printer deets</a></small></td></tr>"
                )

        zaddl = ""
        for zi in pips:
            zaddl = zaddl + f"<li>{zi} :: {pips[zi]}"

        ret_html = (
            ret_html
            + f"""</table></ul><ul>
        </ul><br><hr>
        <h2>Build New Printers Config json // Scan Network For Discoverable Printers</h2><ul>this will probe for printers, and with all discovered printers will create a new printers json and over-write the current fleet data for this lab. <form id='myForm'action=probe_zebra_printers_add_to_printers_json >Enter IP Root To Scan: <input type=text value={self.ip_root} name=ip_stub >
        Select (or enter new) lab: 
        {self._get_labs_datalist()}
        <input type=submit></form> <a href=list_prior_printer_config_files>the current printers json will be backed up and can be foud here.</a>                 </ul>
        """
        )

        return self.wrap_content(ret_html)

    def _get_labs_datalist(self):
        dat_list = "<input type=text name=lab list=lab_names><datalist id=lab_names>"
        for ln in sorted(self.zp.printers["labs"].keys()):
            dat_list += f"<option value={ln}>{ln}</option>"
        dat_list += "</datalist>"
        return dat_list

    @cherrypy.expose
    def index(self, envcheck="skip"):
        if envcheck != ENVCHECK:
            # client_ip = cherrypy.request.remote.ip
            os.system("sleep 31")
            return ""

        llinks = ""
        try:
            for lb in self.zp.printers["labs"].keys():
                llinks = (
                    llinks
                    + f"<li><a href=printer_status?lab={lb}  > {lb} Zebra Printer Status </a>"
                )
        except Exception as e:
            llinks = (
                llinks + "<li> no labs found. try scanning and resetting printers.json"
            )

        llinks = llinks + "<li> __end__ </ul>"

        ret_html = (
            """
        <h1>Daylily Zebra Printer And Print Request Manager</h1><ul><small>ip address detected :: """
            + self.ip
            + """</small>
        <hr><ul>
        <hr>
        <h2>Zebra Printer Fleet Status, By Site</h2>
        <ul>detected sites:
        <ul><ul>"""
            + llinks
            + """</ul><br></ul>
        <hr>
        <h2>Print Labels Manually UI</h2>
        <ul>this tool is meant to for infrequent use, the intention of `zebra` is to be used to create more fully featured tools/systems.
        <ul><ul>
        <li><a href=simple_print_request>print labels manually</a>
        </ul></ul></ul>
        <hr><br> 
        
        <h2>Zebra Printer JSON Config</h2>
        <ul>this json file defines the zebra printers available to the package
        <ul><ul>
        <li><a href=view_pstation_json >view and edit json</a>
        <br>
        
        <li><a href=list_prior_printer_config_files>view backed up printers json config files</a>
        <li><a href=build_new_printers_config_json>build a new printers config json</a></ul><br>
        </ul></ul>
        <hr>
        <h2>Send Print Requests</h2>
        <ul>to accessible zebra printers
        <ul><ul><ul>
        <li><a href=bpr >(use me) select lab + printer + label style</a>
        <li><a href=send_print_request >same as above, but only stable label templates</a>
        </ul><br>
        </ul></ul>
        <hr><h2>Edit Label Templates</h2>
        <ul>modify existing templates, create new templates, preview changes & test print new designs
        <ul><ul>
        <li><a href=edit_zpl>edit zpl files</a></ul><br>
        </ul></ul>
        <hr><h2>Github Docs</h2>
        <ul>for this and other daylily repos
        <ul><ul><small>
        <li><a href=https://github.com/Daylily-Informatics/zebra_day >zebra_day</a>
        <li><a href=https://github.com/Daylily-Informatics/fedex_tracking_day >fedex_tracking_day</a>
        <li><a href=https://github.com/Daylily-Informatics/yaml_config_day >yaml_config_day</a>
        </small>
        </ul></ul>
        </ul></ul></ul>
        <div style="position: fixed; border:5px; bottom: 0; right: 0;padding: 8px; text-decoration:none;" ><a href=chg_ui_style style='font-size: 18px;' id="bottomRightLink">change ui style</a></div>
        """
        )

        return self.wrap_content(ret_html)

    @cherrypy.expose
    def build_new_printers_config_json(self):
        ret_html = f"""
        <h2>Scan Network For Zebra Printers</h2><ul><small><a href=/>home</a></small><br><ul>this will probe for printers, and with all discovered printers will create a new printers json and over-write the current fleet data for this lab. <form id='myForm' action=probe_zebra_printers_add_to_printers_json >
Choose Existing, Or Enter New Lab Code:         {self._get_labs_datalist()}        
        Enter IP Root To Scan: <input type=text value={self.ip_root} name=ip_stub > <input type=submit></form> <a href=list_prior_printer_config_files>the current printers json will be backed up and can be foud here.</a>
        """
        return self.wrap_content(ret_html)

    @cherrypy.expose
    def test_spinner(self):
        ret_html = f"""
        <h2>Test Spinner On Submit</h2>
        <a href=/>XXXX</a>
        <form id='myForm' action=x >
 <input type=submit></form> 
        """
        return self.wrap_content(ret_html)

    @cherrypy.expose
    def x(self, s=15):
        os.system(f"sleep {s}")
        return self.wrap_content("<div align=center><a href=/>home</a></div>")

    @cherrypy.expose
    def send_print_request(self):
        ret_html = ""

        for lab in sorted(self.zp.printers["labs"]):
            ret_html = (
                ret_html
                + f"<h1>Lab {lab}</h1><small><a href=/>home</a><br><ul><hr><table width=90% align=center ><tr width=100% ><td width=40%><ul>"
            )
            for printer in sorted(self.zp.printers["labs"][lab]):
                pip = self.zp.printers["labs"][lab][printer]["ip_address"]
                plab = self.zp.printers["labs"][lab][printer]["label_zpl_styles"]
                ret_html = ret_html + f"<li>{printer} .. {pip}<ul>"
                for plabi in sorted(plab):
                    ret_html = (
                        ret_html
                        + f"<li>{plabi} ----- <a href=build_print_request?lab='{lab}'&printer='{printer}'&printer_ip='{pip}'&label_zpl_style='{plabi}'>PRINT THIS TYPE</a>"
                    )
                ret_html = ret_html + "</ul><br>"

        # was going to expose the in development labels styles... maybe latter, as they can be manu
        # for ft in sorted(os.listdir(self.rel_p+'/etc/label_styles/tmps/')):

        ret_html += "</td><td width=40% align=center>"

        ret_html = ret_html + " </td></tr></table>"

        return self.wrap_content(ret_html)

    @cherrypy.expose
    def build_and_send_raw_print_request(
        self,
        lab,
        printer,
        printer_ip="",
        label_zpl_style="",
        content="",
        filename="",
        ftag="",
    ):
        # override zpl_label_style
        client_ip = cherrypy.request.remote.ip

        self.zp.print_zpl(
            lab=lab,
            printer_name=printer,
            label_zpl_style=None,
            zpl_content=content,
            client_ip=client_ip,
        )

    @cherrypy.expose
    def simple_print_request(self):
        
        filename = ""
        ftag = ""
        files = [
            f
            for f in os.listdir(self.rel_p + "/etc/label_styles/")
            if os.path.isfile(os.path.join(self.rel_p + "/etc/label_styles/", f))
        ]
        
        
        # Create options for the select element
        options = ""
        for file in files:
            filename = file.split('.zpl')[0]  # Remove the .zpl suffix
            options += f'<option value="{filename}">{filename}</option>\n'

        # Build the HTML for the select element
        select_html = f'<select name="label_zpl_style" id="label_zpl_style">\n{options}</select>'


        # Fetch the labs and printers data
        labs_and_printers = self.zp.printers['labs']
        labs_options = '\n'.join([f'<option value="{lab}">{lab}</option>' for lab in labs_and_printers.keys()])

        ret_html = f"""
        <h1>Send Label Print Request</h1>
        <ul><small><a href=/>home</a></small><hr><ul>
        <h3> .. .. .. </h3><ul><hr><ul>
        <form action=_print_label>

        <li>UID for Barcode : <input type=text name=uid_barcode ></input><br>
        <li>ALT-A : <input type=text name=alt_a ></input><br>
        <li>ALT-B : <input type=text name=alt_b ></input><br>
        <li>ALT-C : <input type=text name=alt_c ></input><br>
        <li>ALT-D : <input type=text name=alt_d ></input><br>
        <li>ALT-E : <input type=text name=alt_e ></input><br>
        <li>ALT-F : <input type=text name=alt_f ></input><br>
        
        <!-- Other inputs here -->
        <li>Select Lab: 
            <select id="labSelect" name="lab" onchange="updatePrinters()">
                <option value="">Select a Lab</option>
                {labs_options}
            </select><br>
        <li>Select Printer: 
            <select id="printerSelect" name="printer">
                <option value="">Select a Printer</option>
            </select><br>
        Label ZPL Style (be sure it is apporpriate for the label stock): {select_html} <br>
        <input type=submit>
        </form>   
        <script>
            function updatePrinters() {{
                var labSelect = document.getElementById('labSelect');
                var printerSelect = document.getElementById('printerSelect');
                var selectedLab = labSelect.value;
                var printers = {json.dumps({lab: list(printers.keys()) for lab, printers in labs_and_printers.items()})};

                // Clear current printer options
                printerSelect.innerHTML = '<option value="">Select a Printer</option>';

                if (selectedLab in printers) {{
                    printers[selectedLab].forEach(function(printer) {{
                        var option = document.createElement('option');
                        option.value = printer;
                        option.text = printer;
                        printerSelect.appendChild(option);
                    }});
                }}
            }}
        </script>
        """

        return self.wrap_content(ret_html)
    
    @cherrypy.expose
    def build_print_request(
        self,
        lab,
        printer,
        printer_ip="",
        label_zpl_style="",
        content="",
        filename="",
        ftag="",
    ):
        if label_zpl_style in ["", "None", None] and filename not in ["", "None", None]:
            label_zpl_style = filename.split(".zpl")[0]

        ret_html = f"""
        <h1>Send Label Print Request</h1>
        <ul><small><a href=/>home</a></small><hr><ul>
        <h3>{lab} .. {printer} .. {printer_ip} .. {label_zpl_style}</h3><ul><hr><ul>
        """

        ret_html = (
            ret_html
            + """
        <form action=_print_label>
        <li>UID for Barcode : <input type=text name=uid_barcode ></input><br>
        <li>ALT-A : <input type=text name=alt_a ></input><br>
        <li>ALT-B : <input type=text name=alt_b ></input><br>
        <li>ALT-C : <input type=text name=alt_c ></input><br>
        <li>ALT-D : <input type=text name=alt_d ></input><br>
        <li>ALT-E : <input type=text name=alt_e ></input><br>
        <li>ALT-F : <input type=text name=alt_f ></input><br>
        """
        )
        ret_html = (
            ret_html
            + f"""
        Override Lab: <input type=text name=lab value={lab} ><br>
        Override Printer: <input type=text name=printer value={printer} ><br>
        Override IP: <input type=text name=printer_ip value={printer_ip} ><br>
        Over-Ride label_style_zpl: <input type=text name=label_zpl_style value={label_zpl_style} ><br>
        <input type=submit>
        </form>
        """
        )

        return self.wrap_content(ret_html)

    @cherrypy.expose
    def _print_label(
        self,
        lab=None,
        printer='',
        printer_ip="",
        label_zpl_style="",
        uid_barcode="",
        alt_a="",
        alt_b="",
        alt_c="",
        alt_d="",
        alt_e="",
        alt_f="",
        labSelect=""
    ):
        if lab == None:
            lab = labSelect
        
        client_ip = cherrypy.request.remote.ip

        ret_s = self.zp.print_zpl(
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

        full_url = (
            cherrypy.url()
            + f"?lab={lab}&printer={printer}&printer_ip={printer_ip}&label_zpl_style={label_zpl_style}&uid_barcode={uid_barcode}&alt_a={alt_a}&alt_b={alt_b}&alt_c={alt_c}&alt_d={alt_d}&alt_e={alt_e}&alt_f={alt_f}"
        )

        addl_html = f"<h2>Zday Label Print Request Sent</h2><ul>The URL for this print request(which you can edit and use incurl) is: {full_url}<hr><ul>SUCCESS, LABEL PRINTED<br><ul>"
        if len(ret_s.split(".png")) > 1:
            addl_html = f"<a href=/>home</a><br><br>SUCCESFULLY CREATED PNG<br><img src=files/{ret_s.split('/')[-1]}><br>"
        ret_html = addl_html + "<a href=/>home</a>"

        return self.wrap_content(ret_html)

    @cherrypy.expose
    def _restart(self):
        os.system(f"touch {self.rel_p}/bin/zserve.py")
        os.system("sleep 4")
        ret_html = "server restarted"
        return self.wrap_content(ret_html)

    @cherrypy.expose
    def dl_bin_file(self, fn=None):
        # Set the content type and disposition headers for the file
        cherrypy.response.headers["Content-Type"] = "image/png"
        cherrypy.response.headers[
            "Content-Disposition"
        ] = f'attachment; filename="{fn}"'

        # Open and serve the PNG file as a static file
        try:
            with open(fn, "rb") as f:
                return f.read()
        except FileNotFoundError:
            return self.wrap_content("File not found.")

    @cherrypy.expose
    def view_pstation_json(self, error_msg=None):
        with open(self.zp.printers_filename, "r") as f:
            data = json.load(f)
        error_display = f'<p style="color:red;">{error_msg}</p>' if error_msg else ""
        ret_html = f"""
               <br><a href=/>home</a><br>
                {error_display}
                <form action="save_pstation_json" method="post">
                    <textarea name="json_data" rows="45" cols="50">{json.dumps(data, indent=4)}</textarea><br>
                    <input type="submit" value="Save New Printers Config Json & Make Active">
                </form>
        <ul><ul><hr>
        <li><a href=list_prior_printer_config_files>view backed up printers json config files</a>
        <ul><Ul>
        <hr><hr>
        <li>!! <a href=reset_pstation_json>Restore Printer Settings From Default JSON (THIS WILL DELETE YOUR CURRENT FILE!!)</a>
        <ul><ul>
        <hr><hr><hr>
        <li>!! <a href=clear_printers_json>CLEAR contents of current printers.json file !!!! This Cannot Be Undone</a>

            """

        return self.wrap_content(ret_html)

    @cherrypy.expose
    def clear_printers_json(self):
        self.zp.clear_printers_json()
        self._restart()
        os.system("sleep 1.2")
        referrer = cherrypy.request.headers.get("Referer", "/")
        raise cherrypy.HTTPRedirect(referrer)

    @cherrypy.expose
    def reset_pstation_json(self):
        self.zp.replace_printer_json_from_template()
        self._restart()
        os.system("sleep 1.2")
        referrer = cherrypy.request.headers.get("Referer", "/")
        raise cherrypy.HTTPRedirect(referrer)

    @cherrypy.expose
    def save_pstation_json(self, json_data):
        rec_date = str(datetime.now()).replace(" ", "_")
        bkup_pconfig_fn = (
            f"{self.rel_p}/etc/old_printer_config/{rec_date}_printer_config.json"
        )

        try:
            os.system(f"cp {self.zp.printers_filename} {bkup_pconfig_fn}")

            try:
                data = json.loads(json_data)
                with open(self.zp.printers_filename, "w") as f:
                    json.dump(data, f, indent=4)

                self.zp.load_printer_json(
                    json_file=self.zp.printers_filename, relative=False
                )

                os.system("sleep 2")
                self._restart()
                referrer = cherrypy.request.headers.get("Referer", "/")
                raise cherrypy.HTTPRedirect(referrer)

            except json.JSONDecodeError as e:
                return self.wrap_content(
                    "<br><br><br><h2>POSSIBLE ERROR SAVING CONFIG JSON</h2><br><ul><ul>Please <a href=/ > go back to the home page, and then visit this page agian</a> .... *IF* you do not see your edits when coming back from the home page (not refreshing this page), then try clearing the json file using a link below the text box.<br>Further error details:<br<ul>"
                    + self.view_pstation_json(error_msg=str(e))
                )

        except Exception as ee:
            return self.wrap_content(
                "<br><br><br><h2>POSSIBLE ERROR SAVING CONFIG JSON</h2><br><ul><ul>Please <a href=/ > go back to the home page, and then visit this page agian</a> .... *IF* you do not see your edits when coming back from the home page (not refreshing this page), then try clearing the json file the link below the text box.<br>Further error details:<br<ul>"
                + self.view_pstation_json(error_msg=str(ee))
            )

        return self.wrap_content("how did you get here?.")

    @cherrypy.expose
    def edit_zpl(self):
        files = [
            f
            for f in os.listdir(self.rel_p + "/etc/label_styles/")
            if os.path.isfile(os.path.join(self.rel_p + "/etc/label_styles/", f))
        ]

        file_links = ['<a href="/edit?filename={}">{}</a>'.format(f, f) for f in sorted(files)]

        if not os.path.exists(self.rel_p + "/etc/label_styles/tmps/"):
            os.makedirs(self.rel_p + "/etc/label_styles/tmps/")
            
        filest = [
            ft
            for ft in os.listdir(self.rel_p + "/etc/label_styles/tmps/")
            if os.path.isfile(os.path.join(self.rel_p + "/etc/label_styles/tmps/", ft))
        ]

        file_linkst = [
            '<a href="/edit?dtype=tmps&filename={}">{}</a>'.format(ft, ft)
            for ft in sorted(filest)
        ]

        ret_html = """
        <a href=/>home</a><br><ul>
        To specify a template to use (via the programatic API or <a href=send_print_request>this GUI</a>), use the file name string (not including the path prefix) and remove the trailing '.zpl'. <ul><br><br><ul> ie: <b>test_2inX1in</b></ul> <br><ul><hr><ul><br>stable ZPL templates<br>

                {}
            </ul>

        <br><br><hr><br>draft ZPL templates<ul> {} </ul>
        """.format(
            "<li>" + "</li><li>".join(file_links) + "</li>",
            "<li>" + "</li><li>".join(file_linkst) + "</li>",
        )

        return self.wrap_content(ret_html)

    @cherrypy.expose
    def edit(self, filename=None, dtype=""):
        if not filename:
            return self.wrap_content("No file selected")

        filepath = os.path.join(
            self.rel_p + "/etc/label_styles/" + dtype + "/", filename
        )

        with open(filepath, "r") as file:
            content = file.read()

        self.labs_dict = self.zp.printers
        labs = self.labs_dict["labs"].keys()

        ll = ""
        for lab in labs:
            ll += f'<option value="{lab}">{lab}</option>'

        ret_html = (
            """
        <script>
                function populatePrinters() {
                    var lab = document.getElementById("labsDropdown").value;
                    var printersDropdown = document.getElementById("printersDropdown");
                    printersDropdown.innerHTML = "";
                    var labs = """
            + str(self.labs_dict["labs"])
            + """;
                    for (var printer in labs[lab]) {
                        var option = document.createElement("option");
                        option.text = printer;
                        option.value = printer;
                        printersDropdown.add(option);
                    }
                }
            </script>
            </head>
        <body>
            <h2>Editing: """
            + filename
            + """</h2><small><ul><hr><a href=/>home</a> /// <a href=edit_zpl >back to label list</a> /// <a href=https://labelary.com/zpl.html target=x >zpl intro</a></small><br>
        <table border=1><tr><td style="vertical-align: top;"  >
        <form method="post" action="/save" id="textForm">
                <textarea name="content" rows="26" cols="40">{cont}</textarea><br/>
                <input type="hidden" name="filename" value="{fn}">
                <br>TMP File Tag (added to new file name): <input style="width: 100px;" type=text name=ftag value=na >
                <input type="submit" value="save draft">                <input type="button" value="Render PNG" onclick="submitToPNGrenderer();">
                <hr>
            <hr>
            <br><h3>PRINT IRL:</h3>
            <select id="labsDropdown" name=lab onchange="populatePrinters()">
                <option value="">Select Lab</option>{ll}
                </select>
                <select id="printersDropdown" name=printer>
                    <option value="">Select Printer</option>
                </select>

                <input type="button" value="just format keys from ZPL" onclick="submitToRealPrint();">
            <input type="button" value="w/ data inserted to format keys" onclick="submitToLocPrint();">
            </form>
        </td><td>
         <div style="border: 1;" id="pngContainer"></div>
        <ul><h2>How To Use This Tool</h2>
            <div class=hrMed > </div>
        <small><a href=https://labelary.com/viewer.html target=labels>Become Aquainted With ZPL  (public docs and tools)</a></small><ul>
            <h3>Before Labels, Printers</h3>
            <ul>
            <li> Each printer supports a maximum area it can print, and the label stock only presents a specific area (ie: 1inch X 1 inch) which the printer can print on. If you are getting unexpected behavior, like partial or no printed data, check these things. Zebra printers will not error if asked to print outside their range, or off the label stock label size.
            </ul>
            <h3>ZPL Tempate Files</h3>
            <ul>
            <a href=edit_zpl >stable and draft zpl template files can be found here</a>.
            <li>The template filenames follow the pattern (/path/to/file/)(partA_partB.)(zpl)
            <ul>
            <li>zebra_day identifies templates with '(partA_partB)'
            <li>please do not use '_' in tags you specify for template draft file. Otherwise, these can really be any strings you'd like.  I try to follow the pattern partA=general description, partB=dimensions.
            </ul>
            <h4>Stable ZPL Files</h4><ul>
            A set of files in active use. These can not be overwritten.
            </ul>
            <h4>Draft ZPL Files</h4>
            <ul>
            All template files created using this tool. These also can not be overwritten, each save from this tool creates a new template file (all of which can be used for print requests, hence their immutability)
            <br>
            Moving a draft to the stable tempates is done by moving the zpl file to the reside with the other stable zpls (done manually).
            </ul>
            <h3>Create A Template</h3>
            <ul>
            <h4>Manually</h4>
            Draft a zpl file and save to the appropriate place. 
            <h4>From An Existing Template</h4><ul>
            Any stable or draft template can be the starting point for a new draft.  <a href=edit_zpl>Select from among these</a>.
            <ul>
            <li>When you select a template and land on this page, try rendering it to PNG to make sure it behaves as expected. The png renderer prints what edits to this template will look like, the buttons at the bottom use the unedited template.

            </ul>
            <li>From <a href=edit_zpl >the list of stable and draft zpl files</a>, click on one youd like to use as a template.
            <li>On the following screen (this one), you may edit the file in the text area.
            <li>Test your edits by  <b>rendering as a png</b> (which will present the label in this 1/2 of the page). There are two other buttons which work not on the edits to this file, but assuming the original template.  Use one to print the label zpl with the format keys printed as text, use the other to specify values to be used for format keys.
           
            <h5>Format Keys</h5>            
            <ul>
            Each ZPL template file can specify points to allow insertion of variables when creating a specific print requrest. These format keys are denoted by {{}}, and there are 7 supported. You may use the same format key multiple times in a zpl template file. You may also use none of the keys. The keys are: <i>{{uid_barcode}} and {{alt_a}} {{alt_a}} {{alt_c}} {{alt_d}} {{alt_e}} {{alt_f}} </i>.<br>These may be used however you'd like in your template, 'uid_barcode' is named differently as a convenience.
            <li>The PNG rendering tool here will not substite in your data to these formay points. It will print them as if they were just text to print. You can also send these raw requests to be printed by a physical printer (with no data inserted).
            </ul>
            </ul>
            <h3>Save A Template</h3>
            <ul>
            Specify a tag to be inserted to your new tempate file, and save when you are ready. Each save will create a new template file.
            <h3>Elevate A Draft Template To Stable</h3>
            <ul><li>move your draft to a new file which follows the naming conventions to etc/label_styles/.</ul>
            
            <h2>Use A Template</h2>
            <ul>
            <li>Determine the template name from the filename. For /path/to/template_root/partA_partB.zpl, the value for the 'label_zpl_style' would be 'partA_partB' ( via this UI and programatically).
            <h3>UI</h3>
            <ul>
            <li> You can send print requests from <a href=build_print_reques >this UI</a> (which is not intended for routine use, but for design of labels and managing/bebugging printer issues) .. <a href=build_print_request?lab=scan-results&printer=Download-Label-png&printer_ip=dl_png&label_zpl_style=test_2inX1in >this is an example using the tube_2inX1in zpl template to send a print request to the PNG rederer</a>. And this is an example using a draft template <a href=build_print_request?lab=scan-results&printer=Download-Label-png&printer_ip=dl_png&label_zpl_style=tube_2inX1in.exampleDraft.2023-10-29_01:29:56.342244 >tube_2inX1in.exampleDraft.2023-10-29_01:29:56.342244</a>    
            </ul>
            <h3>Progamatically</h3>
            <ul>
            <li>Instantiate a zebra_day print manager

            <br>
            <br>
            <code>
 from zebra_day import print_mgr as zd
</code>
            <br><code>
            zd_pm = zd.zpl()            
            </code>
            <br><br><br>
            
            <li> Determine the label style code as above, and use it in the <b>print_zpl</b> call. For the 2 examples above, this would look like:
<br><Br>
            <li>for the stable template <b>tube_2inX1in</b>
            <br><ul><br>
            <code>
d_pm.print_zpl( lab="scan-results", printer_name="Download-Label-png", uid_barcode="somebarcode", alt_a="additional info", label_zpl_style="tube_2inX1in")
            </code>
</ul><br><br>
            
            <li>for the draft template <b> tube_2inX1in.exampleDraft.2023-10-29_01:29:56.342244</b>
            <br><br>
     <ul>       <code>
zd_pm.print_zpl( lab="scan-results", printer_name="Download-Label-png", uid_barcode="somebarcode", alt_a="additional info", label_zpl_style="tube_2inX1in.exampleDraft.2023-10-29_01:29:56.342244")
            </code></ul></ul>

            </ul></ul>
            <h2>to do</h2>
            <ul>
            ... use the template file names directly.
            </ul>

        </td></tr></table>

        <script>
            function submitToLocPrint() {{
            var form = document.getElementById('textForm');
            form.action = '/build_print_request';
            form.submit();
            }}

            function submitToRealPrint() {{
            var form = document.getElementById('textForm');
            var formData = new FormData(form);
            
            // Create an XMLHttpRequest object
            var xhr = new XMLHttpRequest();
            
            // Set up the request
            xhr.open('POST', '/build_and_send_raw_print_request', true);
            
            // Handle the response (optional, but can be useful for debugging or feedback)
            xhr.onload = function() {{
            if (xhr.status == 200) {{
            console.log('Request was successful. Response:', xhr.responseText);
            }} else {{
            console.log('Request failed. Returned status:', xhr.status);
            }}
            }};
            
            // Send the form data
            xhr.send(formData);
            }}
            </script>
            <script>
        function submitToPNGrenderer() {{
    var form = document.getElementById('textForm');
    var formData = new FormData(form);

    fetch('/png_renderer', {{
        method: 'POST',
        body: formData
    }})
    .then(response => response.text())  // Treat the response as plain text
    .then(pngPath => {{
        const pngImage = document.createElement('img');
        pngImage.src = pngPath;
        const container = document.getElementById('pngContainer');
        container.innerHTML = ''; // Clear previous images if any
        container.appendChild(pngImage);
    }})
    .catch(error => {{
        console.error('Error:', error);
    }});

    event.preventDefault();  // Prevent form from actually submitting and refreshing page
}}

        </script>
        
        """.format(
                cont=content, fn=filename, ll=ll
            )
        )

        # self.wrap_content(ret_html, close_head_section=False, add_spinner=False)
        return self.wrap_content(ret_html)

    @cherrypy.expose
    def bpr(self):
        self.labs_dict = self.zp.printers
        labs = self.labs_dict["labs"].keys()

        ll = ""
        for lab in labs:
            ll += f'<option value="{lab}">{lab}</option>'

        template_sel = "<select name=label_zpl_style ><option value='select one'>select one</option><option value=stable>--stable templates--</option>"

        for zs in sorted(os.listdir(self.rel_p + "/etc/label_styles/")):
            if zs.endswith(".zpl"):
                zs = zs.removesuffix(".zpl")
                template_sel += f"<option value='{zs}'>{zs}</option>"

        template_sel += f"<option value=draft>--draft templates--</option>"

        for zs in sorted(os.listdir(self.rel_p + "/etc/label_styles/tmps/")):
            if zs.endswith(".zpl"):
                zs = zs.removesuffix(".zpl")
                template_sel += f"<option value='{zs}'>{zs}</option>"
        template_sel += f"</select>"

        ret_html = (
            """
        <script>
                function populatePrinters() {
                    var lab = document.getElementById("labsDropdown").value;
                    var printersDropdown = document.getElementById("printersDropdown");
                    printersDropdown.innerHTML = "";
                    var labs = """
            + str(self.labs_dict["labs"])
            + """;
                    for (var printer in labs[lab]) {
                        var option = document.createElement("option");
                        option.text = printer;
                        option.value = printer;
                        printersDropdown.add(option);
                    }
                }
            </script>
            </head>
           <body>
                    <h1>Formulate Print Request, step 1</h1>
                    <ul><small><a href=/>home</a></smal>
                    <h2>Select Lab + Printer + ZPL Template</h2>
                    <ul><hr><br>
                    <p align=center>You will be prompted for the data to print on the next page</p><br><br><ul><br>
                    <form name=bpr_form action=build_print_request align=center >
                    select a lab: <select id="labsDropdown" name=lab onchange="populatePrinters()">
                <option value="">Select Lab</option>"""
            + ll
            + """
                </select>
                
                select a printer: <select id="printersDropdown" name=printer>
                    <option value="">Select Printer</option>
                </select>
                <br>select a template"""
            + template_sel
            + """<br>
                    <input type=submit>
                    </form>
        """
        )

        return self.wrap_content(ret_html, close_head_section=False, add_spinner=False)

    @cherrypy.expose
    def png_renderer(self, filename, content, lab="", printer="", ftag=""):
        png_tmp_f = tempfile.NamedTemporaryFile(
            suffix=".png", dir=self.rel_p + "/files", delete=False
        ).name

        self.zp.generate_label_png(content, png_fn=png_tmp_f)

        return "files/" + png_tmp_f.split("/")[-1]

    @cherrypy.expose
    def save(self, filename, content, lab="", printer="", ftag=""):
        rec_date = str(datetime.now()).replace(" ", "_")

        tfn = filename.replace(".zpl", f".{ftag}.{rec_date}.zpl")

        temp_filepath = os.path.join(self.rel_p + "/etc/label_styles/tmps/", tfn)

        with open(temp_filepath, "w") as file:
            file.write(content)

        ret_html = "Changes saved to temp file! <br>You may either: (<a href=edit_zpl >go back to the zpl file list</a>) -or- (<a href='/'>go home</a>)"

        return self.wrap_content(ret_html)

    def wrap_content(self, content, close_head_section=True, add_spinner=True):
        header = f"""
        <html>
        <head>
        <link rel="stylesheet" href="static/general.css">
        <link rel="stylesheet" href="{self.css_file}">
        """

        if close_head_section:
            header += """
            </head>
            """
            if add_spinner:
                header += """
                <body>
                <div id="spinner" class="spinner-hidden">
                <div class="loader"></div>
                </div>
                """

        footer = """
        <script>
        document.getElementById('myForm').addEventListener('submit', function(event) {
        // When the form is submitted, show the spinner
        document.getElementById('spinner').classList.remove('spinner-hidden');

        // The actual submission will proceed, and the new page will start loading.
        // As the new page loads, the current page (and spinner) will be unloaded.
        });
        </script>
        </body>
        </html>
        """

        return header + content + footer


if __name__ == "__main__":
    rel_path_to_pkg_dir = sys.argv[1]
    cwd_path = os.path.abspath(rel_path_to_pkg_dir)

    # munge the two paths to get a clean prefix to use
    #  disabled, was causing problems
    lng = cwd_path
    srt = rel_path_to_pkg_dir
    if len(lng.split("/")) < len(srt.split("/")):
        raise Exception(
            f" This path is converting to absolute longer than the relative.... problems. {lng} ... {srt}"
        )

    cherrypy.config.update(
        {
            "tools.staticdir.on": True,
            "tools.staticdir.dir": cwd_path,
            "tools.staticdir.index": "index.html",
            "server.socket_host": "0.0.0.0",
            "server.socket_port": 8118,
            "server.thread_pool": 20,
            "server.socket_queue_size": 20,
            "tools.sessions.on": True,
            "tools.sessions.timeout": 199,  # Session timeout in minutes
        }
    )

    cherrypy.quickstart(Zserve(f"{srt}", f"/{cwd_path}"), "/")
