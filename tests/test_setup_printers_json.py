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
                                                                                'label_zpl_styles': ['tube_2inX1in'],
                                                                                'print_method': 'generate png',
                                                                                'model': 'na',
                                                                                'serial': 'na',
                                                                                'arp_data': 'na'}}}}


def test_manipulating_printers_json():
    
    from zebra_day import print_mgr as zd
    zd_pm = zd.zpl()
    zd_pm.clear_printers_json()
    
    zd_pm.printers['labs']['test'] = {}

    tmp_json = f"etc/tmp_printers{random.randint(0,1000)}.json"
    
    zd_pm.save_printer_json(tmp_json)

    assert 'test' in zd_pm.printers['labs'].keys()
    assert zd_pm.printers_filename.removesuffix(tmp_json)
    assert os.path.exists(zd_pm.printers_filename)
        
    zd_pm.clear_printers_json(tmp_json)
    assert 'test' not in zd_pm.printers['labs'].keys()
    
    zd_pm.clear_printers_json(tmp_json)
    zd_pm.load_printer_json(tmp_json)
    zd_pm.printers['labs']['test'] = {}
    zd_pm.save_printer_json(tmp_json)

    assert zd_pm.printers['labs']['test'] == {}

    zd_pm.create_new_printers_json_with_single_test_printer()
    
    assert zd_pm.printers == {'labs': {'scan-results': {'Download-Label-png': {'ip_address': 'dl_png',
                                                                               'label_zpl_styles': ['tube_2inX1in'],
                                                                               'print_method': 'generate png',
                                                                               'model': 'na',
                                                                               'serial': 'na',
                                                                               'arp_data': 'na'}}}}


    os.system(f"rm {tmp_json}")
