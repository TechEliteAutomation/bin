# [TechEliteAutomation.com](https://techeliteautomation.com) - `bin` Repository

This repository contains several deployment-ready Bash and Python scripts designed for system maintenance, file processing, and AI-based responses. Below is a breakdown of each script and its functionality.

## Scripts Overview

### 1. `file.backup.sh`
- Detects and mounts a USB drive.
- Prompts the user to delete existing files.
- Backs up the user's home directory and `.xinitrc` file.
- Uses `rsync` to transfer files efficiently.
- Logs the backup operation.

### 2. `file.processor.sh`
- Unzips and deletes `.zip` archives.
- Removes small files.
- Identifies and deletes duplicate files using `rmlint`.
- Renames files using a custom script (`file.renamer.sh`).
- Removes EXIF metadata.
- Converts file types.

### 3. `file.renamer.sh`
- Renames all files in the current directory with a 10-digit random numeric name.
- Appends correct file extensions based on MIME type detection.

### 4. `gemini.espeak.py`
- Uses the Gemini API to generate AI responses.
- Implements a computational response system with history tracking.
- Converts responses to speech using `espeak-ng`.

### 5. `gemini.gtts.py`
- Similar to `gemini.espeak.py`, but uses `gTTS` for text-to-speech.
- Saves and plays back generated audio.
- Enforces strict logical response formatting.

### 6. `git.sync.sh`
- Synchronizes Git repositories in a specified directory.
- Configures Git user credentials.
- Detects changes, commits with a timestamp, and pushes updates.
- Logs all operations.

### 7. `sys.clean.sh`
- Clears temporary and cache directories.
- Calculates and logs freed disk space.
- Deletes files from `/tmp`, `/var/cache`, and the user's trash directory.

### 8. `sys.report.sh`
- Generates system information reports in Markdown and text formats.
- Logs OS, kernel, CPU, memory, disk, GPU, and network details.
- Outputs system package list and running services.

### 9. `sys.update.sh`
- Updates system packages via `pacman`.
- Updates AUR packages via `yay`.
- Provides verbose output for troubleshooting.

## Usage
Each script can be executed independently using:
```bash
bash script_name.sh  # For Bash scripts
python script_name.py  # For Python scripts
```
Ensure necessary dependencies are installed before execution.

## License
This repository is released under the MIT License.
