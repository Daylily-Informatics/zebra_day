#!/bin/bash

# Network range (modify if needed)
network=$1  # "192.168.1"
scan_wait=0.4
if [[ "$2" == "" ]]; then
    scan_wait=0.4
else
    scan_wait=$2
fi


# Loop through each IP and use curl
for i in {1..254}; do
    ip="$network.$i"
    # Use curl to fetch the page and grep to check for "Zebra"
    echo $ip
    if curl -m $scan_wait -s "http://$ip:80" | grep -q "Zebra"; then
	content=$(curl -m 4 -s "http://$ip:80")                             
	if echo "$content" | grep -q "Zebra"; then
	    model=$(echo """$content""" | perl -ne 'print $1 if /^(.*?)<\/H1>/')
	    combo=$(echo """$content""" | perl -ne 'print $1 if /<TITLE>(.*?)<\/TITLE>/')
	    serial=$(echo """$combo""" | cut -d '-' -f 1)
	    zstatus=$(echo """$combo""" | cut -d '-' -f 2)
	    arp_resp=$(arp -n $ip)
	    echo "ZebraPrinter|$ip|$model|$serial|$zstatus|$arp_resp"
	fi
    fi
done

