#!/bin/bash
#
# arch-update.sh
#
# A script to manage Arch Linux system and AUR package updates.
# Part of arch-utils
# Project Directory: arch-utils

# Exit immediately if a command exits with a non-zero status.
set -e
# Treat unset variables as an error when substituting.
set -u
# Pipestatus: the return value of a pipeline is the status of the last command to exit with a non-zero status,
# or zero if no command exited with a non-zero status.
set -o pipefail

# --- Configuration ---
# Set to true to enable non-interactive mode for package managers (e.g., --noconfirm)
# Set to false to allow interactive confirmations. (Default: false)
NON_INTERACTIVE_UPDATES=false

# --- Helper Functions ---
log_message() {
    echo "[INFO] $(date +'%Y-%m-%d %H:%M:%S'): $1"
}

log_warning() {
    echo "[WARN] $(date +'%Y-%m-%d %H:%M:%S'): $1" >&2
}

log_error() {
    echo "[ERROR] $(date +'%Y-%m-%d %H:%M:%S'): $1" >&2
}

_ensure_sudo_available() {
    if ! sudo -n true 2>/dev/null; then
        log_message "Sudo requires a password. Please enter it when prompted."
    fi
}

# --- Update Module ---
perform_system_update() {
    log_message "Starting system package update (pacman)..."
    _ensure_sudo_available
    local pacman_args=("-Syu")
    if [ "$NON_INTERACTIVE_UPDATES" = true ]; then
        pacman_args+=("--noconfirm")
    fi

    if ! sudo pacman "${pacman_args[@]}"; then
        log_error "System package update (pacman) failed."
        return 1
    fi
    log_message "System package update (pacman) completed successfully."
    return 0
}

perform_aur_update() {
    if ! command -v yay >/dev/null 2>&1; then
        log_message "yay AUR helper not found. Skipping AUR package update."
        return 0 # Not an error if yay is not installed, just a skip.
    fi

    log_message "Starting AUR package update (yay)..."
    # `yay` does not need sudo explicitly; it calls sudo internally when needed.
    local yay_args=("-Syu")
     if [ "$NON_INTERACTIVE_UPDATES" = true ]; then
        yay_args+=("--noconfirm")
    fi

    if ! yay "${yay_args[@]}"; then
        log_error "AUR package update (yay) failed."
        return 1
    fi
    log_message "AUR package update (yay) completed successfully."
    return 0
}

run_updates() {
    log_message "Initiating system update process..."
    if ! perform_system_update; then
        # Error already logged by perform_system_update
        return 1
    fi
    if ! perform_aur_update; then
        # Error already logged by perform_aur_update
        return 1
    fi
    log_message "System update process finished successfully."
    return 0
}

# --- Main Execution Logic ---
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Manages Arch Linux system and AUR package updates."
    echo ""
    echo "Options:"
    echo "  -h, --help            Show this help message and exit."
    echo "  -n, --non-interactive Run updates without interactive prompts (uses --noconfirm)."
    echo "                        Default: $NON_INTERACTIVE_UPDATES (interactive)"
    echo ""
    echo "Project Directory: arch-utils"
}

main() {
    # Parse options
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -n|--non-interactive)
                NON_INTERACTIVE_UPDATES=true
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done

    run_updates
    log_message "arch-update.sh finished execution."
}

# Script entry point
# Check if running as root, which is generally not recommended for the entire script.
# Sudo will be called internally for commands that need it.
if [[ $EUID -eq 0 ]]; then
   log_warning "This script is designed to be run as a regular user."
   log_warning "It will use 'sudo' internally for privileged operations as needed."
   log_warning "Running the entire script as root is not recommended."
   # exit 1 # Optionally, prevent root execution. For now, just warn.
fi

main "$@"

# Prompt to keep terminal open if running interactively
if [ -t 1 ]; then # If stdout is a terminal
    echo # Ensure a newline before the prompt
    read -r -p "Script finished. Press Enter to exit..."
fi
