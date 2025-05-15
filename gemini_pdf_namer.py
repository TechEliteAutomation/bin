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
DRY_RUN_MODE = False # As per your existing file

# True: Create a ZIP backup of the directory (to ~/.bak/) before renaming (if DRY_RUN_MODE is False).
# False: Skip backup. EXTREMELY RISKY if DRY_RUN_MODE is also False.
ENABLE_BACKUP = True # As per your existing file

# True: Enable verbose logging (DEBUG level).
# False: Standard logging (INFO level).
VERBOSE_LOGGING = False # As per your existing file

# --- Library Imports & Checks ---
try:
    import PyPDF2
    # For encrypted PDFs that PyPDF2 might handle
    try:
        from PyPDF2.errors import PdfReadError, DependencyError
    except ImportError: # Older PyPDF2 might not have specific error types here
        PdfReadError = Exception 
        DependencyError = Exception
except ImportError:
    print("ERROR: PyPDF2 not found. This script needs it to process PDF files. Please install: pip install PyPDF2")
    PyPDF2 = None # Script will exit if not available
    PdfReadError = Exception 
    DependencyError = Exception

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
MAX_CONTENT_PREVIEW_FOR_GEMINI = 10000

# Setup logging
logging.basicConfig(level=logging.DEBUG if VERBOSE_LOGGING else logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)

# --- Helper Functions ---
def sanitize_filename(name_str: Optional[str]) -> str:
    if not name_str: return "untitled_pdf_from_ai" 
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
    if not name_str: return "sanitized_untitled_pdf"
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

# --- Content Extraction for PDF ---
def extract_pdf_content_for_ai(filepath: Path) -> Optional[str]:
    if not PyPDF2: 
        logger.error("PyPDF2 library is not available. Cannot parse PDF files.")
        return None
    
    ai_content_parts = []
    try:
        with open(filepath, 'rb') as f:
            reader = PyPDF2.PdfReader(f)

            if reader.is_encrypted:
                logger.info(f"PDF {filepath.name} is encrypted. Attempting to decrypt with empty password...")
                try:
                    # PyPDF2 > 3.0 uses PasswordType enum
                    # PyPDF2 <= 2.x returns an integer (0 for fail, 1 for user pass, 2 for owner pass)
                    decrypt_result = reader.decrypt('')
                    if hasattr(PyPDF2, 'PasswordType'): # PyPDF2 3.0+
                        if decrypt_result == PyPDF2.PasswordType.OWNER_PASSWORD or decrypt_result == PyPDF2.PasswordType.USER_PASSWORD:
                            logger.info(f"Successfully decrypted {filepath.name} with empty password.")
                        else:
                             logger.warning(f"Could not decrypt {filepath.name} with an empty password. Result: {decrypt_result}")
                             ai_content_parts.append(f"Note: PDF '{filepath.name}' is encrypted and could not be fully decrypted with an empty password.")
                    else: # Older PyPDF2
                        if decrypt_result >= 1:
                            logger.info(f"Successfully decrypted {filepath.name} with empty password (older PyPDF2).")
                        else:
                            logger.warning(f"Could not decrypt {filepath.name} with an empty password (older PyPDF2). Result: {decrypt_result}")
                            ai_content_parts.append(f"Note: PDF '{filepath.name}' is encrypted and could not be fully decrypted with an empty password.")
                except DependencyError as de: 
                    logger.warning(f"Decryption of {filepath.name} failed due to missing dependency: {de}. Install PyCryptodome if AES encrypted.")
                    ai_content_parts.append(f"Note: PDF '{filepath.name}' is encrypted. Decryption failed due to missing dependency ({de}).")
                except Exception as e_decrypt:
                    logger.warning(f"An error occurred during decryption attempt for {filepath.name}: {e_decrypt}")
                    ai_content_parts.append(f"Note: PDF '{filepath.name}' is encrypted. An error occurred during decryption attempt.")

            meta_title = reader.metadata.title.strip() if reader.metadata and reader.metadata.title else None
            if meta_title:
                meta_title = re.sub(r'^(Microsoft Word|PowerPoint Presentation)\s*-\s*', '', meta_title, flags=re.IGNORECASE).strip()
                if meta_title: 
                    ai_content_parts.append(f"PDF Document Title (from metadata): {meta_title}")
            
            num_pages_to_extract = min(len(reader.pages), 5) 
            for i in range(num_pages_to_extract):
                try:
                    page = reader.pages[i]
                    page_text = page.extract_text()
                    if page_text and page_text.strip():
                        ai_content_parts.append(f"--- Page {i+1} Content Snippet ---\n{page_text.strip()}")
                except Exception as page_ex:
                    logger.debug(f"Could not extract text from page {i+1} of {filepath.name}: {page_ex}")
            
            if len(reader.pages) > num_pages_to_extract:
                 ai_content_parts.append(f"[...content from further {len(reader.pages) - num_pages_to_extract} pages truncated...]")

        if not ai_content_parts: 
            logger.info(f"PDF {filepath.name}: No metadata title and no text extracted from pages.")
            return None
        
        text_content = "\n\n".join(ai_content_parts)

    except PdfReadError as e: 
        logger.warning(f"Could not read PDF file {filepath} (possibly corrupted or password protected without empty pass): {e}")
        return None
    except Exception as e:
        logger.warning(f"Could not extract content from PDF file {filepath}: {e}")
        return None
    
    if text_content and len(text_content) > MAX_CONTENT_PREVIEW_FOR_GEMINI:
        text_content = text_content[:MAX_CONTENT_PREVIEW_FOR_GEMINI] + f"\n[...content truncated at {MAX_CONTENT_PREVIEW_FOR_GEMINI} chars...]"
    elif not text_content or not text_content.strip(): 
        logger.info(f"No meaningful text content extracted from PDF {filepath.name} after processing.")
        return None
    return text_content

# --- Name Suggestion via Gemini ---
def suggest_name_via_gemini(text_content: str, original_filename: str) -> Optional[str]:
    if not genai or not GEMINI_API_KEY: return None

    try:
        model = genai.GenerativeModel(os.environ.get("GEMINI_MODEL_NAME", 'gemini-2.0-flash'))
        prompt = (
            f"You are an expert file naming assistant. Based on the following summary of a PDF document originally named '{original_filename}', "
            f"suggest an optimal new base filename (without the .pdf extension).\n"
            f"The summary may include metadata (like title) and text snippets from the first few pages.\n"
            f"Requirements for the new base filename:\n"
            f"1. All lowercase.\n"
            f"2. Use underscores `_` for spaces.\n"
            f"3. Maximum {MAX_FILENAME_LENGTH} characters.\n"
            f"4. Highly descriptive of the PDF's primary topic, purpose, or key entities mentioned.\n"
            f"5. Avoid generic terms like 'document', 'file', 'report' unless truly the best fit or part of a specific title.\n"
            f"6. If dates, form numbers, case numbers, or unique identifiers are prominent and central, try to incorporate them concisely.\n"
            f"7. Output ONLY the suggested base filename. For example: 'company_annual_report_2023' or 'irs_form_w9_instructions'\n\n"
            f"PDF Content Summary:\n```text\n{text_content}\n```\n"
            f"Suggested base filename:"
        )
        logger.debug(f"Sending prompt to Gemini for {original_filename} (content len {len(text_content)})")
        generation_config = genai.types.GenerationConfig(temperature=0.2, top_p=0.9)
        
        # Call generate_content without explicit safety_settings
        response = model.generate_content(
            prompt,
            generation_config=generation_config
        )
        
        # Log more detailed response info if VERBOSE_LOGGING is on
        if VERBOSE_LOGGING:
            logger.debug(f"Gemini raw response object for {original_filename}: {response}")
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                logger.debug(f"Gemini prompt feedback for {original_filename}: {response.prompt_feedback}")
            if hasattr(response, 'candidates') and response.candidates:
                for i, candidate in enumerate(response.candidates):
                    logger.debug(f"Candidate {i} for {original_filename}: Finish Reason: {getattr(candidate, 'finish_reason', 'N/A')}, Safety Ratings: {getattr(candidate, 'safety_ratings', 'N/A')}")
                    if candidate.content:
                         logger.debug(f"Candidate {i} content: {candidate.content}")
            else:
                logger.debug(f"No candidates found in response for {original_filename}")

        if response.parts:
            suggested_base_name = response.text.strip().replace("```", "").replace("`", "").strip()
            logger.info(f"Gemini suggested for {original_filename}: '{suggested_base_name}'")
            if not suggested_base_name or not re.match(r"^[a-z0-9_]+(?:_[a-z0-9]+)*$", suggested_base_name):
                logger.warning(f"Gemini suggestion '{suggested_base_name}' for {original_filename} invalid. Ignoring.")
                return None
            return suggested_base_name
        else:
            logger.warning(f"Gemini returned no usable parts for {original_filename}. Check verbose logs for more details if enabled.")
            # No explicit prompt_feedback log here as it's covered by verbose logging above
            return None
    except GoogleAPIError as e:
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
        logger.info(f"Backing up '{source_dir_path.name}' (PDF files only) to '{backup_path}'...")
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zipf:
            for root_str, dirnames, files_in_zip in os.walk(source_dir_path):
                root = Path(root_str)
                script_name = Path(__file__).name
                excluded_dirs = ['__pycache__', '.git', '.vscode', '.idea', '.bak', 'node_modules', 'venv', 'env', '.DS_Store']
                dirnames[:] = [d for d in dirnames if not d.startswith('.') and d not in excluded_dirs]
                
                pdf_files_to_add = [
                    f for f in files_in_zip 
                    if f.lower().endswith(".pdf")
                    and f != script_name 
                    and not f.endswith(BACKUP_SUFFIX)
                ]
                for file_to_add in pdf_files_to_add:
                    file_path = root / file_to_add
                    arcname = file_path.relative_to(source_dir_path)
                    zipf.write(file_path, arcname)
        logger.info(f"Backup of PDF files successful: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"ZIP Backup failed for {source_dir_path.name}: {e}")
        if backup_path.exists():
            try: os.remove(backup_path)
            except OSError: pass
        return None

def gather_rename_suggestions_pdf(target_dir_path: Path) -> List[Tuple[Path, str, str]]:
    suggestions: List[Tuple[Path, str, str]] = []
    if not genai or not GEMINI_API_KEY: return suggestions 
    if not PyPDF2: return suggestions

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
        
        pdf_files_to_process = [
            f for f in filenames 
            if f.lower().endswith(".pdf")
            and not f.startswith('.') 
            and f != script_name 
            and not f.endswith(BACKUP_SUFFIX)
        ]
        
        if not pdf_files_to_process: continue
        logger.info(f"Analyzing PDF files in: {current_dir}")

        for filename in pdf_files_to_process:
            original_filepath = current_dir / filename
            if not original_filepath.is_file(): continue
            
            original_stem = original_filepath.stem
            original_extension = original_filepath.suffix # .pdf
            
            logger.debug(f"Processing PDF file: {original_filepath}")
            text_content = extract_pdf_content_for_ai(original_filepath)
            if not text_content:
                logger.info(f"No meaningful content extracted from PDF {original_filepath.name}. Skipping.")
                continue

            ai_suggestion = suggest_name_via_gemini(text_content, original_filepath.name)
            if ai_suggestion:
                suggested_stem = sanitize_filename(ai_suggestion)
                sanitized_original_stem = sanitize_filename(original_stem)
                if not suggested_stem or "untitled_pdf" in suggested_stem or "sanitized_untitled_pdf" in suggested_stem:
                    logger.warning(f"AI returned generic/empty name ('{suggested_stem}') for {original_filepath.name}. Skipping.")
                    continue
                if suggested_stem == sanitized_original_stem:
                    logger.info(f"AI name '{suggested_stem}' same as original for {original_filepath.name}.")
                else:
                    suggestions.append((original_filepath, suggested_stem, original_extension))
                    logger.info(f"Proposed AI rename for {original_filepath.name}: '{suggested_stem}{original_extension}'")
            else:
                logger.warning(f"Gemini API no suggestion for PDF {original_filepath.name}. Skipping.")
    return suggestions

def execute_renames(rename_plan: List[Tuple[Path, str, str]], dry_run: bool):
    if not rename_plan: logger.info("No PDF files to rename."); return
    logger.info(f"Preparing to process {len(rename_plan)} PDF file renames.")
    files_renamed_count = 0
    for original_filepath, suggested_stem, original_extension in rename_plan:
        try:
            if not suggested_stem: logger.warning(f"Skipping {original_filepath.name} due to empty stem."); continue
            new_filepath = get_unique_filepath(original_filepath.parent, suggested_stem, original_extension)
            if original_filepath == new_filepath: logger.info(f"Final name for {original_filepath.name} same as original. Skipping."); continue
            
            if not original_filepath.suffix.lower() == ".pdf":
                logger.warning(f"Attempted to rename non-PDF file {original_filepath.name} in plan. Skipping this operation for safety.")
                continue

            if dry_run:
                logger.info(f"[DRY RUN] Would rename PDF: '{original_filepath.name}' -> '{new_filepath.name}' in '{original_filepath.parent}'")
                files_renamed_count +=1
            else:
                logger.info(f"Renaming PDF: '{original_filepath}' -> '{new_filepath}'")
                os.rename(original_filepath, new_filepath)
                files_renamed_count += 1
        except Exception as e:
            logger.error(f"Failed to rename PDF '{original_filepath}' to '{suggested_stem}{original_extension}': {e}", exc_info=VERBOSE_LOGGING)
    if dry_run: logger.info(f"[DRY RUN] Completed. Would have attempted {files_renamed_count} PDF renames.")
    else: logger.info(f"Renaming completed. {files_renamed_count} PDF files renamed.")

# --- Main Execution ---
def main():
    # Critical dependency checks at startup
    if not PyPDF2: 
        logger.critical("PyPDF2 library is required for PDF processing but not found. Please install it ('pip install PyPDF2'). Exiting.")
        return
    if not genai: 
        logger.critical("google-generativeai library is required but not found. Please install it. Exiting.")
        return
    if not GEMINI_API_KEY: 
        logger.critical("GEMINI_API_KEY environment variable is not set. Please define it. Exiting.")
        return

    if not VERBOSE_LOGGING: 
        logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)

    target_dir_path = Path('.').resolve()
    logger.info(f"--- Gemini PDF File Namer (Simplified) ---")
    logger.info(f"Processing PDF files in directory: {target_dir_path}")
    logger.info(f"Dry run mode: {'Enabled' if DRY_RUN_MODE else 'Disabled - WILL MAKE CHANGES!'}")
    logger.info(f"Backup (PDF only): {'Enabled (to ~/.bak/)' if ENABLE_BACKUP else 'Disabled'}")
    if VERBOSE_LOGGING: logger.debug(f"Max content preview for AI: {MAX_CONTENT_PREVIEW_FOR_GEMINI} characters")

    if not ENABLE_BACKUP and not DRY_RUN_MODE:
        logger.warning("="*60 + "\nWARNING: Backup is DISABLED and Dry Run is OFF!\n" +
                       "This script will make PERMANENT changes to your PDF files without a backup.\n" + "="*60)
        if input("Are you ABSOLUTELY SURE you want to proceed? (yes/no): ").lower() != 'yes':
            logger.info("Aborting. Enable backup or use dry run."); return
        logger.warning("Proceeding without backup as confirmed by user. GOOD LUCK!")
    
    if ENABLE_BACKUP and not DRY_RUN_MODE:
        backup_zip_path = backup_directory_zip(target_dir_path) 
        if not backup_zip_path: logger.error("Backup of PDF files failed. Aborting."); return
        logger.info(f"IMPORTANT: PDF files backed up to '{backup_zip_path}'.")
    elif ENABLE_BACKUP and DRY_RUN_MODE:
        logger.info("[DRY RUN] Backup of PDF files to ~/.bak/ would be performed here.")

    rename_suggestions = gather_rename_suggestions_pdf(target_dir_path)
    if rename_suggestions: 
        execute_renames(rename_suggestions, DRY_RUN_MODE)
    else: 
        logger.info("No PDF files found to process or no valid rename suggestions were generated.")
    logger.info("--- Script finished ---")

if __name__ == "__main__":
    main()
