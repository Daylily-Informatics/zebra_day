import subprocess
import re
import sys

ip_root = sys.argv[1]  # ie: 192.168.1.1

# Command
command = ["nmap", "-p", "80", "-sV", "-T4", "--max-retries", "0", "--host-timeout", "21s", "-A", f"{ip_root}/24"]
output = subprocess.check_output(command).decode("utf-8")

# Parse the output
lines = output.split('\n')
zebra_ips = []

for i, line in enumerate(lines):
    if 'Nmap scan report for' in line:
        current_ip = re.search(r'for (\d+\.\d+\.\d+\.\d+)', line).group(1)
    if 'Zebra' in line:
        zebra_ips.append(current_ip)

# Print the results
for ip in zebra_ips:
    print(ip)
