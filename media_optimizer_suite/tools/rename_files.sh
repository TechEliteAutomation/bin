#!/bin/bash
#
# Script Name: rename_files.sh
# Description: Renames files in the current directory to an 8-digit random number
#              followed by an extension determined by their MIME type.
#              Operates on files at maxdepth 1 (current directory only).
# Version: 1.1
# Author: TechEliteAutomation.com

set -euo pipefail

# Function to get common extensions from MIME types
# Add or modify types as needed for your specific use cases.
_get_extension_from_mime() {
    local mime_type="$1"
    case "$mime_type" in
		"application/json") echo ".json" ;;
        "application/msword") echo ".doc" ;;
        "application/pdf") echo ".pdf" ;;
        "application/vnd.oasis.opendocument.text") echo ".odt" ;;
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") echo ".xlsx" ;;
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document") echo ".docx" ;;
        "application/vnd.rar") echo ".rar" ;; # modern `file` often shows this
        "application/x-rar-compressed") echo ".rar" ;; # older `file`
        "application/zip") echo ".zip" ;;
        "audio/mpeg") echo ".mp3" ;;
        "audio/aac") echo ".aac" ;;
        "audio/ogg") echo ".ogg" ;;
        "audio/wav") echo ".wav" ;;
        "audio/x-wav") echo ".wav" ;;
        "font/ttf") echo ".ttf" ;;
        "font/otf") echo ".otf" ;;
		"image/avif") echo ".avif" ;;
        "image/bmp") echo ".bmp" ;;
        "image/gif") echo ".gif" ;;
        "image/jpeg") echo ".jpg" ;;
        "image/png") echo ".png" ;;
        "image/svg+xml") echo ".svg" ;;
        "image/webp") echo ".webp" ;;
        "image/vnd.microsoft.icon") echo ".ico" ;;
        "message/rfc822") echo ".eml" ;;
        "text/html") echo ".html" ;;
        "text/plain") echo ".txt" ;;
        "text/csv") echo ".csv" ;;
        "video/3gpp") echo ".3gp" ;;
        "video/mp4") echo ".mp4" ;;
        "video/quicktime") echo ".mov" ;;
        "video/webm") echo ".webm" ;;
        "video/x-m4v") echo ".m4v" ;;
        "video/x-matroska") echo ".mkv" ;;
        "video/x-msvideo") echo ".avi" ;;
        *) echo "" ;; # Return empty if no match found or unknown
    esac
}

_main_renamer() {
    echo "    Starting filename standardization (8-digit numeric + MIME extension)..."
    local processed_count=0
    local skipped_count=0
    local files_processed_on_line=0
    local readonly SCRIPT_BASENAME=$(basename "$0")

    # Process files safely, even with special characters in names
    # Operates only on files in the current directory (maxdepth 1)
    find . -maxdepth 1 -type f -print0 | while IFS= read -r -d $'\0' current_file_path; do
        # Get just the filename for logging, remove './' prefix if present
        original_filename="${current_file_path#./}"

        # Basic safeguard: skip this script itself.
        if [[ "$original_filename" == "$SCRIPT_BASENAME" ]]; then
            continue
        fi
        # Add similar check if main script could be in CWD and you want to skip it:
        # if [[ "$original_filename" == "process_media.sh" ]]; then continue; fi


        mime_type=$(file -b --mime-type "$current_file_path")
        extension=$(_get_extension_from_mime "$mime_type")

        if [ -z "$extension" ]; then
            # Add a newline if dots were being printed on the previous line
            if (( files_processed_on_line > 0 )); then echo; files_processed_on_line=0; fi
            echo "    WARNING: Skipping '$original_filename': No known extension for MIME '$mime_type'."
            skipped_count=$((skipped_count + 1))
            continue
        fi

        new_full_name=""
        # Loop to find a unique new filename (try up to 20 times)
        for _ in $(seq 1 20); do
            candidate_base_name=$(head /dev/urandom | tr -dc '0-9' | head -c8)
            candidate_full_name="${candidate_base_name}${extension}"
            
            # Check if the candidate name (relative to current dir) already exists
            if [ ! -e "./$candidate_full_name" ]; then
                new_full_name="$candidate_full_name"
                break
            fi
        done

        if [ -z "$new_full_name" ]; then
            if (( files_processed_on_line > 0 )); then echo; files_processed_on_line=0; fi
            echo "    WARNING: Failed to find unique name for '$original_filename' after multiple attempts. Skipping."
            skipped_count=$((skipped_count + 1))
            continue
        fi

        # Ensure we are actually renaming to a different name
        if [ "$original_filename" != "$new_full_name" ]; then
            mv -- "$current_file_path" "./$new_full_name"
            echo -n "." # Print a dot for progress
            files_processed_on_line=$((files_processed_on_line + 1))
            if (( files_processed_on_line >= 80 )); then
                echo # Newline every 80 files
                files_processed_on_line=0
            fi
            processed_count=$((processed_count + 1))
        else
            # File already has the target name or no change needed.
            # This is counted as skipped for simplicity in summary.
            skipped_count=$((skipped_count + 1))
        fi
    done

    # Final newline if dots were printed and line wasn't full
    if (( files_processed_on_line > 0 )); then echo; fi

    echo "    Filename standardization complete. Processed: $processed_count, Skipped/No-action: $skipped_count."
}

# Script execution starts here if run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    _main_renamer
fi
