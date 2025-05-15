#!/bin/bash
#
# arch-cleanup.sh
#
# A script to manage Arch Linux system cleanup tasks.
# Reports total space liberated.
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
# Customize as needed.
CLEANUP_DIRECTORIES=(
    "/tmp"
    # Note: /var/cache/pacman/pkg is handled specially by paccache if available
    "$HOME/.cache"
    "$HOME/.local/share/Trash"
)
# Pacman cache directory, handled by paccache if available.
# If you want this directory to be force-cleaned by delete_directory_contents
# even if paccache is not available, add it to CLEANUP_DIRECTORIES above.
PACMAN_CACHE_DIR="/var/cache/pacman/pkg"


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

human_readable_size() {
    local size_in_bytes="$1"
    numfmt --to=iec-i --suffix=B "$size_in_bytes" 2>/dev/null || echo "${size_in_bytes}B"
}

# --- Cleanup Module ---
calculate_directory_size() {
    local dir="$1"
    if [ -d "$dir" ]; then
        local size_cmd_base="du -sb"
        local size_cmd="$size_cmd_base"
        # If it's a system path AND we are not already root, try to use sudo for accuracy
        if [[ "$dir" == "/tmp"* || "$dir" == "/var/"* || "$dir" == "/etc/"* || "$dir" == "/opt/"* ]] && [ "$(id -u)" -ne 0 ]; then
            if command -v sudo >/dev/null 2>&1; then
                 _ensure_sudo_available
                size_cmd="sudo $size_cmd_base"
            else
                log_warning "sudo not found, calculating size of '$dir' as current user. Size might be inaccurate."
            fi
        fi
        # The `timeout` command prevents `du` from hanging on problematic directories.
        timeout 10s $size_cmd "$dir" 2>/dev/null | awk '{print $1}' || echo 0
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
    if [[ "$dir_to_clean" == "/tmp"* || "$dir_to_clean" == "/var/"* || "$dir_to_clean" == "/etc/"* || "$dir_to_clean" == "/opt/"* ]]; then
        use_sudo=true
    elif [ -e "$dir_to_clean" ] && [ ! -w "$dir_to_clean" ]; then
         use_sudo=true
    fi

    local cmd_prefix=""
    local ls_check_cmd="ls -A"
    if [ "$use_sudo" = true ]; then
        if command -v sudo >/dev/null 2>&1; then
            _ensure_sudo_available
            cmd_prefix="sudo "
            ls_check_cmd="sudo ls -A"
            log_message "Using sudo to delete contents of '$dir_to_clean'."
        else
            log_warning "sudo not found, but sudo privileges might be needed for '$dir_to_clean'. Deletion may fail."
            # Attempt without sudo, will likely fail for system dirs if not root
        fi
    else
        log_message "Deleting contents of '$dir_to_clean' as current user."
    fi

    local subshell_status=0
    (
        cd "$dir_to_clean" || { log_error "Could not cd into '$dir_to_clean'. Skipping deletion for this directory."; exit 1; }
        # shellcheck disable=SC2086
        if ! ${cmd_prefix}rm -rf ./* ./.[!.]* ./..?* 2>/dev/null; then
            if [ -n "$(${cmd_prefix}ls -A . 2>/dev/null)" ]; then # Check if directory is actually empty
                log_error "Failed to delete some contents of '$dir_to_clean'."
                exit 1
            fi
        fi
    )
    subshell_status=$?

    if [ "$subshell_status" -ne 0 ]; then
        if [ -n "$($ls_check_cmd "$dir_to_clean" 2>/dev/null)" ]; then # If dir still not empty
             log_warning "Deletion of '$dir_to_clean' may be incomplete. Some files might remain."
             return 1
        else
            log_message "Contents of '$dir_to_clean' successfully processed (directory is empty post-operation despite subshell non-zero exit)."
        fi
    else
        log_message "Contents of '$dir_to_clean' have been processed for deletion."
    fi
    return 0
}


run_cleanup() {
    log_message "Starting system cleanup process..."
    local total_space_liberated=0
    local cleanup_failed_count=0
    local paccache_available=false

    if command -v paccache > /dev/null 2>&1; then
        paccache_available=true
    fi

    # --- 1. Clean specified directories from CLEANUP_DIRECTORIES array ---
    log_message "--- Processing general directories for cleanup ---"
    for dir_path in "${CLEANUP_DIRECTORIES[@]}"; do
        # If paccache is available, it will handle its dedicated directory later
        if [ "$paccache_available" = true ] && [ "$dir_path" == "$PACMAN_CACHE_DIR" ]; then
            log_message "Pacman cache directory '$PACMAN_CACHE_DIR' is in CLEANUP_DIRECTORIES but will be handled by 'paccache'. Skipping generic deletion here."
            continue
        fi

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
            elif [ "$initial_size" -gt 0 ]; then # Was not empty, but no space gained (or dir perms changed size)
                log_message "No net space liberated from '$dir_path' or it was already effectively empty after processing."
            else
                log_message "'$dir_path' was already empty or non-existent."
            fi
        else
            cleanup_failed_count=$((cleanup_failed_count + 1))
            # Error messages are logged within delete_directory_contents
        fi
        echo # Add a blank line for readability between directories
    done

    if [ "$cleanup_failed_count" -gt 0 ]; then
        log_warning "Directory content cleanup phase completed with $cleanup_failed_count issue(s)."
    else
        log_message "Directory content cleanup phase completed successfully."
    fi

    # --- 2. Pacman cache cleaning (paccache) ---
    log_message "--- Processing Pacman cache with paccache ---"
    if [ "$paccache_available" = true ]; then
        _ensure_sudo_available # paccache needs sudo
        
        local initial_pacman_cache_size
        initial_pacman_cache_size=$(calculate_directory_size "$PACMAN_CACHE_DIR")
        log_message "Initial size of '$PACMAN_CACHE_DIR' (before paccache): $(human_readable_size "$initial_pacman_cache_size")"

        local paccache_issues=0
        if sudo paccache -rk2; then # Keep last 2 versions
             log_message "Pacman cache cleaned (kept last 2 versions)."
        else
            log_warning "Paccache -rk2 command failed or had issues."
            paccache_issues=$((paccache_issues + 1))
        fi
        if sudo paccache -ruk0; then # Remove uninstalled packages
            log_message "Removed uninstalled packages from pacman cache."
        else
            log_warning "Paccache -ruk0 command failed or had issues."
            paccache_issues=$((paccache_issues + 1))
        fi

        local final_pacman_cache_size
        final_pacman_cache_size=$(calculate_directory_size "$PACMAN_CACHE_DIR")
        # Ensure liberated_by_paccache is not negative
        local liberated_by_paccache=$((initial_pacman_cache_size - final_pacman_cache_size > 0 ? initial_pacman_cache_size - final_pacman_cache_size : 0))


        if [ "$liberated_by_paccache" -gt 0 ]; then
            total_space_liberated=$((total_space_liberated + liberated_by_paccache))
            log_message "Liberated $(human_readable_size "$liberated_by_paccache") by paccache from '$PACMAN_CACHE_DIR'."
        elif [ "$initial_pacman_cache_size" -gt 0 ]; then
            log_message "No net space liberated by paccache, or cache was already optimized."
        fi
        
        if [ "$paccache_issues" -eq 0 ]; then
            log_message "Pacman cache cleaning with paccache completed successfully."
        else
            log_warning "Pacman cache cleaning with paccache had $paccache_issues issue(s)."
            # You might want to increment cleanup_failed_count here if paccache failures are critical
            # cleanup_failed_count=$((cleanup_failed_count + paccache_issues))
        fi
    else
        log_message "'paccache' (part of pacman-contrib) not found. Skipping advanced pacman cache cleaning."
        # If PACMAN_CACHE_DIR was also in CLEANUP_DIRECTORIES, it would have been handled by the generic loop.
        # If it's not (default), then it's skipped if paccache isn't found.
        if grep -qF "$PACMAN_CACHE_DIR" <<< "${CLEANUP_DIRECTORIES[*]}"; then
            log_message "Note: '$PACMAN_CACHE_DIR' was listed in CLEANUP_DIRECTORIES and might have been processed by generic cleanup."
        else
            log_message "To clean '$PACMAN_CACHE_DIR' without paccache, add it to the CLEANUP_DIRECTORIES array."
        fi
    fi
    echo # Blank line for readability

    # --- 3. Final Report ---
    log_message "--- Cleanup Summary ---"
    log_message "Total space liberated during this cleanup session: $(human_readable_size "$total_space_liberated")."
    
    log_message "System cleanup process finished."
    if [ "$cleanup_failed_count" -gt 0 ]; then
        return 1
    fi
    return 0 
}

# --- Main Execution Logic ---
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Manages Arch Linux system cleanup and reports space liberated."
    echo ""
    echo "This script cleans directories specified in the CLEANUP_DIRECTORIES array"
    echo "and uses 'paccache' to clean the pacman cache if available."
    echo ""
    echo "Configured CLEANUP_DIRECTORIES:"
    for dir in "${CLEANUP_DIRECTORIES[@]}"; do
        echo "  - $dir"
    done
    echo "Pacman Cache Directory (for paccache): $PACMAN_CACHE_DIR"
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
    log_message "arch-cleanup.sh finished execution."
}

# Script entry point
if [[ $EUID -eq 0 ]]; then
   log_warning "This script is designed to be run as a regular user."
   log_warning "It will use 'sudo' internally for privileged operations as needed."
   log_warning "Running the entire script as root is not recommended."
fi

main "$@"

# Prompt to keep terminal open if running interactively
if [ -t 1 ]; then # If stdout is a terminal
    echo # Ensure a newline before the prompt
    read -r -p "Script finished. Press Enter to exit..."
fi
