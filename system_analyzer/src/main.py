import os
from . import config
from . import system_report_executor
from . import file_operations
from . import gemini_analyzer

def main():
    print("Starting Arch Linux system analysis process...")
    print(f"Project root (CWD): {os.getcwd()}")

    system_report_executor.run_system_report_script()

    md_report_path = config.MD_REPORT_FILENAME
    txt_report_path = file_operations.find_latest_report_file(
        config.TXT_REPORT_PATTERN_PREFIX, search_path="."
    )

    md_content = file_operations.read_file_content(md_report_path)
    txt_content = file_operations.read_file_content(txt_report_path)

    print("Preparing to contact Gemini for analysis...")
    html_analysis = gemini_analyzer.ask_gemini_for_analysis(md_content, txt_content)

    output_filepath = config.get_html_output_filepath()
    file_operations.save_html_output(html_analysis, output_filepath)
    print(f"Analysis complete. View report at: {os.path.abspath(output_filepath)}")

if __name__ == "__main__":
    main()
