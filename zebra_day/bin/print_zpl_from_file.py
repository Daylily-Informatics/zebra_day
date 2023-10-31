import sys
import zebra_day.print_mgr as zdpm

ip = sys.argv[1]

zpl_file = sys.argv[2]

zpld = zdpm.zpl()

zpl_string = ""

fh = open(zpl_file, 'r')
for i in fh:
    zpl_string += i.rstrip()


print(zpl_string)

zpld.print_raw_zpl(zpl_string , ip)

print('done!')
