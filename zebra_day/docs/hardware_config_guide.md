## Hardware

### Zebra Printers
* Printers will need to be able to secure an IP address either via a wired connection or via wireless.  The printers will need to be visible to the machine running this package in order to accept print requests. Further, there are tools to scan the local network and identify Zebra Printers. Identified printers are automatically configured for use by `zebra_day`.

  * Network attached printers should be able to run w/out any connection to a PC/laptop. This affors much greater flexibility in placing print stations. In fact, `zebra_day` does not communicate with USB only printers.
* The below zebra printer models have been tested, but any zebra printer able to obtain an IP address and accept `ZPL` should also work.
* _IMPORTANT_, The initial configuration of zebra printers can be a little gnarly. I intend to add some notes on this topic soon. In the mean time, the GUI printer status report includes links to access the web server admin utility each zebra printer exposes.
  * the printer admin UIs all use the default un/pw: `admin/1234`.
    * The first thing I suggest when setting up a new printer is resetting the factory defaults - doable via the zebra printer admin UIs.
  * Wired ethernet connections are advised for greater robustness.  Configure the wired network settings to obtain an IP automatically.  ask your network admins to set DNS rules which will assign the same IP to each printer.  You'll need to supply the printer MAC address to do this, which you can find on via each printers admin UI.
    * __NOTE__ Sometimes these printers can not seem to obtain an IP with DHCP, this could be a router/hub issue, but sometimes you'll need to set the printer to a static IP.  This can be done via the printer admin UI. If the network config is saved with an error, you'll now need to connect to the printer via USB to reset (there might be a button seuquece cycle which can be hit to factory reset...).
    * Wireless setup is _SUPER_ fussy. You'll need to know precisely what bands your router is running on, and the precise auth used. This can be done via the zebra printer admin UI, or when connected via a USB cable to a computer running a driver config program(not advised really).
  * Next, you may have to mess around with calibration settings for label width and length.
  * I have used this driver/config tool on a MAC when I have needed to connect to a printer via `USB`, [Peninsula Zebra Printer Driver](https://www.peninsula-group.com/install-zebra-printer-mac-osx/install-zebra-printer-mac-osx.html). I'm fairly sure there are several windows options.


#### GX420d - wired, no LCD screen

These printers are NOT reccomended b/c the lack of LCD screen makes them a pain to configure.  You will probably need to connect via USB to set good initial settings.  If you have the `zebra_day` UI running, try connecting the printer to the network and powering on, then run the zebra printer network scan.  If the printer is discovered, you're in luck and can admin it via the UI on the printer.

* [Available From Amazon](https://www.amazon.com/gp/product/B07KCQ67Y1/ref=ppx_yo_dt_b_search_asin_title?ie=UTF8&psc=1)
* Cost per printer : `$264.00`
* [manual]()

#### GX420d - wired, with LCD screen
These are solid, but aging out and not as easy to find for sale.

* [Available From Amazon](https://www.amazon.com/gp/product/B011Q95XX2/ref=ppx_yo_dt_b_search_asin_title?ie=UTF8&psc=1)
* Cost per printer : `$425.00`
* [manual]()


#### ZD620d - wired and wireless, with color LCD screen
These are solid, but aging out and not as easy to find for sale.

* [Available From Amazon](https://www.amazon.com/gp/product/B07VHDR33Z/ref=ppx_yo_dt_b_search_asin_title?ie=UTF8&psc=1)
* Cost per printer : `$331.00`
* [manual]()

#### Zebra QLn420 Direct Thermal Printer - Monochrome - Portable 

* [Amazon](https://www.amazon.com/dp/B084P4KBWS?psc=1&ref=ppx_yo2ov_dt_b_product_details)
* Cost per printer : `$136`
* [manual]()

#### Zebra - ZD620d Direct Thermal Desktop Printer with LCD Screen - Print Width 4 in - 203 dpi - Interface: WiFi, Bluetooth, USB, Serial, Ethernet - ZD62142-D01L01EZ

* [Amazon](https://www.amazon.com/dp/B07VHDR33Z?psc=1&ref=ppx_yo2ov_dt_b_product_details)
* Cost per printer : `$331`
* [manual]()


#### Zebra ZD620t Thermal Transfer Desktop Printer 203 dpi Print Width 4 in Ethernet Serial USB ZD62042
<font color=magenta>note, this is a thermal transfer printer & requires ribbons to print</font>
* [Amazon](https://www.amazon.com/dp/B08PW6ZRL6?psc=1&ref=ppx_yo2ov_dt_b_product_details)
* Cost per printer : `$500`
* [manual]()

### Thermal Transfer Ribbons
Also require distinct label stock from the direct thermal transfer printer labels.

* [Amazon](https://www.amazon.com/dp/B07FX3PJ2M?psc=1&ref=ppx_yo2ov_dt_b_product_details)
* Cost per roll: `$7`


# Label Stock
The `zebra_day` code can easily manage a printer fleet comprised of different printing mechanism. 

> Thermal Transfer vs. Direct Thermal Transfer Labels
  * Printers are only capable of printing using one or the other method only.

  > Direct thermal transfer labels require no ribbon, cheaper, can be less robust in some situations, speciality use case label stock mfgs are numerous. 

  > Thermal transfer labels require a ribbon, can be more durable, prone to smudging, more costly
  
### Aegis Labels
For general purpose use. Very inexpensive and easy to source.

#### 2in x 1in - Direct TT
Good for paperwork, some larger tubes.

* [Amazon](https://www.amazon.com/gp/product/B098Z8JYZC/ref=ppx_yo_dt_b_search_asin_title?ie=UTF8&th=1)
* Cost per roll : `$3.21`

#### 2in x 0.5in - Direct TT
Good for smaller tubes, or tubes that already have space taken up by labels.

* [Available On Amazon](https://www.amazon.com/gp/product/B098Z8JYZC/ref=ppx_yo_dt_b_search_asin_title?ie=UTF8&th=1)
* Cost per roll : `$3.25`


### [Labtag](http://www.labtag.com)

#### 2in x 1in / a few colors / cryo - Direct TT

* [LabTag](https://www.labtag.com/shop/product/cryogenic-direct-thermal-labels-2-x-1-dfp-dfpc-28-2/?attribute_pa_core-size=1&attribute_pa_qty-uom=1000&attribute_pa_color=white)
* Cost per roll : `$81`

#### 2in x 0.25in / plate style / cryo - Direct TT

* [LabTag](https://www.labtag.com/shop/product/cryogenic-direct-thermal-labels-2-x-0-25-dfp-227/?attribute_pa_core-size=1&attribute_pa_qty-uom=2000)
* Cost per roll	: `$67`

#### small tube w/dot / cryo - Direct TT

* [LabTag](https://www.labtag.com/shop/product/cryogenic-direct-thermal-labels-1-25-x-0-625-0-375-dfp-103/?attribute_pa_core-size=1&attribute_pa_qty-uom=2000)
* Cost per roll	: `$105`

#### 2in x 1in / cryo / many colors - Thermal Transfer

* [LabTag](https://www.labtag.com/shop/product/cryogenic-barcode-labels-2-x-1-jtta-28/?attribute_pa_core-size=1&attribute_pa_qty-uom=2000&attribute_pa_color=white)
* Cost per roll : `$117`


#### 2in x 0.25in / plate / cryo - Thermal Transfer

* [LabTag](https://www.labtag.com/shop/product/thermal-transfer-cryogenic-labels-for-frozen-vials-surfaces-2-x-0-25-uc-227/?attribute_pa_core-size=1&attribute_pa_qty-uom=2000)
* Cost per roll : `$80`


# Barcode Scanners

## Tera 1d, 2d, QR  scanner. Corded and bluetooth and wireless
Programable and well supported/adopted.

* [Available From Amazon](https://www.amazon.com/dp/B0953FJZDG?psc=1&ref=ppx_yo2ov_dt_b_product_details)
* Cost per scanner : `$63.00`

## Tera Mini 1d 2d QR. Corded and wireless and bluetooth.
_experimenting_... tiny handheld pretty well behaving non-corded scanner.

* [Available From Amazon](https://www.amazon.com/dp/B08NDFWFKJ?psc=1&ref=ppx_yo2ov_dt_b_product_details)
* Cost per Scanner : `$38.00`
