#!/bin/bash

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
set -eo pipefail # Exit on error, and on pipeline error

TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
MD_OUTPUT_FILE="system_info_report.md"
TXT_OUTPUT_FILE="system_info_detailed_${TIMESTAMP}.txt"
SEPARATOR="========================================"

add_header() {
    local file="$1"
    local title="$2"
    local level="${3:-##}"
    if [[ "$file" == *".md"* ]]; then
        echo -e "\n${level} ${title}\n" >> "$file"
    else
        echo -e "\n${SEPARATOR}\n${title}\n${SEPARATOR}\n" >> "$file"
    fi
}

run_and_append() {
    local file="$1"
    local cmd_to_run_str="$3" # Description ($2) is unused in this version
    bash -o pipefail -c "$cmd_to_run_str" >> "$file"
}

HOSTNAME_INFO=$(hostname)
OS_INFO="Arch Linux" # Hardcoded for Arch Linux
if [ -f /etc/os-release ]; then . /etc/os-release; OS_INFO="${PRETTY_NAME:-$OS_INFO}"; fi
KERNEL_INFO=$(uname -r)
ARCH_INFO=$(uname -m)
UPTIME_INFO=$(uptime -p)

echo "# System Information Report (Arch Linux)\n\nGenerated on: $(date '+%Y-%m-%d %H:%M:%S %Z')\n" > "$MD_OUTPUT_FILE"
echo -e "${SEPARATOR}\nSYSTEM INFORMATION REPORT (Arch Linux)\n${SEPARATOR}\nGenerated on: $(date '+%Y-%m-%d %H:%M:%S %Z')\n" > "$TXT_OUTPUT_FILE"

add_header "$MD_OUTPUT_FILE" "System Overview"
cat << EOF >> "$MD_OUTPUT_FILE"
- **Hostname:** ${HOSTNAME_INFO}
- **Operating System:** ${OS_INFO}
- **Kernel:** ${KERNEL_INFO}
- **Architecture:** ${ARCH_INFO}
- **Uptime:** ${UPTIME_INFO}
EOF
add_header "$TXT_OUTPUT_FILE" "SYSTEM OVERVIEW"
cat << EOF >> "$TXT_OUTPUT_FILE"
Hostname:         ${HOSTNAME_INFO}
Operating System: ${OS_INFO}
Kernel:           ${KERNEL_INFO}
Architecture:     ${ARCH_INFO}
Uptime:           ${UPTIME_INFO}
EOF

add_header "$MD_OUTPUT_FILE" "CPU Information"; run_and_append "$MD_OUTPUT_FILE" "CPU MD" "lscpu | grep -E 'Model name|Architecture|CPU\(s\):|Core\(s\) per socket|Thread\(s\) per core|CPU MHz|Virtualization:' | sed 's/^/- **/' | sed 's/:/:**/'"
add_header "$TXT_OUTPUT_FILE" "CPU INFORMATION"; run_and_append "$TXT_OUTPUT_FILE" "CPU Txt" "lscpu"

add_header "$MD_OUTPUT_FILE" "Memory Information"; echo '```' >> "$MD_OUTPUT_FILE"; run_and_append "$MD_OUTPUT_FILE" "Mem MD" "free -h"; echo '```' >> "$MD_OUTPUT_FILE"
add_header "$TXT_OUTPUT_FILE" "MEMORY INFORMATION"; run_and_append "$TXT_OUTPUT_FILE" "Mem Txt" "free -h"; echo "" >> "$TXT_OUTPUT_FILE"; run_and_append "$TXT_OUTPUT_FILE" "Swap" "swapon --show"

add_header "$MD_OUTPUT_FILE" "Disk Information"; echo '```' >> "$MD_OUTPUT_FILE"; run_and_append "$MD_OUTPUT_FILE" "Disk MD" "lsblk -o NAME,SIZE,TYPE,MOUNTPOINT | grep -v 'loop'"; echo '```' >> "$MD_OUTPUT_FILE"
add_header "$TXT_OUTPUT_FILE" "STORAGE (BLOCKS)"; run_and_append "$TXT_OUTPUT_FILE" "lsblk" "lsblk -o NAME,FSTYPE,SIZE,MOUNTPOINT,LABEL,UUID"
add_header "$TXT_OUTPUT_FILE" "FILESYSTEM USAGE (df)"; run_and_append "$TXT_OUTPUT_FILE" "df" "df -hT -x squashfs -x tmpfs -x devtmpfs"
add_header "$TXT_OUTPUT_FILE" "MOUNTED (findmnt)"; run_and_append "$TXT_OUTPUT_FILE" "findmnt" "findmnt"

add_header "$MD_OUTPUT_FILE" "GPU Information"; echo '```' >> "$MD_OUTPUT_FILE"; run_and_append "$MD_OUTPUT_FILE" "GPU MD" "lspci | grep -i 'VGA compatible controller' || echo 'No VGA device via lspci.'" ; echo '```' >> "$MD_OUTPUT_FILE"
add_header "$TXT_OUTPUT_FILE" "GPU (lspci)"; run_and_append "$TXT_OUTPUT_FILE" "GPU Txt" "lspci -nnk | grep -i -A3 \"VGA\" || echo 'No VGA device details via lspci.'"

add_header "$MD_OUTPUT_FILE" "Hardware Summary (inxi)"
echo '```' >> "$MD_OUTPUT_FILE"; run_and_append "$MD_OUTPUT_FILE" "inxi MD" "inxi -Fxzc0 || echo 'inxi command failed or not found.'" ; echo '```' >> "$MD_OUTPUT_FILE"
add_header "$TXT_OUTPUT_FILE" "HARDWARE (inxi)"
run_and_append "$TXT_OUTPUT_FILE" "inxi Txt" "inxi -Fxxxzc0 || echo 'inxi command failed or not found.'"

add_header "$TXT_OUTPUT_FILE" "NETWORK (PRIVACY-ENHANCED)"
run_and_append "$TXT_OUTPUT_FILE" "Net Interfaces" "ip -br link | awk '{print \$1, \"(\" \$2 \")\"}'"
echo "" >> "$TXT_OUTPUT_FILE"; run_and_append "$TXT_OUTPUT_FILE" "Default Route" "ip route show default"
echo "" >> "$TXT_OUTPUT_FILE"
echo "DNS Configuration (check /etc/resolv.conf manually or network manager settings)" >> "$TXT_OUTPUT_FILE"

add_header "$TXT_OUTPUT_FILE" "PCI DEVICES"; run_and_append "$TXT_OUTPUT_FILE" "lspci" "lspci -tvnn"
add_header "$TXT_OUTPUT_FILE" "USB DEVICES"; run_and_append "$TXT_OUTPUT_FILE" "lsusb" "lsusb -tv"
add_header "$TXT_OUTPUT_FILE" "KERNEL MODULES"; run_and_append "$TXT_OUTPUT_FILE" "lsmod" "lsmod"

add_header "$TXT_OUTPUT_FILE" "INSTALLED PACKAGES (Arch Linux - Explicitly Installed, Top 500)"
echo "Arch Linux (pacman -Qeq, top 500 explicitly installed):" >> "$TXT_OUTPUT_FILE"
run_and_append "$TXT_OUTPUT_FILE" "pacman" "pacman -Qeq | head -n 500"

add_header "$TXT_OUTPUT_FILE" "ENABLED SYSTEMD SERVICES"
run_and_append "$TXT_OUTPUT_FILE" "systemctl" "systemctl list-unit-files --state=enabled"

echo -e "\nReport generation complete.\nMD: $MD_OUTPUT_FILE\nTXT: $TXT_OUTPUT_FILE"
exit 0
