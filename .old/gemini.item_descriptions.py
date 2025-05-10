import os
import re
import argparse
import logging
import string
from typing import Dict, Optional, List, Tuple

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from dotenv import load_dotenv

# --- Constants ---
#DEFAULT_MODEL = 'gemini-2.5-pro-exp-03-25'
DEFAULT_MODEL = 'gemini-2.0-flash'
DEFAULT_MULTI_INPUT_FILE = 'extended_product_input.txt' # Default input with multiple products
DEFAULT_OUTPUT_DIR = 'generated_descriptions' # Default output directory
PRODUCT_SEPARATOR = '--- PRODUCT SEPARATOR ---'
ENV_VAR_API_KEY = 'GEMINI_API_KEY'

OPTIMAL_DESC_LENGTH = 1500
MAX_DESC_LENGTH = 2000
MIN_DESC_LENGTH = 200
GENERATION_MAX_TOKENS = 500
GENERATION_TEMPERATURE = 0.7
MAX_FILENAME_LENGTH = 100 # Max length for generated filenames

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

def sanitize_filename(name: str, fallback_prefix: str = "product") -> str:
    """
    Cleans a string to be suitable for use as a filename.
    Replaces spaces, removes invalid characters, and truncates length.
    """
    if not name or name.lower() == 'unknown product':
        return fallback_prefix # Return generic prefix if name is bad

    # Remove punctuation and invalid characters
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
    cleaned_name = ''.join(c for c in name if c in valid_chars)

    # Replace spaces with underscores
    cleaned_name = cleaned_name.replace(' ', '_')

    # Remove leading/trailing underscores/periods
    cleaned_name = cleaned_name.strip('._')

    # Truncate to avoid overly long filenames
    cleaned_name = cleaned_name[:MAX_FILENAME_LENGTH]

    # Ensure it's not empty after cleaning
    if not cleaned_name:
         return fallback_prefix

    return cleaned_name

class AmazonProductDescriptionGenerator:
    """
    Generates Amazon product descriptions using Google's Gemini AI models.
    Contains methods for processing individual product data.
    """
    def __init__(self, api_key: Optional[str] = None, model_name: str = DEFAULT_MODEL):
        """
        Initialize the generator's connection to the AI model.
        """
        load_dotenv()
        self.api_key = api_key or os.getenv(ENV_VAR_API_KEY)

        if not self.api_key:
            logging.error(f"{ENV_VAR_API_KEY} not found. Set the environment variable or use --api-key.")
            raise ValueError("Gemini API key is required")

        try:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(model_name)
            self.model_name = model_name
            logging.info(f"Successfully configured Gemini AI with model: {self.model_name}")
        except Exception as e:
            logging.error(f"Failed to configure Gemini AI (Model: {model_name}): {e}", exc_info=True)
            raise

    def _parse_feature_list(self, text: str) -> str:
        """Helper to format features as a bulleted list for the prompt."""
        items = [item.strip() for item in re.split(r',|\n', text) if item.strip()]
        return "\n- ".join([""] + items) if items else "Not specified"

    def preprocess_input(self, product_text: str) -> Dict[str, str]:
        """
        Extracts details for a SINGLE product from its text block.
        """
        cleaned_text = re.sub(r'\s+', ' ', product_text).strip()
        logging.debug("Preprocessing input text block...")

        name_match = re.search(r'^(.*?)(?:Features:|Benefits:|$)', cleaned_text, re.IGNORECASE | re.DOTALL)
        name = name_match.group(1).strip() if name_match else ''
        if not name and product_text.strip(): # Fallback if regex fails
             first_line_match = re.match(r'^(.*?)(\r?\n|$)', product_text) # Use original text
             name = first_line_match.group(1).strip() if first_line_match else 'Unknown Product'

        features_match = re.search(r'Features:(.*?)(?:Benefits:|$)', cleaned_text, re.IGNORECASE | re.DOTALL)
        features = features_match.group(1).strip() if features_match else 'Not specified'

        benefits_match = re.search(r'Benefits:(.*?)$', cleaned_text, re.IGNORECASE | re.DOTALL)
        benefits = benefits_match.group(1).strip() if benefits_match else 'Not specified'

        details = {
            'name': name or 'Unknown Product',
            'features': features,
            'benefits': benefits
        }
        logging.debug(f"Extracted: Name='{details['name']}', Features='{details['features'][:30]}...', Benefits='{details['benefits'][:30]}...'")
        return details

    def generate_description(self, product_details: Dict[str, str]) -> Optional[str]:
        """
        Generates description for a SINGLE product using the Gemini model.
        """
        product_name = product_details.get('name', 'N/A')
        logging.debug(f"Attempting generation for: {product_name}")

        formatted_features = self._parse_feature_list(product_details.get('features', ''))
        formatted_benefits = self._parse_feature_list(product_details.get('benefits', ''))

        prompt = f"""Create a compelling Amazon product description for: '{product_name}'.

Follow these guidelines STRICTLY:
1.  **Target Audience:** Amazon Shoppers.
2.  **Goal:** Persuade the customer to buy. Focus on solving problems or fulfilling desires.
3.  **Length:** Aim for around {OPTIMAL_DESC_LENGTH} characters. Do NOT exceed {MAX_DESC_LENGTH} characters.
4.  **Tone:** Enthusiastic, persuasive, customer-focused, trustworthy.
5.  **Content:**
    *   Strong hook start.
    *   Highlight key features provided below.
    *   Emphasize the BENEFITS derived from features (how they help the customer).
    *   Use bullet points or short paragraphs for readability.
    *   Incorporate relevant keywords naturally, **avoid stuffing**.
    *   Include a call to action.
6.  **Formatting:** Use basic HTML like <p>, <b>, <ul>, <li> sparingly and correctly. Avoid complex elements
7.  **DO NOT** include the words "Features:" or "Benefits:" literally unless natural.

**Product Information:**
*   **Name:** {product_name}
*   **Key Features:** {formatted_features}
*   **Key Benefits:** {formatted_benefits}

Generate the description now:
"""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=GENERATION_TEMPERATURE,
                    max_output_tokens=GENERATION_MAX_TOKENS
                )
            )
            if response.parts:
                description = response.text
                logging.debug(f"Generated description (length={len(description)}).")
                return description
            else:
                block_reason = response.prompt_feedback.block_reason if hasattr(response, 'prompt_feedback') and response.prompt_feedback else 'Unknown'
                safety_ratings = response.prompt_feedback.safety_ratings if hasattr(response, 'prompt_feedback') and response.prompt_feedback else 'N/A'
                logging.error(f"Generation failed/blocked for '{product_name}'. Reason: {block_reason}. Safety: {safety_ratings}. Finish reason: {response.candidates[0].finish_reason if response.candidates else 'N/A'}")
                return None

        except google_exceptions.GoogleAPIError as e:
            logging.error(f"Google API error for '{product_name}': {e}", exc_info=True)
            return None
        except Exception as e:
            logging.error(f"Unexpected error during generation for '{product_name}': {e}", exc_info=True)
            return None

    def validate_description(self, description: str) -> str:
        """
        Validates and cleans up a single generated description.
        """
        if not isinstance(description, str):
             logging.warning("Validation input is not a string, returning empty.")
             return ""

        logging.debug(f"Validating description (current length={len(description)}).")

        if len(description) > MAX_DESC_LENGTH:
            logging.warning(f"Description exceeds max length ({MAX_DESC_LENGTH}), trimming.")
            last_space_index = description.rfind(' ', 0, MAX_DESC_LENGTH)
            if last_space_index != -1:
                description = description[:last_space_index] + "..."
            else:
                description = description[:MAX_DESC_LENGTH] + "..."

        if len(description) < MIN_DESC_LENGTH:
            logging.warning(f"Description is shorter than min length ({MIN_DESC_LENGTH} chars).")

        logging.debug(f"Validation complete (final length={len(description)}).")
        return description.strip()

    def process_product_text(self, product_text: str) -> Optional[str]:
        """
        Processes the text for a single product: preprocess, generate, validate.
        Returns the validated description or None on failure.
        """
        product_details = self.preprocess_input(product_text)
        if not product_details.get('name') or product_details['name'] == 'Unknown Product':
             logging.warning(f"Could not parse product name reliably. Using best guess or 'Unknown Product'.")

        generated_desc = self.generate_description(product_details)
        if generated_desc:
            validated_description = self.validate_description(generated_desc)
            return validated_description
        else:
            return None


def main():
    """
    Main function to process the multi-product input file and generate descriptions.
    """
    parser = argparse.ArgumentParser(description="Generate Amazon product descriptions from a multi-product input file.")
    parser.add_argument(
        "-i", "--input_file",
        default=DEFAULT_MULTI_INPUT_FILE,
        help=f"Path to the multi-product input text file. Default: {DEFAULT_MULTI_INPUT_FILE}"
    )
    parser.add_argument(
        "-o", "--output_dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory to save generated description files. Default: {DEFAULT_OUTPUT_DIR}"
    )
    parser.add_argument(
        "--api_key",
        default=None,
        help=f"Gemini API Key (optional, overrides {ENV_VAR_API_KEY} env var)."
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Name of the Gemini model to use. Default: {DEFAULT_MODEL}"
    )
    parser.add_argument(
        "--debug", action='store_true', help="Enable debug logging."
    )

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug("Debug logging enabled.")

    try:
        generator = AmazonProductDescriptionGenerator(api_key=args.api_key, model_name=args.model)
    except ValueError as e:
        logging.error(f"Initialization error: {e}")
        exit(1)

    try:
        with open(args.input_file, 'r', encoding='utf-8') as f:
            multi_product_input_text = f.read()
    except FileNotFoundError:
        logging.error(f"Input file not found: '{args.input_file}'")
        exit(1)
    except IOError as e:
        logging.error(f"Error reading input file '{args.input_file}': {e}")
        exit(1)

    product_texts = multi_product_input_text.strip().split(PRODUCT_SEPARATOR)
    logging.info(f"Processing {len(product_texts)} products from '{args.input_file}'.")

    os.makedirs(args.output_dir, exist_ok=True) # Create output directory if needed

    for index, product_text in enumerate(product_texts):
        if not product_text.strip(): # Skip empty product blocks
            logging.warning(f"Skipping empty product block at index {index+1}.")
            continue

        product_details = generator.preprocess_input(product_text)
        product_name = product_details.get('name', f'Product_{index+1}') # Fallback name if parsing fails
        output_filename = os.path.join(args.output_dir, f"{sanitize_filename(product_name, fallback_prefix=f'product_{index+1}')}.txt")

        logging.info(f"Processing product: '{product_name}' (index {index+1})...")
        description = generator.process_product_text(product_text)

        if description:
            try:
                with open(output_filename, 'w', encoding='utf-8') as outfile:
                    outfile.write(description)
                logging.info(f"Description saved to: '{output_filename}'")
            except IOError as e:
                logging.error(f"Error writing to output file '{output_filename}': {e}")
        else:
            logging.error(f"Failed to generate description for product: '{product_name}'.")

    logging.info("Multi-product description generation process completed.")


if __name__ == "__main__":
    main()
