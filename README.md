# [TechEliteAutomation](https://techeliteautomation.com) - `bin` Repository

This repository contains several deployment-ready scripts designed for AI-based responses, system maintenance, and file processing. Below is a breakdown of each script and its functionality.

## Scripts Overview

### `file.backup.sh`
- Detects and mounts a USB drive.
- Prompts the user to delete existing files.
- Backs up the user's home directory and `.xinitrc` file.
- Uses `rsync` to transfer files efficiently.
- Logs the backup operation.

### `file.processor.sh`
- Unzips and deletes `.zip` archives.
- Removes small files.
- Identifies and deletes duplicate files using `rmlint`.
- Renames files using a custom script (`file.renamer.sh`).
- Removes EXIF metadata.
- Converts file types.

### `file.renamer.sh`
- Renames all files in the current directory with a 10-digit random numeric name.
- Appends correct file extensions based on MIME type detection.

### `gemini.espeak.py`
- Uses the Gemini API to generate AI responses.
- Implements a computational response system with history tracking.
- Converts responses to speech using `espeak-ng`.

### `gemini.espeak_and_piper.py`
- Uses the Gemini API to generate AI responses.
- Implements a computational response system with history tracking.
- Converts responses to speech using `espeak-ng` and `Piper`, a fast and local text to speech system.

### `gemini.gtts.py`
- Similar to `gemini.espeak.py`, but uses `gTTS` for text-to-speech.
- Saves and plays back generated audio.
- Enforces strict logical response formatting.

### 'gemini.item_descriptions.py'
- Parses basic product details from input text.
- Generates descriptions based on Amazon guidelines (via prompt).
- Performs basic length validation.
- Requires a Google AI API key (managed via `.env`).

### `git.sync.sh`
- Synchronizes Git repositories in a specified directory.
- Configures Git user credentials.
- Detects changes, commits with a timestamp, and pushes updates.
- Logs all operations.

### `screen.record.sh`
- Captures full screen video and audio using FFmpeg.
- Records screen at 30 FPS with high-quality video and audio settings.
- Saves output to a pre-defined MP4 file.
- Utilizes x11grab for screen capture and pulse audio for sound recording.

### `sys.clean.sh`
- Clears temporary and cache directories.
- Calculates and logs freed disk space.
- Deletes files from `/tmp`, `/var/cache`, and the user's trash directory.

### `sys.report.sh`
- Generates system information reports in markdown and text formats.
- Logs OS, kernel, CPU, memory, disk, GPU, and network details.
- Outputs system package list and running services.

### `sys.update.sh`
- Updates system packages via `pacman`.
- Updates AUR packages via `yay`.
- Provides verbose output for troubleshooting.

### `yt.wl.js`
- Iterates through YouTube 'Watch Later' videos, removing them automatically.
- Adds a floating control panel for easy activation.
- Implements adaptive DOM selectors for reliability.
- Displays real-time status updates during execution.

## Usage
Each script (with the exception of yt.wl.js) can be executed independently using:
```bash
bash script_name.sh  # For Bash scripts
python script_name.py  # For Python scripts
```
Ensure necessary dependencies are installed before execution.

## License
This repository is released under the MIT License.
