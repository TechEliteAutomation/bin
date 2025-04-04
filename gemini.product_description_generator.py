import os
import re
from typing import Dict, Optional
import google.generativeai as genai
from dotenv import load_dotenv

class AmazonProductDescriptionGenerator:
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the product description generator with Gemini AI.
        
        Args:
            api_key (str, optional): Google AI API key. Defaults to environment variable.
        """
        load_dotenv()
        self.api_key = api_key or os.getenv('GOOGLE_AI_API_KEY')
        
        if not self.api_key:
            raise ValueError("Google AI API key is required")
        
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-pro')

    def preprocess_input(self, input_text: str) -> Dict[str, str]:
        """
        Preprocess and extract product details from input text.
        
        Args:
            input_text (str): Raw product information text
        
        Returns:
            Dict containing normalized product details
        """
        # Remove excessive whitespace and normalize text
        cleaned_text = re.sub(r'\s+', ' ', input_text).strip()
        
        # Basic input parsing (can be enhanced with more robust parsing)
        details = {
            'name': re.search(r'^(.*?)(?=Features:|Benefits:|$)', cleaned_text, re.IGNORECASE)
                    .group(1).strip() if re.search(r'^(.*?)(?=Features:|Benefits:|$)', cleaned_text, re.IGNORECASE) else '',
            'features': re.search(r'Features:(.*?)(?=Benefits:|$)', cleaned_text, re.IGNORECASE)
                        .group(1).strip() if re.search(r'Features:(.*?)(?=Benefits:|$)', cleaned_text, re.IGNORECASE) else '',
            'benefits': re.search(r'Benefits:(.*?)$', cleaned_text, re.IGNORECASE)
                        .group(1).strip() if re.search(r'Benefits:(.*?)$', cleaned_text, re.IGNORECASE) else ''
        }
        
        return details

    def generate_description(self, product_details: Dict[str, str]) -> str:
        """
        Generate Amazon-compliant product description using Gemini AI.
        
        Args:
            product_details (Dict): Preprocessed product information
        
        Returns:
            str: Generated product description
        """
        prompt = f"""Generate an Amazon product description for '{product_details['name']}' 
        adhering to these guidelines:
        - Length: 1500 characters optimal
        - Highlight key features: {product_details['features']}
        - Emphasize benefits: {product_details['benefits']}
        - Use persuasive, user-centric language
        - Avoid keyword stuffing
        - Focus on solving customer needs"""

        response = self.model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=350
            )
        )

        return response.text

    def validate_description(self, description: str) -> str:
        """
        Validate generated description against Amazon guidelines.
        
        Args:
            description (str): Generated product description
        
        Returns:
            str: Validated and potentially adjusted description
        """
        # Trim description to 2000 characters
        description = description[:2000]
        
        # Ensure minimum length
        if len(description) < 200:
            description += " " + " ".join(description.split()[:50])
        
        return description

    def process_product_file(self, input_file: str, output_file: str) -> None:
        """
        Process entire product description generation workflow.
        
        Args:
            input_file (str): Path to input text file
            output_file (str): Path to output description file
        """
        with open(input_file, 'r') as f:
            input_text = f.read()
        
        product_details = self.preprocess_input(input_text)
        description = self.generate_description(product_details)
        validated_description = self.validate_description(description)
        
        with open(output_file, 'w') as f:
            f.write(validated_description)

def main():
    generator = AmazonProductDescriptionGenerator()
    generator.process_product_file('product_input.txt', 'amazon_description.txt')

if __name__ == "__main__":
    main()
