import subprocess
import os
from . import config

def run_system_report_script():
    script_path = config.SYSTEM_REPORT_SCRIPT_PATH
    print(f"Executing system report script: {script_path}...")

    # Assumes script is executable and 'bash' is available
    process = subprocess.run(
        ["bash", script_path],
        capture_output=True,
        text=True,
        check=True, # Will raise CalledProcessError if script returns non-zero
        cwd="."
    )
    print(f"Script '{script_path}' executed.")
    if process.stdout: print("Script STDOUT:\n", process.stdout)
    if process.stderr: print("Script STDERR (informational):\n", process.stderr) # Bash script might output to stderr for its own reasons
    return True # Assumed success if check=True doesn't raise
