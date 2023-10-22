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

FILES_DIR = "etc/label_styles"

class Zserve(object):

    def __init__(self):
        self.zp = zdpm.zpl()


    @cherrypy.expose
    def probe_network_for_zebra_printers(self, ip_stub="192.168.1", scan_wait="0.25"):
        ret_html = f"<h1>Probing {ip_stub} For Zebra Printers</h1><br><a href=printer_status>BACK TO THE NETWORK ZEBRA REPORT</a><ul><hr><ul>"
        try:
            self.detected_printer_ips = {}
        except Exception as e:
            self.detected_printer_ips = {}

        res = os.popen(f"bin/scan_for_networed_zebra_printers_curl.sh {ip_stub} {scan_wait}")
        for i in res.readlines():
            ii = i.rstrip()
            sl = ii.split('|')
            if len(sl) > 1:
                zp = sl[0]
                ip = sl[1]
                model = sl[2]
                serial = sl[3]
                status = sl[4]
                self.detected_printer_ips[ip] = [model, serial, status]
                ret_html = ret_html + f"""
                <li>{zp} ::: <a href={ip} target=new>{ip}</a> ::: {model} ::: {serial} ::: {status}"""

        return ret_html

    @cherrypy.expose
    def clear_printers_json(self):
        self.zp.clear_printers_json()
        return "printers json file has been cleared.<br><a href=/>home</a>"
    
    @cherrypy.expose
    def probe_zebra_printers_add_to_printers_json(self, ip_stub="192.168.1", scan_wait="0.25",lab="scan-results"):

        self.zp.probe_zebra_printers_add_to_printers_json(ip_stub=ip_stub, scan_wait=scan_wait ,lab=lab)

        return "<a href=/>home</a><br><br><br>New Json Object:" + str(self.zp.printers)


    @cherrypy.expose
    def printer_status(self,lab="Daylily-Oakland"):

        if lab not in self.zp.printers['labs']:
            return f"ERROR-- there is no record for this lab, {lab} in the printers.json. Please go <a href=/>home</a> and check the printers.json record to confirm it is valid.  If necessary, you may clear the json and re-build it from a network scan."
        
        printer_deets = {}
        ret_html = f"<h1>Printer Status Summary For {lab}</h1><small><a href=/>BACK HOME</a></small><br><ul><hr>Scan Network For Zebra Printers : <form action=probe_network_for_zebra_printers> Network Stub To Scan : <input type=text name=ip_stub value='192.168.1'> Scan Wait(s)<input type=text name=scan_wait value='0.25'><input type=submit></form><br><ul><table border=1 ><tr><th>Printer Name</th><th>Printer IP</th><th>Label Style</th><th>Status on Network</th></tr>"

        pips = {}
        try:
            pips = self.detected_printer_ips.copy()
        except Exception as e:
            self.detected_printer_ips = {}

            
        for pname in self.zp.printers['labs'][lab]:
            pip = self.zp.printers['labs'][lab][pname]['ip_address']
            if pip in self.detected_printer_ips:
                del(pips[pip])

            printer_deets[pname] = [pip, "...".join(self.zp.printers['labs'][lab][pname]['label_zpl_styles'])]
            print(pname, pip)
            cres = os.popen(f"curl -m 4 {pip}").readlines()
            for ci in cres:
                if len(ci.split('Status:')) > 1:
                    printer_deets[pname].append(ci)

        for pret in printer_deets:
            try:
                pip2 = printer_deets[pret][0]

                pip2a = "" if pip2 not in self.detected_printer_ips else " / ".join(self.detected_printer_ips[pip2])
                ptype = printer_deets[pret][1]
                pconnect = printer_deets[pret][2]
                ret_html = ret_html + f"<tr><td>{pret}<br><small>{pip2a}</small></td><td><a href=http://{pip2} target=pcheck>{pip2}</a><br><small><a target=pl href=_print_label?lab={lab}&printer={pret}&printer_ip={pip2}&label_zpl_style=test_2inX1in  >print-test-label</a></small></td><td>{ptype}</td><td>{pconnect} <small>if state=PAUSED, each printer has a specific pause/unpause button, not one of the menu buttons, which is likely flashiing and needs to be pressed</small></td></tr>"
            except Exception as e:
                print(e)
                ret_html = ret_html + f"<tr><td>{pret}</td><td><a href=http://{pip2} target=pcheck>{pip2}</a></td><td>{ptype}<br></td><td>UNABLE TO CONNECT</td></tr>"

        zaddl = ""
        for zi in pips:
            zaddl = zaddl + f"<li>{zi} :: {pips[zi]}"

        return ret_html + "</table></ul><h3>Detected, But Not Configured, Zebra Printers</h3><small>you must scan the network before this will present info</small><ul>" + zaddl


    @cherrypy.expose
    def index(self):
        
        llinks = "<ul><li> ..."
        try:
            for lb in self.zp.printers['labs'].keys():
                llinks = llinks + f"<li><a href=printer_status?lab={lb} > {lb} Zebra Printer Status </a>"
        except Exception as e:
            llinks = llinks + "<li> no labs found. Try scanning and resetting printers.json"
            
        llinks = llinks + "</ul>"
        
        ret_html = """
        <h1>Daylily Zebra Printer And Print Request Manager</h1><ul><hr><ul>
        <li>Zebra Printer Fleet Status, By Site"""+llinks+"""
        <li><a href=view_pstation_json >VIEW AND EDIT PRINT STATION JSON</a>
        <ul><small> <a href=probe_zebra_printers_add_to_printers_json>... scan network for zebra printers, and add to printers.json</a>    </small>                 </ul>
        <li><a href=send_print_request>Send Print Request</a>
        <li><a href=edit_zpl>EDIT ZPL FILES</a>"""

        return ret_html


    @cherrypy.expose
    def send_print_request(self):
        ret_html = ""

        for lab in sorted(self.zp.printers['labs']):
            ret_html = ret_html + f"<h1>Lab {lab}</h1><br><ul><hr><ul>"
            for printer in sorted(self.zp.printers['labs'][lab]):
                pip = self.zp.printers['labs'][lab][printer]['ip_address']
                plab = self.zp.printers['labs'][lab][printer]['label_zpl_styles']
                ret_html = ret_html + f"<li>{printer} .. {pip}<ul>"
                for plabi in sorted(plab):
                    ret_html = ret_html + f"<li>{plabi} ----- <a href=build_print_request?lab='{lab}'&printer='{printer}'&printer_ip='{pip}'&label_zpl_style='{plabi}'>PRINT THIS TYPE</a>"
                ret_html = ret_html + "</ul><br>"
        return ret_html

    @cherrypy.expose
    def build_print_request(self, lab, printer, printer_ip='', label_zpl_style='',content='', filename=''):


        if label_zpl_style in ['','None', None] and filename not in ['','None',None]:
            label_zpl_style = filename.split('.zpl')[0]
            
        ret_html = f"""
        <h1>Send Label Print Request</h1>
        <ul><hr><ul>
        <h3>{lab} .. {printer} .. {printer_ip} .. {label_zpl_style}</h3><ul><hr><ul>
        """

        ret_html = ret_html + """
        <form action=_print_label>
        <li>UID Barcode Encoded : <input type=text name=uid_barcode ></input><br>
        <li>UID Human Readable (prob want this the same as Barcode Encoded) : <input type=text name=uid_human_readable ></input><br>
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

        return ret_html


    @cherrypy.expose
    def _print_label(self, lab, printer, printer_ip, label_zpl_style, uid_barcode='', uid_human_readable='', alt_a='', alt_b='', alt_c='', alt_d='', alt_e='', alt_f=''):
        ret_s = self.zp.print_zpl(lab=lab ,printer_name=printer, label_zpl_style=label_zpl_style, uid_barcode=uid_barcode,uid_human_readable=uid_human_readable, alt_a=alt_a, alt_b=alt_b, alt_c=alt_c, alt_d=alt_d, alt_e=alt_e, alt_f=alt_f)

        full_url = cherrypy.url() + f"?lab={lab}&printer={printer}&printer_ip={printer_ip}&label_zpl_style={label_zpl_style}&uid_barcode={uid_barcode}&uid_human_readable={uid_human_readable}&alt_a={alt_a}&alt_b={alt_b}&alt_c={alt_c}&alt_d={alt_d}&alt_e={alt_e}&alt_f={alt_f}"

        addl_html = f"<h2>Zday Label Print Request Sent</h2><ul>The URL for this print request(which you can edit and use incurl) is: {full_url}<hr><ul>SUCCESS, LABEL PRINTED"
        if len(ret_s.split('.png')) > 1:
            addl_html = f"<a href=/>home</a><br><br>SUCCESFULLY CREATED PNG<br><img src={ret_s}><br>"
        return addl_html + "<a href=/>home</a>"


    @cherrypy.expose
    def _db_shell(self,ipython=0):
        if ipython in [1,'1']:
            if not self.sfc:
                self.sfc = sftu.connect_to_salesforce(instance=self.sf_domain)
            sfdb = sftd.db(self.sfc)

            from IPython import embed
            embed()


    @cherrypy.expose
    def _restart(self):
        os.system(f"touch bin/zebra_printer_server.py")
        return "restarted"

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
        return f"""
            <html>
            <head><title>JSON File Editor</title></head>
            <body>         <br><a href=/>home</a><br>
                {error_display}
                <form action="save_pstation_json" method="post">
                    <textarea name="json_data" rows="80" cols="50">{json.dumps(data, indent=4)}</textarea><br>
                    <input type="submit" value="Save">
                </form>
        <li>!! <a href=reset_pstation_json>Restore Printer Settings From Default JSON (THIS WILL DELETE YOUR CURRENT FILE!!</a>
        <li>!! <a href=clear_printers_json>CLEAR contents of current printers.json file !!!! This Cannot Be Undone</a>
        </body>
            </html>
            """


    @cherrypy.expose
    def reset_pstation_json(self):
        self.zp.replace_printer_json_from_template()
        return "Done. <a href=/>HOME</a>."


    @cherrypy.expose
    def save_pstation_json(self, json_data):
        try:
            data = json.loads(json_data)
            with open(self.zp.printers_filename, 'w') as f:
                json.dump(data, f, indent=4)
            self.zp.load_printer_json(json_file=self.zp.printers_filename)
            return "JSON saved successfully!<br><br>Print Stations Updated.<br><br><a href=/>HOME</a><br><br><a href=view_pstation_json>open current print station json</a>"
        except json.JSONDecodeError as e:
            return self.view_pstation_json(error_msg=str(e))


    @cherrypy.expose
    def edit_zpl(self):
        files = [f for f in os.listdir(FILES_DIR) if os.path.isfile(os.path.join(FILES_DIR, f))]

        file_links = ['<a href="/edit?filename={}">{}</a>'.format(f, f) for f in files]

        return """<html>
        <body><a href=/>HOME</a><br>
            <h2>Select a file to edit:</h2>
            <ul>
                {}
            </ul>
        </body>
        </html>    """.format("<li>" + "</li><li>".join(file_links) + "</li>")


    @cherrypy.expose
    def xxx(self):
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
    def edit(self, filename=None):
        if not filename:
            return "No file selected"

        filepath = os.path.join(FILES_DIR, filename)

        with open(filepath, 'r') as file:
            content = file.read()

        self.labs_dict = self.zp.printers
        labs = self.labs_dict["labs"].keys()

        ll = ""
        for lab in labs:
            ll += f'<option value="{lab}">{lab}</option>'


        return """<html>
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
            <h2>Editing: """+filename+"""</h2><a href=edit_zpl >BACK TO LABEL LIST</a><br><small><a href=https://labelary.com/zpl.html target=x >ZPL INTRODUCTION</a></small><br>
        <table border=1><tr><td style="vertical-align: top;"  >
        <form method="post" action="/save" id="textForm">
                <select id="labsDropdown" name=lab onchange="populatePrinters()">
                <option value="">Select Lab</option>"""+ll+"""
                </select>                                                                                              \

                <select id="printersDropdown" name=printer>                                                                         \

                    <option value="">Select Printer</option>                                                           \

                </select>
                <textarea name="content" rows="30" cols="50">{}</textarea><br/>
                <input type="hidden" name="filename" value="{}">
                <input type="submit" value="Save Temp File">
                <input type="button" value="Render PNG Of ZPL Label" onclick="submitToPNGrenderer();">
                <input type="button" value="Test Print To Local Zebra" onclick="submitToRealPrint();">                 
            </form><br><small><a href=https://labelary.com/viewer.html target=labels>labely, more advanced, WYSIWYG Label Designer</a></small><br>
        </td><td>
         <div style="border: 1;" id="pngContainer"></div>
        <ul><h3>How To Use This Tool</h3>
        <ul><ul>
        <li>Load existing ZPL format files, make edits and preview the effects by producing a PNG.
        <li>When you wish to save a ZPL format you have worked on here, click 'Save As Temp'.  This will use the original ZPL file name to create a timestamped new file with your changes saved to it.
        <li><a href=edit_zpl >Your New File Appears Here</a>
        <li>To print using this ZPL template to a printer available on your network, <a href=send_print_request >navigate to available printers</a>. When you arrive at the <b>build_print_request</b> form for a specific printer, you are able to enter in any of the format replacement values specified in the ZPL you created. <b>important</b>, new ZPL files are not default available to use for printing.  However, you can override the  label_style_zpl value to select a different ZPL file.  Valid strings for label_style_zpl are the label style zpl file name, minus the .zpl extension, and no path.  So, for 'plate_1inX0.25in.zpl' you would enter 'plate_1inX0.25in' to use this zpl format.  For any non-default ZPL template files which have been created, the same process applies.  Given a draft ZPL file created on this page, ie: 'tube_2inX1in.2023-10-22_05:25:05.004018.zpl', you may use this template by trimming off the .zpl and entering 'tube_2inX1in.2023-10-22_05:25:05.004018'.
        </ul>
        <li>A good way to proceed when designing a new label.  Use the labely tool to generate your ZPL.  Create a zpl template file here with the format wildcards added.  Test using this ZPL, with format substitutions, on the printers you will be using you new template on.

        </ul>

        <h3>ZPL Template Wildcards</h3>
        This tool is a very simple interface to tinker with the overall features of a ZPL label. You may add format wildcards to the ZPL you edit here, but this interface does not execute format replacement of the ZPL previews generated.
        <ul><hr>
        The templates used by this system provide for a set of format wildcards which can be embedded in the ZPL specification file, and values inserted with each new print request.  Not all ZPL formats support all format replacements. The preview pdf generation on this page will not template any values in.  To use a zpl template, and specify format replacement values, <a href=send_print_request >use this interface</a>. <br>The wildcards supported:
        <ul>
        <li>{{uid_barcode}} = This will be encoded as the scannable barcode
        <li>{{uid_human_readable}} = This *should* be the same as 'uid_barcode', in most cases, this value is printed below the 'uid_barcode'. If the scannable barcode does not resolve to this human readable string, please have very good reasons to do this.
        <li>{{alt_a}} = the 'alt_*' wildcards are placehoders for additional information that may be presented beyond the scannable and human readable UID.  These alt_* fields may be used howeever you like with your ZPL templates.
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
        </script>
                <script>
                function submitToRealPrint() {{
                var form = document.getElementById('textForm');
                form.action = '/build_print_request';
                form.submit();
                }}
                </script>
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
        """.format(content, filename)

    @cherrypy.expose
    def png_renderer(self,filename,content,lab='',printer=''):


        png_tmp_f = tempfile.NamedTemporaryFile(suffix='.png', dir='./files', delete=False).name

        self.zp.generate_label_png(content,png_fn=png_tmp_f)

        return png_tmp_f.split('zebra_day')[1]



    @cherrypy.expose
    def save(self, filename, content, lab='',printer=''):
        rec_date = str(datetime.now()).replace(' ','_')
        tfn = filename.replace('.zpl',f'.{rec_date}.zpl')

        temp_filepath = os.path.join(FILES_DIR, tfn)

        with open(temp_filepath, 'w') as file:
            file.write(content)

        return "Changes saved to temp file! <a href='/'>Go back</a>"



if __name__ == '__main__':
    cw_dir = os.path.abspath('.')
    cherrypy.config.update(  {
        'tools.staticdir.on': True,
        'tools.staticdir.dir': cw_dir,
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 8118,
        'server.thread_pool' : 20,
        'server.socket_queue_size': 20,
        'tools.sessions.on': True,
        'tools.sessions.timeout': 199,  # Session timeout in minutes
    })
    cherrypy.quickstart(Zserve(),'/')
