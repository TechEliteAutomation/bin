# utils.py

import string
import config

def sanitize_filename(name: str, fallback_prefix: str = "product") -> str:
    """
    Cleans a string to be suitable for use as a filename.
    Replaces spaces, removes invalid characters, and truncates length.
    """
    if not name or name.lower() == 'unknown product':
        return fallback_prefix  # Return generic prefix if name is bad

    # Remove punctuation and invalid characters
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
    cleaned_name = ''.join(c for c in name if c in valid_chars)

    # Replace spaces with underscores
    cleaned_name = cleaned_name.replace(' ', '_')

    # Remove leading/trailing underscores/periods
    cleaned_name = cleaned_name.strip('._')

    # Truncate to avoid overly long filenames
    cleaned_name = cleaned_name[:config.MAX_FILENAME_LENGTH]

    # Ensure it's not empty after cleaning
    if not cleaned_name:
        return fallback_prefix

    return cleaned_name