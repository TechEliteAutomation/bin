import glob
import os

def find_latest_report_file(pattern_prefix, extension=".txt", search_path="."):
    glob_pattern = os.path.join(search_path, f"{pattern_prefix}*{extension}")
    list_of_files = glob.glob(glob_pattern)
    latest_file = max(list_of_files, key=os.path.getctime)
    print(f"Found latest report: {latest_file}")
    return latest_file

def read_file_content(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    print(f"Read content from: {filepath}")
    return content

def save_html_output(html_content, filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"HTML analysis saved to: {filepath}")
    return True # Kept for logical flow if needed, though not strictly error handling
