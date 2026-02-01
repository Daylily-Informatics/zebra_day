import os
import random

def test_printers_config_loading():
    """Test that printer config loads with v2 schema."""
    from zebra_day import print_mgr as zd
    zd_pm = zd.zpl()
    assert 'labs' in zd_pm.printers.keys()
    assert 'schema_version' in zd_pm.printers.keys()


def test_printers_clear_reset():
    """Test clearing and resetting printer config with v2 schema."""
    from zebra_day import print_mgr as zd
    zd_pm = zd.zpl()
    zd_pm.clear_printers_json()

    assert 'labs' in zd_pm.printers.keys() and len(zd_pm.printers['labs'].keys()) == 0
    assert zd_pm.printers.get('schema_version') == '2.0.0'

    zd_pm.create_new_printers_json_with_single_test_printer()

    # Verify v2 schema structure
    assert 'schema_version' in zd_pm.printers
    assert 'scan-results' in zd_pm.printers['labs']
    lab_data = zd_pm.printers['labs']['scan-results']
    assert 'printers' in lab_data  # v2 schema has nested printers
    assert 'lab_name' in lab_data
    assert 'available_locations' in lab_data

    # Verify printer data
    printer = lab_data['printers']['Download-Label-png']
    assert printer['ip_address'] == 'dl_png'
    assert printer['print_method'] == 'generate png'
    assert 'tube_2inX1in' in printer['label_zpl_styles']


def test_manipulating_printers_json():
    """Test manipulating printer JSON with v2 schema."""
    from zebra_day import print_mgr as zd
    zd_pm = zd.zpl()
    zd_pm.clear_printers_json()

    # Add a test lab with v2 structure
    zd_pm.printers['labs']['test'] = {
        'lab_name': 'Test Lab',
        'available_locations': [],
        'printers': {}
    }

    tmp_json = f"etc/tmp_printers{random.randint(0, 1000)}.json"

    zd_pm.save_printer_json(tmp_json)

    assert 'test' in zd_pm.printers['labs'].keys()
    assert zd_pm.printers_filename.removesuffix(tmp_json)
    assert os.path.exists(zd_pm.printers_filename)

    zd_pm.clear_printers_json(tmp_json)
    assert 'test' not in zd_pm.printers['labs'].keys()

    zd_pm.clear_printers_json(tmp_json)
    zd_pm.load_printer_json(tmp_json)
    zd_pm.printers['labs']['test'] = {
        'lab_name': 'Test Lab',
        'available_locations': [],
        'printers': {}
    }
    zd_pm.save_printer_json(tmp_json)

    assert zd_pm.printers['labs']['test']['printers'] == {}

    zd_pm.create_new_printers_json_with_single_test_printer()

    # Verify v2 schema structure after reset
    assert 'schema_version' in zd_pm.printers
    assert 'scan-results' in zd_pm.printers['labs']
    lab_data = zd_pm.printers['labs']['scan-results']
    assert 'printers' in lab_data
    assert 'Download-Label-png' in lab_data['printers']
    assert lab_data['printers']['Download-Label-png']['ip_address'] == 'dl_png'

    os.system(f"rm {tmp_json}")
