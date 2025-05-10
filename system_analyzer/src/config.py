import os
from datetime import datetime

SYSTEM_REPORT_SCRIPT_NAME = "generate_system_report.sh"
SYSTEM_REPORT_SCRIPT_PATH = os.path.join("scripts", SYSTEM_REPORT_SCRIPT_NAME)

MD_REPORT_FILENAME = "system_info_report.md"
TXT_REPORT_PATTERN_PREFIX = "system_info_detailed_"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL_NAME = "gemini-2.5-pro-exp-03-25"

REPORTS_DIR = "reports"
HTML_OUTPUT_FILENAME_PREFIX = "gemini_system_analysis_"
_HTML_TS_FORMAT = "%Y-%m-%d_%H-%M-%S"

def get_html_output_filepath():
    timestamp = datetime.now().strftime(_HTML_TS_FORMAT)
    filename = f"{HTML_OUTPUT_FILENAME_PREFIX}{timestamp}.html"
    os.makedirs(REPORTS_DIR, exist_ok=True)
    return os.path.join(REPORTS_DIR, filename)
