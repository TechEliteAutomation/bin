#!/usr/bin/env python3

import os
import re
import datetime
import logging
import zipfile
from pathlib import Path
from typing import Optional, List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuration
DRY_RUN_MODE = True
ENABLE_BACKUP = True
VERBOSE_LOGGING = False
MAX_FILENAME_LENGTH = 50
MAX_CONTENT_PREVIEW = 8000
BATCH_SIZE = 10

try:
    from bs4 import BeautifulSoup
    import google.generativeai as genai
    from google.api_core.exceptions import GoogleAPIError
except ImportError as e:
    print(f"Missing dependency: {e}")
    exit(1)

logging.basicConfig(level=logging.DEBUG if VERBOSE_LOGGING else logging.INFO)
logger = logging.getLogger(__name__)

def sanitize_filename(name: str) -> str:
    if not name:
        return "untitled"
    name = re.sub(r'[<>:"/\\|?*\x00-\x1F\n\r\t]', '', name)
    name = re.sub(r'\s+', '_', name)
    name = re.sub(r'_+', '_', name).lower().strip('_.')
    return name[:MAX_FILENAME_LENGTH] if len(name) > MAX_FILENAME_LENGTH else name

def extract_html_metadata(filepath: Path) -> Dict[str, str]:
    """Extract title, headings, and key content from HTML."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
        
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        headings = [h.get_text(strip=True) for h in soup.find_all(['h1', 'h2', 'h3'])[:5]]
        
        # Get main content
        main_content = ""
        for tag in soup.find_all(['main', 'article', 'section']):
            main_content += tag.get_text(separator=' ', strip=True)[:2000]
            break
        
        if not main_content and soup.body:
            main_content = soup.body.get_text(separator=' ', strip=True)[:2000]
        
        return {
            'title': title,
            'headings': ', '.join(headings),
            'content': main_content,
            'filename': filepath.name
        }
    except Exception as e:
        logger.warning(f"Failed to extract from {filepath}: {e}")
        return {'title': '', 'headings': '', 'content': '', 'filename': filepath.name}

def batch_suggest_names(html_files_data: List[Dict]) -> Dict[str, str]:
    """Process multiple files in single API call."""
    if not html_files_data:
        return {}
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY not set")
        return {}
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Construct batch prompt
        batch_prompt = "Generate descriptive filenames for these HTML files. Return JSON format: {\"original_filename\": \"suggested_name\"}.\n\n"
        batch_prompt += "Requirements: lowercase, underscores for spaces, max 50 chars, descriptive.\n\n"
        
        for i, data in enumerate(html_files_data, 1):
            batch_prompt += f"File {i}: {data['filename']}\n"
            if data['title']:
                batch_prompt += f"Title: {data['title']}\n"
            if data['headings']:
                batch_prompt += f"Headings: {data['headings']}\n"
            if data['content']:
                batch_prompt += f"Content: {data['content'][:500]}\n"
            batch_prompt += "\n"
        
        response = model.generate_content(
            batch_prompt,
            generation_config=genai.types.GenerationConfig(temperature=0.1)
        )
        
        # Parse JSON response
        import json
        result_text = response.text.strip()
        if result_text.startswith('```json'):
            result_text = result_text[7:-3]
        elif result_text.startswith('```'):
            result_text = result_text[3:-3]
        
        return json.loads(result_text)
        
    except Exception as e:
        logger.error(f"Batch API call failed: {e}")
        return {}

def process_html_files(directory: Path) -> List[tuple]:
    """Find and process HTML files with parallel extraction."""
    html_files = []
    for filepath in directory.rglob("*.htm*"):
        if filepath.is_file() and not filepath.name.startswith('.'):
            html_files.append(filepath)
    
    if not html_files:
        return []
    
    # Parallel content extraction
    all_data = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_file = {executor.submit(extract_html_metadata, f): f for f in html_files}
        for future in as_completed(future_to_file):
            filepath = future_to_file[future]
            try:
                data = future.result()
                data['filepath'] = filepath
                all_data.append(data)
            except Exception as e:
                logger.warning(f"Failed processing {filepath}: {e}")
    
    # Process in batches
    rename_suggestions = []
    for i in range(0, len(all_data), BATCH_SIZE):
        batch = all_data[i:i+BATCH_SIZE]
        suggestions = batch_suggest_names(batch)
        
        for data in batch:
            original_name = data['filename']
            if original_name in suggestions:
                suggested = sanitize_filename(suggestions[original_name])
                if suggested and suggested != sanitize_filename(data['filepath'].stem):
                    rename_suggestions.append((data['filepath'], suggested, data['filepath'].suffix))
    
    return rename_suggestions

def create_backup(directory: Path) -> Optional[Path]:
    """Create ZIP backup of HTML files only."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path.home() / ".bak"
    backup_dir.mkdir(exist_ok=True)
    
    backup_path = backup_dir / f"{directory.name}_html_{timestamp}.zip"
    
    try:
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for filepath in directory.rglob("*.htm*"):
                if filepath.is_file():
                    zipf.write(filepath, filepath.relative_to(directory))
        logger.info(f"Backup created: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        return None

def execute_renames(suggestions: List[tuple], dry_run: bool):
    """Execute or simulate file renames."""
    if not suggestions:
        logger.info("No files to rename")
        return
    
    for original_path, new_stem, extension in suggestions:
        new_name = f"{new_stem}{extension}"
        counter = 1
        new_path = original_path.parent / new_name
        
        while new_path.exists():
            new_name = f"{new_stem}_{counter}{extension}"
            new_path = original_path.parent / new_name
            counter += 1
        
        if dry_run:
            logger.info(f"[DRY RUN] {original_path.name} → {new_name}")
        else:
            try:
                original_path.rename(new_path)
                logger.info(f"Renamed: {original_path.name} → {new_name}")
            except Exception as e:
                logger.error(f"Failed to rename {original_path.name}: {e}")

def main():
    directory = Path('.').resolve()
    logger.info(f"Processing HTML files in: {directory}")
    logger.info(f"Mode: {'DRY RUN' if DRY_RUN_MODE else 'LIVE'}")
    
    if ENABLE_BACKUP and not DRY_RUN_MODE:
        if not create_backup(directory):
            logger.error("Backup failed, aborting")
            return
    
    suggestions = process_html_files(directory)
    execute_renames(suggestions, DRY_RUN_MODE)
    
    logger.info(f"Completed. Processed {len(suggestions)} files.")

if __name__ == "__main__":
    main()