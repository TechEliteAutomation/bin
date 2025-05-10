#!/bin/bash
OUTPUT_FILE="/home/u/output.mp4"

ffmpeg -f x11grab -framerate 30 -i :0.0 \
       -f pulse -i alsa_output.pci-0000_03_00.6.analog-stereo.monitor \
       -c:v libx264 -preset ultrafast -crf 18 \
       -c:a aac -b:a 128k \
       "$OUTPUT_FILE"
