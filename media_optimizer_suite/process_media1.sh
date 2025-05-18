#!/bin/bash
# process_media.sh: Media processing pipeline
# Version: 5.7 (Strict adherence to 3-Phase logic, NO Phase 4)

# --- Script Setup ---
set -e -u -o pipefail
shopt -s nullglob # Globs that match nothing expand to nothing

# --- Configuration ---
SCRIPT_DIR_RESOLVED="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
SCRIPT_DIR="${SCRIPT_DIR_RESOLVED:-$(pwd)}"

RENAMER_SCRIPT_PATH="$SCRIPT_DIR/tools/rename_files.sh"
PARALLEL_JOBS="${MEDIA_PROCESSOR_JOBS:-$(nproc)}"
BACKUP_BASE_DIR="${MEDIA_BACKUP_DIR:-/home/u/.bak}"

ONE_KIB_IN_BYTES=1024
ONE_MIB_IN_BYTES=$((ONE_KIB_IN_BYTES * ONE_KIB_IN_BYTES))
THRESHOLD_100_KIB_IN_BYTES=$((100 * ONE_KIB_IN_BYTES))

SUB_100KIB_DIR_NAME="sub_100KiB_files"
SUB_1MIB_PNG_DIR_NAME="sub_1MiB_files"

# --- Logging Functions ---
_log_generic() { local type="$1"; shift; echo "[$type] $(date '+%Y-%m-%d %H:%M:%S') $1"; }
log_info() { _log_generic "INFO" "    $1"; }
log_warn() { _log_generic "WARN" "    $1"; }
log_error() { _log_generic "ERROR" "   $1" >&2; }
log_step() {
    echo "----------------------------------------------------------------------"; _log_generic "STEP" "$1"
    echo "----------------------------------------------------------------------";
}
export -f _log_generic log_info log_warn log_error

get_file_size_bytes() { stat -c %s "$1" 2>/dev/null || echo 0; }
export -f get_file_size_bytes

_unzip_single_archive_worker() {
    local zip_file="$1"; local target_dir; target_dir=$(dirname "$zip_file")
    local base_zip_file; base_zip_file=$(basename "$zip_file")
    log_info "[UNZIP] Processing: '$base_zip_file'"
    if nice -n 10 ionice -c 2 -n 7 unzip -q -o "$zip_file" -d "$target_dir"; then
        rm "$zip_file"; log_info "[UNZIP] OK: '$base_zip_file' unzipped, original removed."
    else log_error "[UNZIP] FAIL ($?): Could not unzip '$base_zip_file'."; fi
}

_convert_jpg_worker() {
    local jpg_file="$1"; local png_file="${jpg_file%.jpg}.png"
    local base_jpg_file; base_jpg_file=$(basename "$jpg_file")
    log_info "[CONV JPG>PNG] Attempting for '$base_jpg_file'."
    if nice -n 10 ionice -c 2 -n 7 mogrify -format png "$jpg_file"; then
        if [[ -f "$png_file" ]]; then
            log_info "[CONV JPG>PNG] Converted '$base_jpg_file' to '$(basename "$png_file")'."
            if rm "$jpg_file"; then log_info "[CONV JPG>PNG] Original '$base_jpg_file' removed."; else
                log_warn "[CONV JPG>PNG] Failed to remove original '$base_jpg_file'."; fi
        else log_warn "[CONV JPG>PNG] mogrify OK for '$base_jpg_file', but PNG '$png_file' not found."; fi
    else log_error "[CONV JPG>PNG] Failed for '$base_jpg_file' (mogrify status: $?)."; fi
}
export -f _unzip_single_archive_worker _convert_jpg_worker

_create_backup() {
    log_step "Phase 1.2: Creating Full Backup"
    command -v zip >/dev/null 2>&1 || { log_error "'zip' not found."; return 1; }
    mkdir -p "$BACKUP_BASE_DIR" || { log_error "Could not create backup dir: $BACKUP_BASE_DIR"; return 1; }
    local dn; dn=$(basename "$(pwd)"); local ts; ts=$(date +%Y%m%d_%H%M%S)
    local bf="$BACKUP_BASE_DIR/${dn}_backup_${ts}.zip"; log_info "Backing up to: $bf"
    if nice -n 10 ionice -c 2 -n 7 zip -r -q "$bf" .; then log_info "Backup successful: $bf"; else
        log_error "Backup failed (zip status: $?)."; return 1; fi
}

_run_fdupes_recursive() {
    local pass_desc="$1"
    log_step "$pass_desc: Removing Duplicates (fdupes -r .)"
    command -v fdupes >/dev/null 2>&1 || { log_warn "'fdupes' not found. Skipping."; return; }
    if ! find . -maxdepth 10 -type f -print -quit 2>/dev/null | grep -q .; then
        log_info "No files found for $pass_desc duplicate removal."; return
    fi
    log_info "Running 'fdupes -r -d -N .' for $pass_desc..."
    if nice -n 10 ionice -c 2 -n 7 fdupes -r -d -N .; then
        log_info "Fdupes ($pass_desc) completed."; else
        log_warn "Fdupes ($pass_desc) reported issues or was interrupted (status: $?)."; fi
}

_process_archives() {
    log_step "Phase 1.3: Unzipping Archives"
    local archives_found=(); while IFS= read -r -d $'\0' f; do archives_found+=("$f"); done < <(find . -maxdepth 10 -name "*.zip" -type f -print0)
    if [ ${#archives_found[@]} -eq 0 ]; then log_info "No .zip archives found."; return; fi
    log_info "Unzipping ${#archives_found[@]} archive(s)..."
    printf "%s\0" "${archives_found[@]}" | parallel -0 --bar -P "$PARALLEL_JOBS" _unzip_single_archive_worker {}
    log_info "Archive processing complete."
}

_rename_all_files_recursively() {
    local base_process_dir="$1"
    local step_desc="$2"
    log_step "$step_desc: Renaming All Files (Recursive within '$base_process_dir')"
    if [ ! -f "$RENAMER_SCRIPT_PATH" ]; then log_error "Renamer script '$RENAMER_SCRIPT_PATH' not found!"; return 1; fi
    if [ ! -x "$RENAMER_SCRIPT_PATH" ]; then log_error "Renamer script '$RENAMER_SCRIPT_PATH' not executable!"; return 1; fi

    local dirs_to_rename=()
    while IFS= read -r -d $'\0' dir; do dirs_to_rename+=("$dir"); done < <(find "$base_process_dir" -type d -print0)

    for dir_path in "${dirs_to_rename[@]}"; do
        # Skip processing of already segregated directories in the global pass to avoid re-renaming them here
        # Their turn will come if specific processing for them is ever re-added.
        # For now, this function is called globally before segregation.
        if [[ "$dir_path" == "./$SUB_100KIB_DIR_NAME" || "$dir_path" == "./$SUB_1MIB_PNG_DIR_NAME" ]] && [[ "$base_process_dir" == "." ]]; then
            log_info "Skipping rename for already designated segregation path: '$dir_path' during global pass."
            continue
        fi

        log_info "Entering '$dir_path' for renaming ($step_desc)..."
        local original_pwd; original_pwd=$(pwd)
        cd "$dir_path" || { log_warn "Could not cd to '$dir_path'. Skipping."; cd "$original_pwd"; continue; }
        
        local files_exist_in_curr_dir=false
        for item in *; do if [[ -f "$item" ]]; then files_exist_in_curr_dir=true; break; fi; done

        if $files_exist_in_curr_dir; then
            log_info "Executing renamer in '$(pwd)' ($step_desc)..."
            if "$RENAMER_SCRIPT_PATH"; then log_info "Renaming complete for '$dir_path'."; else
                log_warn "Renamer script failed for '$dir_path' (status: $?)."; fi
        else log_info "No files to rename in '$dir_path'."; fi
        cd "$original_pwd"
    done
    log_info "Recursive renaming pass ($step_desc) within '$base_process_dir' complete."
}

_remove_metadata_recursively() {
    local base_process_dir="$1"
    local step_desc="$2"
    log_step "$step_desc: Metadata Removal (exiftool -r on '$base_process_dir')"
    command -v exiftool >/dev/null 2>&1 || { log_warn "'exiftool' not found. Skipping."; return; }
    
    # Check if the base directory itself has files or subdirectories with files before running exiftool -r
    if ! find "$base_process_dir" -mindepth 1 -type f -print -quit 2>/dev/null | grep -q .; then
        log_info "No files found in '$base_process_dir' or its subdirectories for metadata removal."; return
    fi

    log_info "Stripping all metadata with 'exiftool -all= -overwrite_original -r -P -q -q $base_process_dir'"
    if nice -n 10 ionice -c 2 -n 7 exiftool -all= -overwrite_original -r -P -q -q "$base_process_dir"; then
        log_info "Recursive exiftool metadata stripping complete for '$base_process_dir'."; else
        log_warn "Recursive exiftool reported issues for '$base_process_dir' (status: $?)."; fi
}


_segregate_sub_100KiB_files() {
    local seg_100kib_dir_abs_path="$(pwd)/$SUB_100KIB_DIR_NAME"
    log_step "Phase 3.8: Segregating Files < 100KiB to '$SUB_100KIB_DIR_NAME/'"
    mkdir -p "$seg_100kib_dir_abs_path"
    
    local files_to_segregate=()
    while IFS= read -r -d $'\0' file_path_from_find; do
        local file_size; file_size=$(get_file_size_bytes "$file_path_from_find")
        if (( file_size > 0 && file_size < THRESHOLD_100_KIB_IN_BYTES )); then
            files_to_segregate+=("$file_path_from_find")
        fi
    done < <(find . -path "./$SUB_100KIB_DIR_NAME" -prune -o -path "./$SUB_1MIB_PNG_DIR_NAME" -prune -o -type f ! -iname "*.zip" -print0)

    if [ ${#files_to_segregate[@]} -eq 0 ]; then log_info "No files < 100KiB found for segregation."; return; fi

    log_info "Found ${#files_to_segregate[@]} files < 100KiB to move to '$SUB_100KIB_DIR_NAME/'."
    local moved=0; local failed=0
    for file_to_move in "${files_to_segregate[@]}"; do
        local relative_path="${file_to_move#./}"
        local target_path_in_seg_dir="$seg_100kib_dir_abs_path/$relative_path"
        mkdir -p "$(dirname "$target_path_in_seg_dir")"
        if mv --backup=numbered "$file_to_move" "$target_path_in_seg_dir"; then
            ((moved++)); else log_warn "Failed to move '$file_to_move'"; ((failed++)); fi
    done
    log_info "Segregation to '$SUB_100KIB_DIR_NAME/': $moved files moved. $failed failed."
}

_convert_main_dir_jpgs() {
    log_step "Phase 3.9: Converting Main Dir JPGs (<1MiB, >=100KiB) to PNG"
    command -v mogrify >/dev/null 2>&1 || { log_warn "'mogrify' not found. Skipping."; return; }
    local jpgs_to_convert=()
    for jpg_file in ./*.jpg; do
        if [[ -f "$jpg_file" ]]; then
            local file_size; file_size=$(get_file_size_bytes "$jpg_file")
            if (( file_size < ONE_MIB_IN_BYTES && file_size >= THRESHOLD_100_KIB_IN_BYTES )); then
                jpgs_to_convert+=("$jpg_file")
            fi
        fi
    done
    if [ ${#jpgs_to_convert[@]} -eq 0 ]; then log_info "No main dir JPGs in size range for conversion."; return; fi
    log_info "Found ${#jpgs_to_convert[@]} main dir JPGs for conversion."
    printf "%s\0" "${jpgs_to_convert[@]}" | parallel -0 --bar -P "$PARALLEL_JOBS" _convert_jpg_worker {}
    log_info "Main dir JPG conversion pass complete."
}

_segregate_main_dir_pngs() {
    local seg_1mib_dir_abs_path="$(pwd)/$SUB_1MIB_PNG_DIR_NAME"
    log_step "Phase 3.10: Segregating Main Dir PNGs (<1MiB, >=100KiB) to '$SUB_1MIB_PNG_DIR_NAME/'"
    mkdir -p "$seg_1mib_dir_abs_path"
    local pngs_to_move=()
    for png_file in ./*.png; do
        if [[ -f "$png_file" ]]; then
            local file_size; file_size=$(get_file_size_bytes "$png_file")
            if (( file_size < ONE_MIB_IN_BYTES && file_size >= THRESHOLD_100_KIB_IN_BYTES )); then
                pngs_to_move+=("$png_file")
            fi
        fi
    done
    if [ ${#pngs_to_move[@]} -eq 0 ]; then log_info "No main dir PNGs in size range to segregate."; return; fi
    log_info "Found ${#pngs_to_move[@]} main dir PNGs to move."
    local moved=0; local failed=0
    for png_to_move in "${pngs_to_move[@]}"; do
        if mv --backup=numbered "$png_to_move" "$seg_1mib_dir_abs_path/"; then
            ((moved++)); else log_warn "Failed to move '$png_to_move'."; ((failed++)); fi
    done
    log_info "Main dir PNG segregation: $moved moved to '$SUB_1MIB_PNG_DIR_NAME/'. $failed failed."
}

_delete_other_small_files_main_dir() {
    log_step "Phase 3.11: Deleting Other Files (<1MiB, >=100KiB) from Main Dir"
    local files_to_delete=()
    for file in ./*; do
        if [[ -f "$file" ]]; then
            local ext="${file##*.}"; ext="${ext,,}"
            if [[ "$ext" == "jpg" || "$ext" == "png" ]]; then continue; fi
            local file_size; file_size=$(get_file_size_bytes "$file")
            if (( file_size < ONE_MIB_IN_BYTES && file_size >= THRESHOLD_100_KIB_IN_BYTES )); then
                files_to_delete+=("$file"); log_info "Marked for deletion (other type): '$file' (Size: ${file_size}B)"
            fi
        fi
    done
    if [ ${#files_to_delete[@]} -gt 0 ]; then
        log_info "Deleting ${#files_to_delete[@]} other small files from main dir..."
        if printf "%s\0" "${files_to_delete[@]}" | xargs -0 --no-run-if-empty rm; then
            log_info "Deletion of other small files complete."; else
            log_error "Error deleting other small files."; fi
    else log_info "No other small files (non-JPG/PNG, <1MiB, >=100KiB) for deletion in main dir."; fi
}

# --- Main Execution ---
main() {
    log_step "Media Optimizer Suite Initialized (v5.7)"
    local overall_start_time=$SECONDS

    # Phase 1
    _run_fdupes_recursive "Phase 1.1 Pre-Backup"
    _create_backup
    _process_archives
    _run_fdupes_recursive "Phase 1.4 Post-Unzip"

    # Phase 2
    _rename_all_files_recursively "." "Phase 2.5 Global Rename"
    _remove_metadata_recursively "." "Phase 2.6 Global Metadata Scrub"
    _run_fdupes_recursive "Phase 2.7 Post-Global-Rename-Scrub"
    
    # Phase 3
    _segregate_sub_100KiB_files
    _convert_main_dir_jpgs
    _segregate_main_dir_pngs
    _delete_other_small_files_main_dir
    
    # NO PHASE 4 - Script ends after Phase 3 operations.
    # Segregated files are left as-is in their respective directories for manual review.
    
    local overall_duration=$((SECONDS - overall_start_time))
    log_step "All media processing tasks complete (Phases 1-3)."
    log_info "Files < 100KiB (if any) were moved to './$SUB_100KIB_DIR_NAME/' for manual review."
    log_info "Main dir PNGs (<1MiB, >=100KiB) were moved to './$SUB_1MIB_PNG_DIR_NAME/' for manual review."
    log_info "Files >= 1MiB should remain in the main directory."
    log_info "Other files (<1MiB, >=100KiB, non-JPG/PNG) were deleted from the main directory."
    log_info "Total execution time: $overall_duration seconds."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
