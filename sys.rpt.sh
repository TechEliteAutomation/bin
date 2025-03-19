#!/bin/bash

# Set the output file path
OUTPUT_FILE="system_info.md"

# Initialize the markdown document
echo "# System Information Report" > "$OUTPUT_FILE"
echo "Generated on: $(date)" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# CPU Information
echo "## CPU Information" >> "$OUTPUT_FILE"
lscpu | grep -E 'Model name|Architecture|CPU MHz|Core(s) per socket|Thread(s) per core' >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# Memory Information
echo "## Memory Information" >> "$OUTPUT_FILE"
free -h | grep -E 'Mem|Swap' >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# Disk Information
echo "## Disk Information" >> "$OUTPUT_FILE"
lsblk -o NAME,SIZE,TYPE,MOUNTPOINT | grep -v 'loop' >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# GPU Information
echo "## GPU Information" >> "$OUTPUT_FILE"
lspci | grep VGA >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# System Information (Overall)
echo "## System Information" >> "$OUTPUT_FILE"
uname -a >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# Detailed Hardware Information (excludes sensitive info)
echo "## Detailed Hardware Information" >> "$OUTPUT_FILE"
inxi -F | grep -Ev 'Serial|UUID|MAC|IP' >> "$OUTPUT_FILE"

# Final message
echo "System information has been saved to $OUTPUT_FILE."

# Print the generated markdown document to the console
cat "$OUTPUT_FILE"


#!/bin/bash

# System Info Retrieval Script
# Collects detailed system information for hardware-specific Arch Linux configuration

OUTPUT_FILE="system_info_$(date +%F_%T).txt"

# Basic System Information
echo "==== SYSTEM INFORMATION ====" > "$OUTPUT_FILE"
echo "Hostname: $(hostname)" >> "$OUTPUT_FILE"
echo "OS: $(cat /etc/os-release | grep '^PRETTY_NAME' | cut -d '=' -f2 | tr -d '"')" >> "$OUTPUT_FILE"
echo "Kernel: $(uname -r)" >> "$OUTPUT_FILE"
echo "Architecture: $(uname -m)" >> "$OUTPUT_FILE"
echo "Uptime: $(uptime -p)" >> "$OUTPUT_FILE"

# CPU Information
echo -e "\n==== CPU INFORMATION ====" >> "$OUTPUT_FILE"
lscpu >> "$OUTPUT_FILE"

# Memory Information
echo -e "\n==== MEMORY INFORMATION ====" >> "$OUTPUT_FILE"
free -h >> "$OUTPUT_FILE"
echo -e "\nSwap:" >> "$OUTPUT_FILE"
swapon --show >> "$OUTPUT_FILE"

# Storage Information
echo -e "\n==== STORAGE INFORMATION ====" >> "$OUTPUT_FILE"
lsblk -o NAME,FSTYPE,SIZE,MOUNTPOINT,LABEL,UUID >> "$OUTPUT_FILE"
echo -e "\nPartition Table:" >> "$OUTPUT_FILE"
fdisk -l >> "$OUTPUT_FILE"

# Filesystem Information
echo -e "\n==== FILESYSTEM INFORMATION ====" >> "$OUTPUT_FILE"
findmnt >> "$OUTPUT_FILE"

# GPU Information
echo -e "\n==== GPU INFORMATION ====" >> "$OUTPUT_FILE"
lspci -nnk | grep -i -A3 "VGA" >> "$OUTPUT_FILE"

# Network Information
echo -e "\n==== NETWORK INFORMATION ====" >> "$OUTPUT_FILE"
ip addr show >> "$OUTPUT_FILE"
echo -e "\nRouting Table:" >> "$OUTPUT_FILE"
ip route show >> "$OUTPUT_FILE"
echo -e "\nDNS Servers:" >> "$OUTPUT_FILE"
cat /etc/resolv.conf >> "$OUTPUT_FILE"

# PCI and USB Devices
echo -e "\n==== PCI DEVICES ====" >> "$OUTPUT_FILE"
lspci >> "$OUTPUT_FILE"
echo -e "\n==== USB DEVICES ====" >> "$OUTPUT_FILE"
lsusb >> "$OUTPUT_FILE"

# Kernel Modules
echo -e "\n==== LOADED KERNEL MODULES ====" >> "$OUTPUT_FILE"
lsmod >> "$OUTPUT_FILE"

# Installed Packages
echo -e "\n==== INSTALLED PACKAGES ====" >> "$OUTPUT_FILE"
pacman -Q >> "$OUTPUT_FILE"

# Services
echo -e "\n==== ENABLED SERVICES ====" >> "$OUTPUT_FILE"
systemctl list-unit-files --state=enabled >> "$OUTPUT_FILE"

# Display Results
echo "System information saved to $OUTPUT_FILE"
