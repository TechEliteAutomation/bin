#!/bin/bash
#
# arch-manage.sh
#
# A script to manage Arch Linux system updates and cleanup.
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
CLEANUP_DIRECTORIES=(
    "/tmp"
    "/var/cache/pacman/pkg" # Pacman cache (partially handled by pacman itself, but can be cleaned)
    "$HOME/.cache"
    "$HOME/.local/share/Trash"
)

# Set to true to enable non-interactive mode for package managers (e.g., --noconfirm)
# Set to false to allow interactive confirmations.
NON_INTERACTIVE_UPDATES=true

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

# --- Update Module ---
_ensure_sudo_available() {
    if ! sudo -n true 2>/dev/null; then
        log_message "Sudo requires a password. Please enter it when prompted."
    fi
}

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
    perform_system_update
    perform_aur_update
    log_message "System update process finished."
}

# --- Cleanup Module ---
calculate_directory_size() {
    local dir="$1"
    if [ -d "$dir" ]; then
        # The `timeout` command prevents `du` from hanging on problematic directories.
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

    log_message "Processing directory for cleanup: '$dir_to_clean'"

    local use_sudo=false
    # Determine if sudo is needed: system paths or if current user lacks write permissions.
    if [[ "$dir_to_clean" == "/tmp"* || "$dir_to_clean" == "/var/"* || "$dir_to_clean" == "/etc/"* || "$dir_to_clean" == "/opt/"* ]]; then
        use_sudo=true
    elif [ -e "$dir_to_clean" ] && [ ! -w "$dir_to_clean" ]; then # If dir exists and current user can't write to it.
         use_sudo=true
    fi
    # A more robust check would be to test write access to a temporary file inside the directory if it's not a system path.

    local cmd_prefix=""
    if [ "$use_sudo" = true ]; then
        _ensure_sudo_available
        cmd_prefix="sudo "
        log_message "Using sudo to delete contents of '$dir_to_clean'."
    else
        log_message "Deleting contents of '$dir_to_clean' as current user."
    fi

    # Using the original script's robust globbing to remove contents including hidden files.
    # The '2>/dev/null' suppresses errors if a glob pattern matches no files.
    # Use a subshell to 'cd' into the directory to make 'rm' paths simpler and safer.
    (
        cd "$dir_to_clean" || { log_error "Could not cd into '$dir_to_clean'. Skipping deletion for this directory."; exit 1; }
        # shellcheck disable=SC2086
        if ! ${cmd_prefix}rm -rf ./* ./.[!.]* ./..?* 2>/dev/null; then
            # Check if directory is actually empty. rm might return error on non-matching globs if dir was already empty.
            if [ -n "$(${cmd_prefix}ls -A . 2>/dev/null)" ]; then
                log_error "Failed to delete some contents of '$dir_to_clean'."
                # No 'return 1' here as we are in a subshell; error logged is sufficient.
                # The main function will check overall success.
                exit 1 # Indicates failure in subshell
            fi
        fi
    )

    if [ $? -ne 0 ] && [ "$use_sudo" = true ]; then # If subshell failed and sudo was used.
         # Check if the directory is empty using sudo ls, as direct ls might lack permissions.
        if [ -n "$(sudo ls -A "$dir_to_clean" 2>/dev/null)" ]; then
             log_warning "Deletion of '$dir_to_clean' (with sudo) may be incomplete. Some files might remain."
             return 1 # Indicate actual failure
        fi
    elif [ $? -ne 0 ] && [ "$use_sudo" = false ]; then
        if [ -n "$(ls -A "$dir_to_clean" 2>/dev/null)" ]; then
            log_warning "Deletion of '$dir_to_clean' may be incomplete. Some files might remain."
            return 1 # Indicate actual failure
        fi
    fi


    log_message "Contents of '$dir_to_clean' have been processed for deletion."
    return 0
}


run_cleanup() {
    log_message "Starting system cleanup process..."
    
    local trash_path_for_calc="$HOME/.local/share/Trash" # Path used by the original script for calculation
    local initial_trash_size=0
    initial_trash_size=$(calculate_directory_size "$trash_path_for_calc")

    local cleanup_failed_count=0
    for dir_path in "${CLEANUP_DIRECTORIES[@]}"; do
        if ! delete_directory_contents "$dir_path"; then
            cleanup_failed_count=$((cleanup_failed_count + 1))
            # Error messages are logged within delete_directory_contents
        fi
    done

    if [ "$cleanup_failed_count" -gt 0 ]; then
        log_warning "System cleanup completed with $cleanup_failed_count issue(s) in deleting directory contents."
    else
        log_message "System cleanup process completed successfully."
    fi

    # Report liberated space specifically from the Trash directory, if it was targeted.
    local trash_cleaned=false
    for cleaned_dir in "${CLEANUP_DIRECTORIES[@]}"; do
        if [ "$cleaned_dir" == "$trash_path_for_calc" ] || [ "$cleaned_dir" == "$HOME/.local/share/Trash/files" ] || [ "$cleaned_dir" == "$HOME/.local/share/Trash/info" ]; then
            trash_cleaned=true
            break
        fi
    done

    if [ "$trash_cleaned" = true ] && [ "$initial_trash_size" -gt 0 ]; then
        local final_trash_size
        final_trash_size=$(calculate_directory_size "$trash_path_for_calc")
        local liberated_from_trash=$((initial_trash_size - final_trash_size))
        
        if [ "$liberated_from_trash" -gt 0 ]; then
            local liberated_space_human
            liberated_space_human=$(numfmt --to=iec-i --suffix=B "$liberated_from_trash" 2>/dev/null || echo "${liberated_from_trash}B")
            log_message "Space liberated from Trash ($trash_path_for_calc): $liberated_space_human"
        elif [ "$initial_trash_size" -gt 0 ]; then
             log_message "Trash directory ($trash_path_for_calc) was processed, but no net space was liberated or it was already empty."
        fi
    fi
    
    # Pacman cache cleaning (specific example)
    if command -v paccache > /dev/null 2>&1; then
        log_message "Cleaning pacman cache with paccache..."
        _ensure_sudo_available
        if sudo paccache -rk2; then # Keep last 2 versions
             log_message "Pacman cache cleaned (kept last 2 versions)."
        else
            log_warning "Paccache command failed or had issues."
        fi
        if sudo paccache -ruk0; then # Remove uninstalled packages
            log_message "Removed uninstalled packages from pacman cache."
        else
            log_warning "Paccache (uninstalled) command failed or had issues."
        fi
    else
        log_message "'paccache' (part of pacman-contrib) not found. Skipping advanced pacman cache cleaning."
    fi

    log_message "System cleanup process finished."
    return 0 # Or return based on cleanup_failed_count if strict error propagation is needed
}

# --- Main Execution Logic ---
usage() {
    echo "Usage: $0 [OPTIONS] [COMMAND]"
    echo "Manages Arch Linux system updates and cleanup."
    echo ""
    echo "Options:"
    echo "  -h, --help            Show this help message and exit."
    echo "  -n, --non-interactive Run updates without interactive prompts (uses --noconfirm)."
    echo "                        Default: $NON_INTERACTIVE_UPDATES"
    echo ""
    echo "Commands:"
    echo "  update                Performs system and AUR package updates."
    echo "  cleanup               Cleans specified cache and temporary directories."
    echo "  all                   Performs both update and cleanup (update first)."
    echo ""
    echo "If no command is provided, 'all' is assumed if no other options are given that imply a command."
    echo "Project Directory: arch-utils"
}

main() {
    local command_to_run=""

    # Parse options
    while [[ $# -gt 0 ]]; do
        case "$1" in
            update|cleanup|all)
                if [ -n "$command_to_run" ]; then
                    log_error "Multiple commands specified. Please choose one: update, cleanup, or all."
                    usage
                    exit 1
                fi
                command_to_run="$1"
                shift
                ;;
            -n|--non-interactive)
                NON_INTERACTIVE_UPDATES=true
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                log_error "Unknown option or command: $1"
                usage
                exit 1
                ;;
        esac
    done

    # Default command if none specified
    if [ -z "$command_to_run" ]; then
        log_message "No specific command provided, defaulting to 'all' (update and cleanup)."
        command_to_run="all"
    fi

    # Execute command
    case "$command_to_run" in
        update)
            run_updates
            ;;
        cleanup)
            run_cleanup
            ;;
        all)
            run_updates
            # Only run cleanup if updates were successful (or if set -e is not used and we check $?)
            # With 'set -e', script will exit if run_updates fails.
            log_message "Updates completed, proceeding to cleanup..."
            run_cleanup
            ;;
        *)
            # This case should ideally not be reached due to earlier checks
            log_error "Invalid command state. This should not happen."
            usage
            exit 1
            ;;
    esac

    log_message "arch-manage.sh finished execution for command: '$command_to_run'."
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
