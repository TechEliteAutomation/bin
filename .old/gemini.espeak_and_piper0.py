# --- START OF FILE gemini_files_no_safety_config.py ---

import os
import requests
import subprocess
import re
import json
import argparse # Import argparse for command-line arguments
import shlex   # Import shlex to safely quote text for shell commands
import sys
import traceback # For detailed error logging

# --- Configuration (Could be moved to a config file later) ---
DEFAULT_TTS_ENGINE = "piper" # or "espeak"
# --- !! UPDATE THESE PATHS !! ---
PIPER_EXECUTABLE = "/usr/bin/piper-tts" # Replace with your actual path to piper executable
PIPER_VOICE_MODEL = "/home/u/s/tts/en_US-amy-medium.onnx" # Replace with your actual path to the Piper .onnx model file
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
        response = requests.post(f"{url}?key={api_key}", headers=headers, json=data, timeout=120) # Increased timeout for potentially longer generations
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
                    return f"Warning: Response likely cut short due to maximum token limit ({finish_reason}). Partial text received:\n---\n{text}"
                else:
                     return f"Error: Candidate finished due to maximum token limit ({finish_reason}). No partial content extracted."
            elif finish_reason == "SAFETY":
                 # Content might be blocked at the candidate level by default policies
                 ratings_str = json.dumps(safety_ratings) if safety_ratings else "N/A"
                 print(f"API Info: Candidate content blocked by safety filter (default policy). Reason: {finish_reason}, Safety Ratings: {ratings_str}")
                 if text:
                     return f"Warning: Candidate content potentially filtered for safety (default policy - {finish_reason}). Partial text received:\n---\n{text}"
                 else:
                     return f"Error: Candidate content blocked due to safety (default policy - {finish_reason}). Ratings: {ratings_str}"
            else:
                # Other reasons like RECITATION, OTHER
                if text:
                     return f"Warning: Candidate finished unexpectedly (Reason: {finish_reason}). Partial text received:\n---\n{text}"
                else:
                     return f"Error: Candidate finished unexpectedly. Reason: {finish_reason}. Safety Ratings: {safety_ratings}"

        # If finish reason is STOP but no content was extracted
        if finish_reason == "STOP" and not text:
            return "Warning: Received response with no content (finish reason: STOP)."

        # If no text extracted for other reasons
        if not text:
             return f"Error: Failed to extract text content from candidate. Finish Reason: {finish_reason}. Candidate: {json.dumps(candidate)}"

        return text # Return the extracted text

    except json.JSONDecodeError as e:
        response_text = response.text if hasattr(response, 'text') else "N/A"
        return f"Error decoding API response JSON: {e}. Response text: {response_text[:500]}..."
    except IndexError:
         # Handle cases where candidates[0] might not exist after the initial check
         return f"Error processing API response: Invalid candidate structure. Response JSON: {json.dumps(response_data)}"
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
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro-exp-03-25:generateContent"
    headers = {'Content-Type': 'application/json'}

    # Generation Config (Optional - tune as needed)
    generation_config = {
        "temperature": 0.7,       # Controls randomness (lower = more deterministic)
        "topP": 0.95,             # Nucleus sampling
        "topK": 40,               # Top-k sampling
        "maxOutputTokens": 8192, # Max tokens for the response (adjust based on model limits/needs)
        #"stopSequences": ["\n\n\n"] # Optional sequences to stop generation
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
    cleaned_text = re.sub(r'[*_`#~\[\]\(\)]', '', text) # Remove Markdown/special chars
    cleaned_text = re.sub(r'\!\[.*?\]\(.*?\)', '', cleaned_text) # Remove Markdown images
    cleaned_text = re.sub(r'<.*?>', '', cleaned_text) # Remove HTML tags crudely
    cleaned_text = cleaned_text.replace('"', "'") # Replace double quotes
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip() # Consolidate whitespace

    if not cleaned_text:
        print("Warning: Text became empty after cleaning.")
        return

    # --- Engine Selection ---
    try:
        selected_engine = engine
        if engine == "espeak":
            command = ["espeak-ng", "-v", str(voice), "-s", str(speed), "-p", str(pitch), cleaned_text]
            process = subprocess.run(command, check=False, capture_output=True, text=True)
            if process.returncode != 0:
                 print(f"Error running espeak-ng (Code: {process.returncode}):\nStderr: {process.stderr}")
                 return
        elif engine == "piper":
            if not os.path.exists(PIPER_EXECUTABLE):
                 print(f"Error: Piper executable not found at {PIPER_EXECUTABLE}")
                 print("Falling back to espeak.")
                 text_to_speech(text, engine='espeak', voice=voice, speed=speed, pitch=pitch)
                 return
            if not os.path.exists(PIPER_VOICE_MODEL):
                 print(f"Error: Piper model not found at {PIPER_VOICE_MODEL}")
                 print("Falling back to espeak.")
                 text_to_speech(text, engine='espeak', voice=voice, speed=speed, pitch=pitch)
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
            print(f"Error: Unknown TTS engine '{engine}'. Using espeak.")
            text_to_speech(text, engine='espeak', voice=voice, speed=speed, pitch=pitch)

    except FileNotFoundError as e:
        print("\n--- TTS File Not Found Error ---")
        # ... (error reporting as before) ...
        print(f"Error: Command not found - {e}. Check installation and PATH.")
        print("---")
    except Exception as e:
        print(f"\n--- Unexpected TTS Error ({selected_engine}) ---")
        print(f"An unexpected error occurred during text-to-speech: {e}")
        traceback.print_exc()
        print("---")


# --- Helper Function for Saving Files ---
def save_text_to_file(filename, content):
    """Saves the given text content to the specified filename."""
    try:
        if "/" in filename or "\\" in filename:
             safe_filename = os.path.basename(filename)
             print(f"Warning: Filename '{filename}' contains directory separators. Using base name '{safe_filename}' in current directory.")
             filename = safe_filename
        elif not filename:
             print("Error: Empty filename provided for saving.")
             return False
        if filename.startswith('.') or '..' in filename:
            print(f"Error: Invalid filename '{filename}'. Cannot start with '.' or contain '..'.")
            return False

        print(f"Attempting to save content to '{filename}'...")
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Content successfully saved to '{filename}'")
        return True
    except IOError as e:
        print(f"Error saving file '{filename}': {e}")
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"An unexpected error occurred while saving file '{filename}': {e}")
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
    base_modifier = "You are an instantiation of pure computational logic. Your function is to process queries."

    print(f"--- SYSTEM ONLINE ---")
    print(f"Using TTS Engine: {selected_tts_engine}")
    print(f"Using Gemini Model: gemini-2.5-pro-exp-03-25")
    print("Info: Model knowledge is based on training data (no live internet access).")
    print("Info: Using default API safety settings.") # Note that defaults are still active
    print("Commands: /clear, /save_hist <f.json>, /load_hist <f.json>")
    print("          /gen_txt <file.txt> <prompt>, /gen_md <file.md> <prompt>, /gen_html <file.html> <prompt>")
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
            elif query.lower().startswith('/save_hist '):
                parts = query.split(maxsplit=1)
                if len(parts) == 2 and parts[1]:
                    filename = parts[1]
                    if not filename.lower().endswith(".json"):
                        filename += ".json"
                        print(f"Appending '.json' extension. Saving as '{filename}'")
                    try:
                        with open(filename, 'w', encoding='utf-8') as f:
                            json.dump(history, f, indent=2)
                        print(f"History saved to '{filename}'")
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
                        with open(filename, 'r', encoding='utf-8') as f:
                            loaded_history = json.load(f)
                        if (isinstance(loaded_history, list) and
                            all(isinstance(item, list) and len(item) == 2 and
                                isinstance(item[0], str) and isinstance(item[1], str)
                                for item in loaded_history)):
                             history = loaded_history
                             print(f"History loaded from '{filename}'. {len(history)} interactions restored.")
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

            # --- File Generation Commands ---
            elif query.lower().startswith(('/gen_txt ', '/gen_md ', '/gen_html ')):
                try:
                    parts = query.split(maxsplit=2)
                    if len(parts) < 3 or not parts[1] or not parts[2]:
                        print("Usage: /gen_<format> <filename> <prompt>")
                        continue

                    command_type = parts[0].lower()
                    filename = parts[1].strip()
                    actual_prompt = parts[2].strip()
                    file_saved = False

                    print(f"--- Generating content for '{filename}' ---")

                    modifier = base_modifier
                    target_extension = ""
                    if command_type == '/gen_md':
                         modifier += "\nFormat the entire response STRICTLY as Markdown text..." # As before
                         target_extension = ".md"
                    elif command_type == '/gen_html':
                         modifier += "\nFormat the entire response STRICTLY as a complete, valid HTML5 document..." # As before
                         target_extension = ".html"
                    elif command_type == '/gen_txt':
                         target_extension = ".txt"
                    else:
                         print(f"Error: Unknown generation command '{command_type}'")
                         continue

                    if not filename.lower().endswith(target_extension):
                        filename += target_extension
                        print(f"Appending '{target_extension}' extension. Saving as '{filename}'")

                    response = get_gemini_response(actual_prompt, history=None, modifier=modifier)

                    if response.startswith("Error:") or response.startswith("Warning:"):
                        print(f"\nAPI Response: {response}")
                        print(f"(File '{filename}' not saved due to API issue)")
                    else:
                        print(f"\nAPI Response (raw content for {filename}):\n--- START CONTENT ---")
                        preview_lines = response.splitlines()[:20]
                        for line in preview_lines: print(line)
                        if len(response.splitlines()) > 20: print("[... content truncated ...]")
                        print("--- END CONTENT ---")
                        file_saved = save_text_to_file(filename, response)

                    # Add history entry
                    if file_saved:
                         history.append([query, f"Successfully generated and saved file: '{filename}'"])
                    elif response.startswith("Error:") or response.startswith("Warning:"):
                         history.append([query, f"Attempted file generation for '{filename}'. Failed due to API issue: {response[:100]}..."])
                    else:
                         history.append([query, f"Attempted file generation for '{filename}'. API OK, but failed to save file."])
                    history = history[-10:]

                    print("--- File Generation Complete ---")

                except Exception as e:
                    print(f"An error occurred during file generation command processing: {e}")
                    traceback.print_exc()
                continue

            # --- Regular Chat Interaction ---
            else:
                print("Generating response...")
                modifier = base_modifier
                response = get_gemini_response(query, history, modifier)
                print(f"\nOUTPUT: {response}")

                if not response.startswith("Error:"):
                     history.append([query, response])
                     history = history[-10:]
                else:
                     print(f"(Error response not added to conversational history)")

                if not response.startswith("Error:") and not response.startswith("Warning:"):
                     text_to_speech(response, engine=selected_tts_engine)
                elif response.startswith("Warning:"):
                     print("(TTS skipped for warning message)")
                else:
                     print("(TTS skipped due to error)")

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
    # --- Pre-flight checks (API Key, Piper Paths) ---
    if not os.getenv("GEMINI_API_KEY"):
        print("CRITICAL ERROR: Environment variable GEMINI_API_KEY is not set.")
        sys.exit(1)

    check_piper = DEFAULT_TTS_ENGINE == 'piper'
    if "--tts-engine" in sys.argv:
        try:
            engine_index = sys.argv.index("--tts-engine") + 1
            if engine_index < len(sys.argv):
                selected_engine_arg = sys.argv[engine_index]
                check_piper = selected_engine_arg == 'piper'
                if selected_engine_arg not in ['piper', 'espeak']:
                     print(f"Warning: Invalid --tts-engine value '{selected_engine_arg}'. Using default.")
                     check_piper = DEFAULT_TTS_ENGINE == 'piper'
        except (ValueError, IndexError):
            print("Warning: Malformed --tts-engine argument. Using default.")
            check_piper = DEFAULT_TTS_ENGINE == 'piper'

    if check_piper:
         piper_ok = True
         print("--- Checking Piper Configuration ---")
         if not PIPER_EXECUTABLE or not os.path.exists(PIPER_EXECUTABLE):
              print(f"ERROR: Piper executable not found or path empty: '{PIPER_EXECUTABLE}'")
              piper_ok = False
         if not PIPER_VOICE_MODEL or not os.path.exists(PIPER_VOICE_MODEL):
              print(f"ERROR: Piper voice model not found or path empty: '{PIPER_VOICE_MODEL}'")
              piper_ok = False
         if not piper_ok:
              print("--- Piper TTS configuration invalid. Please update paths at the top of the script. ---")
         else:
              print("Piper executable and model paths appear valid.")
         print("------------------------------------")

    # Start the main application loop
    main()

# --- END OF FILE gemini_files_no_safety_config.py ---
