#!/bin/bash
# Optimized file processing script

# Function for displaying process steps
log_step() {
    echo "==> $1"
}

# Function for completion messages
log_complete() {
    echo "    Complete."
}

# Function for EXIF data removal
remove_exif() {
    log_step "Removing EXIF data"
    exiftool -all= -overwrite_original -r .
    log_complete
}

# Function for removing duplicates
remove_duplicates() {
    log_step "Removing duplicates"
    rmlint
    ./rmlint.sh -d
    rm -f rmlint.json
    log_complete
}

# Main execution
log_step "File processor initialized"

# Process archives
log_step "Unzipping and deleting archives"
find . -name "*.zip" -type f -exec unzip -B {} \; -exec rm {} \;
log_complete

# Remove small files
log_step "Deleting all files less than 25k"
find . -maxdepth 1 -type f -size -25k -delete
log_complete

# First duplicate removal
remove_duplicates

# Rename files
log_step "Renaming all files"
/home/u/s/bin/file.ren.sh
log_complete

# First EXIF removal
remove_exif

# Simple WebP to PNG conversion with parallel processing
log_step "Converting WebP files to PNG"
find . -type f -name "*.webp" -print0 | xargs -0 -I{} -P $(nproc) bash -c '
    file="$1"
    if magick "$file" "${file%.webp}.png"; then
        rm "$file"
        echo "    Converted $file to PNG"
    else
        echo "    Failed to convert $file to PNG"
    fi
' -- {}
log_complete

# JPEG to PNG conversion
log_step "Converting JPEGs less than 1MiB to PNG"
find . -type f -name "*.jpg" -size -2M -print0 | xargs -0 -I{} -P $(nproc) bash -c '
    file="$1"
    if mogrify -format png "$file"; then
        rm "$file"
        echo "    Converted $file to PNG"
    else
        echo "    Failed to convert $file"
    fi
' -- {}
log_complete

# Second EXIF removal
remove_exif

# Second duplicate removal
remove_duplicates

# Final message
log_step "File processing complete"

# Commented out section preserved for reference
# log_step "Removing all files less than 1MiB"
# find . -maxdepth 1 -type f -size -2M -delete
# log_complete
