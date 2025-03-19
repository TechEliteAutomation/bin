#!/bin/bash

USB_MOUNT_POINT="/mnt/usb_backup"
LOG_FILE="$HOME/backup.log"
BACKUP_SOURCE="$HOME"
BACKUP_DEST=""
DATE_FORMAT=$(date "+%Y-%m-%d_%H-%M-%S")
CONFIRM=""

# Function to detect and let user select USB
detect_usb() {
    USB_DEVICES=($(lsblk -o NAME,TRAN,MOUNTPOINT | grep 'usb' | awk '{print $1}'))
    if [ ${#USB_DEVICES[@]} -eq 0 ]; then
        echo "No USB drives detected."
        exit 1
    fi
    echo "Available USB devices:"
    for i in "${!USB_DEVICES[@]}"; do
        echo "$((i + 1)). /dev/${USB_DEVICES[$i]}"
    done
    read -p "Select a USB device (enter number): " CHOICE
    if ! [[ "$CHOICE" =~ ^[1-${#USB_DEVICES[@]}]$ ]]; then
        echo "Invalid choice."
        exit 1
    fi
    USB_DEVICE="/dev/${USB_DEVICES[$((CHOICE - 1))]}"
    echo "Selected USB device: $USB_DEVICE"
    if ! mount | grep -q "$USB_MOUNT_POINT"; then
        sudo mkdir -p "$USB_MOUNT_POINT"
        sudo mount "$USB_DEVICE" "$USB_MOUNT_POINT"
        echo "Mounted $USB_DEVICE to $USB_MOUNT_POINT"
    fi
}

# Function to check USB contents and prompt for deletion
check_usb_contents() {
    if [ "$(ls -A "$USB_MOUNT_POINT")" ]; then
        echo "The USB drive contains files:"
        ls -lh "$USB_MOUNT_POINT"
        read -p "Do you want to delete all files before backup? (y/n): " DELETE_CONFIRM
        if [[ "$DELETE_CONFIRM" == "y" || "$DELETE_CONFIRM" == "Y" ]]; then
            sudo rm -rf "$USB_MOUNT_POINT"/*
            echo "USB drive cleared."
        else
            echo "Proceeding without deletion."
        fi
    else
        echo "USB drive is empty."
    fi
}

# Function to perform the backup
backup_files() {
    BACKUP_DEST="$USB_MOUNT_POINT/backup_$DATE_FORMAT"
    mkdir -p "$BACKUP_DEST"

    # Collect non-hidden directories in HOME and .xinitrc
    DIRECTORIES=()
    for DIR in "$BACKUP_SOURCE"/*/; do
        if [ -d "$DIR" ]; then
            DIRECTORIES+=("$(basename "$DIR")")
        fi
    done
    DIRECTORIES+=(".xinitrc")

    # Confirm with the user before proceeding
    echo "The following directories and files will be backed up:"
    for DIR in "${DIRECTORIES[@]}"; do
        echo "- $DIR"
    done
    read -p "Do you want to proceed with the backup? (y/n): " CONFIRM
    if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
        echo "Backup cancelled."
        exit 0
    fi

    echo "Starting backup... (This may take a while)"
    
    # Perform backup with progress indicator
    for DIR in "${DIRECTORIES[@]}"; do
        if [ "$DIR" == ".xinitrc" ]; then
            if [ -f "$BACKUP_SOURCE/.xinitrc" ]; then
                rsync -ah --info=progress2 "$BACKUP_SOURCE/.xinitrc" "$BACKUP_DEST/.xinitrc"
            fi
        else
            rsync -ah --info=progress2 "$BACKUP_SOURCE/$DIR" "$BACKUP_DEST/"
        fi
    done

    echo "Backup completed: $BACKUP_DEST"
}

# Function to log the backup
log_backup() {
    echo "$(date) - Backup completed to $BACKUP_DEST" >> "$LOG_FILE"
}

# Execute backup process
detect_usb
check_usb_contents
backup_files
log_backup
