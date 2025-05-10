# app.py
import logging
import argparse

# Initialize config and logging first
import config # This also checks for API_KEY
logging.basicConfig(level=config.LOG_LEVEL, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

import gemini_handler
import tts_player # Import the new TTS module

def main():
    parser = argparse.ArgumentParser(description="Simple Gemini Chat with TTS")
    parser.add_argument(
        "--tts",
        default=config.DEFAULT_TTS_ENGINE,
        choices=['piper', 'espeak', 'none'],
        help=f"TTS engine to use (default: {config.DEFAULT_TTS_ENGINE}). 'none' disables TTS."
    )
    args = parser.parse_args()

    logger.info(f"Application starting with model: {config.MODEL_NAME}, TTS Engine: {args.tts}")
    print(f"Welcome to Simple Gemini Chat! Model: {config.MODEL_NAME}")
    if args.tts != 'none':
        print(f"TTS Engine: {args.tts.capitalize()}")
    print("Type 'exit' to quit.")

    conversation_history = []
    active_tts_engine = None

    if args.tts != 'none':
        active_tts_engine = tts_player.get_tts_engine(args.tts, config)
        if active_tts_engine and not active_tts_engine.is_available():
            logger.warning(f"{args.tts.capitalize()} TTS engine is not available/configured. TTS disabled.")
            print(f"Warning: {args.tts.capitalize()} TTS not available. Continuing without speech.")
            active_tts_engine = None
        elif not active_tts_engine:
             print(f"Warning: Could not initialize TTS engine '{args.tts}'. Continuing without speech.")


    while True:
        try:
            user_input = input("\nYou: ").strip()

            if user_input.lower() == 'exit':
                logger.info("User requested exit.")
                print("Goodbye!")
                break

            if not user_input:
                continue

            logger.info(f"User input: {user_input[:50]}...") # Log first 50 chars
            print("Gemini: Thinking...")
            response_text = gemini_handler.generate_text(
                api_key=config.API_KEY,
                model_name=config.MODEL_NAME,
                prompt=user_input,
                history=conversation_history
            )

            print(f"Gemini: {response_text}")
            logger.info(f"Gemini response: {response_text[:100]}...") # Log first 100 chars

            if not response_text.startswith("Error:"):
                conversation_history.append({"role": "user", "parts": [{"text": user_input}]})
                conversation_history.append({"role": "model", "parts": [{"text": response_text}]})
                if len(conversation_history) > 10: # Limit history to last 5 turns
                    conversation_history = conversation_history[-10:]

                if active_tts_engine:
                    try:
                        logger.debug(f"Attempting to speak response with {args.tts}")
                        active_tts_engine.speak(response_text)
                    except Exception as tts_err: # Broad catch for TTS speak errors
                        logger.error(f"TTS speak error with {args.tts}: {tts_err}", exc_info=True)
                        print(f"Warning: TTS failed for this response. Check logs.")
                        # Optionally disable TTS for the rest of the session if it keeps failing
                        # active_tts_engine = None
            else:
                logger.warning(f"Gemini handler returned an error: {response_text}")


        except KeyboardInterrupt:
            logger.info("Application interrupted by user (Ctrl+C).")
            print("\nExiting due to user interruption.")
            break
        except Exception as e:
            logger.exception(f"An unexpected error occurred in the main loop: {e}")
            print(f"\nAn critical unexpected error occurred: {e}. Exiting.")
            break # Exit on unhandled critical errors in the main loop

if __name__ == "__main__":
    main()
