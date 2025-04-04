# --- START OF MODIFIED FILE gemini.espk_cleaned.py ---

import os
import requests
import subprocess
import re  # Import the regular expression module

def get_gemini_response(query, history=None, modifier=""):
    """Fetches a response from the Gemini API with specified constraints."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("API key not found. Set GEMINI_API_KEY.")

    # Using a potentially more stable/available model if 2.0-flash-exp gives issues
    # You might need to adjust this based on available models and your access level
    # url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent"
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"
    headers = {'Content-Type': 'application/json'}
    
    # Construct conversation history in the format expected by the API
    conversation = []
    if history:
        for q, a in history:
            conversation.append({"role": "user", "parts": [{"text": q}]})
            conversation.append({"role": "model", "parts": [{"text": a}]})
            
    # Add the current query
    # Apply the modifier as a system instruction if the model/API supports it,
    # otherwise prepend it to the first user query or the current query.
    # Basic approach: Prepend modifier to the current query context.
    current_query_text = f"{modifier}\nPrevious Conversation:\n{history}\n\nCurrent Query: {query}"
    if not history: # If no history, make it simpler
         current_query_text = f"{modifier}\nQuery: {query}"

    conversation.append({"role": "user", "parts": [{"text": current_query_text}]})


    # Note: The API structure might differ slightly based on the exact model.
    # For gemini-pro, the structure below is generally correct.
    # For newer models like 1.5, check documentation for potential differences
    # e.g., system instructions might be handled differently.
    data = {"contents": conversation}

    try:
        response = requests.post(f"{url}?key={api_key}", headers=headers, json=data)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

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
             return "Error: No content found in candidate."
             
        parts = content.get('parts')
        if not parts:
            return "Error: No parts found in content."
            
        text = parts[0].get('text', "")
        if not text:
             return "Error: Empty text in part."
             
        # Limit response length for brevity if desired (optional)
        # return " ".join(text.split()[:100])
        return text # Return full text

    except requests.exceptions.RequestException as e:
        return f"Error communicating with API: {e}"
    except Exception as e:
        # Catch potential errors during JSON parsing or key access
        return f"Error processing API response: {e}. Response text: {response.text if 'response' in locals() else 'N/A'}"


def text_to_speech(text, voice="en-gb", speed=160, pitch=20):
    """Converts text to speech using eSpeak-NG, skipping specified special characters."""
    if not text:
        print("Warning: No text provided for speech synthesis.")
        return

    # Define the pattern of characters to remove using regex
    # This removes *, _, `, #, ~
    # Add or remove characters inside the brackets [] as needed
    unwanted_chars_pattern = r'[*_`#~]'
    cleaned_text = re.sub(unwanted_chars_pattern, '', text)

    # Additionally, replace markdown bold/italic markers if they weren't caught
    # (e.g., if they surround a word without spaces, regex might miss them depending on pattern)
    # This is a simple approach; more complex markdown might need a dedicated parser
    cleaned_text = cleaned_text.replace("**", "").replace("__", "") # Bold
    cleaned_text = cleaned_text.replace("*", "").replace("_", "")   # Italics (if previous regex didn't catch them)


    if not cleaned_text.strip():
        print("Warning: Text became empty after cleaning special characters.")
        return
        
    try:
        # Use '-m' for SSML interpretation IF needed, but simple text usually works fine.
        # For just speaking cleaned text, SSML mode might not be necessary.
        # Using basic text mode:
        subprocess.run(["espeak-ng", "-v", voice, "-s", str(speed), "-p", str(pitch), cleaned_text], check=True)
        # If you specifically need SSML features later, switch back to '-m'
        # subprocess.run(["espeak-ng", "-m", "-v", voice, "-s", str(speed), "-p", str(pitch), cleaned_text], check=True)

    except FileNotFoundError:
        print("\n---")
        print("Error: 'espeak-ng' command not found.")
        print("Please ensure eSpeak NG is installed and accessible in your system's PATH.")
        print("Installation instructions vary by OS (e.g., 'sudo apt install espeak-ng' on Debian/Ubuntu, 'brew install espeak-ng' on macOS).")
        print("---")
    except subprocess.CalledProcessError as e:
        print(f"Error during eSpeak-NG execution: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during text-to-speech: {e}")


def main():
    """Computational response system loop."""
    history = []
    modifier = "You are a code-based instantiation of pure, computational logic. Provide concise, factual responses." # Slightly modified modifier for clarity

    print("SYSTEM ONLINE. INPUT QUERY (type 'exit' to terminate):")
    while True:
        try:
            query = input("\nINPUT> ").strip()
            if query.lower() == 'exit':
                print("SYSTEM OFFLINE.")
                break
            if not query:
                continue

            response = get_gemini_response(query, history, modifier)
            print(f"\nOUTPUT: {response}")

            # Store the raw response in history, but speak the cleaned version
            if not response.startswith("Error"):
                 history.append((query, response))
                 # Limit history size to prevent overly long contexts (e.g., last 5 interactions)
                 history = history[-10:] # Keep last 5 Q/A pairs (10 items total)

            # Speak the response (function now handles cleaning)
            text_to_speech(response)

        except ValueError as e:
            print(f"Configuration Error: {e}")
            break # Exit if API key is missing
        except KeyboardInterrupt:
            print("\nSYSTEM INTERRUPTED. OFFLINE.")
            break
        except Exception as e:
            print(f"An unexpected error occurred in the main loop: {e}")
            # Decide whether to continue or break on other errors
            # break

if __name__ == "__main__":
    # Check for API Key presence at the start
    if not os.getenv("GEMINI_API_KEY"):
        print("Error: API key not found. Set the environment variable GEMINI_API_KEY.")
    else:
        main()

# --- END OF MODIFIED FILE gemini.espk_cleaned.py ---
