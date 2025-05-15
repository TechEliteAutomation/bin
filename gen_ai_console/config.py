# config.py
import os
from dotenv import load_dotenv
import logging

load_dotenv()

# --- API Configuration ---
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-pro-preview-05-06")

# --- TTS Configuration ---
# 'piper', 'espeak', or 'none'
DEFAULT_TTS_ENGINE = os.getenv("DEFAULT_TTS_ENGINE", "espeak")

# Piper TTS specific paths (User MUST update PIPER_VOICE_MODEL_PATH if using Piper)
PIPER_EXECUTABLE_PATH = os.getenv("PIPER_EXECUTABLE_PATH", "piper-tts") # Assumes piper-tts is in PATH
PIPER_VOICE_MODEL_PATH = os.getenv("PIPER_VOICE_MODEL_PATH", "/home/u/s/tts/en_GB-alan-medium.onnx") # << EXAMPLE PATH

# eSpeak-NG specific
ESPEAK_VOICE = os.getenv("ESPEAK_VOICE", "en-gb")
ESPEAK_SPEED = int(os.getenv("ESPEAK_SPEED", "180"))
ESPEAK_PITCH = int(os.getenv("ESPEAK_PITCH", "60"))

# --- Logging ---
LOG_LEVEL_STR = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)


if not API_KEY:
    print("ERROR: GEMINI_API_KEY not found in .env file or environment variables.")
    print("Please create a .env file with GEMINI_API_KEY='your_key' in the project root.")
    exit(1)
