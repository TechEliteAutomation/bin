#!/usr/bin/env python3

import os
import shutil
import re
import datetime
import logging
import zipfile
from pathlib import Path
from typing import Optional, Tuple, List

# --- Script Configuration (User Modify These) ---
# True: Show what would be renamed without actual changes.
# False: Perform actual renaming. HIGHLY RECOMMENDED TO RUN WITH True FIRST.
DRY_RUN_MODE = False

# True: Create a ZIP backup of the directory (to ~/.bak/) before renaming (if DRY_RUN_MODE is False).
# False: Skip backup. EXTREMELY RISKY if DRY_RUN_MODE is also False.
ENABLE_BACKUP = True

# True: Enable verbose logging (DEBUG level).
# False: Standard logging (INFO level).
VERBOSE_LOGGING = False

# --- Library Imports & Checks ---
try:
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: BeautifulSoup4 not found. This script needs it to process HTML. Please install: pip install beautifulsoup4")
    BeautifulSoup = None # Script will exit if not available

try:
    import google.generativeai as genai
    from google.api_core.exceptions import GoogleAPIError # To catch specific API errors
except ImportError:
    print("ERROR: google-generativeai library not found. This script needs it. Please install: pip install google-generativeai")
    genai = None # Script will exit if not available
    GoogleAPIError = None # type: ignore

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass # python-dotenv is optional

# --- Core Configuration ---
MAX_FILENAME_LENGTH = 50
BACKUP_SUFFIX = "_backup.zip"
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
# For HTML, sending a bit more might be useful for context, especially if titles are generic.
MAX_CONTENT_PREVIEW_FOR_GEMINI = 15000 # Increased slightly for HTML focus

# Setup logging
logging.basicConfig(level=logging.DEBUG if VERBOSE_LOGGING else logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)

# --- Helper Functions ---
def sanitize_filename(name_str: Optional[str]) -> str:
    if not name_str: return "untitled_html_from_ai" # More specific default
    name_str = str(name_str) 
    name_str = re.sub(r'[<>:"/\\|?*\x00-\x1F\n\r\t]', '', name_str)
    name_str = name_str.replace(' ', '_')
    name_str = re.sub(r'_+', '_', name_str)
    name_str = name_str.lower()
    name_str = name_str.strip('_.')
    if len(name_str) > MAX_FILENAME_LENGTH:
        name_str = name_str[:MAX_FILENAME_LENGTH]
        if '_' in name_str and name_str.count('_') > 1:
             name_str = name_str.rsplit('_', 1)[0] 
        name_str = name_str.strip('_.')
    if not name_str: return "sanitized_untitled_html"
    return name_str

def get_unique_filepath(directory: Path, base_name: str, extension: str) -> Path:
    counter = 1
    new_stem = base_name
    ext_with_dot = ('.' + extension) if extension and not extension.startswith('.') else extension
    new_filepath = directory / f"{new_stem}{ext_with_dot}"
    while new_filepath.exists():
        new_stem = f"{base_name}_{counter}"
        new_filepath = directory / f"{new_stem}{ext_with_dot}"
        counter += 1
    return new_filepath

# --- Content Extraction for HTML ---
def extract_html_content_for_ai(filepath: Path) -> Optional[str]:
    """Extracts key textual content from an HTML file for AI processing."""
    if not BeautifulSoup: # Should have been caught at startup, but good check
        logger.error("BeautifulSoup library is not available. Cannot parse HTML.")
        return None
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            raw_html = f.read()
        
        soup = BeautifulSoup(raw_html, 'html.parser')
        
        title_tag_text = soup.title.string.strip() if soup.title and soup.title.string else ""
        
        # Try to get main content text, then fallback
        body_text_parts = []
        for tag_name in ['main', 'article', 'section']: # Prioritize semantic tags
            for tag in soup.find_all(tag_name):
                body_text_parts.append(tag.get_text(separator=' ', strip=True))
        
        if not body_text_parts and soup.body: # Fallback to whole body if no main/article/section
            body_text_parts.append(soup.body.get_text(separator=' ', strip=True))

        body_text = ' '.join(' '.join(part.split()) for part in body_text_parts) # Normalize whitespace

        # Construct the content string for the AI
        ai_content_parts = []
        if title_tag_text:
            ai_content_parts.append(f"HTML Document Title: {title_tag_text}")
        
        # Add headings for context
        for h_level in range(1, 4): # h1, h2, h3
            headings = soup.find_all(f'h{h_level}')
            if headings:
                h_text = ", ".join(h.get_text(strip=True) for h in headings[:3]) # First 3 of each level
                if h_text:
                    ai_content_parts.append(f"Key H{h_level} Headings: {h_text}")
        
        if body_text:
            ai_content_parts.append(f"Key Body Content Snippet:\n{body_text}")
        elif not title_tag_text and not ai_content_parts: # If nothing substantial found, use raw start
            logger.info(f"Could not find title, headings or significant body text in {filepath.name}. Using raw HTML start.")
            ai_content_parts.append(f"Raw HTML content start:\n{raw_html[:2000]}") # Use a smaller portion of raw

        text_content = "\n\n".join(ai_content_parts)

    except Exception as e:
        logger.warning(f"Could not extract content from HTML file {filepath}: {e}")
        return None
    
    if text_content and len(text_content) > MAX_CONTENT_PREVIEW_FOR_GEMINI:
        text_content = text_content[:MAX_CONTENT_PREVIEW_FOR_GEMINI] + f"\n[...content truncated at {MAX_CONTENT_PREVIEW_FOR_GEMINI} chars...]"
    elif not text_content or not text_content.strip():
        logger.info(f"No meaningful text content extracted from HTML {filepath.name} after processing.")
        return None
    return text_content

# --- Name Suggestion via Gemini ---
def suggest_name_via_gemini(text_content: str, original_filename: str) -> Optional[str]:
    """Suggests a filename for an HTML file using the Gemini API."""
    if not genai or not GEMINI_API_KEY: return None # Should be caught earlier

    try:
        model = genai.GenerativeModel(os.environ.get("GEMINI_MODEL_NAME", 'gemini-2.0-flash'))
        prompt = (
            f"You are an expert file naming assistant. Based on the following HTML content summary from a file originally named '{original_filename}', "
            f"suggest an optimal new base filename (without the .html extension).\n"
            f"Requirements for the new base filename:\n"
            f"1. All lowercase.\n"
            f"2. Use underscores `_` for spaces.\n"
            f"3. Maximum {MAX_FILENAME_LENGTH} characters.\n"
            f"4. Highly descriptive of the HTML page's primary topic or purpose.\n"
            f"5. Avoid generic terms like 'webpage', 'html_document', 'index' unless truly generic.\n"
            f"6. Output ONLY the suggested base filename. For example: 'company_about_us_page' or 'product_features_overview'\n\n"
            f"HTML Content Summary:\n```text\n{text_content}\n```\n"
            f"Suggested base filename:"
        )
        logger.debug(f"Sending prompt to Gemini for {original_filename} (content len {len(text_content)})")
        generation_config = genai.types.GenerationConfig(temperature=0.2, top_p=0.9) # Slightly more deterministic
        
        response = model.generate_content(
            prompt,
            generation_config=generation_config
        )
        
        if response.parts:
            suggested_base_name = response.text.strip().replace("```", "").replace("`", "").strip()
            logger.info(f"Gemini suggested for {original_filename}: '{suggested_base_name}'")
            # Stricter validation for typical filename characters
            if not suggested_base_name or not re.match(r"^[a-z0-9_]+(?:_[a-z0-9]+)*$", suggested_base_name):
                logger.warning(f"Gemini suggestion '{suggested_base_name}' for {original_filename} invalid after cleaning. Ignoring.")
                return None
            return suggested_base_name
        else:
            logger.warning(f"Gemini returned no usable parts for {original_filename}.")
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                logger.warning(f"Gemini prompt feedback for {original_filename}: {response.prompt_feedback}")
            return None

    except GoogleAPIError as e: # Catch specific API errors
        logger.error(f"Gemini API error for {original_filename}: {e}. Details: {getattr(e, 'message', str(e))}")
    except Exception as e:
        logger.error(f"Unexpected error calling Gemini API for {original_filename}: {e}", exc_info=VERBOSE_LOGGING)
    return None

# --- Main Processing Logic ---
def backup_directory_zip(source_dir_path: Path) -> Optional[Path]:
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    user_home_dir = Path.home()
    base_backup_dir = user_home_dir / ".bak" 
    try:
        base_backup_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error(f"Could not create base backup directory {base_backup_dir}: {e}"); return None

    backup_filename = f"{source_dir_path.name}_{timestamp}{BACKUP_SUFFIX}" 
    backup_path = base_backup_dir / backup_filename
    
    try:
        logger.info(f"Backing up '{source_dir_path.name}' (HTML files only) to '{backup_path}'...")
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zipf:
            for root_str, dirnames, files_in_zip in os.walk(source_dir_path):
                root = Path(root_str)
                script_name = Path(__file__).name
                # Exclude common dev/cache/system dirs
                excluded_dirs = ['__pycache__', '.git', '.vscode', '.idea', '.bak', 'node_modules', 'venv', 'env', '.DS_Store']
                dirnames[:] = [d for d in dirnames if not d.startswith('.') and d not in excluded_dirs]
                
                # Only add HTML files to the backup
                html_files_to_add = [
                    f for f in files_in_zip 
                    if (f.lower().endswith(".html") or f.lower().endswith(".htm")) 
                    and f != script_name 
                    and not f.endswith(BACKUP_SUFFIX)
                ]

                for file_to_add in html_files_to_add:
                    file_path = root / file_to_add
                    arcname = file_path.relative_to(source_dir_path)
                    zipf.write(file_path, arcname)
        logger.info(f"Backup of HTML files successful: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"ZIP Backup failed for {source_dir_path.name}: {e}")
        if backup_path.exists():
            try: os.remove(backup_path)
            except OSError: pass
        return None

def gather_rename_suggestions_html(target_dir_path: Path) -> List[Tuple[Path, str, str]]:
    suggestions: List[Tuple[Path, str, str]] = []
    if not genai or not GEMINI_API_KEY: return suggestions # Handled at startup
    if not BeautifulSoup: return suggestions # Handled at startup

    try:
        genai.configure(api_key=GEMINI_API_KEY) 
        logger.info("Gemini API configured.")
    except Exception as e:
        logger.critical(f"Failed to configure Gemini API: {e}. Check API key. Exiting."); return suggestions

    for dirpath_str, dirnames, filenames in os.walk(target_dir_path):
        current_dir = Path(dirpath_str)
        script_name = Path(__file__).name
        excluded_dirs = ['__pycache__', '.git', '.vscode', '.idea', '.bak', 'node_modules', 'venv', 'env', '.DS_Store']
        dirnames[:] = [d for d in dirnames if not d.startswith('.') and d not in excluded_dirs]
        
        html_files_to_process = [
            f for f in filenames 
            if (f.lower().endswith(".html") or f.lower().endswith(".htm"))
            and not f.startswith('.') 
            and f != script_name 
            and not f.endswith(BACKUP_SUFFIX)
        ]
        
        if not html_files_to_process: continue
        logger.info(f"Analyzing HTML files in: {current_dir}")

        for filename in html_files_to_process:
            original_filepath = current_dir / filename
            if not original_filepath.is_file(): continue # Should be redundant due to os.walk
            
            original_stem = original_filepath.stem
            original_extension = original_filepath.suffix # .html or .htm
            
            logger.debug(f"Processing HTML file: {original_filepath}")
            text_content = extract_html_content_for_ai(original_filepath)
            if not text_content:
                logger.info(f"No meaningful content extracted from HTML {original_filepath.name}. Skipping.")
                continue

            ai_suggestion = suggest_name_via_gemini(text_content, original_filepath.name)
            if ai_suggestion:
                suggested_stem = sanitize_filename(ai_suggestion)
                sanitized_original_stem = sanitize_filename(original_stem)
                if not suggested_stem or "untitled_html" in suggested_stem or "sanitized_untitled_html" in suggested_stem :
                    logger.warning(f"AI returned generic/empty name ('{suggested_stem}') for {original_filepath.name}. Skipping.")
                    continue
                if suggested_stem == sanitized_original_stem:
                    logger.info(f"AI name '{suggested_stem}' same as original for {original_filepath.name}.")
                else:
                    suggestions.append((original_filepath, suggested_stem, original_extension))
                    logger.info(f"Proposed AI rename for {original_filepath.name}: '{suggested_stem}{original_extension}'")
            else:
                logger.warning(f"Gemini API no suggestion for HTML {original_filepath.name}. Skipping.")
    return suggestions

def execute_renames(rename_plan: List[Tuple[Path, str, str]], dry_run: bool):
    if not rename_plan: logger.info("No HTML files to rename."); return
    logger.info(f"Preparing to process {len(rename_plan)} HTML file renames.")
    files_renamed_count = 0
    for original_filepath, suggested_stem, original_extension in rename_plan:
        try:
            if not suggested_stem: logger.warning(f"Skipping {original_filepath.name} due to empty stem."); continue
            new_filepath = get_unique_filepath(original_filepath.parent, suggested_stem, original_extension)
            if original_filepath == new_filepath: logger.info(f"Final name for {original_filepath.name} same as original. Skipping."); continue
            
            # Ensure we are only renaming HTML files as a final check
            if not (original_filepath.suffix.lower() == ".html" or original_filepath.suffix.lower() == ".htm"):
                logger.warning(f"Attempted to rename non-HTML file {original_filepath.name} in plan. Skipping this operation for safety.")
                continue

            if dry_run:
                logger.info(f"[DRY RUN] Would rename HTML: '{original_filepath.name}' -> '{new_filepath.name}' in '{original_filepath.parent}'")
                files_renamed_count +=1
            else:
                logger.info(f"Renaming HTML: '{original_filepath}' -> '{new_filepath}'")
                os.rename(original_filepath, new_filepath)
                files_renamed_count += 1
        except Exception as e:
            logger.error(f"Failed to rename HTML '{original_filepath}' to '{suggested_stem}{original_extension}': {e}", exc_info=VERBOSE_LOGGING)
    if dry_run: logger.info(f"[DRY RUN] Completed. Would have attempted {files_renamed_count} HTML renames.")
    else: logger.info(f"Renaming completed. {files_renamed_count} HTML files renamed.")

# --- Main Execution ---
def main():
    # Critical dependency checks at startup
    if not BeautifulSoup:
        logger.critical("BeautifulSoup4 library is required but not found. Please install it ('pip install beautifulsoup4'). Exiting.")
        return
    if not genai: 
        logger.critical("google-generativeai library is required but not found. Please install it. Exiting.")
        return
    if not GEMINI_API_KEY: 
        logger.critical("GEMINI_API_KEY environment variable is not set. Please define it. Exiting.")
        return

    # Quieten overly verbose http client from google libraries if not verbose
    if not VERBOSE_LOGGING: 
        logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)

    target_dir_path = Path('.').resolve()
    logger.info(f"--- Gemini HTML File Namer (Simplified) ---")
    logger.info(f"Processing HTML files in directory: {target_dir_path}")
    logger.info(f"Dry run mode: {'Enabled' if DRY_RUN_MODE else 'Disabled - WILL MAKE CHANGES!'}")
    logger.info(f"Backup (HTML only): {'Enabled (to ~/.bak/)' if ENABLE_BACKUP else 'Disabled'}")
    if VERBOSE_LOGGING: logger.debug(f"Max content preview for AI: {MAX_CONTENT_PREVIEW_FOR_GEMINI} characters")

    if not ENABLE_BACKUP and not DRY_RUN_MODE:
        logger.warning("="*60 + "\nWARNING: Backup is DISABLED and Dry Run is OFF!\n" +
                       "This script will make PERMANENT changes to your HTML files without a backup.\n" + "="*60)
        if input("Are you ABSOLUTELY SURE you want to proceed? (yes/no): ").lower() != 'yes':
            logger.info("Aborting. Enable backup or use dry run."); return
        logger.warning("Proceeding without backup as confirmed by user. GOOD LUCK!")
    
    if ENABLE_BACKUP and not DRY_RUN_MODE:
        backup_zip_path = backup_directory_zip(target_dir_path) # Backs up only HTML files now
        if not backup_zip_path: logger.error("Backup of HTML files failed. Aborting."); return
        logger.info(f"IMPORTANT: HTML files backed up to '{backup_zip_path}'.")
    elif ENABLE_BACKUP and DRY_RUN_MODE:
        logger.info("[DRY RUN] Backup of HTML files to ~/.bak/ would be performed here.")

    rename_suggestions = gather_rename_suggestions_html(target_dir_path)
    if rename_suggestions: 
        execute_renames(rename_suggestions, DRY_RUN_MODE)
    else: 
        logger.info("No HTML files found to process or no valid rename suggestions were generated.")
    logger.info("--- Script finished ---")

if __name__ == "__main__":
    main()
