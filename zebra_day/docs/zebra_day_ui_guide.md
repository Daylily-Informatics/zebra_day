# ZDAY UI GUIDE

## ALL PAGES
* everything which can be accomplished via this UI can also be acheived with the library code directly (more so in fact)
  
### Home, 4 Primary Tool Clusters Available

#### _1_ Automated Zebra Printer Discovery & Centralized Management /// _2_ Zebra Printer Status And Activity Reports /// _3_ ZPL Label Template Design + Preview + Deployment of New Styles /// _4_ Manual Print Request Formulation For Any Printer + ZPL Combination Desired

<img width="1016" alt="home" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/8960686a-8444-4b17-8cf2-a27dfe0432eb">

  > the link to change ZDAY style can be found in the lower right of the home page

### Printer Fleet Status Report & Scan For New Printers Tool

<img width="1024" alt="fleetreport" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/3620b38b-88ac-4c22-8c36-76e427d91a27">

### Example of Printer Config JSON 

> ( this is fully user editable (modify the atomatically added entries, delete or add )

<img width="667" alt="editconf" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/0f6b04d7-0d98-491c-815f-ef157c6c5af8">
  > links to clear the current json file, refresh from the default template, or save current edits to become active.

####  List Of All Archived Printer Config JSON Files, 

> these can be restored if desired

<img width="999" alt="bkupconf" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/31970151-2015-40c5-a75e-8f3a694d5a78">

### List Of Available ZPL Template Files

> ( the top list are uneditable defaults, the bottom are user created )

<img width="834" alt="chooseZPL" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/c3a03dd6-2d04-47fc-9aa3-a3dc1c6b4677">

#### View of ZPL Preview/Editor
> ( changes to the ZPL on this page produce a preview PNG of what the printer will print  )
<img width="953" alt="zpl_editing" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/025851d2-813e-43d7-80af-f66a71a45bf4">
  * Drafts can be saved, previewed as PNG, or sent to an available printer

### Form To Send Manual Formulated ZPL Print Jobs To Specific Printers

<img width="895" alt="printmanual" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/9a0d7b4d-a808-4008-bd74-f4a3e8e1b670">

#### Manual Print Request Success (including presenting link which can be used by other systems to print)

<img width="312" alt="zpl_exa" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/62afc4d8-dbec-43f8-817e-a30e620aeb51">

#### Example Of Manually Printed Label Showing Zebra Printer Details

<img width="909" alt="print_success" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/5da259f3-0ed4-4c18-953d-c091690e703c">

<img width="411" alt="zplab" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/024a49b8-b86f-4950-abe4-93eedc62101c">
<hr>
<hr>

## Zebra Printer Web Admin UI
Often, I find these pages valuable in triaging a poorly behaving printer.  I compare a well behaved printer to a problem one and see which settings are not in agreement.

### Main Page (these links are presented in the printer status report towards the top of the ZDAY home)
<img width="430" alt="z1" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/c5f55ef4-1a69-491a-8f58-b733768d2e7b">

### General Setup Page
<img width="586" alt="z2" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/84ecc09f-05b1-4414-a38a-b83ad803f51d">
  * Darkness, Print Speed and Label Top often need editing.

### Media Setup
<img width="445" alt="z3" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/433e426e-7cff-4fcf-962c-2b8a3b80fc66">
  * Media Type Must Be Set For Label Stock
  * Almost always sensor=Web.
  * Width and length should be edited if labels are printing off the label stock (auto calibration is not working in these cases)
  * !! When you save changes to these pages, they are temporarily saved... you must go to the main setting page and apply all saved changes for them to take effect.
  
### Calibration Page
<img width="441" alt="z4" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/7843d86c-1a95-4bcd-b98a-b80ea6b93654">

### Network Settings: Wired
<img width="472" alt="z5" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/01784778-1665-46b5-8089-93db478f300e">
  * Get MAC address here.
  * Set static IP assignment here if needed, else DHCP

### Network Settings: Wireless 
<img width="484" alt="z6" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/a1a55e92-5a29-4d30-89a1-baa0f4b0837f">
  * Generally not a smooth thing to setup.  It is quite hard to fuss with these settings remotely.


## Alternate ZDAY Styles
why not?

### Datchund, Night & Neon
<img width="779" alt="dyldog" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/1d433b45-bbd0-4ea5-95f2-e4a89cf9fa7f">

### Blue TRON
<img width="774" alt="dyltron" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/de87a37b-1d51-4854-a7f6-a1381df8ce89">

### Oakland
<img width="774" alt="oak" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/b854f474-beb8-42bc-8f10-35ea1d1cd88d">

### Petrichor
<img width="776" alt="petrichor" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/a4e52aa8-ba1b-4634-a195-96302d44a1ec">

### Daylily Garish
<img width="778" alt="dylyel" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/651e1e47-aa1f-4f45-ac22-49764a7fda2e">

### Daylily FLWRZ
<img width="778" alt="dylflr" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/a628e721-26a8-44fa-91f9-71765938a8bc">

### Triangles
<img width="778" alt="dyltri" src="https://github.com/Daylily-Informatics/zebra_day/assets/4713659/af52353d-b188-439c-afaa-ae47cca61399">


