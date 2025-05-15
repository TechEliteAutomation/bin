#!/usr/bin/env python3

import os
import shutil
import re
import datetime
import logging
import zipfile
import ast # For parsing Python code
from pathlib import Path
from typing import Optional, Tuple, List, Any

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
BACKUP_SUFFIX = "_py_backup.zip"
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MAX_CONTENT_PREVIEW_FOR_GEMINI = 10000

# Setup logging
logging.basicConfig(level=logging.DEBUG if VERBOSE_LOGGING else logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)

# --- Helper Functions ---
def sanitize_filename(name_str: Optional[str]) -> str:
    if not name_str: return "untitled_py_from_ai"
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
    if not name_str: return "sanitized_untitled_py"
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

# --- Content Extraction for Python ---
def extract_py_content_for_ai(filepath: Path) -> Optional[str]:
    if not filepath.is_file():
        logger.warning(f"File not found: {filepath}")
        return None
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            source_code = f.read()
    except Exception as e:
        logger.warning(f"Could not read Python file {filepath}: {e}")
        return None

    content_parts = []
    try:
        tree = ast.parse(source_code, filename=filepath.name)
        module_docstring = ast.get_docstring(tree)
        if module_docstring:
            content_parts.append(f"Module Docstring:\n{module_docstring.strip()}")

        imports_summary = []
        classes_summary = []
        functions_summary = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names: imports_summary.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module or ""
                for alias in node.names: imports_summary.append(f"from {module_name} import {alias.name}")
            elif isinstance(node, ast.ClassDef):
                class_doc = ast.get_docstring(node)
                class_info = f"Class: {node.name}"
                if class_doc: class_info += f"\n  Docstring: {class_doc.strip()[:200]}..."
                method_names = [m.name for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
                if method_names: class_info += f"\n  Methods: {', '.join(method_names[:3])}{'...' if len(method_names) > 3 else ''}"
                classes_summary.append(class_info)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_doc = ast.get_docstring(node)
                func_type = "Async Function" if isinstance(node, ast.AsyncFunctionDef) else "Function"
                func_info = f"{func_type}: {node.name}"
                if func_doc: func_info += f"\n  Docstring: {func_doc.strip()[:200]}..."
                functions_summary.append(func_info)

        if imports_summary:
            unique_imports = sorted(list(set(imports_summary)))
            content_parts.append(f"Key Imports (up to 10):\n{', '.join(unique_imports[:10])}")
        if classes_summary: content_parts.append("Classes Defined (up to 5 with methods):\n" + "\n\n".join(classes_summary[:5]))
        if functions_summary: content_parts.append("Functions Defined (up to 10):\n" + "\n\n".join(functions_summary[:10]))
        if not content_parts and source_code.strip():
            logger.info(f"No structured Python elements prominently extracted from {filepath.name}. Using raw code snippet.")
            content_parts.append(f"Python code snippet:\n{source_code[:2000]}")
        text_content = "\n\n---\n\n".join(filter(None, content_parts))
    except SyntaxError as e:
        logger.warning(f"Syntax error parsing Python file {filepath}: {e}. Using raw content snippet.")
        text_content = f"Problematic Python Code Snippet (due to parsing error):\n{source_code[:MAX_CONTENT_PREVIEW_FOR_GEMINI]}"
    except Exception as e:
        logger.warning(f"Could not extract structured content from Python file {filepath}: {e}. Using raw content snippet.")
        text_content = f"Python Code Snippet (due to AST processing error):\n{source_code[:MAX_CONTENT_PREVIEW_FOR_GEMINI]}"

    if text_content and len(text_content) > MAX_CONTENT_PREVIEW_FOR_GEMINI:
        text_content = text_content[:MAX_CONTENT_PREVIEW_FOR_GEMINI] + f"\n[...content truncated at {MAX_CONTENT_PREVIEW_FOR_GEMINI} chars...]"
    elif not text_content or not text_content.strip():
        logger.info(f"No meaningful text content extracted from Python file {filepath.name} after processing.")
        if source_code.strip(): return f"Raw Python code start:\n{source_code[:500]}"
        return None
    return text_content

# --- Name Suggestion via Gemini ---
def suggest_name_via_gemini(text_content: str, original_filename: str) -> Optional[str]:
    """Suggests a filename for a Python file using the Gemini API."""
    if not genai or not GEMINI_API_KEY: return None

    try:
        # Ensure genai.types is available for FinishReason if not already globally accessible
        # from google.generativeai import types as genai_types (alternative if direct access is an issue)
        # However, genai.types.FinishReason should work if genai is imported.

        model = genai.GenerativeModel(os.environ.get("GEMINI_MODEL_NAME", 'gemini-2.0-flash'))
        prompt = (
            f"You are an expert file naming assistant specializing in Python modules. Based on the following Python code summary from a file originally named '{original_filename}', "
            f"suggest an optimal new base filename (Python module name, without the .py extension).\n"
            f"Requirements for the new base filename (module name):\n"
            f"1. All lowercase (snake_case is preferred).\n"
            f"2. Use underscores `_` to separate words if needed.\n"
            f"3. Maximum {MAX_FILENAME_LENGTH} characters.\n"
            f"4. Highly descriptive of the Python module's primary functionality or purpose.\n"
            f"5. Avoid overly generic terms like 'script', 'main', 'module', 'code', 'program' unless truly unavoidable.\n"
            f"6. If it's a utility module, prefer names like 'string_utils', 'file_helpers', 'datetime_extensions'.\n"
            f"7. If it defines a primary class (e.g., 'UserDataProcessor'), the name might reflect that (e.g., 'user_data_processor').\n"
            f"8. If it's a script for a specific task, name it after the task, e.g., 'generate_report', 'process_sales_data'.\n"
            f"9. Output ONLY the suggested base filename. For example: 'data_validator' or 'api_client_services' or 'configuration_loader'\n\n"
            f"Python Code Summary:\n```text\n{text_content}\n```\n"
            f"Suggested base filename:"
        )
        logger.debug(f"Sending prompt to Gemini for {original_filename} (content len {len(text_content)})")
        generation_config = genai.types.GenerationConfig(temperature=0.2, top_p=0.9)

        response = model.generate_content(
            prompt,
            generation_config=generation_config
            # No explicit safety_settings are passed; model defaults will be used.
        )

        if response.parts:
            suggested_base_name = response.text.strip().replace("```", "").replace("`", "").strip()
            logger.info(f"Gemini suggested for {original_filename}: '{suggested_base_name}'")
            if not suggested_base_name or not re.match(r"^[a-z_][a-z0-9_]*$", suggested_base_name):
                logger.warning(f"Gemini suggestion '{suggested_base_name}' for {original_filename} is not a valid Python module name format after cleaning. Ignoring.")
                return None
            return suggested_base_name
        else:
            logger.warning(f"Gemini returned no usable parts for {original_filename}.")
            # More robust feedback logging
            try:
                feedback_logged = False
                # Check prompt_feedback first for blocking reasons
                if response.prompt_feedback is not None: # Check if prompt_feedback object exists
                    if hasattr(response.prompt_feedback, 'block_reason') and response.prompt_feedback.block_reason:
                        safety_ratings_str = str(response.prompt_feedback.safety_ratings) if hasattr(response.prompt_feedback, 'safety_ratings') else "N/A"
                        logger.warning(f"Gemini prompt feedback for {original_filename}: Blocked - {response.prompt_feedback.block_reason}, Safety Ratings: {safety_ratings_str}")
                        feedback_logged = True
                    elif hasattr(response.prompt_feedback, 'safety_ratings'): # Log safety ratings even if not explicitly blocked here
                        logger.info(f"Gemini prompt feedback safety ratings for {original_filename}: {response.prompt_feedback.safety_ratings}")
                        # feedback_logged = True # Don't set to true, as it might not be the primary reason for no parts

                # Then check candidate finish reason if prompt_feedback isn't conclusive or no parts
                if response.candidates and response.candidates[0].finish_reason != genai.types.FinishReason.STOP:
                    candidate = response.candidates[0]
                    safety_ratings_str = str(candidate.safety_ratings) if hasattr(candidate, 'safety_ratings') else "N/A"
                    logger.warning(f"Gemini candidate finish reason for {original_filename}: {candidate.finish_reason.name}, Safety Ratings: {safety_ratings_str}")
                    feedback_logged = True
                elif not feedback_logged : # If no specific block/finish reason found yet
                    logger.warning(f"Gemini returned no usable parts for {original_filename}, and no specific block/finish reason identified in prompt_feedback or candidates.")

            except AttributeError as e:
                logger.warning(f"Error accessing detailed feedback attributes for {original_filename}: {e}. Raw response object might be unusual.")
            except Exception as e: # Catch any other exception during feedback logging
                logger.warning(f"Unexpected error while logging detailed feedback for {original_filename}: {e}")
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
        logger.info(f"Backing up '{source_dir_path.name}' (Python files only) to '{backup_path}'...")
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zipf:
            for root_str, dirnames, files_in_zip in os.walk(source_dir_path):
                root = Path(root_str)
                script_name = Path(__file__).name
                excluded_dirs = ['__pycache__', '.git', '.vscode', '.idea', '.bak', 'node_modules', 'venv', 'env', '.DS_Store']
                dirnames[:] = [d for d in dirnames if not d.startswith('.') and d not in excluded_dirs]
                py_files_to_add = [
                    f for f in files_in_zip
                    if f.lower().endswith(".py")
                    and f != script_name
                    and not f.endswith(BACKUP_SUFFIX)
                ]
                for file_to_add in py_files_to_add:
                    file_path = root / file_to_add
                    arcname = file_path.relative_to(source_dir_path)
                    zipf.write(file_path, arcname)
        logger.info(f"Backup of Python files successful: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"ZIP Backup failed for {source_dir_path.name}: {e}")
        if backup_path.exists():
            try: os.remove(backup_path)
            except OSError: pass
        return None

def gather_rename_suggestions_py(target_dir_path: Path) -> List[Tuple[Path, str, str]]:
    suggestions: List[Tuple[Path, str, str]] = []
    if not genai or not GEMINI_API_KEY: return suggestions

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
        py_files_to_process = [
            f for f in filenames
            if f.lower().endswith(".py")
            and not f.startswith('.')
            and f != script_name
            and not f.endswith(BACKUP_SUFFIX)
        ]
        if not py_files_to_process: continue
        logger.info(f"Analyzing Python files in: {current_dir}")

        for filename in py_files_to_process:
            original_filepath = current_dir / filename
            if not original_filepath.is_file(): continue
            original_stem = original_filepath.stem
            original_extension = original_filepath.suffix
            logger.debug(f"Processing Python file: {original_filepath}")
            text_content = extract_py_content_for_ai(original_filepath)
            if not text_content:
                logger.info(f"No meaningful content extracted from Python file {original_filepath.name}. Skipping.")
                continue
            ai_suggestion = suggest_name_via_gemini(text_content, original_filepath.name)
            if ai_suggestion:
                suggested_stem = sanitize_filename(ai_suggestion)
                sanitized_original_stem = sanitize_filename(original_stem)
                if not suggested_stem or "untitled_py" in suggested_stem or "sanitized_untitled_py" in suggested_stem:
                    logger.warning(f"AI returned generic/empty name ('{suggested_stem}') for {original_filepath.name}. Skipping.")
                    continue
                if suggested_stem == sanitized_original_stem:
                    logger.info(f"AI name '{suggested_stem}' same as original (after sanitization) for {original_filepath.name}.")
                else:
                    suggestions.append((original_filepath, suggested_stem, original_extension))
                    logger.info(f"Proposed AI rename for {original_filepath.name}: '{suggested_stem}{original_extension}'")
            else:
                logger.warning(f"Gemini API no suggestion for Python file {original_filepath.name}. Skipping.")
    return suggestions

def execute_renames(rename_plan: List[Tuple[Path, str, str]], dry_run: bool):
    if not rename_plan: logger.info("No Python files to rename."); return
    logger.info(f"Preparing to process {len(rename_plan)} Python file renames.")
    files_renamed_count = 0
    for original_filepath, suggested_stem, original_extension in rename_plan:
        try:
            if not suggested_stem: logger.warning(f"Skipping {original_filepath.name} due to empty stem."); continue
            new_filepath = get_unique_filepath(original_filepath.parent, suggested_stem, original_extension)
            if original_filepath == new_filepath: logger.info(f"Final name for {original_filepath.name} same as original. Skipping."); continue
            if not original_filepath.suffix.lower() == ".py":
                logger.warning(f"Attempted to rename non-Python file {original_filepath.name} in plan. Skipping this operation for safety.")
                continue
            if dry_run:
                logger.info(f"[DRY RUN] Would rename Python file: '{original_filepath.name}' -> '{new_filepath.name}' in '{original_filepath.parent}'")
                files_renamed_count +=1
            else:
                logger.info(f"Renaming Python file: '{original_filepath}' -> '{new_filepath}'")
                os.rename(original_filepath, new_filepath)
                files_renamed_count += 1
        except Exception as e:
            logger.error(f"Failed to rename Python file '{original_filepath}' to '{suggested_stem}{original_extension}': {e}", exc_info=VERBOSE_LOGGING)
    if dry_run: logger.info(f"[DRY RUN] Completed. Would have attempted {files_renamed_count} Python file renames.")
    else: logger.info(f"Renaming completed. {files_renamed_count} Python files renamed.")

# --- Main Execution ---
def main():
    if not genai:
        logger.critical("google-generativeai library is required but not found. Please install it. Exiting.")
        return
    if not GEMINI_API_KEY:
        logger.critical("GEMINI_API_KEY environment variable is not set. Please define it. Exiting.")
        return

    if not VERBOSE_LOGGING:
        logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
        logging.getLogger("google.api_core.grpc").setLevel(logging.WARNING)
        logging.getLogger("google.auth.transport.requests").setLevel(logging.WARNING)

    target_dir_path = Path('.').resolve()
    logger.info(f"--- Gemini Python File Namer ---")
    logger.info(f"Processing Python files in directory: {target_dir_path}")
    logger.info(f"Dry run mode: {'Enabled' if DRY_RUN_MODE else 'Disabled - WILL MAKE CHANGES!'}")
    logger.info(f"Backup (Python files only): {'Enabled (to ~/.bak/)' if ENABLE_BACKUP else 'Disabled'}")
    if VERBOSE_LOGGING: logger.debug(f"Max content preview for AI: {MAX_CONTENT_PREVIEW_FOR_GEMINI} characters")

    if not ENABLE_BACKUP and not DRY_RUN_MODE:
        logger.warning("="*60 + "\nWARNING: Backup is DISABLED and Dry Run is OFF!\n" +
                       "This script will make PERMANENT changes to your Python files without a backup.\n" + "="*60)
        if input("Are you ABSOLUTELY SURE you want to proceed? (yes/no): ").lower() != 'yes':
            logger.info("Aborting. Enable backup or use dry run."); return
        logger.warning("Proceeding without backup as confirmed by user. GOOD LUCK!")

    if ENABLE_BACKUP and not DRY_RUN_MODE:
        backup_zip_path = backup_directory_zip(target_dir_path)
        if not backup_zip_path: logger.error("Backup of Python files failed. Aborting."); return
        logger.info(f"IMPORTANT: Python files backed up to '{backup_zip_path}'.")
    elif ENABLE_BACKUP and DRY_RUN_MODE:
        logger.info("[DRY RUN] Backup of Python files to ~/.bak/ would be performed here.")

    rename_suggestions = gather_rename_suggestions_py(target_dir_path)
    if rename_suggestions:
        execute_renames(rename_suggestions, DRY_RUN_MODE)
    else:
        logger.info("No Python files found to process or no valid rename suggestions were generated.")
    logger.info("--- Script finished ---")

if __name__ == "__main__":
    main()
