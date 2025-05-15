#!/bin/bash
#
# arch-cleanup-user.sh
#
# A script to manage user-specific cleanup tasks on Arch Linux.
# Reports total space liberated. This version does NOT use sudo.
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
# Directories to clean. User-specific paths use $HOME.
# These are examples; customize as needed.
# The script will only be able to clean paths the current user has permissions for.
CLEANUP_DIRECTORIES=(
    "$HOME/.cache"
    "$HOME/.local/share/Trash"
    # Example of a system path - cleaning will likely fail or be partial without sudo:
    # "/tmp"
    # Pacman cache - cleaning will likely fail without sudo:
    # "/var/cache/pacman/pkg"
)

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

human_readable_size() {
    local size_in_bytes="$1"
    numfmt --to=iec-i --suffix=B "$size_in_bytes" 2>/dev/null || echo "${size_in_bytes}B"
}

# --- Cleanup Module ---
calculate_directory_size() {
    local dir="$1"
    if [ -d "$dir" ]; then
        # Calculate size as current user. `du` might output errors for unreadable subdirs.
        # timeout prevents `du` from hanging. Errors from du are suppressed.
        timeout 10s du -sb "$dir" 2>/dev/null | awk '{print $1}' || echo 0
    else
        echo 0
    fi
}

delete_directory_contents() {
    local dir_to_clean="$1"

    if [ ! -d "$dir_to_clean" ]; then
        log_message "Directory '$dir_to_clean' does not exist. Skipping."
        return 0
    fi

    log_message "Processing directory for cleanup: '$dir_to_clean' (as current user)"

    # Check if current user can write to the directory to even attempt deletion
    if [ ! -w "$dir_to_clean" ]; then
        log_warning "No write permission for directory '$dir_to_clean'. Skipping deletion of its contents."
        return 1 # Indicate failure due to permissions
    fi

    local subshell_status=0
    (
        # shellcheck disable=SC2164 # We check -d and -w above, cd should be safe enough
        cd "$dir_to_clean" || { log_error "Could not cd into '$dir_to_clean'. Skipping deletion for this directory."; exit 1; }
        # Attempt to remove contents. Errors for individual unremovable files are suppressed by 2>/dev/null.
        # The overall success relies on `rm -rf` and then checking if the directory is empty.
        if ! rm -rf ./* ./.[!.]* ./..?* 2>/dev/null; then
            # rm might return non-zero if some globs didn't match anything,
            # or if it failed to remove some files (e.g., due to permissions on sub-items).
            # We check if the directory is empty to determine actual success.
            if [ -n "$(ls -A . 2>/dev/null)" ]; then
                log_error "Failed to delete some contents of '$dir_to_clean'."
                exit 1 # Indicates failure in subshell
            fi
        fi
    )
    subshell_status=$?

    if [ "$subshell_status" -ne 0 ]; then
        # If subshell failed, re-check if the directory is actually empty.
        if [ -n "$(ls -A "$dir_to_clean" 2>/dev/null)" ]; then
             log_warning "Deletion of '$dir_to_clean' may be incomplete. Some files might remain (e.g. due to permissions)."
             return 1 # Indicate actual failure
        else
            log_message "Contents of '$dir_to_clean' successfully processed (directory is empty post-operation despite subshell non-zero exit)."
        fi
    else
        log_message "Contents of '$dir_to_clean' have been processed for deletion."
    fi
    return 0
}


run_cleanup() {
    log_message "Starting user-level system cleanup process..."
    local total_space_liberated=0
    local cleanup_failed_count=0

    # --- 1. Clean specified directories from CLEANUP_DIRECTORIES array ---
    log_message "--- Processing general directories for cleanup (user-level permissions) ---"
    for dir_path in "${CLEANUP_DIRECTORIES[@]}"; do
        local initial_size
        local final_size
        local liberated_this_dir

        initial_size=$(calculate_directory_size "$dir_path")
        log_message "Initial size of '$dir_path': $(human_readable_size "$initial_size")"

        if delete_directory_contents "$dir_path"; then
            final_size=$(calculate_directory_size "$dir_path")
            # Ensure liberated_this_dir is not negative
            liberated_this_dir=$((initial_size - final_size > 0 ? initial_size - final_size : 0))

            if [ "$liberated_this_dir" -gt 0 ]; then
                total_space_liberated=$((total_space_liberated + liberated_this_dir))
                log_message "Liberated $(human_readable_size "$liberated_this_dir") from '$dir_path'."
            elif [ "$initial_size" -gt 0 ]; then
                log_message "No net space liberated from '$dir_path' or it was already effectively empty after processing."
            else
                log_message "'$dir_path' was already empty, non-existent, or no space gained."
            fi
        else
            cleanup_failed_count=$((cleanup_failed_count + 1))
            # Error/warning messages are logged within delete_directory_contents
            log_warning "Failed to fully clean '$dir_path'."
        fi
        echo # Add a blank line for readability between directories
    done

    if [ "$cleanup_failed_count" -gt 0 ]; then
        log_warning "Directory content cleanup phase completed with $cleanup_failed_count directory/directories having issues."
    else
        log_message "Directory content cleanup phase completed."
    fi
    
    # --- 2. Pacman cache cleaning (paccache) ---
    # This section is removed as paccache requires sudo.
    # log_message "--- Pacman cache ---"
    # log_message "Advanced Pacman cache cleaning with 'paccache' requires sudo privileges and is not included in this version."
    # log_message "If you added /var/cache/pacman/pkg to CLEANUP_DIRECTORIES, an attempt was made to clean it with user permissions (likely failed)."

    echo # Blank line for readability

    # --- 3. Final Report ---
    log_message "--- Cleanup Summary ---"
    log_message "Total space liberated by this user-level cleanup: $(human_readable_size "$total_space_liberated")."
    
    log_message "User-level cleanup process finished."
    if [ "$cleanup_failed_count" -gt 0 ]; then
        return 1 # Indicate overall process had failures
    fi
    return 0 
}

# --- Main Execution Logic ---
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Manages user-level Arch Linux system cleanup and reports space liberated."
    echo "This script does NOT use sudo and will only clean what the current user has permissions for."
    echo ""
    echo "Configured CLEANUP_DIRECTORIES (user-level access):"
    for dir in "${CLEANUP_DIRECTORIES[@]}"; do
        echo "  - $dir"
    done
    echo ""
    echo "Options:"
    echo "  -h, --help            Show this help message and exit."
    echo ""
    echo "Project Directory: arch-utils"
}

main() {
    # Parse options
    while [[ $# -gt 0 ]]; do
        case "$1" in
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

    run_cleanup
    log_message "arch-cleanup-user.sh finished execution."
}

# Script entry point
if [[ $EUID -eq 0 ]]; then
   log_warning "This script is designed to be run as a regular user."
   log_warning "It will only clean files and directories the current user (root, in this case) has permissions for."
   log_warning "For user-specific caches, run it as that user, not as root."
   log_warning "e.g., if $HOME/.cache is listed and you run as root, it will clean /root/.cache"
fi

main "$@"

# Prompt to keep terminal open if running interactively
if [ -t 1 ]; then # If stdout is a terminal
    echo # Ensure a newline before the prompt
    read -r -p "Script finished. Press Enter to exit..."
fi
