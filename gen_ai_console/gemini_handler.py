# gemini_handler.py
import requests
import json
import logging

logger = logging.getLogger(__name__)

def generate_text(api_key: str, model_name: str, prompt: str, history: list = None) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    headers = {'Content-Type': 'application/json'}

    contents = []
    if history:
        contents.extend(history)
    contents.append({"role": "user", "parts": [{"text": prompt}]})

    data = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.6,
            "maxOutputTokens": 2048, # Increased for potentially longer TTS-friendly responses
        }
    }

    try:
        logger.debug(f"Sending request to Gemini API. URL: {url}")
        # logger.debug(f"Payload: {json.dumps(data)}") # Can be very verbose
        response = requests.post(url, headers=headers, json=data, timeout=90)
        response.raise_for_status()

        response_data = response.json()
        logger.debug(f"Gemini API Response received.") # Avoid logging full response if too large

        candidates = response_data.get('candidates')
        if candidates and candidates[0].get('content', {}).get('parts'):
            text_parts = candidates[0]['content']['parts']
            full_text = "".join(part.get('text', '') for part in text_parts).strip()

            if full_text:
                # Simple check for API refusal/inability to answer
                refusal_phrases = ["i cannot fulfill this request", "i'm unable to create content of that nature", "i am unable to provide assistance"]
                if any(phrase in full_text.lower() for phrase in refusal_phrases):
                    logger.warning(f"Gemini API indicated refusal: {full_text[:100]}...")
                    # Return the refusal as is, so user sees it.
                return full_text
            else:
                logger.warning("Received empty text part(s) from Gemini API.")
                return "Error: Received an empty response from the model."
        else:
            prompt_feedback = response_data.get('promptFeedback')
            if prompt_feedback and prompt_feedback.get('blockReason'):
                reason = prompt_feedback['blockReason']
                logger.warning(f"Gemini API request blocked. Reason: {reason}")
                return f"Error: Your request was blocked by the API. Reason: {reason}"
            logger.error(f"Invalid response structure from Gemini API: {response_data}")
            return "Error: Could not parse the response from the model."

    except requests.exceptions.HTTPError as http_err:
        error_text = http_err.response.text if hasattr(http_err.response, 'text') else str(http_err)
        logger.error(f"HTTP error occurred: {http_err} - {error_text[:500]}") # Log first 500 chars of error
        return f"Error: API request failed (Status {http_err.response.status_code})."
    except requests.exceptions.RequestException as req_err:
        logger.error(f"Request exception occurred: {req_err}")
        return f"Error: Could not connect to the API. ({req_err})"
    except Exception as e:
        logger.exception(f"An unexpected error occurred in generate_text: {e}")
        return f"Error: An unexpected error occurred. ({e})"
