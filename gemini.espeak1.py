# --- START OF MODIFIED FILE gemini.espk_cleaned_enhanced.py ---

import os
import requests
import subprocess
import re  # Import the regular expression module
import json # Import the json module for save/load history

# --- Refactoring: Helper Functions for get_gemini_response ---

def _format_gemini_payload(query, history, modifier):
    """Formats the request payload for the Gemini API."""
    conversation = []
    if history:
        for q, a in history:
            # Basic validation in case history loading had issues
            if isinstance(q, str) and isinstance(a, str):
                 conversation.append({"role": "user", "parts": [{"text": q}]})
                 conversation.append({"role": "model", "parts": [{"text": a}]})
            else:
                 print(f"Warning: Skipping invalid history entry: ({type(q)}, {type(a)})")


    # Prepend modifier and context hint to the current query
    history_context = "\n".join([f"User: {q}\nModel: {a}" for q, a in history]) if history else "None"
    current_query_text = f"{modifier}\n\n--- Previous Conversation ---\n{history_context}\n\n--- Current Query ---\n{query}"
    # Simpler version if no history or modifier
    if not history and modifier:
        current_query_text = f"{modifier}\nQuery: {query}"
    elif not history and not modifier:
         current_query_text = query # Just the query if no history and no modifier


    conversation.append({"role": "user", "parts": [{"text": current_query_text}]})

    # Note: The API structure might differ slightly based on the exact model.
    # Check documentation for potential differences e.g., system instructions.
    data = {"contents": conversation}
    return data

def _call_gemini_api(url, api_key, headers, data):
    """Makes the POST request to the Gemini API and handles request errors."""
    try:
        response = requests.post(f"{url}?key={api_key}", headers=headers, json=data)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        return response
    except requests.exceptions.RequestException as e:
        return f"Error communicating with API: {e}" # Return error string on request failure

def _parse_gemini_response(response):
    """Parses the JSON response from Gemini API and extracts text."""
    if isinstance(response, str): # If _call_gemini_api returned an error string
        return response

    try:
        response_data = response.json()

        # Defensive checking of the response structure
        candidates = response_data.get('candidates')
        if not candidates:
            # Handle potential safety blocks or empty responses
            prompt_feedback = response_data.get('promptFeedback')
            if prompt_feedback:
                block_reason = prompt_feedback.get('blockReason')
                safety_ratings = prompt_feedback.get('safetyRatings')
                return f"Error: Response blocked. Reason: {block_reason}. Ratings: {safety_ratings}"
            return "Error: No candidates found in response."

        content = candidates[0].get('content')
        if not content:
            # Check if finishReason provides info (e.g., safety)
            finish_reason = candidates[0].get('finishReason')
            if finish_reason and finish_reason != "STOP":
                 return f"Error: Candidate finished unexpectedly. Reason: {finish_reason}. Check safety ratings if available."
            return "Error: No content found in candidate."

        parts = content.get('parts')
        if not parts:
            return "Error: No parts found in content."

        text = parts[0].get('text', "")
        if not text:
            # It's possible to get an empty text part legitimately, but flag it if empty.
            return "Warning: Empty text received in response part." # Changed from Error to Warning

        # Limit response length for brevity if desired (optional)
        # return " ".join(text.split()[:100])
        return text # Return full text

    except json.JSONDecodeError as e:
        return f"Error decoding API response JSON: {e}. Response text: {response.text}"
    except Exception as e:
        # Catch potential errors during key access
        return f"Error processing API response structure: {e}. Response JSON: {response_data if 'response_data' in locals() else 'N/A'}"


# --- Main Function using Refactored Helpers ---

def get_gemini_response(query, history=None, modifier=""):
    """Fetches a response from the Gemini API with specified constraints."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("API key not found. Set GEMINI_API_KEY.")

    # Model Selection (keep configurable if needed later)
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"
    headers = {'Content-Type': 'application/json'}

    # 1. Format Payload
    payload_data = _format_gemini_payload(query, history, modifier)

    # 2. Call API
    api_response = _call_gemini_api(url, api_key, headers, payload_data)

    # 3. Parse Response
    result_text = _parse_gemini_response(api_response)

    return result_text


def text_to_speech(text, voice="en-gb", speed=160, pitch=15):
    """Converts text to speech using eSpeak-NG, skipping specified special characters."""
    if not text:
        print("Warning: No text provided for speech synthesis.")
        return

    # Define the pattern of characters to remove using regex
    unwanted_chars_pattern = r'[*_`#~]'
    cleaned_text = re.sub(unwanted_chars_pattern, '', text)

    # Additionally, replace markdown bold/italic markers
    cleaned_text = cleaned_text.replace("**", "").replace("__", "") # Bold
    cleaned_text = cleaned_text.replace("*", "").replace("_", "")   # Italics

    if not cleaned_text.strip():
        print("Warning: Text became empty after cleaning special characters.")
        return

    try:
        subprocess.run(["espeak-ng", "-v", voice, "-s", str(speed), "-p", str(pitch), cleaned_text], check=True)
    except FileNotFoundError:
        print("\n---")
        print("Error: 'espeak-ng' command not found.")
        print("Please ensure eSpeak NG is installed and accessible in your system's PATH.")
        print("---")
    except subprocess.CalledProcessError as e:
        print(f"Error during eSpeak-NG execution: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during text-to-speech: {e}")

# --- Multiline Input Function ---
def get_multiline_input():
    """Gets multiline input from the user, ending with '/end'."""
    lines = []
    print("Enter query (type '/end' on a new line to finish):")
    while True:
        try:
            line = input()
            if line.strip().lower() == '/end':
                break
            lines.append(line)
        except EOFError: # Handle Ctrl+D
             break
    return "\n".join(lines).strip()

def main():
    """Computational response system loop with history management and commands."""
    history = []
    modifier = "You are a code-based instantiation of pure, computational logic. Provide concise, factual responses."

    print("SYSTEM ONLINE.")
    print("Commands: /clear, /save <filename.json>, /load <filename.json>, /end (for multiline), exit")

    while True:
        try:
            # Use multiline input function
            query = get_multiline_input() # Replaces simple input("\nINPUT> ").strip()

            if not query and not history: # Skip if initial input is empty
                 continue
            elif not query and history: # If empty after history exists, maybe just prompt again
                 print("Empty input received. Enter a query, command, or 'exit'.")
                 continue


            # --- Command Handling ---
            if query.lower() == 'exit':
                print("SYSTEM OFFLINE.")
                break
            elif query.lower() == '/clear':
                history = []
                print("History cleared.")
                continue # Skip API call
            elif query.lower().startswith('/save '):
                parts = query.split(maxsplit=1)
                if len(parts) == 2:
                    filename = parts[1]
                    try:
                        with open(filename, 'w', encoding='utf-8') as f:
                            json.dump(history, f, indent=2) # Use indent for readability
                        print(f"History saved to {filename}")
                    except IOError as e:
                        print(f"Error saving history: {e}")
                    except Exception as e:
                        print(f"An unexpected error occurred during save: {e}")
                else:
                    print("Usage: /save <filename.json>")
                continue # Skip API call
            elif query.lower().startswith('/load '):
                parts = query.split(maxsplit=1)
                if len(parts) == 2:
                    filename = parts[1]
                    try:
                        with open(filename, 'r', encoding='utf-8') as f:
                            loaded_history = json.load(f)
                        # Basic validation of loaded data structure
                        if isinstance(loaded_history, list) and all(isinstance(item, list) and len(item) == 2 for item in loaded_history):
                             history = loaded_history
                             print(f"History loaded from {filename}. {len(history)} interactions restored.")
                        else:
                             print(f"Error: Invalid history format in {filename}. Must be a list of [query, response] pairs.")
                    except FileNotFoundError:
                        print(f"Error: File not found - {filename}")
                    except json.JSONDecodeError as e:
                        print(f"Error decoding JSON from {filename}: {e}")
                    except IOError as e:
                        print(f"Error loading history: {e}")
                    except Exception as e:
                         print(f"An unexpected error occurred during load: {e}")
                else:
                    print("Usage: /load <filename.json>")
                continue # Skip API call

            # --- Thinking Indicator ---
            print("Generating response...") # Moved after command checks

            # --- API Call ---
            response = get_gemini_response(query, history, modifier)
            print(f"\nOUTPUT: {response}")

            # Store interaction in history if no error from API
            # Note: Even 'Warning: Empty text...' response is stored for context.
            if not response.startswith("Error:"):
                 history.append([query, response]) # Store as list for JSON compatibility
                 # Limit history size (e.g., last 5 interactions)
                 history = history[-10:] # Keep last 5 Q/A pairs (10 items total)

            # Speak the response (function handles cleaning)
            # Avoid speaking error messages
            if not response.startswith("Error:") and not response.startswith("Warning:"):
                 text_to_speech(response)
            elif response.startswith("Warning:"): # Optionally speak warnings
                 print("(TTS skipped for warning message)")
                 # text_to_speech(response) # Uncomment to speak warnings
            else: # Error occurred
                 print("(TTS skipped due to error)")


        except ValueError as e:
            print(f"Configuration Error: {e}")
            break # Exit if API key is missing
        except KeyboardInterrupt:
            print("\nSYSTEM INTERRUPTED. OFFLINE.")
            break
        except Exception as e:
            print(f"An unexpected error occurred in the main loop: {e}")
            # Optional: Add a small delay or decide to break/continue
            # import time
            # time.sleep(1)
            # break # Uncomment to stop on unexpected errors

if __name__ == "__main__":
    # Check for API Key presence at the start
    if not os.getenv("GEMINI_API_KEY"):
        print("Error: API key not found. Set the environment variable GEMINI_API_KEY.")
    else:
        main()

# --- END OF MODIFIED FILE gemini.espk_cleaned_enhanced.py ---
