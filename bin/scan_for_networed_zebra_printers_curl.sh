#!/bin/bash

# Network range (modify if needed)
network=$1  # "192.168.1"

# Loop through each IP and use curl
for i in {1..254}; do
    ip="$network.$i"
    # Use curl to fetch the page and grep to check for "Zebra"
    if curl -m 4 -s "http://$ip:80" | grep -q "Zebra"; then
	content=$(curl -s "http://$ip:80")                             
	if echo "$content" | grep -q "Zebra"; then
	    model=$(echo """$content""" | perl -ne 'print $1 if /^(.*?)<\/H1>/')
	    combo=$(echo """$content""" | perl -ne 'print $1 if /<TITLE>(.*?)<\/TITLE>/')
	    serial=$(echo """$combo""" | cut -d '-' -f 1)
	    zstatus=$(echo """$combo""" | cut -d '-' -f 2)
	    echo "ZebraPrinter|$ip|$model|$serial|$zstatus"
	fi
    fi
done

