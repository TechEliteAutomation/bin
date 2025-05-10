# config.py

# --- Constants ---
DEFAULT_MODEL = 'gemini-2.5-pro-exp-03-25' # Default model
DEFAULT_MULTI_INPUT_FILE = 'extended_product_input.txt'  # Default input with multiple products
DEFAULT_OUTPUT_DIR = 'generated_descriptions'  # Default output directory
PRODUCT_SEPARATOR = '--- PRODUCT SEPARATOR ---'
ENV_VAR_API_KEY = 'GEMINI_API_KEY'

OPTIMAL_DESC_LENGTH = 1500
MAX_DESC_LENGTH = 2000
MIN_DESC_LENGTH = 200
GENERATION_MAX_TOKENS = 500
GENERATION_TEMPERATURE = 0.7
MAX_FILENAME_LENGTH = 100  # Max length for generated filenames
