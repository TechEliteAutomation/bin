# --- START OF FILE gemini.espeak_and_piper0.py --- # (Modified for generic file generation)

# --- START OF FILE gemini_files_no_safety_config.py --- # (Original base)

import os
import requests
import subprocess
import re
import json
import argparse # Import argparse for command-line arguments
import shlex   # Import shlex to safely quote text for shell commands
import sys
import traceback # For detailed error logging
import pathlib # For robust path handling and extension extraction

# --- Configuration (Could be moved to a config file later) ---
DEFAULT_TTS_ENGINE = "piper" # or "espeak"
# --- !! UPDATE THESE PATHS !! ---
# Ensure these paths are correct for your system
PIPER_EXECUTABLE = "/usr/bin/piper-tts" # Replace with your actual path to piper executable
PIPER_VOICE_MODEL = "/home/u/s/tts/en_GB-alan-medium.onnx" # Replace with your actual path to the Piper .onnx model file
# --- !! UPDATE THESE PATHS !! ---


# --- API Request/Response Functions ---
def _format_gemini_payload(query, history, modifier):
    """Formats the request payload for the Gemini API."""
    conversation = []
    if history:
        for q, a in history:
            # Basic validation to ensure history items are pairs of strings
            if isinstance(q, str) and isinstance(a, str):
                conversation.append({"role": "user", "parts": [{"text": q}]})
                conversation.append({"role": "model", "parts": [{"text": a}]})
            else:
                # More informative warning or skip
                print(f"Warning: Skipping invalid history entry: ({type(q)}, {type(a)})")


    # Construct the prompt, incorporating the modifier and history context if applicable
    if history:
         # Create a simple string representation of history for context
         history_context = "\n".join([f"User: {q}\nModel: {a}" for q, a in history])
         # Ensure modifier is present and add context/query clearly
         full_query = f"{modifier}\n---\nPrevious Conversation Context:\n{history_context}\n---\nCurrent Query:\n{query}"
    else:
         # No history, just modifier and query
         full_query = f"{modifier}\n---\nQuery:\n{query}" if modifier else query


    conversation.append({"role": "user", "parts": [{"text": full_query}]})
    data = {"contents": conversation}
    # print(f"DEBUG: Payload Data: {json.dumps(data, indent=2)}") # Uncomment for debugging payload
    return data

def _call_gemini_api(url, api_key, headers, data):
    """Makes the POST request to the Gemini API and handles request errors."""
    try:
        response = requests.post(f"{url}?key={api_key}", headers=headers, json=data, timeout=180) # Increased timeout further for potentially complex code generation
        response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
        return response
    except requests.exceptions.Timeout:
        print("Error: API request timed out.")
        return "Error: API request timed out."
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err} - Status Code: {http_err.response.status_code}")
        try:
            # Attempt to get more details from the response body if available
            error_details = http_err.response.json()
            print(f"API Error Details: {json.dumps(error_details, indent=2)}")
            # Try to extract the most specific error message
            api_error_message = error_details.get('error', {}).get('message', 'Unknown API error')
            return f"Error: HTTP {http_err.response.status_code} - {api_error_message}"
        except json.JSONDecodeError:
            # If response is not JSON or empty
            response_text = http_err.response.text
            print(f"Response body (non-JSON): {response_text}")
            return f"Error: HTTP {http_err.response.status_code} - {http_err}. Response: {response_text[:200]}..."
        except Exception as e:
            print(f"An error occurred processing the HTTP error response: {e}")
            return f"Error: HTTP {http_err.response.status_code} - {http_err}"
    except requests.exceptions.RequestException as e:
        print(f"Error communicating with API: {e}")
        return f"Error communicating with API: {e}"
    except Exception as e:
        print(f"An unexpected error occurred during API call: {e}")
        traceback.print_exc()
        return f"An unexpected error occurred during API call: {e}"


def _parse_gemini_response(response):
    """Parses the JSON response from Gemini API and extracts text."""
    if isinstance(response, str): # If an error string was returned from _call_gemini_api
        return response

    try:
        response_data = response.json()
        # print(f"DEBUG: Full API Response JSON:\n{json.dumps(response_data, indent=2)}") # Debugging

        # Check for top-level API errors first
        api_error = response_data.get('error')
        if api_error:
            return f"Error from API: {api_error.get('message', 'Unknown API error')} (Code: {api_error.get('code', 'N/A')})"

        # Check for prompt feedback (content filtering, etc.)
        # Even without sending custom safetySettings, the API might return feedback/blocks based on defaults
        prompt_feedback = response_data.get('promptFeedback')
        if prompt_feedback:
            block_reason = prompt_feedback.get('blockReason')
            if block_reason and block_reason != 'BLOCK_REASON_UNSPECIFIED':
                safety_ratings = prompt_feedback.get('safetyRatings')
                # Provide clearer feedback on blocking
                ratings_str = json.dumps(safety_ratings) if safety_ratings else "N/A"
                print(f"API Info: Request blocked by content filter (default policy). Reason: {block_reason}, Safety Ratings: {ratings_str}")
                return f"Error: Response blocked due to content policy (default). Reason: {block_reason}."

        # Check for candidates
        candidates = response_data.get('candidates')
        if not candidates:
             # If no candidates and no block reason, it might be an unexpected empty response
             return f"Error: No candidates found in response and no blocking reason identified. Response JSON: {json.dumps(response_data)}"

        # Check if candidate list itself is empty or contains null items
        if not candidates or not candidates[0]:
             return f"Error: Received empty or invalid candidate list. Response JSON: {json.dumps(response_data)}"

        # Process the first candidate
        candidate = candidates[0]

        # Check finish reason and safety ratings within the candidate
        finish_reason = candidate.get('finishReason')
        # Safety ratings can still be present even if default settings are used
        safety_ratings = candidate.get('safetyRatings')

        # --- Content Extraction ---
        content = candidate.get('content')
        text = ""

        if content and 'parts' in content and content['parts']:
            # Standard way: extract text from parts
            text = "".join(part.get('text', '') for part in content['parts']).strip()
        elif content and 'text' in content:
             # Fallback: sometimes text might be directly in content
             text = content['text'].strip()

        # --- Post-Extraction Checks ---

        # Check finish reason *after* attempting to extract content
        if finish_reason and finish_reason not in ["STOP", "FINISH_REASON_UNSPECIFIED"]:
            if finish_reason == "MAX_TOKENS":
                if text:
                    # For code generation, even partial output might be useful, but warn clearly
                    print(f"Warning: Response cut short due to maximum token limit ({finish_reason}).")
                    return f"Warning: MAX_TOKENS limit reached. Output may be incomplete.\n---\n{text}"
                else:
                     return f"Error: Candidate finished due to maximum token limit ({finish_reason}). No partial content extracted."
            elif finish_reason == "SAFETY":
                 # Content might be blocked at the candidate level by default policies
                 ratings_str = json.dumps(safety_ratings) if safety_ratings else "N/A"
                 print(f"API Info: Candidate content blocked by safety filter (default policy). Reason: {finish_reason}, Safety Ratings: {ratings_str}")
                 if text: # Sometimes partial text might be returned even with SAFETY blocking
                     print(f"Warning: Candidate content potentially filtered for safety (default policy - {finish_reason}). Partial text received might be incomplete or modified.")
                     return f"Warning: SAFETY block triggered. Output may be filtered or incomplete.\n---\n{text}"
                 else:
                     return f"Error: Candidate content blocked due to safety (default policy - {finish_reason}). Ratings: {ratings_str}"
            else:
                # Other reasons like RECITATION, OTHER
                if text:
                     print(f"Warning: Candidate finished unexpectedly (Reason: {finish_reason}).")
                     return f"Warning: Unexpected finish reason ({finish_reason}). Output may be incomplete.\n---\n{text}"
                else:
                     return f"Error: Candidate finished unexpectedly. Reason: {finish_reason}. Safety Ratings: {safety_ratings}"

        # If finish reason is STOP but no content was extracted
        if finish_reason == "STOP" and not text:
            # This can happen legitimately if the prompt asks for something impossible or the model refuses.
            return "Warning: Received response with no content (finish reason: STOP)."

        # If no text extracted for other reasons (should be less likely now)
        if not text and finish_reason != "STOP":
             return f"Error: Failed to extract text content from candidate. Finish Reason: {finish_reason}. Candidate: {json.dumps(candidate)}"

        # --- Code Cleaning (Attempt to remove markdown backticks if present) ---
        # If the response seems to be wrapped in ```python ... ``` or similar
        if text.startswith("```") and text.endswith("```"):
            lines = text.splitlines()
            if len(lines) > 1:
                 # Check if the first line is like ```python or ```
                 first_line_content = lines[0].strip()[3:].strip()
                 # Only strip if it looks like a language identifier or is empty
                 if len(first_line_content.split()) <= 1: # Allows 'python', 'bash', '', etc.
                      print("Info: Removing markdown code block fences (```).")
                      text = "\n".join(lines[1:-1]).strip()


        return text # Return the extracted (and potentially cleaned) text

    except json.JSONDecodeError as e:
        response_text = response.text if hasattr(response, 'text') else "N/A"
        return f"Error decoding API response JSON: {e}. Response text: {response_text[:500]}..."
    except IndexError:
         # Handle cases where candidates[0] might not exist after the initial check
         response_data_str = str(response_data)[:500] if 'response_data' in locals() else 'N/A'
         return f"Error processing API response: Invalid candidate structure. Response JSON slice: {response_data_str}"
    except Exception as e:
        # Catch-all for other unexpected parsing errors
        response_data_str = str(response_data)[:500] if 'response_data' in locals() else 'N/A'
        print(f"Unexpected parsing error: {e}") # Log the specific error
        traceback.print_exc() # Print traceback for debugging
        return f"Error processing API response structure: {e}. Response JSON slice: {response_data_str}"


# --- Updated get_gemini_response ---
def get_gemini_response(query, history=None, modifier=""):
    """Fetches a response from the Gemini API with specified constraints."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        # Return error instead of raising, handled in main loop
        return "Error: API key not found. Set GEMINI_API_KEY."

    # --- Use the specified experimental model ---
    # url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro-latest:generateContent"
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent"
    headers = {'Content-Type': 'application/json'}

    # Generation Config (Optional - tune as needed)
    generation_config = {
        "temperature": 0.6,       # Slightly lower temp for more predictable code/structured output
        "topP": 0.95,             # Nucleus sampling
        "topK": 40,               # Top-k sampling
        "maxOutputTokens": 8192, # Max tokens for the response (adjust based on model limits/needs)
        # "stopSequences": [...] # Generally avoid stop sequences for code generation unless specific cases arise
    }

    # --- Safety Settings REMOVED ---
    # The 'safetySettings' block is no longer defined or sent in the payload.
    # The API will use its default safety configurations.

    payload_data = _format_gemini_payload(query, history, modifier)
    # Add generation config to the payload
    payload_data["generationConfig"] = generation_config
    # --- REMOVED: payload_data["safetySettings"] = safety_settings ---

    api_response = _call_gemini_api(url, api_key, headers, payload_data)
    result_text = _parse_gemini_response(api_response)
    return result_text


# --- Text to Speech Function ---
def text_to_speech(text, engine='espeak', voice="en-gb", speed=160, pitch=20):
    """Converts text to speech using the specified engine."""
    if not text:
        print("Warning: No text provided for speech synthesis.")
        return

    # --- Text Cleaning (Common for both engines) ---
    # Keep cleaning minimal for TTS confirmation messages, original logic mostly OK
    cleaned_text = re.sub(r'[*_`#~\[\]\(\)]', '', text) # Remove Markdown/special chars
    cleaned_text = re.sub(r'\!\[.*?\]\(.*?\)', '', cleaned_text) # Remove Markdown images
    cleaned_text = re.sub(r'<.*?>', '', cleaned_text) # Remove HTML tags crudely
    cleaned_text = cleaned_text.replace('"', "'") # Replace double quotes
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip() # Consolidate whitespace

    if not cleaned_text:
        print("Warning: Text became empty after cleaning for TTS.")
        return

    # --- Engine Selection ---
    try:
        selected_engine = engine # Store the intended engine
        if engine == "espeak":
            # Check if espeak-ng exists (basic check)
            espeak_path = subprocess.run(['which', 'espeak-ng'], capture_output=True, text=True, check=False).stdout.strip()
            if not espeak_path:
                print("Error: 'espeak-ng' command not found in PATH. Cannot use espeak engine.")
                return

            command = ["espeak-ng", "-v", str(voice), "-s", str(speed), "-p", str(pitch), cleaned_text]
            process = subprocess.run(command, check=False, capture_output=True, text=True)
            if process.returncode != 0:
                 print(f"Error running espeak-ng (Code: {process.returncode}):\nStderr: {process.stderr.strip()}")
                 return
        elif engine == "piper":
            # Check Piper path validity
            if not PIPER_EXECUTABLE or not os.path.exists(PIPER_EXECUTABLE):
                 print(f"Error: Piper executable not found at configured path: {PIPER_EXECUTABLE}")
                 print("Skipping Piper TTS.")
                 return # Don't fallback here, just skip if Piper is explicitly requested but misconfigured
            if not PIPER_VOICE_MODEL or not os.path.exists(PIPER_VOICE_MODEL):
                 print(f"Error: Piper model not found at configured path: {PIPER_VOICE_MODEL}")
                 print("Skipping Piper TTS.")
                 return # Don't fallback here

            # Check paplay dependency
            paplay_path = subprocess.run(['which', 'paplay'], capture_output=True, text=True, check=False).stdout.strip()
            if not paplay_path:
                 print("Error: 'paplay' command not found in PATH. Cannot play Piper output.")
                 return

            # Construct and run the Piper pipeline
            piper_command = (
                f"echo {shlex.quote(cleaned_text)} | "
                f"{shlex.quote(PIPER_EXECUTABLE)} --model {shlex.quote(PIPER_VOICE_MODEL)} --output_file - | "
                f"paplay --raw --rate=22050 --format=s16le --channels=1"
            )
            # Use subprocess.Popen for potentially better error capture/handling if needed later
            process = subprocess.run(
                piper_command, shell=True, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True # Capture stderr
            )
            if process.returncode != 0:
                 # Log the error from the pipeline (could be piper or paplay)
                 print(f"Error running Piper/paplay pipeline (Code: {process.returncode}):\nStderr: {process.stderr.strip()}")
                 return
        else:
            print(f"Error: Unknown TTS engine '{engine}'. Skipping TTS.")
            # No fallback here to avoid unexpected behavior if user explicitly chose non-existent engine

    except FileNotFoundError as e:
         # This catch might be less likely now with 'which' checks, but keep for safety
        print(f"Error: TTS command not found - {e}. Check installation and PATH.")
    except Exception as e:
        print(f"\n--- Unexpected TTS Error ({selected_engine}) ---")
        print(f"An unexpected error occurred during text-to-speech: {e}")
        traceback.print_exc()
        print("---")


# --- Helper Function for Saving Files ---
def save_text_to_file(filename, content):
    """Saves the given text content to the specified filename in the current directory."""
    try:
        # Use pathlib for safer path handling
        target_path = pathlib.Path(filename)

        # Basic security checks: Prevent directory traversal and absolute paths
        if target_path.is_absolute() or ".." in target_path.parts:
             print(f"Error: Invalid filename '{filename}'. Path traversal or absolute paths are not allowed.")
             return False

        # Ensure filename is not empty after potential stripping
        if not target_path.name:
             print("Error: Empty filename provided after processing.")
             return False

        # Check if parent directories are involved (we only want to save in the current dir)
        if target_path.parent and str(target_path.parent) != '.':
             print(f"Error: Filename '{filename}' implies directories. Only saving to current directory is allowed.")
             # Attempt to use just the filename part
             target_path = pathlib.Path(target_path.name)
             print(f"Corrected filename to: '{target_path}'")
             if not target_path.name: # Double check after correction
                 print("Error: Corrected filename is empty.")
                 return False

        print(f"Attempting to save content to '{target_path}' in the current directory...")
        # Write the file
        target_path.write_text(content, encoding='utf-8')

        print(f"Content successfully saved to '{target_path}'")
        return True
    except IOError as e:
        print(f"Error saving file '{target_path}': {e}")
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"An unexpected error occurred while saving file '{target_path}': {e}")
        traceback.print_exc()
        return False

# --- Main Function ---
def main():
    """Computational response system loop with engine selection and file generation."""

    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(description="Gemini Chat with Text-to-Speech and File Generation.")
    parser.add_argument(
        "--tts-engine",
        choices=["espeak", "piper"],
        default=DEFAULT_TTS_ENGINE,
        help=f"Select the TTS engine (default: {DEFAULT_TTS_ENGINE})"
    )
    args = parser.parse_args()
    selected_tts_engine = args.tts_engine

    # --- Initialization ---
    history = []
    # Base modifier applies to all interactions unless overridden
    base_modifier = "You are a helpful AI assistant. Provide clear and concise responses."
    # Keep max history length reasonable
    MAX_HISTORY = 10

    print(f"--- SYSTEM ONLINE ---")
    print(f"Using TTS Engine: {selected_tts_engine}")
    print(f"Using Gemini Model: gemini-1.5-flash-latest") # Update if model changes
    print("Info: Model knowledge is based on training data (no live internet access).")
    print("Info: Using default API safety settings.") # Note that defaults are still active
    print("Commands: /clear, /save_hist <f.json>, /load_hist <f.json>")
    # Updated help text for the new /gen command
    print("          /gen <filename.ext> <prompt> (Generates content for file)")
    print("          exit")
    print("---------------------")


    while True:
        try:
            query = input("\nINPUT> ").strip()

            if not query:
                continue

            # --- Command Handling ---
            if query.lower() == 'exit':
                print("SYSTEM OFFLINE.")
                break
            elif query.lower() == '/clear':
                history = []
                print("History cleared.")
                continue
            # --- History Save/Load (Keep as is) ---
            elif query.lower().startswith('/save_hist '):
                parts = query.split(maxsplit=1)
                if len(parts) == 2 and parts[1]:
                    filename = parts[1]
                    if not filename.lower().endswith(".json"):
                        filename += ".json"
                        print(f"Appending '.json' extension. Saving as '{filename}'")
                    try:
                        # Use pathlib for consistency
                        save_path = pathlib.Path(filename)
                        # Basic check against saving outside current dir (though save_text_to_file does more)
                        if save_path.parent and str(save_path.parent) != '.':
                           print(f"Error: Cannot save history outside current directory ('{filename}').")
                           continue
                        with open(save_path, 'w', encoding='utf-8') as f:
                            json.dump(history, f, indent=2)
                        print(f"History saved to '{save_path}'")
                    except Exception as e:
                        print(f"Error saving history to '{filename}': {e}")
                        traceback.print_exc()
                else:
                    print("Usage: /save_hist <filename.json>")
                continue

            elif query.lower().startswith('/load_hist '):
                parts = query.split(maxsplit=1)
                if len(parts) == 2 and parts[1]:
                    filename = parts[1]
                    try:
                        load_path = pathlib.Path(filename)
                        if not load_path.is_file():
                           print(f"Error: File not found - '{filename}'")
                           continue

                        with open(load_path, 'r', encoding='utf-8') as f:
                            loaded_history = json.load(f)
                        # Validate history format more robustly
                        if (isinstance(loaded_history, list) and
                            all(isinstance(item, list) and len(item) == 2 and
                                isinstance(item[0], str) and isinstance(item[1], str)
                                for item in loaded_history)):
                             history = loaded_history[-MAX_HISTORY:] # Load max N items
                             print(f"History loaded from '{filename}'. {len(history)} interactions restored (max {MAX_HISTORY}).")
                        else:
                             print(f"Error: Invalid history format in '{filename}'. Expected list of [str, str] pairs.")
                    except FileNotFoundError: # Should be caught by is_file() but good practice
                        print(f"Error: File not found - '{filename}'")
                    except json.JSONDecodeError:
                        print(f"Error: Could not decode JSON from '{filename}'.")
                    except Exception as e:
                         print(f"Error loading history from '{filename}': {e}")
                         traceback.print_exc()
                else:
                    print("Usage: /load_hist <filename.json>")
                continue

            # --- Generic File Generation Command ---
            elif query.lower().startswith('/gen '):
                try:
                    parts = query.split(maxsplit=2)
                    if len(parts) < 3 or not parts[1] or not parts[2]:
                        print("Usage: /gen <filename.ext> <prompt>")
                        continue

                    filename = parts[1].strip()
                    actual_prompt = parts[2].strip()
                    file_saved = False

                    # Validate filename early
                    temp_path = pathlib.Path(filename)
                    if not temp_path.name or temp_path.is_absolute() or ".." in temp_path.parts or (temp_path.parent and str(temp_path.parent) != '.'):
                        print(f"Error: Invalid filename '{filename}'. Must be a simple filename for the current directory.")
                        continue

                    print(f"--- Generating content for '{filename}' ---")
                    print(f"Prompt: {actual_prompt[:100]}{'...' if len(actual_prompt) > 100 else ''}")

                    # --- Determine Generation Modifier based on file extension ---
                    file_ext = temp_path.suffix.lower().lstrip('.') # Get '.py', '.txt' etc. -> 'py', 'txt'
                    generation_modifier = "" # Specific instructions for the generation task

                    if file_ext == 'md':
                        generation_modifier = "Format the entire response STRICTLY as Markdown text. Do not include any introductory or concluding remarks outside the Markdown content itself."
                    elif file_ext == 'html':
                        generation_modifier = "Format the entire response STRICTLY as a complete, valid HTML5 document, including <!DOCTYPE html>, <html>, <head>, and <body> tags. Do not add any text before or after the HTML structure."
                    elif file_ext == 'py':
                        generation_modifier = "Generate Python code that fulfills the following request. Output ONLY the raw Python code, without any surrounding text, explanations, or markdown formatting like ```python ... ```."
                    elif file_ext == 'sh' or file_ext == 'bash':
                         generation_modifier = "Generate a Shell script (Bash) that fulfills the following request. Output ONLY the raw script content, including a shebang (#!/bin/bash) if appropriate. Do not add any surrounding text, explanations, or markdown formatting like ```bash ... ```."
                    elif file_ext == 'json':
                         generation_modifier = "Generate valid JSON data that fulfills the following request. Output ONLY the raw JSON data. Do not add any surrounding text, explanations, or markdown formatting."
                    elif file_ext == 'xml':
                         generation_modifier = "Generate valid XML data that fulfills the following request. Output ONLY the raw XML data, including a root element. Do not add any surrounding text, explanations, or markdown formatting."
                    elif file_ext == 'yaml' or file_ext == 'yml':
                         generation_modifier = "Generate valid YAML data that fulfills the following request. Output ONLY the raw YAML data. Do not add any surrounding text, explanations, or markdown formatting."
                    elif file_ext == 'css':
                        generation_modifier = "Generate CSS code that fulfills the following request. Output ONLY the raw CSS code. Do not add any surrounding text, explanations, or markdown formatting."
                    elif file_ext == 'js':
                        generation_modifier = "Generate JavaScript code that fulfills the following request. Output ONLY the raw JavaScript code. Do not add any surrounding text, explanations, or markdown formatting like ```javascript ... ```."
                    elif file_ext == 'txt' or not file_ext: # Treat no extension as plain text
                        generation_modifier = "Generate plain text content for the following request. Output only the text itself."
                    else:
                        # Generic instruction for other types
                        generation_modifier = f"Generate content suitable for a file with the extension '{file_ext}' based on the following request. Output ONLY the raw content suitable for this file type."

                    # Combine with base modifier for context (or just use the specific one)
                    # Let's use the specific generation modifier directly for focus
                    final_modifier = generation_modifier # Override base modifier for focused generation

                    # Call API - use None for history to avoid chat context interfering with generation
                    response = get_gemini_response(actual_prompt, history=None, modifier=final_modifier)

                    # Process and save the response
                    if response.startswith("Error:") or response.startswith("Warning: No content"): # Handle specific no-content warning
                        print(f"\nAPI Response: {response}")
                        print(f"(File '{filename}' not saved due to API issue or no content)")
                        history_entry = f"Attempted file generation for '{filename}'. Failed: {response[:100]}..."
                    elif response.startswith("Warning:"): # Handle other warnings (MAX_TOKENS, SAFETY) but still save
                        print(f"\nAPI Response: {response}")
                        print(f"Attempting to save potentially incomplete/filtered content to '{filename}'...")
                        file_saved = save_text_to_file(filename, response.split('---\n', 1)[-1]) # Save content after warning prefix
                        if file_saved:
                            history_entry = f"Generated file '{filename}' with warning: {response.split('---\\n', 1)[0]}"
                        else:
                            history_entry = f"Attempted file generation for '{filename}'. API Warning, but failed to save file."
                    else:
                        # Success case - print preview and save
                        print(f"\nAPI Response (raw content for {filename}):\n--- START CONTENT ---")
                        preview_lines = response.splitlines()
                        for i, line in enumerate(preview_lines):
                            if i < 20: # Show first 20 lines
                                print(line)
                            elif i == 20:
                                print(f"[... {len(preview_lines) - 20} more lines ...]")
                                break
                        print("--- END CONTENT ---")
                        file_saved = save_text_to_file(filename, response)
                        if file_saved:
                            history_entry = f"Successfully generated and saved file: '{filename}'"
                        else:
                            history_entry = f"Attempted file generation for '{filename}'. API OK, but failed to save file."

                    # Add concise history entry
                    history.append([query, history_entry])
                    history = history[-MAX_HISTORY:] # Trim history

                    print("--- File Generation Complete ---")

                except Exception as e:
                    print(f"An error occurred during file generation command processing: {e}")
                    traceback.print_exc()
                continue # Go back to input prompt

            # --- Regular Chat Interaction ---
            else:
                print("Generating response...")
                # Use the base modifier for general chat
                response = get_gemini_response(query, history, base_modifier)
                print(f"\nOUTPUT: {response}")

                # Update history only on success (no error/warning prefixes)
                if not response.startswith("Error:") and not response.startswith("Warning:"):
                     history.append([query, response])
                     history = history[-MAX_HISTORY:] # Trim history
                     # Speak the response if TTS is enabled and no issues
                     text_to_speech(response, engine=selected_tts_engine)
                elif response.startswith("Warning:"):
                     print("(TTS skipped for warning message)")
                     # Optionally add warning to history? For now, skip.
                else: # Error case
                     print("(TTS skipped due to error)")
                     print("(Error response not added to conversational history)")


        except ValueError as e:
            print(f"Configuration Error: {e}")
            traceback.print_exc()
            break # Fatal config error
        except KeyboardInterrupt:
            print("\nSYSTEM INTERRUPTED. OFFLINE.")
            break
        except Exception as e:
            print(f"\n--- UNEXPECTED ERROR IN MAIN LOOP ---")
            print(f"An unexpected error occurred: {e}")
            traceback.print_exc()
            print("Attempting to continue...") # Try to recover if possible

if __name__ == "__main__":
    # --- Pre-flight checks (API Key, Piper Paths) ---
    if not os.getenv("GEMINI_API_KEY"):
        print("CRITICAL ERROR: Environment variable GEMINI_API_KEY is not set.")
        print("Please set this variable with your Gemini API key.")
        sys.exit(1)
    else:
        print("GEMINI_API_KEY found.")

    # Determine selected TTS engine *before* checking paths
    temp_args, _ = argparse.ArgumentParser().parse_known_args()
    selected_tts_engine_check = getattr(temp_args, 'tts_engine', DEFAULT_TTS_ENGINE) # Get from args or default

    # Check Piper paths ONLY if piper is selected
    if selected_tts_engine_check == 'piper':
         piper_ok = True
         print("--- Checking Piper Configuration (since piper is selected) ---")
         if not PIPER_EXECUTABLE or not os.path.exists(PIPER_EXECUTABLE):
              print(f"ERROR: Piper executable not found or path empty: '{PIPER_EXECUTABLE}'")
              piper_ok = False
         else:
             print(f"Piper executable found: '{PIPER_EXECUTABLE}'")

         if not PIPER_VOICE_MODEL or not os.path.exists(PIPER_VOICE_MODEL):
              print(f"ERROR: Piper voice model not found or path empty: '{PIPER_VOICE_MODEL}'")
              piper_ok = False
         else:
              print(f"Piper voice model found: '{PIPER_VOICE_MODEL}'")

         if not piper_ok:
              print("--- Piper TTS configuration invalid. Please update paths at the top of the script. ---")
              # Decide if you want to exit or just warn
              # sys.exit(1) # Exit if Piper must work
              print("Warning: Piper will likely fail if used.")
         else:
              print("Piper executable and model paths appear valid.")
         print("---------------------------------------------------------")
    elif selected_tts_engine_check == 'espeak':
         print("--- Checking eSpeak Configuration (since espeak is selected) ---")
         espeak_path = subprocess.run(['which', 'espeak-ng'], capture_output=True, text=True, check=False).stdout.strip()
         if not espeak_path:
             print("ERROR: 'espeak-ng' command not found in system PATH.")
             print("Warning: eSpeak TTS will fail if used.")
         else:
             print(f"eSpeak executable found: '{espeak_path}'")
         print("----------------------------------------------------------")


    # Start the main application loop
    main()

# --- END OF FILE gemini.espeak_and_piper0.py ---
