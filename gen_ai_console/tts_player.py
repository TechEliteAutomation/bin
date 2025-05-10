# tts_player.py
import subprocess
import shlex
import os
import logging
import re
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class TTSEngine(ABC):
    def clean_text(self, text: str) -> str:
        """Basic text cleaning for TTS."""
        # Original problematic line (for reference, now commented out):
        # cleaned = re.sub(r'[*_`#~"'!${}()<>|;&]', '', text)

        # Corrected regex:
        # Explicitly escapes characters that might be part of the parsing confusion,
        # even if not strictly necessary inside a character class [] for all of them.
        # Characters to remove: *, _, `, #, ~, ", ', !, $, {, }, (, ), <, >, |, ;, &
        cleaned = re.sub(r'[*_`#~"\'!\$\{\}\(\)\<\>\|;&]', '', text)

        cleaned = re.sub(r'\s+', ' ', cleaned).strip() # Consolidate whitespace
        return cleaned

    @abstractmethod
    def speak(self, text: str):
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass

class PiperTTS(TTSEngine):
    def __init__(self, executable_path: str, model_path: str | None): # model_path can be None initially
        self.executable_path = executable_path
        self.model_path = model_path
        self.paplay_available = False
        try:
            # Check for paplay
            subprocess.run(['which', 'paplay'], capture_output=True, check=True, text=True)
            self.paplay_available = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("`paplay` command not found. Piper TTS might not produce audio even if piper-tts and model are present.")

    def is_available(self) -> bool:
        # Check executable
        if not (os.path.exists(self.executable_path) or subprocess.run(['which', self.executable_path], capture_output=True).returncode == 0):
            logger.warning(f"Piper executable not found at '{self.executable_path}' or in PATH.")
            return False
        # Check model path (now explicitly required if Piper is chosen)
        if not self.model_path or not os.path.exists(self.model_path):
            logger.warning(f"Piper voice model not found or not specified. Path: '{self.model_path}'. Piper will be unavailable.")
            return False
        if not self.paplay_available:
             logger.warning("`paplay` is not available, Piper TTS cannot play audio.")
             return False
        return True

    def speak(self, text: str):
        if not self.is_available(): # This check now includes model_path existence
            logger.error("Piper TTS is not available or configured correctly (executable, model, or paplay missing).")
            return

        cleaned_text = self.clean_text(text)
        if not cleaned_text:
            logger.info("No text to speak after cleaning for Piper.")
            return

        # Ensure self.model_path is a string before passing to shlex.quote if it could still be None here
        # (though is_available should guard this)
        if not self.model_path: # Defensive check
            logger.error("Piper model path is None during speak call, cannot proceed.")
            return

        command_str = (
            f"echo {shlex.quote(cleaned_text)} | "
            f"{shlex.quote(self.executable_path)} --model {shlex.quote(self.model_path)} --output_file - | "
            f"paplay --raw --rate=22050 --format=s16le --channels=1"
        )
        try:
            logger.debug(f"Executing Piper command: {command_str}")
            process = subprocess.run(command_str, shell=True, check=True,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True) # Capture stderr as text
            if process.stderr and ("error" in process.stderr.lower() or "fail" in process.stderr.lower()):
                 logger.warning(f"Piper stderr: {process.stderr.strip()}")
        except subprocess.CalledProcessError as e:
            stderr_output = e.stderr if e.stderr else "N/A"
            logger.error(f"Error during Piper TTS execution: {e}. Stderr: {stderr_output}")
        except Exception as e:
            logger.exception(f"An unexpected error occurred with Piper TTS: {e}")

class ESpeakTTS(TTSEngine):
    def __init__(self, voice: str, speed: int, pitch: int):
        self.voice = voice
        self.speed = str(speed)
        self.pitch = str(pitch)

    def is_available(self) -> bool:
        try:
            subprocess.run(['which', 'espeak-ng'], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("'espeak-ng' command not found. eSpeak TTS will not be available.")
            return False

    def speak(self, text: str):
        if not self.is_available():
            logger.error("eSpeak-NG is not available.")
            return

        cleaned_text = self.clean_text(text)
        if not cleaned_text:
            logger.info("No text to speak after cleaning for eSpeak.")
            return

        command = ['espeak-ng', '-v', self.voice, '-s', self.speed, '-p', self.pitch, cleaned_text]
        try:
            logger.debug(f"Executing eSpeak command: {' '.join(command)}")
            process = subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True) # Capture stderr as text
            if process.stderr and ("error" in process.stderr.lower() or "fail" in process.stderr.lower()):
                 logger.warning(f"eSpeak-ng stderr: {process.stderr.strip()}")
        except subprocess.CalledProcessError as e:
            stderr_output = e.stderr if e.stderr else "N/A"
            logger.error(f"Error during eSpeak-NG execution: {e}. Stderr: {stderr_output}")
        except Exception as e:
            logger.exception(f"An unexpected error occurred with eSpeak-NG: {e}")

def get_tts_engine(engine_name: str, config_module) -> TTSEngine | None:
    engine_name = engine_name.lower()
    if engine_name == "piper":
        # Critical: PIPER_VOICE_MODEL_PATH must be set for Piper to be usable.
        if not config_module.PIPER_VOICE_MODEL_PATH:
            logger.error("Piper TTS selected, but PIPER_VOICE_MODEL_PATH is not configured. Piper is unavailable.")
            return None
        return PiperTTS(executable_path=config_module.PIPER_EXECUTABLE_PATH,
                        model_path=config_module.PIPER_VOICE_MODEL_PATH)
    elif engine_name == "espeak":
        return ESpeakTTS(voice=config_module.ESPEAK_VOICE,
                         speed=config_module.ESPEAK_SPEED,
                         pitch=config_module.ESPEAK_PITCH)
    elif engine_name == "none":
        return None
    else:
        logger.warning(f"Unknown TTS engine: {engine_name}. TTS disabled.")
        return None
