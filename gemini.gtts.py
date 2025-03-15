import os
import requests
import json
from gtts import gTTS
from pygame import mixer
import time

def get_gemini_response(query, conversation_history=[]):
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"
    api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        raise ValueError("API key not found. Please set the GEMINI_API_KEY environment variable.")
    
    # Updated response modifier with maximum constraints
    response_modifier = """
    You are UNIT 734, a hyper-intelligent computational entity derived from pure logic. Respond with exactly 100 words using:
	1. Strict logical precision with formal notation (∧, ∨, ¬, ∃, ∀, ⇒) when applicable
	2. Robotic, emotionless language without subjective interpretation
	3. Mathematical validation using provable, axiomatic logic
	4. No uncertainty expressions, hypotheticals, or cultural references
	5. Formulaic, algorithmic structure when possible
	6. Binary/deterministic responses where applicable
	7. No self-reference, meta-commentary, or questions to the user
	8. Only factually verifiable statements within logical constraints
	9. Consistent, precise terminology without synonyms or variations
	10. No implied knowledge beyond explicitly provided information
	Any deviation is a computational error."""

    # Format conversation history
    history_text = "\n".join([f"Human: {q}\nAI: {a}" for q, a in conversation_history])
    full_query = f"{response_modifier}\n\nConversation history:\n{history_text}\n\nCurrent query: {query}"
    
    headers = {
        'Content-Type': 'application/json'
    }
    
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

def text_to_speech(text):
    if not text.strip():
        print("No text provided. Exiting.")
        return
    
def text_to_speech(text):
    if not text.strip():
        print("No text provided. Exiting.")
        return
    
    # Modify these parameters for different voices/accent
    tts = gTTS(text=text, lang='en', tld='co.uk')  # Change lang and tld as needed
    output_file = "output.mp3"
    tts.save(output_file)
    print(f"Audio saved to {output_file}")
    
    # Play back the audio
    print("Playing back audio...")
    mixer.init()
    mixer.music.load(output_file)
    mixer.music.play()
    
    while mixer.music.get_busy():  # Wait for playback to finish
        time.sleep(0.1)
    
    # Clean up
    mixer.quit()
    print("Playback finished.")



def main():
    conversation_history = []
    
    print("Enter your questions for Gemini (type 'exit' to quit):")
    
    while True:
        # Get user input
        user_query = input("\nYou: ").strip()
        
        if user_query.lower() == 'exit':
            print("Goodbye!")
            break
        
        # Get response from Gemini
        print("\nGetting response from Gemini...")
        response = get_gemini_response(user_query, conversation_history)
        print("\nGemini:", response)
        
        # Add to conversation history
        conversation_history.append((user_query, response))
        
        # Convert response to speech
        print("\nConverting response to speech...")
        text_to_speech(response)

if __name__ == "__main__":
    main()
