import cherrypy
import os
import sys
import time
from datetime import datetime, timedelta, date
import pytz
import yaml
import json

import zebra_day.print_mgr as zdpm


class Zserve(object):

    def __init__(self):
        self.zp = zdpm.zpl()


    @cherrypy.expose
    def printer_status(self,lab="Daylily-Oakland"):
        printer_deets = {}
        ret_html = f"<h1>Printer Status Summary For {lab}</h1><small><a href=/>BACK HOME</a></small><br><ul><table border=1 ><tr><th>Printer Name</th><th>Printer IP</th><th>Label Style</th><th>Status on Network</th></tr>"


        for pname in self.zp.printers['labs'][lab]:
            pip = self.zp.printers['labs'][lab][pname]['ip_address']
            printer_deets[pname] = [pip, "...".join(self.zp.printers['labs'][lab][pname]['label_zpl_styles'])]
            print(pname, pip)
            cres = os.popen(f"curl -m 4 {pip}").readlines()
            for ci in cres:
                if len(ci.split('Status:')) > 1:
                    printer_deets[pname].append(ci)

        for pret in printer_deets:
            try:
                pip2 = printer_deets[pret][0]
                ptype = printer_deets[pret][1]
                pconnect = printer_deets[pret][2]
                ret_html = ret_html + f"<tr><td>{pret}</td><td><a href=http://{pip2} target=pcheck>{pip2}</a></td><td>{ptype}</td><td>{pconnect} <small>if state=PAUSED, each printer has a specific pause/unpause button, not one of the menu buttons, which is likely flashiing and needs to be pressed</small></td></tr>"
            except Exception as e:
                print(e)
                ret_html = ret_html + f"<tr><td>{pret}</td><td><a href=http://{pip2} target=pcheck>{pip2}</a></td><td>{ptype}</td><td>UNABLE TO CONNECT</td></tr>"

        return ret_html + "</table>"


    @cherrypy.expose
    def index(self):
        ret_html = """
        <h1>Daylily Zebra Printer And Print Request Manager</h1><ul><hr><ul>
        <li><a target=new href=printer_status>Printer Fleet Report</a>
        <li><a href=view_pstation_json >VIEW AND EDIT PRINT STATION JSON</a>
        <li><a href=send_print_request>Send Print Request</a>"""

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
    def build_print_request(self, lab, printer, printer_ip, label_zpl_style):
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
        <input type=hidden name=lab value={lab} >
        <input type=hidden name=printer value={printer} >                                          
        <input type=hidden name=printer_ip value={printer_ip} >
        <input type=hidden name=label_zpl_style value={label_zpl_style} >
        <input type=submit>
        </form>
        """

        return ret_html


    @cherrypy.expose
    def _print_label(self, lab, printer, printer_ip, label_zpl_style,uid_barcode, uid_human_readable, alt_a, alt_b, alt_c, alt_d, alt_e, alt_f):
        ret_s = self.zp.print_zpl(lab=lab ,printer_name=printer, label_zpl_style=label_zpl_style, uid_barcode=uid_barcode,uid_human_readable=uid_human_readable, alt_a=alt_a, alt_b=alt_b, alt_c=alt_c, alt_d=alt_d, alt_e=alt_e, alt_f=alt_f)

        addl_html = "SUCCESS, LABEL PRINTED"
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
        <a href=reset_pstation_json>Restore Printer Settings From Default JSON (THIS WILL DELETE YOUR CURRENT FILE!!</a>
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
