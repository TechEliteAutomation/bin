#!/bin/bash

# Strip extensions & rename using 10 random digits
for file in *; do
if [ -f "$file" ]; then
	new_name=$(head /dev/urandom | base64 | tr -dc 0-9 | head -c10)
	while [ -e "$new_name" ]; do
		new_name=$(head /dev/urandom | base64 | tr -dc 0-9 | head -c10)
    done
mv -- "$file" "$new_name"
fi
done

get_extension() {
    local mime_type=$1
    case $mime_type in
		"application/msword") echo ".doc" ;;
        "application/pdf") echo ".pdf" ;;
        "application/x-rar-compressed") echo ".rar" ;;
        "application/zip") echo ".zip" ;;
        "audio/mpeg") echo ".mp3" ;;
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
        "video/3gpp") echo ".3gp" ;;
        "video/mp4") echo ".mp4" ;;
        "video/webm") echo ".webm" ;;
        "video/x-m4v") echo ".m4v" ;;
        "video/x-msvideo") echo ".avi" ;;
        *) echo "" ;; # Return empty if no match found       
    esac
}

# Loop through all files in the current directory
for file in *; do
    # Check if it is a regular file, not a directory
    if [ -f "$file" ]; then
        
        # Get the MIME type
        mime_type=$(file -b --mime-type "$file")
        
        # Get the extension for this MIME type
        extension=$(get_extension "$mime_type")
        
        # If an extension was found and the file doesn't already have it, append it
        if [ -n "$extension" ] && [[ "$file" != *"$extension" ]]; then
            mv -- "$file" "$file$extension"
            echo "Renamed '$file' to '$file$extension'"
        elif [ -z "$extension" ]; then
            echo "Could not determine extension for '$file' (MIME type: $mime_type)"
        fi
    fi
done
