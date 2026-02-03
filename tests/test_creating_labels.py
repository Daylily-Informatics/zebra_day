import os


def test_creating_zpl_from_template():
    from zebra_day import print_mgr as zd

    zd_pm = zd.zpl()
    zd_pm.clear_printers_json()

    zpl = zd_pm.formulate_zpl(
        uid_barcode="TESTBC",
        alt_a="A",
        alt_b="B",
        alt_c="C",
        alt_d="D",
        alt_e="E",
        alt_f="F",
        label_zpl_style="tube_2inX1in",
    )

    x = """^XA\n^FO235,20\n^BY1\n^B3N,N,40,N,N\n^FDTESTBC^FS\n^FO235,70\n^ADN,30,20\n^FDTESTBC^FS\n^FO235,115\n^ADN,25,12\n^FDA^FS\n^FO235,145\n^ADN,25,12\n^FDB^FS\n^FO70,180\n^FO235,170\n^ADN,30,20\n^FDC^FS\n^FO300,180\n^ADN,25,12\n^FDD^FS\n^FO490,180\n^ADN,25,12\n^FDE^FS\n^XZ"""

    assert x == zpl


def test_creating_a_png_of_label_zpl():
    import random

    from zebra_day import print_mgr as zd

    zd_pm = zd.zpl()
    zd_pm.clear_printers_json()
    zpl = zd_pm.formulate_zpl(
        uid_barcode="TESTBC",
        alt_a="A",
        alt_b="B",
        alt_c="C",
        alt_d="D",
        alt_e="E",
        alt_f="F",
        label_zpl_style="tube_2inX1in",
    )
    tmp_png = f"{os.path.dirname(zd.__file__)}/files/test_png_{random.randint(0, 101010)}.png"
    tmp_full_png = zd_pm.generate_label_png(zpl_string=zpl, png_fn=tmp_png, relative=False)

    assert os.path.abspath(tmp_png) == os.path.abspath(tmp_full_png)


def test_printing_label():
    # Test generating a PNG using generate_label_png directly
    # (virtual printer was removed - use render endpoint or generate_label_png)

    from zebra_day import paths as xdg
    from zebra_day import print_mgr as zd

    zd_pm = zd.zpl()

    # Generate ZPL from template
    zpl_string = zd_pm.formulate_zpl(
        uid_barcode="TESTBC",
        alt_a="A",
        alt_b="B",
        alt_c="C",
        alt_d="D",
        alt_e="E",
        alt_f="F",
        label_zpl_style="tube_2inX1in",
    )

    # Generate PNG
    png_path = str(xdg.get_generated_files_dir() / "test_print_label.png")
    result = zd_pm.generate_label_png(zpl_string, png_path, relative=False)

    assert os.path.exists(result)


def test_probing_network_for_printers():
    # Expected to fail, testing if the top level png printer is added

    from zebra_day import print_mgr as zd

    zd_pm = zd.zpl()
    zd_pm.clear_printers_json()
    zd_pm.create_new_printers_json_with_single_test_printer()

    # Set the scan wait to FAR too short.  Good values are like 0.5+
    zd_pm.probe_zebra_printers_add_to_printers_json(
        ip_stub="192.168.1", scan_wait="0.01", lab="unit_test"
    )

    # this just sees if the mechanise work... can't scan the network.
    assert "unit_test" in zd_pm.printers["labs"]
