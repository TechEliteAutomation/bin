#!/bin/bash

# Set the output file paths
MD_OUTPUT_FILE="system_info.md"
TXT_OUTPUT_FILE="system_info_$(date +%F_%T).txt"

# Initialize the markdown document
echo "# System Information Report" > "$MD_OUTPUT_FILE"
echo "Generated on: $(date)" >> "$MD_OUTPUT_FILE"
echo "" >> "$MD_OUTPUT_FILE"

# Basic System Information (Markdown)
echo "## System Information" >> "$MD_OUTPUT_FILE"
echo "Hostname: $(hostname)" >> "$MD_OUTPUT_FILE"
echo "OS: $(cat /etc/os-release | grep '^PRETTY_NAME' | cut -d '=' -f2 | tr -d '"')" >> "$MD_OUTPUT_FILE"
echo "Kernel: $(uname -r)" >> "$MD_OUTPUT_FILE"
echo "Architecture: $(uname -m)" >> "$MD_OUTPUT_FILE"
echo "Uptime: $(uptime -p)" >> "$MD_OUTPUT_FILE"
echo "" >> "$MD_OUTPUT_FILE"

# CPU Information (Markdown)
echo "## CPU Information" >> "$MD_OUTPUT_FILE"
lscpu | grep -E 'Model name|Architecture|CPU MHz|Core(s) per socket|Thread(s) per core' >> "$MD_OUTPUT_FILE"
echo "" >> "$MD_OUTPUT_FILE"

# Memory Information (Markdown)
echo "## Memory Information" >> "$MD_OUTPUT_FILE"
free -h | grep -E 'Mem|Swap' >> "$MD_OUTPUT_FILE"
echo "" >> "$MD_OUTPUT_FILE"

# Disk Information (Markdown)
echo "## Disk Information" >> "$MD_OUTPUT_FILE"
lsblk -o NAME,SIZE,TYPE,MOUNTPOINT | grep -v 'loop' >> "$MD_OUTPUT_FILE"
echo "" >> "$MD_OUTPUT_FILE"

# GPU Information (Markdown)
echo "## GPU Information" >> "$MD_OUTPUT_FILE"
lspci | grep VGA >> "$MD_OUTPUT_FILE"
echo "" >> "$MD_OUTPUT_FILE"

# Detailed Hardware Information (Markdown)
echo "## Detailed Hardware Information" >> "$MD_OUTPUT_FILE"
inxi -F | grep -Ev 'Serial|UUID|MAC|IP' >> "$MD_OUTPUT_FILE"
echo "" >> "$MD_OUTPUT_FILE"

# Save text report (TXT)
echo "==== SYSTEM INFORMATION ====" > "$TXT_OUTPUT_FILE"
echo "Hostname: $(hostname)" >> "$TXT_OUTPUT_FILE"
echo "OS: $(cat /etc/os-release | grep '^PRETTY_NAME' | cut -d '=' -f2 | tr -d '"')" >> "$TXT_OUTPUT_FILE"
echo "Kernel: $(uname -r)" >> "$TXT_OUTPUT_FILE"
echo "Architecture: $(uname -m)" >> "$TXT_OUTPUT_FILE"
echo "Uptime: $(uptime -p)" >> "$TXT_OUTPUT_FILE"

# CPU Information (TXT)
echo -e "\n==== CPU INFORMATION ====" >> "$TXT_OUTPUT_FILE"
lscpu >> "$TXT_OUTPUT_FILE"

# Memory Information (TXT)
echo -e "\n==== MEMORY INFORMATION ====" >> "$TXT_OUTPUT_FILE"
free -h >> "$TXT_OUTPUT_FILE"
echo -e "\nSwap:" >> "$TXT_OUTPUT_FILE"
swapon --show >> "$TXT_OUTPUT_FILE"

# Storage Information (TXT)
echo -e "\n==== STORAGE INFORMATION ====" >> "$TXT_OUTPUT_FILE"
lsblk -o NAME,FSTYPE,SIZE,MOUNTPOINT,LABEL,UUID >> "$TXT_OUTPUT_FILE"
echo -e "\nPartition Table:" >> "$TXT_OUTPUT_FILE"
fdisk -l >> "$TXT_OUTPUT_FILE"

# Filesystem Information (TXT)
echo -e "\n==== FILESYSTEM INFORMATION ====" >> "$TXT_OUTPUT_FILE"
findmnt >> "$TXT_OUTPUT_FILE"

# GPU Information (TXT)
echo -e "\n==== GPU INFORMATION ====" >> "$TXT_OUTPUT_FILE"
lspci -nnk | grep -i -A3 "VGA" >> "$TXT_OUTPUT_FILE"

# Network Information (TXT)
echo -e "\n==== NETWORK INFORMATION ====" >> "$TXT_OUTPUT_FILE"
ip addr show >> "$TXT_OUTPUT_FILE"
echo -e "\nRouting Table:" >> "$TXT_OUTPUT_FILE"
ip route show >> "$TXT_OUTPUT_FILE"
echo -e "\nDNS Servers:" >> "$TXT_OUTPUT_FILE"
cat /etc/resolv.conf >> "$TXT_OUTPUT_FILE"

# PCI and USB Devices (TXT)
echo -e "\n==== PCI DEVICES ====" >> "$TXT_OUTPUT_FILE"
lspci >> "$TXT_OUTPUT_FILE"
echo -e "\n==== USB DEVICES ====" >> "$TXT_OUTPUT_FILE"
lsusb >> "$TXT_OUTPUT_FILE"

# Kernel Modules (TXT)
echo -e "\n==== LOADED KERNEL MODULES ====" >> "$TXT_OUTPUT_FILE"
lsmod >> "$TXT_OUTPUT_FILE"

# Installed Packages (TXT)
echo -e "\n==== INSTALLED PACKAGES ====" >> "$TXT_OUTPUT_FILE"
pacman -Q >> "$TXT_OUTPUT_FILE"

# Services (TXT)
echo -e "\n==== ENABLED SERVICES ====" >> "$TXT_OUTPUT_FILE"
systemctl list-unit-files --state=enabled >> "$TXT_OUTPUT_FILE"

# Final Message
echo "System information has been saved to $MD_OUTPUT_FILE and $TXT_OUTPUT_FILE."

# Display Results
cat "$MD_OUTPUT_FILE"
cat "$TXT_OUTPUT_FILE"
