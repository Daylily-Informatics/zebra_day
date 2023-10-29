import os
import random

def test_printers_config_loading():
    
    from zebra_day import print_mgr as zd

    zd_pm = zd.zpl()

    assert 'labs' in zd_pm.printers.keys()


def test_printers_clear_reset():


    from zebra_day import print_mgr as zd

    zd_pm = zd.zpl()

    zd_pm.clear_printers_json()

    assert ('labs' in zd_pm.printers.keys() and len(zd_pm.printers['labs'].keys()) == 0)


    zd_pm.create_new_printers_json_with_single_test_printer()
    assert zd_pm.printers  == {'labs': {'scan-results': {'Download-Label-png': {'ip_address': 'dl_png',
                                                                                'label_zpl_styles': ['test_2inX1in'],
                                                                                'print_method': 'generate png',
                                                                                'model': 'na',
                                                                                'serial': 'na',
                                                                                'arp_data': ''}}}}

    zd_pm.printers['labs']['test'] = {}
    tmp_json = f"etc/tmp_printers{random.randint(0,1000)}.json"
    
    zd_pm.save_printer_json(tmp_json)
    assert 'test' in zd_pm.printers['labs'].keys()
    
    assert zd_pm.printers_filename.removesuffix(tmp_json)
    assert os.path.exists(zd_pm.printers_filename)
    
    print("x",zd_pm.printers_filename)
    
    zd_pm.clear_printers_json(tmp_json)
    assert 'test' not in zd_pm.printers['labs'].keys()
    
    zd_pm.clear_printers_json(tmp_json)
    zd_pm.load_printer_json(tmp_json)
    zd_pm.printers['labs']['test'] = {}
    zd_pm.save_printer_json(tmp_json)


    assert zd_pm.printers['labs']['test'] == {}


    zd_pm.create_new_printers_json_with_single_test_printer()
    

    assert zd_pm.printers == {'labs': {'scan-results': {'Download-Label-png': {'ip_address': 'dl_png',
                                                                               'label_zpl_styles': ['test_2inX1in'],
                                                                               'print_method': 'generate png',
                                                                               'model': 'na',
                                                                               'serial': 'na',
                                                                               'arp_data': ''}}}}


    
    zpl = zd_pm.formulate_zpl(uid_barcode='TESTBC', alt_a='A', alt_b='B', alt_c='C', alt_d='D', alt_e='E', alt_f='F', label_zpl_style='test_2inX1in')
    assert zpl == """^XA\n^FO235,20\n^BY1\n^B3N,N,40,N,N\n^FDTESTBC^FS\n^FO235,70\n^ADN,30,20\n^FDTESTBC^FS\n^FO235,115\n^ADN,25,12\n^FDalt_a^FS\n^FO235,145\n^ADN,25,12\n^FDalt_b^FS\n^FO70,180\n^FO235,170\n^ADN,30,20\n^FDalt_c^FS\n^FO490,180\n^ADN,25,12\n^FDalt_d^FS\n^XZ"""

    tmp_png = f"files/test_png_{random.randint(0,101010)}.png"
    zd_pm.generate_label_png(zpl_string=zpl, png_fn=tmp_png)
    assert os.path.exists(tmp_png)

    zd_pm.clear_printers_json(tmp_json)
    zd_pm.create_new_printers_json_with_single_test_printer()
    tmp_png_2 =  zd_pm.print_zpl(lab="scan-results", printer_name="Download-Label-png", uid_barcode='TESTBC', alt_a='A', alt_b='B', alt_c='C', alt_d='D', alt_e='E', alt_f='F', label_zpl_style="test_2inX1in", client_ip='pkg', print_n=1, zpl_content=None, relative=True)

    assert os.path.exists(tmp_png_2)
    

    probe_zebra_printers_add_to_printers_json(self, ip_stub="192.168.1", scan_wait="0.25",lab="unit_test"):

    # this just sees if the mechanise work... can't scan the network.
    assert 'unit_test' in zd_pm.printers['labs']
