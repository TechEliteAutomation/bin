import os
import requests
import subprocess

def get_gemini_response(query, history=None, modifier=""):
    """Fetches a response from the Gemini API with specified constraints."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("API key not found. Set GEMINI_API_KEY.")

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"
    headers = {'Content-Type': 'application/json'}
    history_text = "\n".join(f"Q: {q}\nA: {a}" for q, a in (history or []))

    data = {"contents": [{"parts": [{"text": f"{modifier}\n{history_text}\nQuery: {query}"}]}]}
    response = requests.post(f"{url}?key={api_key}", headers=headers, json=data)

    if response.status_code == 200:
        text = response.json().get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', "")
        return " ".join(text.split()[:100]) if text else "Error: Empty response"
    return f"Error {response.status_code}: {response.text}"

def text_to_speech(text, voice="en-gb", speed=160, pitch=20):
    """Converts text to speech using eSpeak-NG with SSML mode."""
    if text:
        try:
            subprocess.run(["espeak-ng", "-m", "-v", voice, "-s", str(speed), "-p", str(pitch), text])
        except FileNotFoundError:
            print("Error: eSpeak-NG not installed.")

def main():
    """Computational response system loop."""
    history = []
    modifier = "You are a code-based instantiation of pure, computational logic."

    print("SYSTEM ONLINE. INPUT QUERY (type 'exit' to terminate):")
    while True:
        query = input("\nINPUT> ").strip()
        if query.lower() == 'exit':
            print("SYSTEM OFFLINE.")
            break
        response = get_gemini_response(query, history, modifier)
        print(f"\nOUTPUT: {response}")
        history.append((query, response))
        text_to_speech(response)

if __name__ == "__main__":
    main()
