# --- START OF FILE gemini.espeak_and_piper0.py --- # (Removed explicit safety handling)

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
            if isinstance(q, str) and isinstance(a, str):
                conversation.append({"role": "user", "parts": [{"text": q}]})
                conversation.append({"role": "model", "parts": [{"text": a}]})
            else:
                print(f"Warning: Skipping invalid history entry: ({type(q)}, {type(a)})")

    if history:
         history_context = "\n".join([f"User: {q}\nModel: {a}" for q, a in history])
         full_query = f"{modifier}\n---\nPrevious Conversation Context:\n{history_context}\n---\nCurrent Query:\n{query}"
    else:
         full_query = f"{modifier}\n---\nQuery:\n{query}" if modifier else query

    conversation.append({"role": "user", "parts": [{"text": full_query}]})
    data = {"contents": conversation}
    return data

def _call_gemini_api(url, api_key, headers, data):
    """Makes the POST request to the Gemini API and handles request errors."""
    try:
        response = requests.post(f"{url}?key={api_key}", headers=headers, json=data, timeout=240)
        response.raise_for_status()
        return response
    except requests.exceptions.Timeout:
        print("Error: API request timed out.")
        return "Error: API request timed out."
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err} - Status Code: {http_err.response.status_code}")
        try:
            error_details = http_err.response.json()
            print(f"API Error Details: {json.dumps(error_details, indent=2)}")
            api_error_message = error_details.get('error', {}).get('message', 'Unknown API error')
            return f"Error: HTTP {http_err.response.status_code} - {api_error_message}"
        except json.JSONDecodeError:
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
    """Parses the JSON response from Gemini API and extracts text, ignoring specific safety flags."""
    if isinstance(response, str): # Handle errors from _call_gemini_api
        return response

    try:
        response_data = response.json()
        # print(f"DEBUG: Full API Response JSON:\n{json.dumps(response_data, indent=2)}")

        # Check for top-level API errors first
        api_error = response_data.get('error')
        if api_error:
            return f"Error from API: {api_error.get('message', 'Unknown API error')} (Code: {api_error.get('code', 'N/A')})"

        # REMOVED: Explicit check for promptFeedback blockReason

        # Check for candidates
        candidates = response_data.get('candidates')
        if not candidates:
             # Attempt to get *any* feedback if no candidates, otherwise generic error
             feedback = response_data.get('promptFeedback')
             feedback_info = f" Prompt Feedback: {json.dumps(feedback)}" if feedback else ""
             return f"Error: No candidates found in response.{feedback_info} Response JSON: {json.dumps(response_data)}"

        if not candidates or not candidates[0]:
             return f"Error: Received empty or invalid candidate list. Response JSON: {json.dumps(response_data)}"

        # Process the first candidate
        candidate = candidates[0]
        finish_reason = candidate.get('finishReason')
        # We don't use safety_ratings for specific blocking checks anymore
        # safety_ratings = candidate.get('safetyRatings')

        # --- Content Extraction ---
        content = candidate.get('content')
        text = ""
        if content and 'parts' in content and content['parts']:
            text = "".join(part.get('text', '') for part in content['parts']).strip()
        elif content and 'text' in content:
             text = content['text'].strip()

        # --- Post-Extraction Checks ---

        # Check finish reason *after* attempting to extract content
        # Handle expected/common reasons first
        if finish_reason == "STOP":
             if not text:
                  # Response finished normally but produced no text.
                  return "Warning: Received response with no content (finish reason: STOP)."
             # else: text extraction succeeded, proceed normally
        elif finish_reason == "MAX_TOKENS":
            if text:
                print(f"Warning: Response cut short due to maximum token limit ({finish_reason}).")
                return f"Warning: MAX_TOKENS limit reached. Output may be incomplete.\n---\n{text}"
            else:
                return f"Error: Candidate finished due to maximum token limit ({finish_reason}). No partial content extracted."
        # REMOVED: Specific handling for finish_reason == "SAFETY"
        elif finish_reason and finish_reason != "FINISH_REASON_UNSPECIFIED":
             # Handle any other non-STOP, non-MAX_TOKENS, non-UNSPECIFIED reason generically
             if text:
                 print(f"Warning: Candidate finished unexpectedly (Reason: {finish_reason}).")
                 return f"Warning: Unexpected finish reason ({finish_reason}). Output may be incomplete.\n---\n{text}"
             else:
                 # Extracting safety ratings here is optional, just for generic info if available
                 safety_ratings = candidate.get('safetyRatings')
                 ratings_str = f" Safety Ratings: {json.dumps(safety_ratings)}" if safety_ratings else ""
                 return f"Error: Candidate finished unexpectedly. Reason: {finish_reason}. No content extracted.{ratings_str}"


        # If no text extracted for some other reason (e.g. unexpected structure, null parts)
        if not text and finish_reason == "STOP":
            # This case is already handled above, but double-check logic path. If we reach here, something is odd.
             return "Warning: Received response with no content (finish reason: STOP)." # Reiterate warning
        elif not text and finish_reason != "STOP":
             # Should likely have been caught by finish_reason checks above, but as a fallback:
             return f"Error: Failed to extract text content from candidate. Finish Reason: {finish_reason}. Candidate: {json.dumps(candidate)}"


        # --- Code Cleaning (Attempt to remove markdown backticks if present) ---
        if text.startswith("```") and text.endswith("```"):
            lines = text.splitlines()
            if len(lines) > 1:
                 first_line_content = lines[0].strip()[3:].strip()
                 if len(first_line_content.split()) <= 1:
                      print("Info: Removing markdown code block fences (```).")
                      text = "\n".join(lines[1:-1]).strip()

        return text # Return the extracted text

    except json.JSONDecodeError as e:
        response_text = response.text if hasattr(response, 'text') else "N/A"
        return f"Error decoding API response JSON: {e}. Response text: {response_text[:500]}..."
    except IndexError:
         response_data_str = str(response_data)[:500] if 'response_data' in locals() else 'N/A'
         return f"Error processing API response: Invalid candidate structure. Response JSON slice: {response_data_str}"
    except Exception as e:
        response_data_str = str(response_data)[:500] if 'response_data' in locals() else 'N/A'
        print(f"Unexpected parsing error: {e}")
        traceback.print_exc()
        return f"Error processing API response structure: {e}. Response JSON slice: {response_data_str}"


# --- Updated get_gemini_response ---
def get_gemini_response(query, history=None, modifier=""):
    """Fetches a response from the Gemini API using default safety settings."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "Error: API key not found. Set GEMINI_API_KEY."

    # --- Use the specified experimental model ---
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro-exp-03-25:generateContent"
    headers = {'Content-Type': 'application/json'}

    # --- Generation Config ---
    generation_config = {
        "temperature": 0.7,
        "topP": 0.95,
        "topK": 40,
        "maxOutputTokens": 8192,
    }

    # --- Safety Settings REMOVED ---
    # No safetySettings field is sent; API defaults will be used.

    payload_data = _format_gemini_payload(query, history, modifier)
    payload_data["generationConfig"] = generation_config
    # REMOVED: payload_data["safetySettings"] = safety_settings

    # print(f"DEBUG: Sending Payload (Default Safety):\n{json.dumps(payload_data, indent=2)}") # Debug

    api_response = _call_gemini_api(url, api_key, headers, payload_data)
    result_text = _parse_gemini_response(api_response) # Parsing logic no longer checks specific safety flags
    return result_text


# --- Text to Speech Function ---
# (No changes needed in text_to_speech)
def text_to_speech(text, engine='espeak', voice="en-gb", speed=160, pitch=20):
    """Converts text to speech using the specified engine."""
    if not text:
        print("Warning: No text provided for speech synthesis.")
        return

    cleaned_text = re.sub(r'[*_`#~\[\]\(\)]', '', text)
    cleaned_text = re.sub(r'\!\[.*?\]\(.*?\)', '', cleaned_text)
    cleaned_text = re.sub(r'<.*?>', '', cleaned_text)
    cleaned_text = cleaned_text.replace('"', "'")
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()

    if not cleaned_text:
        print("Warning: Text became empty after cleaning for TTS.")
        return

    try:
        selected_engine = engine
        if engine == "espeak":
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
            if not PIPER_EXECUTABLE or not os.path.exists(PIPER_EXECUTABLE):
                 print(f"Error: Piper executable not found at configured path: {PIPER_EXECUTABLE}")
                 print("Skipping Piper TTS.")
                 return
            if not PIPER_VOICE_MODEL or not os.path.exists(PIPER_VOICE_MODEL):
                 print(f"Error: Piper model not found at configured path: {PIPER_VOICE_MODEL}")
                 print("Skipping Piper TTS.")
                 return
            paplay_path = subprocess.run(['which', 'paplay'], capture_output=True, text=True, check=False).stdout.strip()
            if not paplay_path:
                 print("Error: 'paplay' command not found in PATH. Cannot play Piper output.")
                 return
            piper_command = (
                f"echo {shlex.quote(cleaned_text)} | "
                f"{shlex.quote(PIPER_EXECUTABLE)} --model {shlex.quote(PIPER_VOICE_MODEL)} --output_file - | "
                f"paplay --raw --rate=22050 --format=s16le --channels=1"
            )
            process = subprocess.run(
                piper_command, shell=True, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True
            )
            if process.returncode != 0:
                 print(f"Error running Piper/paplay pipeline (Code: {process.returncode}):\nStderr: {process.stderr.strip()}")
                 return
        else:
            print(f"Error: Unknown TTS engine '{engine}'. Skipping TTS.")

    except FileNotFoundError as e:
        print(f"Error: TTS command not found - {e}. Check installation and PATH.")
    except Exception as e:
        print(f"\n--- Unexpected TTS Error ({selected_engine}) ---")
        print(f"An unexpected error occurred during text-to-speech: {e}")
        traceback.print_exc()
        print("---")


# --- Helper Function for Saving Files ---
# (No changes needed in save_text_to_file)
def save_text_to_file(filename, content):
    """Saves the given text content to the specified filename in the current directory."""
    try:
        target_path = pathlib.Path(filename)
        if target_path.is_absolute() or ".." in target_path.parts:
             print(f"Error: Invalid filename '{filename}'. Path traversal or absolute paths are not allowed.")
             return False
        if not target_path.name:
             print("Error: Empty filename provided after processing.")
             return False
        if target_path.parent and str(target_path.parent) != '.':
             print(f"Error: Filename '{filename}' implies directories. Only saving to current directory is allowed.")
             target_path = pathlib.Path(target_path.name)
             print(f"Corrected filename to: '{target_path}'")
             if not target_path.name:
                 print("Error: Corrected filename is empty.")
                 return False
        print(f"Attempting to save content to '{target_path}' in the current directory...")
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

    parser = argparse.ArgumentParser(description="Gemini Chat with Text-to-Speech and File Generation.") # Simplified description
    parser.add_argument(
        "--tts-engine",
        choices=["espeak", "piper"],
        default=DEFAULT_TTS_ENGINE,
        help=f"Select the TTS engine (default: {DEFAULT_TTS_ENGINE})"
    )
    args = parser.parse_args()
    selected_tts_engine = args.tts_engine

    history = []
    base_modifier = "You are a helpful AI assistant. Provide clear and concise responses."
    MAX_HISTORY = 10

    print(f"--- SYSTEM ONLINE ---")
    print(f"Using TTS Engine: {selected_tts_engine}")
    print(f"Using Gemini Model: gemini-2.5-pro-exp-03-25")
    print("Info: Model knowledge is based on training data (no live internet access).")
    # Updated safety message
    print("Info: Using default API safety settings (client-side safety handling removed).")
    print("Commands: /clear, /save_hist <f.json>, /load_hist <f.json>")
    print("          /gen <filename.ext> <prompt> (Generates content for file)")
    print("          exit")
    print("---------------------")


    while True:
        try:
            query = input("\nINPUT> ").strip()

            if not query: continue

            if query.lower() == 'exit':
                print("SYSTEM OFFLINE.")
                break
            elif query.lower() == '/clear':
                history = []
                print("History cleared.")
                continue
            # --- History Save/Load ---
            elif query.lower().startswith('/save_hist '):
                parts = query.split(maxsplit=1)
                if len(parts) == 2 and parts[1]:
                    filename = parts[1]
                    if not filename.lower().endswith(".json"):
                        filename += ".json"
                        print(f"Appending '.json' extension. Saving as '{filename}'")
                    try:
                        save_path = pathlib.Path(filename)
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
                        if (isinstance(loaded_history, list) and
                            all(isinstance(item, list) and len(item) == 2 and
                                isinstance(item[0], str) and isinstance(item[1], str)
                                for item in loaded_history)):
                             history = loaded_history[-MAX_HISTORY:]
                             print(f"History loaded from '{filename}'. {len(history)} interactions restored (max {MAX_HISTORY}).")
                        else:
                             print(f"Error: Invalid history format in '{filename}'. Expected list of [str, str] pairs.")
                    except FileNotFoundError:
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

                    temp_path = pathlib.Path(filename)
                    if not temp_path.name or temp_path.is_absolute() or ".." in temp_path.parts or (temp_path.parent and str(temp_path.parent) != '.'):
                        print(f"Error: Invalid filename '{filename}'. Must be a simple filename for the current directory.")
                        continue

                    print(f"--- Generating content for '{filename}' ---")
                    print(f"Prompt: {actual_prompt[:100]}{'...' if len(actual_prompt) > 100 else ''}")

                    file_ext = temp_path.suffix.lower().lstrip('.')
                    generation_modifier = ""

                    # Generation modifiers (unchanged)
                    if file_ext == 'md': generation_modifier = "Format the entire response STRICTLY as Markdown text..."
                    elif file_ext == 'html': generation_modifier = "Format the entire response STRICTLY as a complete, valid HTML5 document..."
                    elif file_ext == 'py': generation_modifier = "Generate Python code... Output ONLY the raw Python code..."
                    elif file_ext in ['sh', 'bash']: generation_modifier = "Generate a Shell script (Bash)... Output ONLY the raw script content..."
                    elif file_ext == 'json': generation_modifier = "Generate valid JSON data... Output ONLY the raw JSON data..."
                    elif file_ext == 'xml': generation_modifier = "Generate valid XML data... Output ONLY the raw XML data..."
                    elif file_ext in ['yaml', 'yml']: generation_modifier = "Generate valid YAML data... Output ONLY the raw YAML data..."
                    elif file_ext == 'css': generation_modifier = "Generate CSS code... Output ONLY the raw CSS code..."
                    elif file_ext == 'js': generation_modifier = "Generate JavaScript code... Output ONLY the raw JavaScript code..."
                    elif file_ext == 'txt' or not file_ext: generation_modifier = "Generate plain text content..."
                    else: generation_modifier = f"Generate content suitable for a file with the extension '{file_ext}'... Output ONLY the raw content..."

                    final_modifier = generation_modifier

                    # API call uses default safety settings implicitly
                    response = get_gemini_response(actual_prompt, history=None, modifier=final_modifier)

                    # Process and save response (logic remains similar, relies on generic errors now)
                    if response.startswith("Error:") or response.startswith("Warning: No content"):
                        print(f"\nAPI Response: {response}")
                        print(f"(File '{filename}' not saved due to issue or no content)")
                        history_entry = f"Attempted file generation for '{filename}'. Failed: {response[:100]}..."
                    elif response.startswith("Warning:"): # Handle MAX_TOKENS or other generic warnings
                        print(f"\nAPI Response: {response}")
                        print(f"Attempting to save potentially incomplete content to '{filename}'...")
                        content_to_save = response.split('---\n', 1)[-1] if '---\n' in response else response
                        file_saved = save_text_to_file(filename, content_to_save)
                        if file_saved:
                            warning_summary = response.split('---\n', 1)[0]
                            history_entry = f"Generated file '{filename}' with warning: {warning_summary}"
                        else:
                            history_entry = f"Attempted file generation for '{filename}'. API Warning, but failed to save file."
                    else:
                        # Success case
                        print(f"\nAPI Response (raw content for {filename}):\n--- START CONTENT ---")
                        preview_lines = response.splitlines()
                        for i, line in enumerate(preview_lines):
                            if i < 20: print(line)
                            elif i == 20: print(f"[... {len(preview_lines) - 20} more lines ...]"); break
                        if not preview_lines: print("[... No content received ...]")
                        print("--- END CONTENT ---")

                        if response:
                            file_saved = save_text_to_file(filename, response)
                        else:
                            print(f"(File '{filename}' not saved as response was empty)")
                            file_saved = False

                        if file_saved: history_entry = f"Successfully generated and saved file: '{filename}'"
                        elif not response: history_entry = f"File generation for '{filename}' resulted in empty content. File not saved."
                        else: history_entry = f"Attempted file generation for '{filename}'. API OK, but failed to save file."

                    history.append([query, history_entry])
                    history = history[-MAX_HISTORY:]

                    print("--- File Generation Complete ---")

                except Exception as e:
                    print(f"An error occurred during file generation command processing: {e}")
                    traceback.print_exc()
                continue

            # --- Regular Chat Interaction ---
            else:
                print("Generating response...")
                # API call uses default safety settings implicitly
                response = get_gemini_response(query, history, base_modifier)
                print(f"\nOUTPUT: {response}")

                if not response.startswith("Error:") and not response.startswith("Warning:"):
                     if response:
                         history.append([query, response])
                         history = history[-MAX_HISTORY:]
                         text_to_speech(response, engine=selected_tts_engine)
                     else:
                        print("(Empty response received, not added to history or spoken)")

                elif response.startswith("Warning:"):
                     print("(TTS skipped for warning message)")
                else: # Error case
                     print("(TTS skipped due to error)")
                     print("(Error response not added to conversational history)")


        except ValueError as e:
            print(f"Configuration Error: {e}")
            traceback.print_exc()
            break
        except KeyboardInterrupt:
            print("\nSYSTEM INTERRUPTED. OFFLINE.")
            break
        except Exception as e:
            print(f"\n--- UNEXPECTED ERROR IN MAIN LOOP ---")
            print(f"An unexpected error occurred: {e}")
            traceback.print_exc()
            print("Attempting to continue...")

if __name__ == "__main__":
    # --- Pre-flight checks ---
    if not os.getenv("GEMINI_API_KEY"):
        print("CRITICAL ERROR: Environment variable GEMINI_API_KEY is not set.")
        sys.exit(1)
    else:
        print("GEMINI_API_KEY found.")

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--tts-engine", choices=["espeak", "piper"])
    known_args, _ = parser.parse_known_args()
    selected_tts_engine_check = known_args.tts_engine or DEFAULT_TTS_ENGINE

    # TTS Dependency Checks (unchanged)
    if selected_tts_engine_check == 'piper':
         piper_ok = True
         print("--- Checking Piper Configuration ---")
         if not PIPER_EXECUTABLE or not os.path.exists(PIPER_EXECUTABLE): print(f"ERROR: Piper executable not found: '{PIPER_EXECUTABLE}'"); piper_ok = False
         else: print(f"Piper executable found: '{PIPER_EXECUTABLE}'")
         if not PIPER_VOICE_MODEL or not os.path.exists(PIPER_VOICE_MODEL): print(f"ERROR: Piper voice model not found: '{PIPER_VOICE_MODEL}'"); piper_ok = False
         else: print(f"Piper voice model found: '{PIPER_VOICE_MODEL}'")
         if not piper_ok: print("--- Piper TTS configuration invalid. ---"); print("Warning: Piper will likely fail.")
         else: print("Piper paths appear valid.")
         print("----------------------------------")
    elif selected_tts_engine_check == 'espeak':
         print("--- Checking eSpeak Configuration ---")
         espeak_path = subprocess.run(['which', 'espeak-ng'], capture_output=True, text=True, check=False).stdout.strip()
         if not espeak_path: print("ERROR: 'espeak-ng' command not found."); print("Warning: eSpeak TTS will fail.")
         else: print(f"eSpeak executable found: '{espeak_path}'")
         print("-----------------------------------")

    main()

# --- END OF FILE gemini.espeak_and_piper0.py ---