# main.py

import os
import argparse
import logging

import config # For default values and constants
import utils # For utility functions like sanitize_filename
from product_description_generator import AmazonProductDescriptionGenerator

# --- Logging Configuration ---
# Configure root logger. Child loggers in other modules will inherit this.
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    """
    Main function to process the multi-product input file and generate descriptions.
    """
    parser = argparse.ArgumentParser(description="Generate Amazon product descriptions from a multi-product input file.")
    parser.add_argument(
        "-i", "--input_file",
        default=config.DEFAULT_MULTI_INPUT_FILE,
        help=f"Path to the multi-product input text file. Default: {config.DEFAULT_MULTI_INPUT_FILE}"
    )
    parser.add_argument(
        "-o", "--output_dir",
        default=config.DEFAULT_OUTPUT_DIR,
        help=f"Directory to save generated description files. Default: {config.DEFAULT_OUTPUT_DIR}"
    )
    parser.add_argument(
        "--api_key",
        default=None,
        help=f"Gemini API Key (optional, overrides {config.ENV_VAR_API_KEY} env var)."
    )
    parser.add_argument(
        "--model",
        default=config.DEFAULT_MODEL,
        help=f"Name of the Gemini model to use. Default: {config.DEFAULT_MODEL}"
    )
    parser.add_argument(
        "--debug", action='store_true', help="Enable debug logging."
    )

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG) # Set root logger to DEBUG
        for handler in logging.getLogger().handlers: # Also set handlers to DEBUG
            handler.setLevel(logging.DEBUG)
        logging.debug("Debug logging enabled.")


    try:
        generator = AmazonProductDescriptionGenerator(api_key=args.api_key, model_name=args.model)
    except ValueError as e:
        logging.error(f"Initialization error: {e}")
        exit(1)
    except Exception as e: # Catch other potential init errors from genai
        logging.error(f"Failed to initialize AmazonProductDescriptionGenerator: {e}", exc_info=True)
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

    product_texts = multi_product_input_text.strip().split(config.PRODUCT_SEPARATOR)
    logging.info(f"Processing {len(product_texts)} products from '{args.input_file}'.")

    os.makedirs(args.output_dir, exist_ok=True)  # Create output directory if needed

    for index, product_text in enumerate(product_texts):
        product_text_stripped = product_text.strip()
        if not product_text_stripped:  # Skip empty product blocks
            logging.warning(f"Skipping empty product block at index {index + 1}.")
            continue

        # Preprocess once to get details for filename and logging
        # The process_product_text method will call preprocess_input again,
        # which is slightly redundant but keeps process_product_text self-contained.
        # Alternatively, pass preprocessed_details to process_product_text.
        # For this refactor, keeping it simple and closer to original flow.
        preliminary_details = generator.preprocess_input(product_text_stripped)
        product_name = preliminary_details.get('name', f'Product_{index + 1}') # Fallback name
        output_filename = os.path.join(args.output_dir, f"{utils.sanitize_filename(product_name, fallback_prefix=f'product_{index + 1}')}.txt")

        logging.info(f"Processing product: '{product_name}' (index {index + 1})...")
        description = generator.process_product_text(product_text_stripped)

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