#!/bin/bash
# Change = line25 & do an rmlint initially to get dupes out of the way; ?ensure files less than 500k get removed
# Script Name: process_media.sh
# Description: Orchestrates a media file processing pipeline including:
#              - Automatic backup of the processing directory
#              - Prompting for minimum file size for deletion
#              - Unzipping archives
#              - Deleting small files post-unzip based on user threshold
#              - Renaming files (using an external script)
#              - Converting small JPEGs ( < 500KB) to PNG
#              - Removing EXIF data
#              - Deduplicating files
# Version: 1.4
# Author: TechEliteAutomation.com (modified by user request)
# Date: $(date +%Y-%m-%d)

# --- Script Setup ---
set -e # Exit immediately if a command exits with a non-zero status.
set -u # Treat unset variables as an error when substituting.
set -o pipefail # Pipestatus: if any command in a pipeline fails, the pipeline's return status is that command's status.

# --- Configuration ---
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
RENAMER_SCRIPT_PATH="$SCRIPT_DIR/tools/rename_files.sh"
PARALLEL_JOBS=${PARALLEL_JOBS:-$(nproc)}
BACKUP_BASE_DIR="/home/u/.bak" # Backup base directory

# Global variable for minimum file size in bytes, to be set by user
MIN_FILE_SIZE_BYTES=0 # Default to 0 (no deletion unless specified by user)

# --- Logging Functions ---
_log_generic() {
    local type="$1"; shift
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$type] $1"
}
log_step() { _log_generic "STEP" "$1"; }
log_info() { _log_generic "INFO" "    $1"; }
log_warn() { _log_generic "WARN" "    $1"; }
log_error() { _log_generic "ERROR" "   $1" >&2; }

# --- Worker Functions for Parallel Tasks (must be exported) ---
_unzip_single_archive_worker() {
    local zip_file="$1"; local target_dir; target_dir=$(dirname "$zip_file")
    local base_zip_file; base_zip_file=$(basename "$zip_file")
    echo "    [UNZIP-WORKER][$(date '+%H:%M:%S')] Processing: '$base_zip_file'..."
    if unzip -q -B -o "$zip_file" -d "$target_dir" &>/dev/null; then
        echo "    [UNZIP-WORKER][$(date '+%H:%M:%S')] OK: '$base_zip_file' unzipped, removing archive."
        rm "$zip_file"
    else
        echo "    [UNZIP-WORKER][$(date '+%H:%M:%S')] FAIL: Could not unzip '$base_zip_file'. Archive not removed." >&2
    fi
}
export -f _unzip_single_archive_worker

# --- Core Processing Functions ---

_prompt_for_min_file_size() {
    log_step "Specify Minimum File Size Threshold for Deletion"
    local min_kb_input
    while true; do
        read -r -p "Enter minimum file size in Kilobytes (KB). Files smaller than this will be deleted after unzipping. Enter 0 to disable this deletion: " min_kb_input
        if [[ -z "$min_kb_input" ]]; then # Handle empty input
            log_warn "Input cannot be empty. Please enter a number (e.g., 100 for 100KB, or 0 to disable)."
            continue
        fi
        if [[ "$min_kb_input" =~ ^[0-9]+$ ]]; then # Check if input is a non-negative integer
            if (( min_kb_input == 0 )); then
                MIN_FILE_SIZE_BYTES=0 # Explicitly set to 0 if user enters 0
                log_info "Deletion of files smaller than a specified threshold is disabled by user."
                break
            fi
            # Calculate bytes, ensuring integer arithmetic
            MIN_FILE_SIZE_BYTES=$((min_kb_input * 1024))
            log_info "Files smaller than $min_kb_input KB (${MIN_FILE_SIZE_BYTES} bytes) will be targeted for deletion after archives are unzipped."
            break
        else
            log_warn "Invalid input: '$min_kb_input'. Please enter a non-negative integer value for Kilobytes."
        fi
    done
}

_create_backup() {
    log_step "Attempting to create backup of current directory"
    if ! command -v zip >/dev/null 2>&1; then
        log_error "'zip' command not found. Backup cannot be created."
        log_error "Please install 'zip' (e.g., sudo apt install zip) and try again."
        return 1 # Indicate failure
    fi

    mkdir -p "$BACKUP_BASE_DIR" || {
        log_error "Could not create backup directory: $BACKUP_BASE_DIR"
        return 1
    }

    local current_dir_name
    current_dir_name=$(basename "$(pwd)") # This is the name of the directory being processed
    local timestamp
    timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_filename="${current_dir_name}_backup_${timestamp}.zip"
    local backup_filepath="$BACKUP_BASE_DIR/$backup_filename"

    log_info "Backup target: $backup_filepath"
    log_info "Creating ZIP archive of '.' (current directory being processed)... this may take a while."

    if zip -r -q "$backup_filepath" . ; then
        log_info "Backup created successfully: $backup_filepath"
    else
        log_error "Backup creation failed. Check permissions and available disk space for $BACKUP_BASE_DIR."
        log_error "Zip command exited with status: $?"
        return 1 # Indicate critical failure
    fi
    return 0
}

_process_archives() {
    log_step "Processing archives (unzip and delete, parallel)"
    if ! find . -maxdepth 10 -name "*.zip" -type f -print -quit 2>/dev/null | grep -q .; then
        log_info "No .zip archives found."
        return
    fi
    log_info "Unzipping archives in parallel (max $PARALLEL_JOBS jobs)..."
    find . -maxdepth 10 -name "*.zip" -type f -print0 | \
        xargs -0 -r -P "$PARALLEL_JOBS" -I{} bash -c '_unzip_single_archive_worker "$@"' _ {}
    log_info "Archive processing complete. Check logs above for details."
}

_delete_small_files_after_unzip() {
    if (( MIN_FILE_SIZE_BYTES <= 0 )); then
        log_info "Minimum file size threshold is 0 or not set by user. Skipping deletion of small files."
        return 0 # Not an error, expected behavior
    fi

    local min_kb_for_log=$((MIN_FILE_SIZE_BYTES / 1024)) # For user-friendly logging
    log_step "Deleting files smaller than $min_kb_for_log KB (${MIN_FILE_SIZE_BYTES} bytes)"

    local file_list_tmp
    file_list_tmp=$(mktemp "small_files_to_delete.XXXXXX")
    if [[ -z "$file_list_tmp" ]] || [[ ! -f "$file_list_tmp" ]]; then
        log_error "Failed to create temporary file for listing small files. Skipping deletion."
        return 1
    fi

    trap 'rm -f "$file_list_tmp"; trap - EXIT HUP INT QUIT TERM' EXIT HUP INT QUIT TERM

    if ! find . -type f -size "-${MIN_FILE_SIZE_BYTES}c" -print0 > "$file_list_tmp"; then
        log_warn "Find command encountered issues searching for small files. List may be incomplete or operation failed."
    fi
    
    local num_files_to_delete
    num_files_to_delete=$(awk 'BEGIN{RS="\0"; count=0} {if(length($0)>0) count++} END{print count}' < "$file_list_tmp")

    if (( num_files_to_delete > 0 )); then
        log_info "Found $num_files_to_delete files smaller than $min_kb_for_log KB. Attempting to delete them..."
        if xargs -0 --no-run-if-empty rm < "$file_list_tmp"; then
            log_info "$num_files_to_delete small files processed for deletion successfully."
        else
            log_error "Error occurred while deleting $num_files_to_delete small files. Some may not have been removed. Check xargs output (if any) or file permissions."
        fi
    else
        log_info "No files found smaller than $min_kb_for_log KB."
    fi

    rm -f "$file_list_tmp"
    trap - EXIT HUP INT QUIT TERM
    return 0
}

_rename_files_external() {
    log_step "Renaming files using external script: $RENAMER_SCRIPT_PATH"
    log_info "Note: The provided rename_files.sh script processes files in the current directory only (non-recursively by default)."
    if [ ! -f "$RENAMER_SCRIPT_PATH" ]; then
        log_error "Renamer script not found at '$RENAMER_SCRIPT_PATH'."
        return 1
    fi
    if [ ! -x "$RENAMER_SCRIPT_PATH" ]; then
        log_error "Renamer script is not executable: '$RENAMER_SCRIPT_PATH'."
        return 1
    fi
    "$RENAMER_SCRIPT_PATH"
    log_info "File renaming process complete."
}

_convert_jpegs_to_png() {
    log_step "Converting JPEGs smaller than 500KiB to PNG (parallel)"
    if ! command -v mogrify >/dev/null 2>&1; then
        log_warn "ImageMagick 'mogrify' not found. Skipping JPEG to PNG conversion."
        return
    fi
    if ! find . -maxdepth 10 -type f \( -iname "*.jpg" -o -iname "*.jpeg" \) -size -500k -print -quit 2>/dev/null | grep -q .; then
        log_info "No JPEGs smaller than 500KiB found for conversion."
        return
    fi
    log_info "Converting JPEGs smaller than 500KiB in parallel (max $PARALLEL_JOBS jobs)..."
    find . -maxdepth 10 -type f \( -iname "*.jpg" -o -iname "*.jpeg" \) -size -500k -print0 | \
    xargs -0 -r -P "$PARALLEL_JOBS" -I{} bash -c '
        file="$1"; base_file=$(basename "$file")
        _log_conv_ok() { echo "    [CONVERT-JPG-WORKER][$(date "+%H:%M:%S")] OK: $1"; }
        _log_conv_fail() { echo "    [CONVERT-JPG-WORKER][$(date "+%H:%M:%S")] FAIL: $1" >&2; }

        if mogrify -format png "$file" &>/dev/null; then
            rm "$file"
            _log_conv_ok "Converted '\''$base_file'\'' to PNG and removed original."
        else
            _log_conv_fail "Could not convert '\''$base_file'\'' to PNG. Original JPEG not removed."
        fi
    ' -- {}
    log_info "JPEG to PNG conversion pass (for files < 500KiB) complete. Check logs above for details."
}

_remove_exif_data() {
    log_step "Removing EXIF data (recursively)"
    if ! command -v exiftool >/dev/null 2>&1; then
        log_warn "exiftool not found. Skipping EXIF data removal."
        return
    fi
    if ! find . -maxdepth 10 -type f -print -quit 2>/dev/null | grep -q .; then
        log_info "No files found to process for EXIF removal."
        return
    fi
    log_info "Processing files with exiftool..."
    exiftool -all= -overwrite_original -r -q -q .
    log_info "EXIF data removal complete."
}

_remove_duplicates() {
    log_step "Removing duplicates"
    if ! command -v rmlint >/dev/null 2>&1; then
        log_warn "rmlint not found. Skipping duplicate removal."
        return
    fi
    log_info "Running rmlint to generate a deduplication script..."
    rm -f ./rmlint.json ./rmlint.sh ./rmlint.csv
    if ! rmlint --progress --types=duplicates ./ >/dev/null; then
        log_info "rmlint finished. It might not have found duplicates or encountered an issue (check for stderr messages if any)."
    fi

    if [ -f "./rmlint.sh" ]; then
        if [ -s "./rmlint.sh" ]; then
            log_info "Executing rmlint.sh to remove duplicates..."
            if bash "./rmlint.sh" -d; then 
                 log_info "Duplicate removal script executed successfully."
            else
                 log_warn "Duplicate removal script execution may have reported errors or warnings."
            fi
        else
            log_info "rmlint.sh was generated but is empty. No duplicates to remove or no actions defined."
        fi
        rm -f "./rmlint.sh"
    else
        log_info "No rmlint.sh script generated by rmlint (likely no duplicates found or an issue occurred)."
    fi
    rm -f ./rmlint.json ./rmlint.csv
    log_info "Duplicate removal process complete."
}

# --- Main Execution ---
main() {
    log_step "Media Optimizer Suite Initialized"
    local overall_start_time=$SECONDS

    _prompt_for_min_file_size

    _create_backup || {
        log_error "Critical: Backup step failed. Aborting all further operations."
        exit 1
    }

    log_info "Performing initial duplicate check (before archive processing)..."
    _remove_duplicates

    _process_archives

    _delete_small_files_after_unzip || {
        log_error "Deletion of small files failed. Aborting subsequent steps."
        exit 1
    }

    log_info "Performing duplicate check (after archive processing and small file deletion)..."
    _remove_duplicates

    _rename_files_external || { log_error "Renaming step failed. Aborting subsequent steps."; exit 1; }
    
    _convert_jpegs_to_png
    
    _remove_exif_data

    log_info "Performing duplicate check (after EXIF data removal)..."
    _remove_duplicates

    local overall_duration=$((SECONDS - overall_start_time))
    log_step "All media processing tasks complete."
    log_info "Total execution time: $overall_duration seconds."
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main
fi
