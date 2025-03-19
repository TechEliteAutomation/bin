#!/bin/bash

# Update function
update() {
    echo "Starting system update..."
    
    # Update system packages
    echo "Updating system packages..."
    if ! sudo pacman -Syu; then
        echo "Error updating system packages"
        return 1
    fi

    # Update AUR packages
    echo "Updating AUR packages..."
    if ! yay -Syu; then
        echo "Error updating AUR packages"
        return 1
    fi

    echo "System update completed successfully"
    return 0
}

# Execute update function
update
