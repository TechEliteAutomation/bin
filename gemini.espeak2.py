# --- START OF MODIFIED FILE gemini.espk_piper.py ---

import os
import requests
import subprocess
import re
import json
import argparse # Import argparse for command-line arguments
import shlex   # Import shlex to safely quote text for shell commands
import sys

# --- Configuration (Could be moved to a config file later) ---
DEFAULT_TTS_ENGINE = "espeak" # or "piper"
PIPER_EXECUTABLE = "/usr/bin/piper-tts"
PIPER_VOICE_MODEL = "/home/u/s/tts/en_GB-alan-medium.onnx"

# --- API Request/Response Functions (Assume _format_gemini_payload, _call_gemini_api, _parse_gemini_response are defined as in previous versions) ---
# (Include the definitions of _format_gemini_payload, _call_gemini_api, _parse_gemini_response here)
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

    history_context = "\n".join([f"User: {q}\nModel: {a}" for q, a in history]) if history else "None"
    current_query_text = f"{modifier}\n---\nPrevious Context:\n{history_context}\n---\nCurrent Query:\n{query}"
    if not history:
         current_query_text = f"{modifier}\nQuery: {query}" if modifier else query

    conversation.append({"role": "user", "parts": [{"text": current_query_text}]})
    data = {"contents": conversation}
    return data

def _call_gemini_api(url, api_key, headers, data):
    """Makes the POST request to the Gemini API and handles request errors."""
    try:
        response = requests.post(f"{url}?key={api_key}", headers=headers, json=data, timeout=60) # 60 second timeout
        response.raise_for_status()
        return response
    except requests.exceptions.Timeout:
        return "Error: API request timed out."
    except requests.exceptions.RequestException as e:
        return f"Error communicating with API: {e}"

def _parse_gemini_response(response):
    """Parses the JSON response from Gemini API and extracts text."""
    if isinstance(response, str):
        return response
    try:
        response_data = response.json()
        candidates = response_data.get('candidates')
        if not candidates:
            prompt_feedback = response_data.get('promptFeedback')
            if prompt_feedback:
                block_reason = prompt_feedback.get('blockReason')
                safety_ratings = prompt_feedback.get('safetyRatings')
                return f"Error: Response blocked. Reason: {block_reason}. Ratings: {safety_ratings}"
            api_error = response_data.get('error')
            if api_error:
                return f"Error from API: {api_error.get('message', 'Unknown API error')}"
            return f"Error: No candidates found in response. Response JSON: {response_data}"

        if not candidates[0]:
             return "Error: Received empty candidate."

        content = candidates[0].get('content')
        if not content:
            finish_reason = candidates[0].get('finishReason')
            safety_ratings = candidates[0].get('safetyRatings')
            if finish_reason and finish_reason != "STOP":
                 return f"Error: Candidate finished unexpectedly. Reason: {finish_reason}. Safety Ratings: {safety_ratings}"
            return "Error: No content found in candidate."

        parts = content.get('parts')
        if not parts:
            text_direct = content.get('text')
            if text_direct: return text_direct
            return "Error: No parts found in content."

        text = parts[0].get('text', "") if parts else ""
        if not text and len(parts) == 0: return "Warning: Received content with zero parts."
        elif not text and len(parts) > 0: return "Warning: Empty text received in the first part."
        return text

    except json.JSONDecodeError as e:
        response_text = response.text if hasattr(response, 'text') else "N/A"
        return f"Error decoding API response JSON: {e}. Response text: {response_text[:500]}..."
    except Exception as e:
        response_data_str = str(response_data)[:500] if 'response_data' in locals() else 'N/A'
        return f"Error processing API response structure: {e}. Response JSON: {response_data_str}"


def get_gemini_response(query, history=None, modifier=""):
    """Fetches a response from the Gemini API with specified constraints."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("API key not found. Set GEMINI_API_KEY.")

    #url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro-exp-03-25:generateContent"
    headers = {'Content-Type': 'application/json'}
    payload_data = _format_gemini_payload(query, history, modifier)
    api_response = _call_gemini_api(url, api_key, headers, payload_data)
    result_text = _parse_gemini_response(api_response)
    return result_text

# --- Modified text_to_speech ---

def text_to_speech(text, engine='espeak', voice="en-gb", speed=160, pitch=20):
    """Converts text to speech using the specified engine."""
    if not text:
        print("Warning: No text provided for speech synthesis.")
        return

    # --- Text Cleaning (Common for both engines) ---
    unwanted_chars_pattern = r'[*_`#~]'
    cleaned_text = re.sub(unwanted_chars_pattern, '', text)
    cleaned_text = cleaned_text.replace("**", "").replace("__", "")
    cleaned_text = cleaned_text.replace("*", "").replace("_", "")
    # Replace quotes that might cause issues with shell commands
    cleaned_text = cleaned_text.replace('"', "'")

    if not cleaned_text.strip():
        print("Warning: Text became empty after cleaning special characters.")
        return

    # --- Engine Selection ---
    try:
        if engine == "espeak":
            # Use basic text mode for espeak-ng
            subprocess.run(["espeak-ng", "-v", voice, "-s", str(speed), "-p", str(pitch), cleaned_text], check=True)

        elif engine == "piper":
            # Check if Piper executable and model exist
            if not os.path.exists(PIPER_EXECUTABLE):
                 print(f"Error: Piper executable not found at {PIPER_EXECUTABLE}")
                 print("Falling back to espeak.")
                 text_to_speech(text, engine='espeak', voice=voice, speed=speed, pitch=pitch) # Fallback
                 return
            if not os.path.exists(PIPER_VOICE_MODEL):
                 print(f"Error: Piper model not found at {PIPER_VOICE_MODEL}")
                 print("Falling back to espeak.")
                 text_to_speech(text, engine='espeak', voice=voice, speed=speed, pitch=pitch) # Fallback
                 return

            # Construct the Piper command pipeline: echo text | piper ... | aplay
            # Use shlex.quote to handle potential problematic characters in the text
            piper_command = f"echo {shlex.quote(cleaned_text)} | {shlex.quote(PIPER_EXECUTABLE)} --model {shlex.quote(PIPER_VOICE_MODEL)} --output_file - | paplay --raw --rate=22050 --format=s16le --channels=1"
            # print(f"DEBUG: Running Piper command: {piper_command}") # Uncomment for debugging
            
            # OLD CODE = subprocess.run(piper_command, shell=True, check=True) # shell=True is needed for the pipe
            # Run the command and redirect stdout/stderr to /dev/null
            # This prevents echo, piper, and paplay from printing status messages to the terminal
            subprocess.run(
                piper_command,
                shell=True,        # shell=True is needed for the pipe (|)
                check=True,        # Raise an error if the command fails
                stdout=subprocess.DEVNULL, # Discard standard output of the pipeline (audio goes via pipe)
                stderr=subprocess.DEVNULL  # Discard standard error (where piper logs messages)
            )

        else:
            print(f"Error: Unknown TTS engine '{engine}'. Using espeak.")
            text_to_speech(text, engine='espeak', voice=voice, speed=speed, pitch=pitch) # Fallback

    except FileNotFoundError as e:
        print("\n---")
        if engine == "espeak" and 'espeak-ng' in str(e):
            print("Error: 'espeak-ng' command not found.")
        elif engine == "piper" and ('aplay' in str(e) or 'piper' in str(e)):
             print(f"Error: Required command for Piper TTS not found ('piper' executable or 'aplay').")
             print(f"Attempted command: {piper_command if 'piper_command' in locals() else 'N/A'}")
        else:
             print(f"Error: Command not found - {e}. Check installation and PATH.")
        print("Please ensure the required TTS engine and audio player are installed and accessible.")
        print("---")
    except subprocess.CalledProcessError as e:
        print(f"Error during {engine} TTS execution: {e}")
        # Provide more detail if possible
        if hasattr(e, 'stderr') and e.stderr:
             print(f"Stderr: {e.stderr.decode(errors='ignore')}")
        if hasattr(e, 'stdout') and e.stdout:
             print(f"Stdout: {e.stdout.decode(errors='ignore')}")
    except Exception as e:
        print(f"An unexpected error occurred during text-to-speech ({engine}): {e}")


# --- Main Function ---

def main():
    """Computational response system loop with engine selection."""

    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(description="Gemini Chat with Text-to-Speech.")
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
    modifier = "You are a code-based instantiation of pure, computational logic. Provide concise, factual responses."

    print(f"SYSTEM ONLINE. Using TTS Engine: {selected_tts_engine}")
    print("Commands: /clear, /save <filename.json>, /load <filename.json>, exit")

    while True:
        try:
            query = input("\nINPUT> ").strip() # Reverted to single-line input

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
            elif query.lower().startswith('/save '):
                parts = query.split(maxsplit=1)
                if len(parts) == 2:
                    filename = parts[1]
                    try:
                        with open(filename, 'w', encoding='utf-8') as f:
                            json.dump(history, f, indent=2)
                        print(f"History saved to {filename}")
                    except Exception as e:
                        print(f"Error saving history: {e}")
                else:
                    print("Usage: /save <filename.json>")
                continue
            elif query.lower().startswith('/load '):
                parts = query.split(maxsplit=1)
                if len(parts) == 2:
                    filename = parts[1]
                    try:
                        with open(filename, 'r', encoding='utf-8') as f:
                            loaded_history = json.load(f)
                        if isinstance(loaded_history, list) and all(isinstance(item, list) and len(item) == 2 for item in loaded_history):
                             history = loaded_history
                             print(f"History loaded from {filename}. {len(history)} interactions restored.")
                        else:
                             print(f"Error: Invalid history format in {filename}.")
                    except FileNotFoundError:
                        print(f"Error: File not found - {filename}")
                    except Exception as e:
                         print(f"Error loading history: {e}")
                else:
                    print("Usage: /load <filename.json>")
                continue

            # --- Thinking Indicator ---
            print("Generating response...")

            # --- API Call ---
            response = get_gemini_response(query, history, modifier)
            print(f"\nOUTPUT: {response}")

            # Store interaction in history
            if not response.startswith("Error:"):
                 history.append([query, response])
                 history = history[-10:] # Keep last 5 Q/A pairs

            # --- Speak Response ---
            if not response.startswith("Error:") and not response.startswith("Warning:"):
                 # Pass the selected engine to the function
                 text_to_speech(response, engine=selected_tts_engine)
            elif response.startswith("Warning:"):
                 print("(TTS skipped for warning message)")
            else:
                 print("(TTS skipped due to error)")


        except ValueError as e: # Catches API key error from get_gemini_response
            print(f"Configuration Error: {e}")
            break
        except KeyboardInterrupt:
            print("\nSYSTEM INTERRUPTED. OFFLINE.")
            break
        except Exception as e:
            print(f"An unexpected error occurred in the main loop: {e}")
            # Consider adding traceback for debugging unexpected errors
            # import traceback
            # traceback.print_exc()


if __name__ == "__main__":
    if not os.getenv("GEMINI_API_KEY"):
        print("Error: API key not found. Set the environment variable GEMINI_API_KEY.")
    else:
        # Check essential Piper config if Piper is the default or potentially selected
        # You might want more robust config checks here
        if DEFAULT_TTS_ENGINE == 'piper' or '--tts-engine=piper' in sys.argv: # Simple check
             if not os.path.exists(PIPER_EXECUTABLE) or not os.path.exists(PIPER_VOICE_MODEL):
                  print("--- PIPER CONFIGURATION WARNING ---")
                  print(f"Piper executable set to: {PIPER_EXECUTABLE}")
                  print(f"Piper voice model set to: {PIPER_VOICE_MODEL}")
                  print("One or both paths are invalid. Please update the script.")
                  print("Piper TTS will fallback to espeak if selected/defaulted.")
                  print("---")
        main()

# --- END OF MODIFIED FILE gemini.espk_piper.py ---
