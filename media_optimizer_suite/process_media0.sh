#!/bin/bash
# process_media.sh: Media processing pipeline
# Version: 3.0 (Major simplification of find usage)

# --- Script Setup ---
set -e -u -o pipefail

# --- Configuration ---
SCRIPT_DIR_RESOLVED="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
SCRIPT_DIR="${SCRIPT_DIR_RESOLVED:-$(pwd)}"

RENAMER_SCRIPT_PATH="$SCRIPT_DIR/tools/rename_files.sh"
PARALLEL_JOBS="${MEDIA_PROCESSOR_JOBS:-$(nproc)}"
BACKUP_BASE_DIR="${MEDIA_BACKUP_DIR:-/home/u/.bak}"

KIB_IN_BYTES=1024
MIB_IN_BYTES=$((1024 * KIB_IN_BYTES))

MIN_FILE_SIZE_FOR_DELETION_KIB=0
MIN_FILE_SIZE_FOR_DELETION_BYTES=0

SEGREGATION_THRESHOLD_KIB=100
MIN_CONVERSION_SIZE_KIB=100

JPEG_MAX_CONVERSION_SIZE_MIB=1
FINAL_DELETION_THRESHOLD_MIB=1

SEGREGATION_DIR_NAME="sub_100k_files"

# --- Logging Functions ---
_log_generic() { local type="$1"; shift; echo "[$type] $1"; }
log_info() { _log_generic "INFO" "    $1"; }
log_warn() { _log_generic "WARN" "    $1"; }
log_error() { _log_generic "ERROR" "   $1" >&2; }
log_step() {
    echo "----------------------------------------------------------------------"
    _log_generic "STEP" "$1"
    echo "----------------------------------------------------------------------"
}

export -f _log_generic log_info log_warn log_error

# --- Worker Functions for Parallel Tasks ---
_unzip_single_archive_worker() {
    local zip_file="$1"
    local target_dir
    target_dir=$(dirname "$zip_file")
    local base_zip_file
    base_zip_file=$(basename "$zip_file")
    echo "[UNZIP] Processing: '$base_zip_file'"
    if nice -n 10 ionice -c 2 -n 7 unzip -q -o "$zip_file" -d "$target_dir"; then
        rm "$zip_file"
        echo "[UNZIP] OK: '$base_zip_file' unzipped, removed."
    else
        local unzip_status=$?
        echo "[UNZIP] FAIL ($unzip_status): Could not unzip '$base_zip_file'." >&2
    fi
}

_convert_image_worker() {
    local file="$1"
    local new_ext="png"
    local base_file
    base_file=$(basename "$file")
    local original_extension="${file##*.}"
    local src_ext_upper="${original_extension^^}"
    local new_filename_expected="${file%.*}.$new_ext"
    local log_prefix="[CONV:${src_ext_upper}>PNG]"
    local mogrify_cmd_status=0

    nice -n 10 ionice -c 2 -n 7 mogrify -format "$new_ext" "$file"
    mogrify_cmd_status=$?

    if [[ $mogrify_cmd_status -eq 0 ]]; then
        if [[ -f "$new_filename_expected" ]]; then
            if [[ "$file" != "$new_filename_expected" ]]; then
                if rm "$file"; then
                    log_info "$log_prefix Converted '$base_file' to '$(basename "$new_filename_expected")' (original removed)"
                else
                    log_warn "$log_prefix Converted '$base_file' to '$(basename "$new_filename_expected")', BUT FAILED TO REMOVE ORIGINAL '$file'."
                fi
            else 
                log_info "$log_prefix Processed '$base_file' (already PNG or overwritten by mogrify)"
            fi
        else
            if [[ "$original_extension" == "$new_ext" ]]; then
                 log_info "$log_prefix Processed '$base_file' (already $new_ext, no change by mogrify -format)"
            else # This case should ideally not happen if mogrify -format works as expected
                log_warn "$log_prefix Processed '$base_file' (mogrify exit 0), but expected new file '$(basename "$new_filename_expected")' not found. Original '$file' not removed."
            fi
        fi
    else
        log_error "$log_prefix Failed to convert '$base_file' (mogrify -format exit status: $mogrify_cmd_status). Original not removed."
    fi
}

export -f _unzip_single_archive_worker _convert_image_worker

# --- Core Processing Functions ---

_prompt_for_min_file_size() {
    log_step "Configure Post-Unzip Small File Deletion (Main Directory Only)"
    local min_kib_input
    while true; do
        read -r -p "Enter min file size (KiB) for DELETING files from MAIN dir (0 to disable, default 0): " min_kib_input
        min_kib_input=${min_kib_input:-0}
        if [[ "$min_kib_input" =~ ^[0-9]+$ ]]; then
            MIN_FILE_SIZE_FOR_DELETION_KIB=$min_kib_input
            MIN_FILE_SIZE_FOR_DELETION_BYTES=$((min_kib_input * KIB_IN_BYTES))
            if (( MIN_FILE_SIZE_FOR_DELETION_BYTES > 0 )); then
                log_info "Post-unzip: Files < ${MIN_FILE_SIZE_FOR_DELETION_KIB}KiB in MAIN directory will be deleted."
            else
                log_info "Post-unzip: User-defined small file deletion (main dir) disabled."
            fi
            break
        else
            log_warn "Invalid input: '$min_kib_input'. Please enter a non-negative integer for KiB."
        fi
    done
}

_create_backup() {
    log_step "Creating Backup"
    command -v zip >/dev/null 2>&1 || { log_error "'zip' command not found. Backup cannot be created."; return 1; }
    mkdir -p "$BACKUP_BASE_DIR" || { log_error "Could not create backup directory: $BACKUP_BASE_DIR"; return 1; }

    local current_dir_name
    current_dir_name=$(basename "$(pwd)")
    local timestamp
    timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_filepath="$BACKUP_BASE_DIR/${current_dir_name}_backup_${timestamp}.zip"

    log_info "Backing up current directory to: $backup_filepath"
    if nice -n 10 ionice -c 2 -n 7 zip -r -q "$backup_filepath" .; then
        log_info "Backup created successfully: $backup_filepath"
    else
        log_error "Backup creation failed (zip exit status: $?)."
        return 1
    fi
}

_process_archives() {
    log_step "Processing Archives (Unzip & Delete Original)"
    # Use a temporary array to store filenames for parallel processing
    # This is a compromise for reliability over extreme memory efficiency for huge numbers of zips
    local archives_found_array=()
    while IFS= read -r -d $'\0' file; do
        archives_found_array+=("$file")
    done < <(find . -maxdepth 10 -name "*.zip" -type f -print0)
    
    if [ ${#archives_found_array[@]} -eq 0 ]; then
        log_info "No .zip archives found to process."
        return
    fi
    log_info "Unzipping ${#archives_found_array[@]} archive(s) using up to $PARALLEL_JOBS parallel jobs..."
    printf "%s\0" "${archives_found_array[@]}" | parallel -0 --bar -P "$PARALLEL_JOBS" _unzip_single_archive_worker {}
    log_info "Archive processing complete."
}

_segregate_small_files() {
    local segregation_dir_path="./$SEGREGATION_DIR_NAME"
    log_step "Segregating Files < ${SEGREGATION_THRESHOLD_KIB}KiB to '$segregation_dir_path/'"

    mkdir -p "$segregation_dir_path"

    local files_to_segregate_array=()
    # Using POSIX find syntax: options, path, expressions
    # Exclude files already in the segregation directory from being considered.
    # The -path ... -prune -o logic is standard for excluding a directory.
    while IFS= read -r -d $'\0' file; do
         # Double check we are not moving files from within the segregation dir itself
        if ! [[ "$(realpath -m "$file")" == "$(realpath -m "$segregation_dir_path")"* ]]; then
            files_to_segregate_array+=("$file")
        fi
    done < <(find . -maxdepth 10 \( -path "$segregation_dir_path" -prune \) -o \( -type f ! -iname "*.zip" -size "-${SEGREGATION_THRESHOLD_KIB}k" -print0 \))


    if [ ${#files_to_segregate_array[@]} -eq 0 ]; then
        log_info "No files found smaller than ${SEGREGATION_THRESHOLD_KIB}KiB to segregate."
        return
    fi

    log_info "Found ${#files_to_segregate_array[@]} files < ${SEGREGATION_THRESHOLD_KIB}KiB. Moving to '$segregation_dir_path/'..."
    local moved_count=0
    local failed_count=0
    for file_to_move in "${files_to_segregate_array[@]}"; do
        local relative_path_to_file="${file_to_move#./}" 
        local target_subdir_in_seg_dir="$segregation_dir_path/$(dirname "$relative_path_to_file")"
        
        if [[ "$relative_path_to_file" == */* ]]; then 
             mkdir -p "$target_subdir_in_seg_dir"
        fi

        if mv --backup=numbered "$file_to_move" "$segregation_dir_path/$relative_path_to_file"; then
            ((moved_count++))
        else
            log_warn "Failed to move '$file_to_move' to segregation directory."
            ((failed_count++))
        fi
    done
    log_info "Segregation: $moved_count files moved. $failed_count files failed to move."
}


_delete_files_smaller_than() {
    local size_val="$1" 
    local size_unit="$2" 
    local log_reason="$3"
    local target_dir_desc="$4"
    # local segregation_dir_path_local="./$SEGREGATION_DIR_NAME" # Not strictly needed for -maxdepth 1
    local find_size_char

    if [[ "$size_unit" == "KiB" ]]; then
        find_size_char="${size_val}k"
    elif [[ "$size_unit" == "MiB" ]]; then
        find_size_char="${size_val}M"
    else
        log_error "Invalid size unit '$size_unit' for deletion. Must be KiB or MiB."
        return 1
    fi

    log_step "Deleting Files < $size_val$size_unit ($log_reason - $target_dir_desc)"

    local files_to_delete_array=()
    # Simpler find, direct execution, then pipe to readarray/mapfile or while loop
    # For "Main Directory Only", find in "." with -maxdepth 1
    # Standard find syntax: find [path...] [options] [expression]
    # For GNU find, options like -maxdepth can often appear before paths.
    # Let's use the common: find [options] [path] [expression]
    while IFS= read -r -d $'\0' file; do
        files_to_delete_array+=("$file")
    done < <(find . -maxdepth 1 -type f -size "-$find_size_char" -print0)
    # Note: If target_dir_desc was "All non-segregated", the find would be:
    # find . -maxdepth 10 \( -path "./$SEGREGATION_DIR_NAME" -prune \) -o \( -type f -size "-$find_size_char" -print0 \)


    if [ ${#files_to_delete_array[@]} -gt 0 ]; then
        log_info "Found ${#files_to_delete_array[@]} files < $size_val$size_unit for $log_reason ($target_dir_desc). Attempting to delete..."
        # Use xargs with printf for safety with filenames
        if printf "%s\0" "${files_to_delete_array[@]}" | xargs -0 --no-run-if-empty rm; then
            log_info "${#files_to_delete_array[@]} files for $log_reason ($target_dir_desc) deleted successfully."
        else
            log_error "Error occurred while deleting ${#files_to_delete_array[@]} files for $log_reason ($target_dir_desc)."
        fi
    else
        log_info "No files found < $size_val$size_unit for $log_reason ($target_dir_desc) deletion."
    fi
}

_rename_files_external_wrapper() {
    local target_dir="$1"
    local dir_desc="$2"

    log_info "Attempting to rename files in $dir_desc ('$target_dir')..."
    if [ ! -d "$target_dir" ]; then
        log_info "Directory '$target_dir' for renaming does not exist. Skipping."
        return
    fi
    
    # Standard find syntax for checking files in a directory
    if ! find "$target_dir" -maxdepth 1 -type f -print -quit 2>/dev/null | grep -q .; then
        log_info "No files found directly in '$target_dir' to rename. Skipping $dir_desc."
        return
    fi

    if [ ! -f "$RENAMER_SCRIPT_PATH" ]; then log_error "Renamer script not found: '$RENAMER_SCRIPT_PATH'"; return 1; fi
    if [ ! -x "$RENAMER_SCRIPT_PATH" ]; then log_error "Renamer script not executable: '$RENAMER_SCRIPT_PATH'"; return 1; fi
    
    local original_pwd
    original_pwd=$(pwd)
    cd "$target_dir" || { log_error "Could not cd to '$target_dir' for renaming."; cd "$original_pwd"; return 1; }
    
    log_info "Executing renamer script in '$(pwd)'..."
    if "$RENAMER_SCRIPT_PATH"; then
        log_info "File renaming process complete for $dir_desc."
    else
        log_warn "Renamer script execution failed or reported issues for $dir_desc (status: $?)."
    fi
    cd "$original_pwd"
}


_convert_images() {
    local type_name="$1" 
    # $find_pattern_args_str is for the -iname part, e.g. "*.jpg" or "*.webp"
    # $jpeg_or_logic_str is for the specific JPEG \( ... -o ... \) logic
    local name_pattern_str="$2" 
    local jpeg_or_logic_str="$3" # Only used if type_name is JPEG
    local upper_size_limit_mb_str="$4" # e.g., "-1M" for JPEG < 1MiB
    local size_desc_log=""

    if [[ "$type_name" == "JPEG" ]]; then
        size_desc_log=" (>= ${MIN_CONVERSION_SIZE_KIB}KiB and < ${JPEG_MAX_CONVERSION_SIZE_MIB}MiB)"
    else 
        size_desc_log=" (>= ${MIN_CONVERSION_SIZE_KIB}KiB)"
    fi

    log_step "Converting $type_name${size_desc_log} to PNG (Main Directory Only)"
    command -v mogrify >/dev/null 2>&1 || { log_warn "'mogrify' command not found. Skipping $type_name conversion."; return; }
    
    local files_to_convert_array=()
    local find_cmd # Will build this string

    # Base find command for "Main Directory Only"
    # Using find [options] [path] [expressions] which is common for GNU find
    find_cmd="find . -maxdepth 1 -type f"

    if [[ "$type_name" == "JPEG" ]]; then
        # $jpeg_or_logic_str should be like: \( -iname "*.jpg" -o -iname "*.jpeg" \)
        find_cmd+=" $jpeg_or_logic_str"
    else
        # $name_pattern_str should be like "*.webp"
        find_cmd+=" -iname \"$name_pattern_str\""
    fi
    
    find_cmd+=" -size +$((MIN_CONVERSION_SIZE_KIB - 1))k"

    if [[ -n "$upper_size_limit_mb_str" ]]; then
        # $upper_size_limit_mb_str is like "-1M" (meaning < 1M)
        find_cmd+=" -size $upper_size_limit_mb_str"
    fi
    
    find_cmd+=" -print0"

    log_info "DEBUG: Find command for $type_name: $find_cmd"

    # Populate the array using the constructed find command
    # Using eval here is safer as find_cmd is carefully constructed.
    while IFS= read -r -d $'\0' file; do
        files_to_convert_array+=("$file")
    done < <(eval "$find_cmd")


    if [ ${#files_to_convert_array[@]} -eq 0 ]; then
        log_info "No $type_name files found in Main Directory matching conversion criteria."
        return
    fi

    log_info "Converting ${#files_to_convert_array[@]} $type_name file(s) to PNG (Parallel jobs: $PARALLEL_JOBS)..."
    printf "%s\0" "${files_to_convert_array[@]}" | parallel -0 --bar -P "$PARALLEL_JOBS" _convert_image_worker {}
    log_info "$type_name to PNG conversion pass complete for Main Directory."
}

_remove_metadata() {
    log_step "Metadata Removal - Comprehensive Scrub (exiftool - All Dirs)"
    if command -v exiftool >/dev/null 2>&1; then
        if ! find . -maxdepth 10 -type f -print -quit 2>/dev/null | grep -q .; then # Check reasonably deep
            log_info "No files found to process for exiftool metadata removal."
            return
        fi
        log_info "Attempting to strip all remaining metadata with 'exiftool -all= -overwrite_original -r -P -q -q .'"
        log_info "This may take some time depending on the number and type of files..."
        if nice -n 10 ionice -c 2 -n 7 exiftool -all= -overwrite_original -r -P -q -q .; then
            log_info "exiftool metadata stripping complete."
        else
            log_warn "exiftool processing finished, possibly with non-critical errors (status: $?). Some metadata may remain on certain files."
        fi
    else
        log_warn "'exiftool' command not found. Skipping Stage 2 (comprehensive) metadata removal."
    fi
}

_remove_duplicates_fdupes() {
    log_step "Removing Duplicate Files (fdupes - All Dirs)"
    command -v fdupes >/dev/null 2>&1 || { log_warn "'fdupes' command not found. Skipping duplicate removal."; return; }
    
    if ! find . -maxdepth 10 -type f -print -quit 2>/dev/null | grep -q .; then
        log_info "No files found to process for duplicate removal."
        return
    fi

    log_info "Running 'fdupes -r -d -N .' (recursive, delete non-first duplicates, no prompt)..."
    if nice -n 10 ionice -c 2 -n 7 fdupes -r -d -N .; then
        log_info "fdupes duplicate removal process completed."
    else
        local fdupes_status=$?
        if [[ $fdupes_status -ne 0 ]]; then
             log_warn "fdupes process reported issues or was interrupted (exit status: $fdupes_status)."
        fi
    fi
}

# --- Main Execution ---
main() {
    log_step "Media Optimizer Suite Initialized (v3.0)"
    local overall_start_time=$SECONDS
    local segregation_dir_abs_path 
    segregation_dir_abs_path="$(pwd)/$SEGREGATION_DIR_NAME"

    _create_backup || { log_error "Critical: Backup step failed. Aborting all further operations."; exit 1; }
    _remove_duplicates_fdupes
    _process_archives # Uses array population for parallel
    _segregate_small_files # Uses array population

    _prompt_for_min_file_size
    if (( MIN_FILE_SIZE_FOR_DELETION_BYTES > 0 )); then
        _delete_files_smaller_than "$MIN_FILE_SIZE_FOR_DELETION_KIB" "KiB" \
            "user-defined cleanup" "Main Directory Only" # Uses array population
    else
        log_info "Skipping user-defined small file deletion (Main Dir) as threshold is 0."
    fi

    _remove_duplicates_fdupes
    
    log_step "Renaming Files"
    _rename_files_external_wrapper "." "Main Directory"
    if [ -d "$segregation_dir_abs_path" ]; then 
        _rename_files_external_wrapper "$segregation_dir_abs_path" "$SEGREGATION_DIR_NAME Directory"
    else
        log_info "Segregation directory '$segregation_dir_abs_path' not found for renaming, skipping."
    fi

    # For _convert_images:
    # Arg1: Type Name (JPEG/WEBP)
    # Arg2: Simple name pattern (e.g., "*.webp")
    # Arg3: Complex logic string for JPEG (e.g., '\( -iname "*.jpg" -o -iname "*.jpeg" \)')
    # Arg4: Upper size limit string (e.g., "-1M")
    _convert_images "JPEG" "*.jpg" '\( -iname "*.jpg" -o -iname "*.jpeg" \)' "-${JPEG_MAX_CONVERSION_SIZE_MIB}M"
    _convert_images "WEBP" "*.webp" "" "" # No complex logic, no upper MiB limit string for webp here

    _remove_metadata

    _delete_files_smaller_than "$FINAL_DELETION_THRESHOLD_MIB" "MiB" \
        "final small file cleanup" "Main Directory Only" # Uses array population

    _remove_duplicates_fdupes

    local overall_duration=$((SECONDS - overall_start_time))
    log_step "All media processing tasks complete."
    log_info "Files smaller than ${SEGREGATION_THRESHOLD_KIB}KiB (if any) were moved to './$SEGREGATION_DIR_NAME/' for manual review."
    log_info "These segregated files were renamed and had metadata scrubbed, but were NOT converted or deleted by size thresholds (beyond initial segregation)."
    log_info "Total execution time: $overall_duration seconds."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
