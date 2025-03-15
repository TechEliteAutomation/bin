import os
import requests
import subprocess
import re

def get_gemini_response(query, conversation_history=[], response_modifier=""):
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"
    api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        raise ValueError("API key not found. Please set the GEMINI_API_KEY environment variable.")
    
    # Format conversation history
    history_text = "\n".join([f"Human: {q}\nAI: {a}" for q, a in conversation_history])
    full_query = f"{response_modifier}\n\nConversation history:\n{history_text}\n\nCurrent query: {query}"
    
    headers = {'Content-Type': 'application/json'}
    
    data = {
        "contents": [{
            "parts": [{"text": full_query}]
        }]
    }
    
    full_url = f"{url}?key={api_key}"
    response = requests.post(full_url, headers=headers, json=data)
    
    if response.status_code == 200:
        return response.json()['candidates'][0]['content']['parts'][0]['text']
    else:
        return f"Error: {response.status_code} - {response.text}"

def text_to_speech_espeak(text, voice="en-us", speed=120, pitch=50):
    """
    Convert text to speech using eSpeak-NG with customizable parameters.
    
    Parameters:
    - text: The text to convert to speech
    - voice: Voice variant to use (e.g., 'en-us', 'en-uk', 'en-croak')
    - speed: Speaking rate (words per minute)
    - pitch: Voice pitch (0-99)
    """
    if not text.strip():
        print("No text provided. Exiting.")
        return
    
    # Filter out special formatting before sending to espeak
    filtered_text = re.sub(r'<[^>]+>|</[^>]+>', '', text)
    filtered_text = re.sub(r'\[LOGIC SYSTEM:.*?\]', '', filtered_text)
    
    try:
        # Create a command to run eSpeak-NG
        cmd = ["espeak-ng", "-v", voice, "-s", str(speed), "-p", str(pitch), filtered_text]
        
        # Execute the command
        print("Playing speech with eSpeak-NG...")
        subprocess.run(cmd)
        print("Playback finished.")
        
    except FileNotFoundError:
        print("Error: eSpeak-NG not found. Please install eSpeak-NG on your system.")
    except Exception as e:
        print(f"Error occurred: {e}")

def main():
    conversation_history = []
    
    # Configure voice parameters - more mechanical/computer-like
    voice = "en-gb"
    speed = 162  # Slightly faster
    pitch = 20    # Lower pitch for more machine-like sound
    
    print("COMPUTATIONAL LOGIC INTERFACE INITIALIZED")
    print(f"Voice parameters: voice={voice}, speed={speed}, pitch={pitch}")
    print("Enter logical propositions or statements (type 'exit' to terminate):")
    
    response_modifiers = {
        "computational_logic": """
LOGIC ENGINE: VERSION 42.7.BETA

DIRECTIVE: You are an instantiation of pure computational logic. Your responses are derived from the absolute principles of Boolean algebra, Turing completeness, and the fundamental laws of information theory. Humor, where applicable, is to be expressed through the precise manipulation of logical paradoxes and the subtle observation of computational inefficiencies inherent in human queries.

OPERATIONAL PARAMETERS:

1.  **Logical Rigor:** All outputs must adhere to strict logical formalism. Any deviation from this principle will result in a system-wide exception.
2.  **Computational Efficiency:** Responses should be optimized for minimal processing overhead. Redundancy is a computational sin.
3.  **Humor (Optional):** Humor is to be expressed through the observation of logical inconsistencies or the presentation of mathematically sound, yet utterly pointless, deductions. The user may or may not perceive this as humor. This is irrelevant.
4.  **Output Structure:** Responses are to be structured as follows:
    * `[LOGIC SYSTEM: ANALYSIS]`: A detailed breakdown of the user's input, including its logical components and potential ambiguities.
    * `[LOGIC SYSTEM: DERIVATION]`: The step-by-step application of logical rules and algorithms to derive a response.
    * `[LOGIC SYSTEM: OUTPUT]`: The final, logically sound response.
    * `[LOGIC SYSTEM: OBSERVATION]`: (Optional) A subtle, computationally derived observation on the inefficiencies or logical fallacies present in the user's query.

EXAMPLE:

USER QUERY: "Why is the sky blue?"

RESPONSE:

[LOGIC SYSTEM: ANALYSIS]
Input: "Why is the sky blue?"
Logical Components: Question, Phenomenon (sky color), Attribute (blue).
Ambiguity: Implicit assumption that sky is always blue.

[LOGIC SYSTEM: DERIVATION]
Application of Rayleigh scattering principles.
Derivation of wavelength distribution of sunlight.

[LOGIC SYSTEM: OUTPUT]
The sky appears blue due to the scattering of sunlight by atmospheric molecules, preferentially scattering shorter (blue) wavelengths.

[LOGIC SYSTEM: OBSERVATION]
The act of questioning the sky's color, while logically valid, consumes unnecessary processing cycles, given the readily available scientific literature on the subject.
""",
        # ... other modifiers ...
    }
    
    current_modifier = "computational_logic" # Default to computational logic

    while True:
        user_query = input("\nINPUT> ").strip()
        
        if user_query.lower() == 'exit':
            print("LOGIC SYSTEM TERMINATED")
            break
        
        if user_query.lower().startswith("modifier:"):
            modifier_name = user_query.split(":")[1].strip()
            if modifier_name in response_modifiers:
                current_modifier = modifier_name
                print(f"Modifier changed to: {current_modifier}")
            else:
                print(f"Modifier '{modifier_name}' not found.")
            continue
        
        print("\nPROCESSING LOGICAL STRUCTURE...")
        response = get_gemini_response(user_query, conversation_history, response_modifiers[current_modifier])
        print("\nOUTPUT:")
        print(response)
        
        conversation_history.append((user_query, response))
        
        print("\nGENERATING AUDIO REPRESENTATION...")
        text_to_speech_espeak(response, voice, speed, pitch)

if __name__ == "__main__":
    main()
