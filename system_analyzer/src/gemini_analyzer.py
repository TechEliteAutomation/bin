import google.generativeai as genai
from . import config

def _build_prompt(md_content, txt_content):
    combined_reports = f"""
Markdown Report:
---
{md_content or "Markdown report not available."}
---
Detailed Text Report:
---
{txt_content or "Detailed text report not available."}
---
"""
    prompt = f"""
You are an expert system analyst. Analyze the following Arch Linux system information.
Provide a comprehensive analysis as a single, well-formed HTML document.

The HTML analysis should:
1.  Overview: OS (Arch Linux), Kernel, Hostname, Uptime.
2.  CPU: Model, cores, speed, virtualization.
3.  Memory: Total, used, free, swap.
4.  Disk: Partitions, usage, types.
5.  GPU: If present.
6.  Network: Interface names/states, default route. Note privacy omissions.
7.  Packages/Services: Notable Arch Linux packages (pacman) or systemd services.
8.  Issues: Identify potential problems, bottlenecks, optimizations, security considerations.
9.  Recommendations: Clear next steps for maintenance/improvement for an Arch Linux system.
10. HTML Structure: Use <h1>, <h2>, <p>, <ul>/<ol>, <table>, <code>, <pre>.
11. Output: ONLY the HTML document (<!DOCTYPE html> to </html>).
12. Styling (Solarized Dark Theme - embed CSS in <style> in <head>):
    body {{ background-color: #002b36; color: #839496; font-family: sans-serif; margin: 20px; line-height: 1.6; }}
    h1, h2, h3 {{ color: #268bd2; border-bottom: 1px solid #586e75; padding-bottom: 0.3em; margin-top: 1.5em; }}
    h1 {{ font-size: 2em; }} h2 {{ font-size: 1.5em; }}
    table {{ border-collapse: collapse; width: 95%; margin: 1em auto; box-shadow: 0 2px 3px rgba(0,0,0,0.1); }}
    th, td {{ border: 1px solid #586e75; padding: 10px 12px; text-align: left; }}
    th {{ background-color: #073642; color: #93a1a1; font-weight: bold; }}
    tr:nth-child(even) {{ background-color: #073642; }}
    pre, code {{ background-color: #073642; color: #b58900; padding: 0.2em 0.4em; border-radius: 4px; font-family: 'Courier New', Courier, monospace; }}
    pre {{ padding: 1em; overflow-x: auto; display: block; white-space: pre-wrap; word-wrap: break-word; border: 1px solid #586e75; }}
    p code {{ display: inline; padding: 0.1em 0.3em; }}
    ul, ol {{ margin-left: 25px; padding-left: 0; }} li {{ margin-bottom: 0.5em; }}
    a {{ color: #b58900; text-decoration: none; }} a:hover {{ color: #cb4b16; text-decoration: underline; }}
    .overview-box {{ background-color: #073642; border: 1px solid #586e75; padding: 15px; margin-bottom: 20px; border-radius: 5px; }}
    .recommendations {{ border-left: 3px solid #859900; padding-left: 15px; background-color: #073642; }}
    .issues {{ border-left: 3px solid #dc322f; padding-left: 15px; background-color: #073642; }}

System Information:
{combined_reports}

Generate the HTML analysis now.
"""
    return prompt

def ask_gemini_for_analysis(md_report_content, txt_report_content):
    print(f"Initializing Gemini model: {config.GEMINI_MODEL_NAME}...")
    genai.configure(api_key=config.GEMINI_API_KEY)
    model = genai.GenerativeModel(config.GEMINI_MODEL_NAME)

    prompt = _build_prompt(md_report_content, txt_report_content)
    print("Sending prompt to Gemini for analysis...")

    response = model.generate_content(prompt)
    html_content = response.text.strip()
    print("Successfully received HTML analysis from Gemini.")
    return html_content
