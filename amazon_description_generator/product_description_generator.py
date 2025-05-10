# product_description_generator.py

import os
import re
import logging
from typing import Dict, Optional

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from dotenv import load_dotenv

import config # Import constants from config.py

class AmazonProductDescriptionGenerator:
    """
    Generates Amazon product descriptions using Google's Gemini AI models.
    Contains methods for processing individual product data.
    """
    def __init__(self, api_key: Optional[str] = None, model_name: str = config.DEFAULT_MODEL):
        """
        Initialize the generator's connection to the AI model.
        """
        load_dotenv()
        self.api_key = api_key or os.getenv(config.ENV_VAR_API_KEY)

        if not self.api_key:
            logging.error(f"{config.ENV_VAR_API_KEY} not found. Set the environment variable or use --api-key.")
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
        if not name and product_text.strip():  # Fallback if regex fails
            first_line_match = re.match(r'^(.*?)(\r?\n|$)', product_text)  # Use original text
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
3.  **Length:** Aim for around {config.OPTIMAL_DESC_LENGTH} characters. Do NOT exceed {config.MAX_DESC_LENGTH} characters.
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
                    temperature=config.GENERATION_TEMPERATURE,
                    max_output_tokens=config.GENERATION_MAX_TOKENS
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

        if len(description) > config.MAX_DESC_LENGTH:
            logging.warning(f"Description exceeds max length ({config.MAX_DESC_LENGTH}), trimming.")
            last_space_index = description.rfind(' ', 0, config.MAX_DESC_LENGTH)
            if last_space_index != -1:
                description = description[:last_space_index] + "..."
            else:
                description = description[:config.MAX_DESC_LENGTH] + "..."

        if len(description) < config.MIN_DESC_LENGTH:
            logging.warning(f"Description is shorter than min length ({config.MIN_DESC_LENGTH} chars).")

        logging.debug(f"Validation complete (final length={len(description)}).")
        return description.strip()

    def process_product_text(self, product_text: str) -> Optional[str]:
        """
        Processes the text for a single product: preprocess, generate, validate.
        Returns the validated description or None on failure.
        """
        product_details = self.preprocess_input(product_text)
        if not product_details.get('name') or product_details['name'] == 'Unknown Product':
            logging.warning("Could not parse product name reliably. Using best guess or 'Unknown Product'.")

        generated_desc = self.generate_description(product_details)
        if generated_desc:
            validated_description = self.validate_description(generated_desc)
            return validated_description
        else:
            return None