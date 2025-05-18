#!/bin/bash

# Script to rename subdirectories by prepending a rank based on their total size.
# Ranks from smallest (01) to largest.

# Target directory (default: current directory)
TARGET_DIR="${1:-.}"

# --- Sanity Checks and Initialization ---
if [ ! -d "$TARGET_DIR" ]; then
  echo "Error: Directory '$TARGET_DIR' not found."
  exit 1
fi

# Convert to absolute path for consistency
TARGET_DIR=$(realpath "$TARGET_DIR")

echo "Processing subdirectories in: $TARGET_DIR"
echo "------------------------------------------"

# --- Temporary files for processing ---
TEMP_DIR_LIST=$(mktemp)
SORTED_DIR_LIST=$(mktemp)
trap 'rm -f "$TEMP_DIR_LIST" "$SORTED_DIR_LIST"' EXIT

# --- 1. Collect directory information (size and path) ---
DIR_COUNT=0
echo "Calculating sizes of subdirectories..."

# Use process substitution to avoid subshell issues with the while loop
while IFS= read -r -d $'\0' SUBDIR; do
  # Minimal debug for confirmation
  echo "  Processing directory: '$SUBDIR'"
  
  SIZE_BYTES=$(du -sb "$SUBDIR" | awk '{print $1}')

  if [ -z "$SIZE_BYTES" ]; then
    echo "    Warning: Could not determine size for '$SUBDIR'. Skipping."
    continue
  fi
  
  echo "    Size: $SIZE_BYTES bytes"

  # Store size and full path, tab-separated
  echo -e "$SIZE_BYTES\t$SUBDIR" >> "$TEMP_DIR_LIST"
  ((DIR_COUNT++))
done < <(find "$TARGET_DIR" -mindepth 1 -maxdepth 1 -type d -print0)


if [ "$DIR_COUNT" -eq 0 ]; then
  echo "No subdirectories were found or successfully processed for size."
  exit 0
fi

echo "Successfully calculated sizes for $DIR_COUNT subdirectories."
echo "Total entries in TEMP_DIR_LIST: $(wc -l < "$TEMP_DIR_LIST")"

# --- 2. Determine formatting for rank (leading zeros) ---
MAX_RANK_DIGITS=$(echo -n "$DIR_COUNT" | wc -c)

# --- 3. Sort directories by size (ascending - smallest first) ---
echo "Sorting directories by size (smallest first)..."
# MODIFIED LINE: Changed -k1,1nr to -k1,1n
sort -t$'\t' -k1,1n -k2,2 "$TEMP_DIR_LIST" -o "$SORTED_DIR_LIST"
echo "Sorted list content (head - smallest first):"
head "$SORTED_DIR_LIST"

# --- 4. Rename directories ---
echo "Renaming directories..."
CURRENT_RANK=1
while IFS=$'\t' read -r SIZE ORIGINAL_FULL_PATH; do
  if [ -z "$ORIGINAL_FULL_PATH" ]; then
      continue
  fi

  ORIGINAL_NAME=$(basename "$ORIGINAL_FULL_PATH")
  PARENT_DIR=$(dirname "$ORIGINAL_FULL_PATH")
  FORMATTED_RANK=$(printf "%0${MAX_RANK_DIGITS}d" "$CURRENT_RANK")
  NEW_NAME="${FORMATTED_RANK}_${ORIGINAL_NAME}"
  NEW_PATH="${PARENT_DIR}/${NEW_NAME}"

  echo "------------------------------------------"
  echo "Rank: $CURRENT_RANK, Size: $SIZE bytes, Original: '$ORIGINAL_NAME'"

  if [ "$ORIGINAL_FULL_PATH" == "$NEW_PATH" ]; then
    echo "  Already named correctly as '$NEW_NAME'. No change needed."
  elif [ -e "$NEW_PATH" ]; then
    echo "  Warning: A file or directory named '$NEW_NAME' already exists in '$PARENT_DIR'."
    echo "  Skipping rename of '$ORIGINAL_NAME' to avoid conflict."
  else
    echo "  Renaming to: '$NEW_NAME'"
    if mv -v "$ORIGINAL_FULL_PATH" "$NEW_PATH"; then
      echo "  Successfully renamed."
    else
      echo "  Error: Failed to rename '$ORIGINAL_NAME'."
    fi
  fi

  ((CURRENT_RANK++))
done < "$SORTED_DIR_LIST"

echo "------------------------------------------"
echo "Script finished."
