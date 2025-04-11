#!/bin/bash

# --- Configuration ---
PIPER_EXE="/usr/bin/piper-tts"
PIPER_MODEL="/home/u/s/tts/en_GB-alan-medium.onnx" # <-- Update if needed
PAPLAY_ARGS="--raw --rate=22050 --format=s16le --channels=1"
PANDOC_ARGS="--to=plain --wrap=none"
# --- End Configuration ---

# Check if a markdown file was provided
if [ -z "$1" ]; then
  echo "Usage: $0 <path_to_markdown_file.md>"
  exit 1
fi

MARKDOWN_FILE="$1"

# Check if files/executables exist (basic checks)
# ... (Include checks from previous script version) ...
if [ ! -f "$MARKDOWN_FILE" ]; then
  echo "Error: Markdown file not found: $MARKDOWN_FILE"
  exit 1
fi
if [ ! -x "$PIPER_EXE" ]; then
  echo "Error: Piper executable not found or not executable: $PIPER_EXE"
  exit 1
fi
if [ ! -f "$PIPER_MODEL" ]; then
  echo "Error: Piper model file not found: $PIPER_MODEL"
  exit 1
fi
command -v pandoc >/dev/null 2>&1 || { echo >&2 "Error: 'pandoc' command not found. Please install it (sudo pacman -S pandoc)."; exit 1; }
command -v sed >/dev/null 2>&1 || { echo >&2 "Error: 'sed' command not found. This is unexpected on Linux."; exit 1; }
command -v paplay >/dev/null 2>&1 || { echo >&2 "Error: 'paplay' command not found. Is PulseAudio or PipeWire-Pulse installed and running?"; exit 1; }
# ---

echo "Reading and cleaning '$MARKDOWN_FILE'..."

# Execute the pipeline with cleaning
pandoc $PANDOC_ARGS "$MARKDOWN_FILE" | \
sed -e 's/[][*_`#~()]//g' \
    -e 's/^[[:space:]]*[-*+]\s\+//' \
    -e 's/^[[:space:]]*[0-9]\+\.\s\+//' \
    -e 's/ \+/ /g' | \
"$PIPER_EXE" --model "$PIPER_MODEL" --output_file - | \
paplay $PAPLAY_ARGS

echo "Finished reading."
