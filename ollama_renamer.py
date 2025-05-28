#!/usr/bin/env python3

import requests
import json
from pathlib import Path
from bs4 import BeautifulSoup
import re # Moved import re to top as it's used in suggest_filename_ollama and potentially good practice

# Ollama configuration
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma3:1b" # Note: Ensure this model name is correct for your Ollama setup

def query_ollama(prompt: str) -> str:
    """Query local Ollama instance."""
    try:
        response = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1}
        }, timeout=30)
        
        if response.status_code == 200:
            return response.json()["response"].strip()
        print(f"Ollama query returned status {response.status_code}: {response.text}")
        return ""
    except requests.exceptions.Timeout:
        print(f"Ollama query timed out after 30 seconds.")
        return ""
    except requests.exceptions.ConnectionError:
        print(f"Ollama connection failed. Is Ollama running at {OLLAMA_URL}?")
        return ""
    except Exception as e:
        print(f"Ollama query failed: {e}")
        return ""

def suggest_filename_ollama(html_content: str, original_name: str) -> str:
    """Generate filename using local AI."""
    prompt = f"""Based on this HTML content, suggest a descriptive filename (without extension).
Requirements:
- Use only lowercase letters, numbers, underscores
- Maximum 50 characters
- Be descriptive of the main content/purpose
- Output only the filename string itself, nothing else.

HTML Title/Content: {html_content[:1000]}
Current filename: {original_name}

Suggested filename:"""
    
    suggestion = query_ollama(prompt)
    if suggestion:
        # Clean and validate
        # Remove any potential markdown like ``` or quotes around the filename
        suggestion = suggestion.strip().replace('```', '').replace('`', '').replace("'", "").replace('"', '')
        clean = re.sub(r'[^a-z0-9_]', '', suggestion.lower())
        # Ensure it's not empty after cleaning and respects max length
        return clean[:50] if clean else ""
    return ""

def process_with_ollama(directory: Path):
    """Process HTML files using Ollama and rename them."""
    print(f"Scanning for HTML files in {directory.resolve()} and its subdirectories...")
    files_processed_count = 0
    files_renamed_count = 0

    for filepath in directory.rglob("*.htm*"): # Handles .htm, .html, etc.
        if not filepath.is_file():
            continue
        
        files_processed_count += 1
        print(f"\nProcessing: {filepath.relative_to(directory)}")
            
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                # Read only a portion of the file if it's very large, to avoid memory issues
                # BeautifulSoup can handle this, but Ollama prompt has a limit anyway.
                # For now, f.read() is fine as suggest_filename_ollama slices content.
                soup = BeautifulSoup(f.read(), 'html.parser')
            
            content_parts = []
            if soup.title and soup.title.string:
                content_parts.append(f"Title: {soup.title.string.strip()}")
            
            # Get main content text more robustly
            main_text_candidates = []
            for tag_name in ['main', 'article', 'h1', 'h2', 'body']: # Added body as a fallback
                for tag in soup.find_all(tag_name):
                    tag_text = tag.get_text(separator=' ', strip=True)
                    if tag_text:
                        main_text_candidates.append(tag_text)
                        if len(tag_text) > 200: # Prefer longer, more specific tags
                            break # Found a good candidate from this tag type
                if main_text_candidates and len(main_text_candidates[-1]) > 200:
                    break # Found a good candidate overall

            if main_text_candidates:
                # Join first few candidates or a long one, up to a limit
                extracted_text = " ".join(main_text_candidates)[:1500] # Increased limit slightly for context
                content_parts.append(f"Content: {extracted_text}")
            
            if not content_parts:
                print(f"  - No usable title or main content found for {filepath.name}. Skipping.")
                continue

            combined_content = "\n".join(content_parts)
            
            suggested_stem = suggest_filename_ollama(combined_content, filepath.name)
            
            if suggested_stem and suggested_stem != filepath.stem:
                new_filename_with_extension = suggested_stem + filepath.suffix
                new_filepath = filepath.with_name(new_filename_with_extension)

                print(f"  - Suggestion for {filepath.name}: {new_filename_with_extension}")

                if new_filepath.exists():
                    print(f"  - SKIPPED rename: Target file '{new_filepath.name}' already exists in '{new_filepath.parent.relative_to(directory)}'.")
                elif new_filepath == filepath:
                    print(f"  - SKIPPED rename: Suggested name is identical to current name after considering path.")
                else:
                    try:
                        filepath.rename(new_filepath)
                        print(f"  - SUCCESS: Renamed to '{new_filepath.name}'")
                        files_renamed_count += 1
                    except FileNotFoundError:
                        print(f"  - ERROR: Original file '{filepath.name}' not found at rename time (should not happen).")
                    except FileExistsError: # Should be caught by new_filepath.exists() but good to have
                        print(f"  - ERROR: Target file '{new_filepath.name}' appeared after check.")
                    except OSError as e_rename: # Catches permission errors, etc.
                        print(f"  - ERROR renaming '{filepath.name}' to '{new_filepath.name}': {e_rename}")
                    except Exception as e_rename:
                        print(f"  - UNEXPECTED ERROR renaming '{filepath.name}': {e_rename}")
            elif not suggested_stem:
                print(f"  - No valid filename suggestion received from Ollama for {filepath.name}.")
            else: # suggestion == filepath.stem
                print(f"  - Suggested name '{suggested_stem}' is the same as current stem. No rename needed.")
                
        except Exception as e:
            print(f"  - Error processing {filepath.name}: {e}")

    print(f"\n--- Summary ---")
    print(f"Total HTML files found and processed: {files_processed_count}")
    print(f"Total files successfully renamed: {files_renamed_count}")

if __name__ == "__main__":
    print("Checking Ollama status...")
    try:
        # Check if the specific model is available, not just if Ollama is running
        response_tags = requests.get(OLLAMA_URL.replace("/api/generate", "/api/tags"), timeout=5)
        if response_tags.status_code == 200:
            models_info = response_tags.json()
            available_models = [m['name'] for m in models_info.get('models', [])]
            if MODEL in available_models:
                print(f"Ollama detected and model '{MODEL}' is available.")
                # Ask for confirmation before proceeding with potentially destructive actions
                user_confirmation = input(f"Proceed with renaming files in the current directory '{Path('.').resolve()}' and its subdirectories? (yes/no): ").strip().lower()
                if user_confirmation == 'yes':
                    print("Processing files...")
                    process_with_ollama(Path('.'))
                else:
                    print("Operation cancelled by user.")
            else:
                print(f"Ollama is running, but model '{MODEL}' is not available.")
                print(f"Available models: {', '.join(available_models) if available_models else 'None'}")
                print(f"You can pull the model with: ollama pull {MODEL}")
        else:
            print(f"Ollama not responding as expected at /api/tags. Status: {response_tags.status_code}")
            print("Ensure Ollama is running: ollama serve")
    except requests.exceptions.ConnectionError:
        print(f"Ollama not available or not running at {OLLAMA_URL.replace('/api/generate', '')}.")
        print("Install Ollama from https://ollama.ai and ensure it's running with 'ollama serve'.")
    except Exception as e:
        print(f"An error occurred while checking Ollama status: {e}")