#!/bin/bash

echo "File processor initiliazed."

echo "Unzipping and deleting archives..."
unzip -B '*.zip'
rm *.zip
echo "Complete."

echo "Deleting all files less than 25k..."
find . -maxdepth 1 -type f -size -25k -delete
echo "Complete."

echo "Removing duplicates(1)..."
rmlint
./rmlint.sh -d
rm rmlint.json
echo "Complete."

echo "Renaming all files..."
# Renames files according to parameters in file renamer script
/home/u/s/bin/file.renamer.sh
echo "Complete."

# Remove EXIF data
echo "Removing EXIF data(1)..."
exiftool -all= -overwrite_original -r .
echo "Complete."

find . -type f -name "*.webp" -print0 | while IFS= read -r -d '' file; do
    # Check the file type
    file_type=$(identify -format "%m" "$file")
    case "$file_type" in
        WEBP)
            echo "Converting $file to PNG"
            magick "$file" "${file%.webp}.png"
            rm "$file"
            ;;
        GIF)
            echo "Converting $file to GIF"
            magick "$file" "${file%.webp}.gif"
            rm "$file"
            ;;
        *)
            echo "$file is not a WEBP file or is in an unexpected format, skipping."
            ;;
    esac
done

echo "Converting JPEGs less than 1MiB to PNG..."
find . -type f \( -name "*.jpg" \) -size -2M -print0 | while IFS= read -r -d '' file; do
    if mogrify -format png "$file"; then
        rm "$file"
    else
        echo "Failed to convert $file"
    fi
done
echo "Complete."

# Remove EXIF data
echo "Removing EXIF data(2)..."
exiftool -all= -overwrite_original -r .
echo "Complete."

echo "Removing duplicates(2)..."
rmlint
./rmlint.sh -d
rm rmlint.json
echo "Complete."
 
echo "File processing complete."
