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


ENVCHECK = os.environ.get('ZDAY','skip')  # Start zserve.py like: export ZDAY=somestring && python /bin/zserve.py and the index (for now) will not load unless you send along the same string with the HTTP request using the envcheck variable.  If not detected, set to skip and this is not checked.  NOTE!  This is hugely crude and something much better needs to be done before anything here is exposed routinely in the wild.  A quick improvement coming soon, session level auth and so on.

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
            self.ip_root = ".".join(self.ip.split('.')[:-1])
        except Exception as e:
            self.ip = '192.168.1.0' # FAILS
            self.ip_root = '192.168.1'  # FAILS


    @cherrypy.expose
    def chg_ui_style(self,css_file=None):

        if css_file not in [None]:
            self.css_file = "static/"+css_file
            raise cherrypy.HTTPRedirect("/")

        ret_html = "<h1>Change The Zebra Day UI Style</h1><ul><small><a href=/>home</a></small><br><ul><hr><br><ul>Available Style CSS Files:<br><ul>"
        for i in sorted(os.listdir(self.rel_p+'/static')):
            if i.endswith('.css'):
                ret_html += f"<li><a href=chg_ui_style?css_file={i} >{i}</a>"
        ret_html += "</ul></ul></ul>"

        return self.wrap_content(ret_html)


    @cherrypy.expose
    def probe_network_for_zebra_printers(self, ip_stub=None, scan_wait="0.25"):
        if ip_stub in [None]:
            ip_stub = ".".join(self.ip.split('.')[:-1])
        ret_html = f"<h1>Probing {ip_stub} For Zebra Printers</h1><br><a href=printer_status>BACK TO THE NETWORK ZEBRA REPORT</a><ul><hr><ul>"
        try:
            self.detected_printer_ips = {}
        except Exception as e:
            self.detected_printer_ips = {}

        res = os.popen(self.rel_p+f"/bin/scan_for_networed_zebra_printers_curl.sh {ip_stub} {scan_wait}")
        for i in res.readlines():
            ii = i.rstrip()
            sl = ii.split('|')
            if len(sl) > 1:
                zp = sl[0]
                ip = sl[1]
                model = sl[2]
                serial = sl[3]
                status = sl[4]
                arp_data = sl[5]
                self.detected_printer_ips[ip] = [model, serial, status, arp_data]
                ret_html = ret_html + f"""
                <li>{zp} ::: <a href=http://{ip} target=new>{ip}</a> ::: {model} ::: {serial} ::: {status} ::: {arp_data}"""

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
    def probe_zebra_printers_add_to_printers_json(self, ip_stub="192.168.1", scan_wait="0.25",lab="scan-results"):

        self.zp.probe_zebra_printers_add_to_printers_json(ip_stub=ip_stub, scan_wait=scan_wait ,lab=lab)

        ret_html = "<a href=/>home</a><br><br><br>New Json Object:" + str(self.zp.printers)
        return self.wrap_content(ret_html)


    @cherrypy.expose
    def printer_status(self,lab="scan-results"):

        if lab not in self.zp.printers['labs']:
            return f"ERROR-- there is no record for this lab, {lab} in the printers.json. Please go <a href=/>home</a> and check the printers.json record to confirm it is valid.  If necessary, you may clear the json and re-build it from a network scan."

        printer_deets = {}
        ret_html = f"""<h1>Printer Status Summary For {lab}</h1><small><a href=/>BACK HOME</a></small><ul><hr>        <br>        <ul><table border=1 ><tr><th>Printer Name</th><th>Printer IP</th><th>Label Style Available</th><th>Status on Network</th></tr>"""

        pips = {}
        try:
            pips = self.detected_printer_ips.copy()
        except Exception as e:
            self.detected_printer_ips = {}


        for pname in self.zp.printers['labs'][lab]:
            pip = self.zp.printers['labs'][lab][pname]['ip_address']
            if pip in self.detected_printer_ips:
                del(pips[pip])

            serial = self.zp.printers['labs'][lab][pname]['serial'].replace(' ','_')
            model = self.zp.printers['labs'][lab][pname]['model']
            lzs_links = "<small>"
            default = ' >'
            for lzs in self.zp.printers['labs'][lab][pname]['label_zpl_styles']:
                lzs_links += f"""<small>{default} <a href=edit_zpl >{lzs}</a> (<a target=pl href="_print_label?lab={lab}&printer={pname}&printer_ip={pip}&label_zpl_style={lzs}&uid_barcode={pip}&alt_a={model}&alt_b={serial}&alt_c={lab}&alt_d={lab}"  >test</a>)<br>"""
                if default in [' >']:
                    lzs_links += "<br><ul><div style='height: 1px; background-color: pink; width:97%;' class=hrTiny >"
                default = ""
            lzs_links += "</ul></small>"

            printer_deets[pname] = [pip, lzs_links]  # "...".join(self.zp.printers['labs'][lab][pname]['label_zpl_styles'])]
            print(pname, pip)
            print(f"curl -m {pip}")
            cres = os.popen(f"curl -m 4 {pip}").readlines()
            for ci in cres:
                if len(ci.split('Status:')) > 1:
                    printer_deets[pname].append(ci)

        ptype = ''
        for pret in printer_deets:
            try:
                pip2 = printer_deets[pret][0]

                pip2a = f"<small>{self.zp.printers['labs'][lab][pret]['model']} <br>{self.zp.printers['labs'][lab][pret]['serial']}</small>" # "" if pip2 not in self.detected_printer_ips else " / ".join(self.detected_printer_ips[pip2])
                ptype = printer_deets[pret][1]
                pconnect = printer_deets[pret][2]
                serial = self.zp.printers['labs'][lab][pret]['serial'].replace(' ','_')
                model = self.zp.printers['labs'][lab][pret]['model']
                arp_data = self.zp.printers['labs'][lab][pret]['arp_data']
                ret_html = ret_html + f'<tr><td>{pret}<br><small>{pip2a}</small></td><td><a href=http://{pip2} target=pcheck>{pip2}</a><br><small>{arp_data}</small><br></td><td valign=top ><br>{ptype}</td><td>{pconnect} <small>if state=PAUSED, each printer has a specific pause/unpause button, not one of the menu buttons, which is likely flashing and needs to be pressed</small></td></tr>'
            except Exception as e:
                print(e)
                ret_html = ret_html + f"<tr><td>{pret}</td><td><a href=http://{pip2} target=pcheck>{pip2}</a></td><td>{ptype}<br></td><td>UNABLE TO CONNECT</td></tr>"

        zaddl = ""
        for zi in pips:
            zaddl = zaddl + f"<li>{zi} :: {pips[zi]}"

        ret_html = ret_html + f"""</table></ul><ul>
        </ul><br><hr>
        <h2>Scan Network For Zebra Printers</h2><ul>this will probe for printers, and with all discovered printers will create a new printers json and over-write the current fleet data for this lab. <form id='myForm'action=probe_zebra_printers_add_to_printers_json >Enter IP Root To Scan: <input type=text value={self.ip_root} name=ip_stub > <input type=submit></form> <a href=list_prior_printer_config_files>the current printers json will be backed up and can be foud here.</a>                 </ul>
        """        


        return self.wrap_content(ret_html)


    @cherrypy.expose
    def index(self,envcheck='skip'):
        if envcheck != ENVCHECK:
            #client_ip = cherrypy.request.remote.ip
            os.system('sleep 31')
            return ''

        llinks = ""
        try:
            for lb in self.zp.printers['labs'].keys():
                llinks = llinks + f"<li><a href=printer_status?lab={lb}  > {lb} Zebra Printer Status </a>"
        except Exception as e:
            llinks = llinks + "<li> no labs found. try scanning and resetting printers.json"

        llinks = llinks + "<li> __end__ </ul>"

        ret_html = """
        <h1>Daylily Zebra Printer And Print Request Manager</h1><ul><small>ip address detected :: """+self.ip+"""</small>
        <hr><ul>
        <hr>
        <h2>Zebra Printer Fleet Status, By Site</h2>
        <ul>detected sites:
        <ul><ul>"""+llinks+"""</ul><br></ul>
        <hr>
        <h2>Zebra Printer JSON Config</h2>
        <ul>this json file defines the zebra printers available to the package
        <ul><ul>
        <li><a href=view_pstation_json >view and edit json</a>
        <br>
        
        <li><a href=list_prior_printer_config_files>view backed up printers json config files</a>                 </ul><br>
        </ul></ul>
        <hr>
        <h2>Send Print Requests</h2>
        <ul>to accessible zebra printers
        <ul><ul>
        <li><a href=send_print_request>manually compose & send print request</a>
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

        return self.wrap_content(ret_html)


    @cherrypy.expose
    def send_print_request(self):
        ret_html = ""

        for lab in sorted(self.zp.printers['labs']):
            ret_html = ret_html + f"<h1>Lab {lab}</h1><small><a href=/>home</a><br><ul><hr><table width=90% align=center ><tr width=100% ><td width=40%><ul>"
            for printer in sorted(self.zp.printers['labs'][lab]):
                pip = self.zp.printers['labs'][lab][printer]['ip_address']
                plab = self.zp.printers['labs'][lab][printer]['label_zpl_styles']
                ret_html = ret_html + f"<li>{printer} .. {pip}<ul>"
                for plabi in sorted(plab):
                    ret_html = ret_html + f"<li>{plabi} ----- <a href=build_print_request?lab='{lab}'&printer='{printer}'&printer_ip='{pip}'&label_zpl_style='{plabi}'>PRINT THIS TYPE</a>"
                ret_html = ret_html + "</ul><br>"

        # was going to expose the in development labels styles... maybe latter, as they can be manu
        # for ft in sorted(os.listdir(self.rel_p+'/etc/label_styles/tmps/')):

        ret_html += "</td><td width=40% align=center>"


        ret_html = ret_html + " </td></tr></table>"

        return self.wrap_content(ret_html)


    @cherrypy.expose
    def build_and_send_raw_print_request(self, lab, printer, printer_ip='', label_zpl_style='',content='', filename='',ftag=''):

        # override zpl_label_style
        client_ip = cherrypy.request.remote.ip

        self.zp.print_zpl(lab=lab ,printer_name=printer, label_zpl_style=None, zpl_content=content, client_ip=client_ip)


    @cherrypy.expose
    def build_print_request(self, lab, printer, printer_ip='', label_zpl_style='',content='', filename='',ftag=''):

        if label_zpl_style in ['','None', None] and filename not in ['','None',None]:
            label_zpl_style = filename.split('.zpl')[0]

        ret_html = f"""
        <h1>Send Label Print Request</h1>
        <ul><small><a href=/>home</a></small><hr><ul>
        <h3>{lab} .. {printer} .. {printer_ip} .. {label_zpl_style}</h3><ul><hr><ul>
        """

        ret_html = ret_html + """
        <form action=_print_label>
        <li>UID for Barcode : <input type=text name=uid_barcode ></input><br>
        <li>ALT-A : <input type=text name=alt_a ></input><br>
        <li>ALT-B : <input type=text name=alt_b ></input><br>
        <li>ALT-C : <input type=text name=alt_c ></input><br>
        <li>ALT-D : <input type=text name=alt_d ></input><br>
        <li>ALT-E : <input type=text name=alt_e ></input><br>
        <li>ALT-F : <input type=text name=alt_f ></input><br>
        """
        ret_html = ret_html + f"""
        Override Lab: <input type=text name=lab value={lab} ><br>
        Override Printer: <input type=text name=printer value={printer} ><br>
        Override IP: <input type=text name=printer_ip value={printer_ip} ><br>
        Over-Ride label_style_zpl: <input type=text name=label_zpl_style value={label_zpl_style} ><br>
        <input type=submit>
        </form>
        """

        return self.wrap_content(ret_html)


    @cherrypy.expose
    def _print_label(self, lab, printer, printer_ip='', label_zpl_style='', uid_barcode='', alt_a='', alt_b='', alt_c='', alt_d='', alt_e='', alt_f=''):
        client_ip = cherrypy.request.remote.ip

        ret_s = self.zp.print_zpl(lab=lab ,printer_name=printer, label_zpl_style=label_zpl_style, uid_barcode=uid_barcode, alt_a=alt_a, alt_b=alt_b, alt_c=alt_c, alt_d=alt_d, alt_e=alt_e, alt_f=alt_f, client_ip=client_ip)

        full_url = cherrypy.url() + f"?lab={lab}&printer={printer}&printer_ip={printer_ip}&label_zpl_style={label_zpl_style}&uid_barcode={uid_barcode}&alt_a={alt_a}&alt_b={alt_b}&alt_c={alt_c}&alt_d={alt_d}&alt_e={alt_e}&alt_f={alt_f}"

        addl_html = f"<h2>Zday Label Print Request Sent</h2><ul>The URL for this print request(which you can edit and use incurl) is: {full_url}<hr><ul>SUCCESS, LABEL PRINTED<br><ul>"
        if len(ret_s.split('.png')) > 1:
            addl_html = f"<a href=/>home</a><br><br>SUCCESFULLY CREATED PNG<br><img src=files/{ret_s.split('/')[-1]}><br>"
        ret_html = addl_html + "<a href=/>home</a>"

        return self.wrap_content(ret_html)


    @cherrypy.expose
    def _restart(self):
        os.system(f"touch {self.rel_p}/bin/zserve.py")
        os.system('sleep 4')
        ret_html = 'server restarted'
        return self.wrap_content(ret_html)


    @cherrypy.expose
    def dl_bin_file(self, fn=None):

        # Set the content type and disposition headers for the file
        cherrypy.response.headers['Content-Type'] = 'image/png'
        cherrypy.response.headers['Content-Disposition'] = f'attachment; filename="{fn}"'

        # Open and serve the PNG file as a static file
        try:
            with open(fn, 'rb') as f:
                return f.read()
        except FileNotFoundError:
            return "File not found."


    @cherrypy.expose
    def view_pstation_json(self, error_msg=None):

        with open(self.zp.printers_filename, 'r') as f:
            data = json.load(f)
        error_display = f'<p style="color:red;">{error_msg}</p>' if error_msg else ''
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
        referrer = cherrypy.request.headers.get('Referer', '/')
        raise cherrypy.HTTPRedirect(referrer)

        
        
    @cherrypy.expose
    def reset_pstation_json(self):
        self.zp.replace_printer_json_from_template()
        self._restart()
        referrer = cherrypy.request.headers.get('Referer', '/')
        raise cherrypy.HTTPRedirect(referrer)



    @cherrypy.expose
    def save_pstation_json(self, json_data):
        rec_date = str(datetime.now()).replace(' ','_')
        bkup_pconfig_fn = f"{self.rel_p}/etc/old_printer_config/{rec_date}_printer_config.json"

        os.system(f"cp {self.zp.printers_filename} {bkup_pconfig_fn}")

        try:
            data = json.loads(json_data)
            with open(self.zp.printers_filename, 'w') as f:
                json.dump(data, f, indent=4)
            self.zp.load_printer_json(json_file=self.zp.printers_filename)
            self._restart()
            return "JSON saved successfully!<br><br>Print Stations Updated.<br><br><a href=/>home</a><br><br><a href=view_pstation_json>open current print station json</a>"
        except json.JSONDecodeError as e:
            return self.view_pstation_json(error_msg=str(e))


    @cherrypy.expose
    def edit_zpl(self):

        files = [f for f in os.listdir(self.rel_p+'/etc/label_styles/') if os.path.isfile(os.path.join(self.rel_p+'/etc/label_styles/', f))]

        file_links = ['<a href="/edit?filename={}">{}</a>'.format(f, f) for f in files]

        filest = [ft for ft in os.listdir(self.rel_p+'/etc/label_styles/tmps/') if os.path.isfile(os.path.join(self.rel_p+'/etc/label_styles/tmps/', ft))]

        file_linkst = ['<a href="/edit?dtype=tmps&filename={}">{}</a>'.format(ft, ft) for ft in filest]

        ret_html = """
        <a href=/>home</a><br><ul>
        To specify a template to use (via the programatic API or <a href=send_print_request>this GUI</a>), use the file name string (not including the path prefix) and remove the trailing '.zpl'. <ul><br><br><ul> ie: <b>test_2inX1in</b></ul> <br><ul><hr><ul><br>stable ZPL templates<br>

                {}
            </ul>

        <br><br><hr><br>draft ZPL templates<ul> {} </ul>
        """.format("<li>" + "</li><li>".join(file_links) + "</li>", "<li>" + "</li><li>".join(file_linkst) + "</li>")

        return self.wrap_content(ret_html)


    @cherrypy.expose
    def qqqxxx(self):
        self.labs_dict = self.zp.printers
        labs = self.labs_dict["labs"].keys()

        html = """<html>
        <head>
            <script>
                function populatePrinters() {
                    var lab = document.getElementById("labsDropdown").value;
                    var printersDropdown = document.getElementById("printersDropdown");
                    printersDropdown.innerHTML = "";
                    var labs = """ + str(self.labs_dict["labs"]) + """;
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
            <form>
                <select id="labsDropdown" onchange="populatePrinters()">
                    <option value="">Select Lab</option>"""

        for lab in labs:
            html += f'<option value="{lab}">{lab}</option>'

        html += """
                </select>
                <select id="printersDropdown">
                    <option value="">Select Printer</option>
                </select>
            </form>
        </body>
        </html>"""

        return html


    @cherrypy.expose
    def edit(self, filename=None, dtype=''):
        if not filename:
            return "No file selected"

        filepath = os.path.join(self.rel_p + '/etc/label_styles/' + dtype + '/', filename)

        with open(filepath, 'r') as file:
            content = file.read()

        self.labs_dict = self.zp.printers
        labs = self.labs_dict["labs"].keys()

        ll = ""
        for lab in labs:
            ll += f'<option value="{lab}">{lab}</option>'


        return """<html>
        <head>
        <link rel="stylesheet" href="""+self.css_file+""">
        <script>
                function populatePrinters() {
                    var lab = document.getElementById("labsDropdown").value;
                    var printersDropdown = document.getElementById("printersDropdown");
                    printersDropdown.innerHTML = "";
                    var labs = """ + str(self.labs_dict["labs"]) + """;
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
            <h2>Editing: """+filename+"""</h2><small><ul><hr><a href=/>home</a> /// <a href=edit_zpl >back to label list</a> /// <a href=https://labelary.com/zpl.html target=x >zpl intro</a></small><br>
        <table border=1><tr><td style="vertical-align: top;"  >
        <form method="post" action="/save" id="textForm">
                <textarea name="content" rows="30" cols="40">{cont}</textarea><br/>
                <input type="hidden" name="filename" value="{fn}">
                <br>TMP File Tag (added to new file name): <input style="width: 100px;" type=text name=ftag value=na >
                <input type="submit" value="Save Tmp File">                <input type="button" value="Render PNG" onclick="submitToPNGrenderer();">
                <hr>
               <select id="labsDropdown" name=lab onchange="populatePrinters()">
                <option value="">Select Lab</option>{ll}
                </select>
                <select id="printersDropdown" name=printer>
                    <option value="">Select Printer</option>
                </select>
                <input type="button" value="set lab and printer & print" onclick="submitToRealPrint();">
            </form>
        </td><td>
         <div style="border: 1;" id="pngContainer"></div>
        <ul><h3>How To Use This Tool</h3>
        <small><a href=https://labelary.com/viewer.html target=labels>For More On ZPL (docs and tools)</a></small><ul>
        <ul><li>Load existing ZPL format files, make edits and preview the effects by producing a PNG.
        <li>When you wish to save a ZPL format you have worked on here, click 'Save As Temp'.  This will use the original ZPL file name to create a timestamped new file with your changes saved to it, the new file name will contain the TAG you specify.  <b>THE ORIGINAL FILE IS NOT CHANGED OR DELETED</b>.
        <li><a href=edit_zpl >Your New File Appears Here</a>
        <li>To print using this ZPL template to a printer available on your network, <a href=send_print_request >navigate to available printers</a>. When you arrive at the <b>build_print_request</b> form for a specific printer, you are able to enter in any of the format replacement values specified in the ZPL you created. <b>important</b>, new ZPL files are not default available to use for printing.  However, you can override the  label_style_zpl value to select a different ZPL file.  Valid strings for label_style_zpl are the label style zpl file name, minus the .zpl extension, and no path.  So, for 'plate_1inX0.25in.zpl' you would enter 'plate_1inX0.25in' to use this zpl format.  For any non-default ZPL template files which have been created, the same process applies.  Given a draft ZPL file created on this page, ie: 'tube_2inX1in.2023-10-22_05:25:05.004018.zpl', you may use this template by trimming off the .zpl and entering 'tube_2inX1in.2023-10-22_05:25:05.004018'.
        </ul>
        <li>A good way to proceed when designing a new label.  Use the labely tool to generate your ZPL.  Create a zpl template file here with the format wildcards added.  Test using this ZPL, with format substitutions, on the printers you will be using you new template on.

        <li> <b>When A ZPL File Is Ready For Wider Use...</b> For now, the file needs to be manually moved to a permanent ZPL file name.  A tool to do this will be available everntually.
        </ul>

        <h3>ZPL Template Wildcards</h3>
        This tool is a very simple interface to tinker with the overall features of a ZPL label. You may add format wildcards to the ZPL you edit here, but this interface does not execute format replacement of the ZPL previews generated.
        <ul><hr>
        The templates used by this system provide for a set of format wildcards which can be embedded in the ZPL specification file, and values inserted with each new print request.  Not all ZPL formats support all format replacements. The preview pdf generation on this page will not template any values in.  To use a zpl template, and specify format replacement values, <a href=send_print_request >use this interface</a>. <br>The wildcards supported:
        <ul>
        <li>{{uid_barcode}} = This will be encoded as the scannable barcode and presented in human readable form (at least for all default label templates)
        <li>{{alt_a}} = the 'alt_*' wildcards are placehoders for additional information that may be presented beyond the .  These alt_* fields may be used howeever you like with your ZPL templates.
        <li>{{alt_b}} = <a href=send_print_request >use this interface to test sending wildcards to ZPL templates.</a>
        <li>... through {{alt_f}}
        </ul></ul>
        </td></tr></table>

        <script>
            function submitToLocPrint() {{
                var form = document.getElementById('textForm');                                                                         var formData = new FormData(form);

                fetch('/build_print_request', {{
                method: 'POST',
                body: formData
                }})}}

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
        </body>
        </html>
        """.format(cont=content, fn=filename,ll=ll)

    @cherrypy.expose
    def png_renderer(self,filename,content,lab='',printer='', ftag=''):

        png_tmp_f = tempfile.NamedTemporaryFile(suffix='.png', dir=self.rel_p+'/files', delete=False).name

        self.zp.generate_label_png(content,png_fn=png_tmp_f)

        return "files/" + png_tmp_f.split('/')[-1]



    @cherrypy.expose
    def save(self, filename, content, lab='',printer='', ftag=''):
        rec_date = str(datetime.now()).replace(' ','_')

        tfn = filename.replace('.zpl',f'.{ftag}.{rec_date}.zpl')

        temp_filepath = os.path.join(self.rel_p+'/etc/label_styles/tmps/', tfn)

        with open(temp_filepath, 'w') as file:
            file.write(content)

        ret_html = "Changes saved to temp file! <br>You may either: (<a href=edit_zpl >go back to the zpl file list</a>) -or- (<a href='/'>go home</a>)"

        return self.wrap_content(ret_html)


    def wrap_content(self, content):
        header = f"""
        <html>
        <head>
        <link rel="stylesheet" href="{self.css_file}">
        </head>
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


if __name__ == '__main__':
    rel_path_to_pkg_dir = sys.argv[1]
    cwd_path = os.path.abspath(rel_path_to_pkg_dir)

    # munge the two paths to get a clean prefix to use
    lng = cwd_path.rstrip('/.').lstrip('./')
    srt = rel_path_to_pkg_dir.rstrip('/.').lstrip('./')
    if len(lng.split('/')) < len(srt.split('/')):
        raise Exception( f" This path is converting to absolute longer than the relative.... problems. {lng} ... {srt}")

    cherrypy.config.update(  {
        'tools.staticdir.on': True,
        'tools.staticdir.dir': cwd_path,
        'tools.staticdir.index':'index.html',
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 8118,
        'server.thread_pool' : 20,
        'server.socket_queue_size': 20,
        'tools.sessions.on': True,
        'tools.sessions.timeout': 199,  # Session timeout in minutes
    })

    cherrypy.quickstart(Zserve(f"{srt}", f"/{cwd_path}"),'/')
