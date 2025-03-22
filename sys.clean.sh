#!/bin/bash

# Function to calculate directory size
calculate_size() {
    local dir="$1"
    if [ -d "$dir" ]; then
        du -sb "$dir" 2>/dev/null | awk '{print $1}'
    else
        echo 0
    fi
}

# Function to delete contents of a directory
delete_contents() {
    local dir="$1"
    if [ -d "$dir" ]; then
        echo "Deleting contents of $dir"
        rm -rf "$dir"/* "$dir"/.[!.]* "$dir"/..?* 2>/dev/null
        echo "Contents of $dir have been deleted."
    else
        echo "Directory $dir does not exist."
    fi
}

# Main cleanup function
cleanup() {
    echo "Starting system cleanup..."
    
    # Directories to clean
    local -a directories=(
        "/tmp"
        "/var/cache"
        "/home/u/.cache/"
        "/home/u/.local/share/Trash"
    )

    local trash_size=0

    # Calculate trash size before cleanup
    trash_size=$(calculate_size "/home/u/.local/share/Trash")

    # Clean directories
    for dir in "${directories[@]}"; do
        delete_contents "$dir"
    done

    # Calculate and display liberated space
    if [ $trash_size -gt 0 ]; then
        local liberated_space_human=$(numfmt --to=iec-i --suffix=B $trash_size)
        echo "Total space liberated from Trash: $liberated_space_human"
    fi
}

# Execute cleanup function
cleanup
