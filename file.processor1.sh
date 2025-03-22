#!/bin/bash
# Highly optimized file processing script
# Minimizes redundancy and maximizes performance

# Enable bash error handling
set -e

# Function for concise logging
log() {
    echo "[$(date +%T)] $1"
}

# Main execution block
log "Starting file processing"

# Process archives once and remove - combined operation
if find . -name "*.zip" -type f | grep -q .; then
    log "Processing archives"
    find . -name "*.zip" -type f -exec unzip -B -o {} \; -exec rm {} \;
fi

# Run renaming script (kept as dependency)
log "Renaming files"
/home/u/s/bin/file.ren.sh

# Combined format conversion with parallel processing
# Convert both WebP and small JPGs in a single pass
log "Converting files (WebP→PNG, small JPG→PNG)"
{
    find . -type f -name "*.webp" -print0
    find . -type f -name "*.jpg" -size -2M -print0
} | xargs -0 -r -P "$(nproc)" -I{} bash -c '
    file="$1"
    ext="${file##*.}"
    base="${file%.*}"
    target="${base}.png"
    
    # Use appropriate conversion method based on file extension
    if [ "$ext" = "webp" ]; then
        if magick "$file" "$target"; then
            rm "$file"
        fi
    elif [ "$ext" = "jpg" ]; then
        if mogrify -format png "$file"; then
            rm "$file"
        fi
    fi
' -- {}

# Single EXIF removal pass after all conversions
log "Removing EXIF data"
exiftool -all= -overwrite_original -r .

# Single duplicate removal pass after all operations
log "Removing duplicates"
rmlint --types="duplicates" --output-handler=summary:stdout
if [ -f rmlint.sh ]; then
    ./rmlint.sh -d
    rm -f rmlint.json rmlint.sh
fi

log "File processing complete"
