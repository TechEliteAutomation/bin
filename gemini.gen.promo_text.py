import os
import requests
import json
import csv
from typing import List, Dict

class PromotionGenerator:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("API key not found. Please set the GEMINI_API_KEY environment variable.")
        
        self.url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"
        
    def create_promotion_prompt(self, product_data: Dict) -> str:
        """Creates an optimized prompt for generating promotional content."""
        prompt_template = """
        Create a conversational, sales-driven promotional script for the following product. 
        The script should:
        - Be naturally spoken in approximately 30 seconds
        - Highlight key features and benefits
        - Use engaging, persuasive language
        - Maintain a conversational tone while driving sales
        - Focus on value proposition and customer benefits
        
        Product Information:
        Name: {name}
        Description: {description}
        Price: {price}
        
        Generate a promotional script that compels viewers to take action while maintaining authenticity.
        """
        
        return prompt_template.format(
            name=product_data.get('name', ''),
            description=product_data.get('description', ''),
            price=product_data.get('price', '')
        )

    def get_gemini_response(self, prompt: str) -> str:
        """Sends request to Gemini API and returns the generated promotion text."""
        headers = {'Content-Type': 'application/json'}
        data = {"contents": [{"parts": [{"text": prompt}]}]}
        
        response = requests.post(
            f"{self.url}?key={self.api_key}",
            headers=headers,
            json=data
        )
        
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text']
        else:
            raise Exception(f"API Error: {response.status_code} - {response.text}")

    def process_csv_file(self, csv_filepath: str) -> List[Dict]:
        """Processes CSV file and returns generated promotions."""
        results = []
        
        with open(csv_filepath, 'r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                prompt = self.create_promotion_prompt(row)
                promotion_text = self.get_gemini_response(prompt)
                
                results.append({
                    'product_name': row.get('name', ''),
                    'original_description': row.get('description', ''),
                    'generated_promotion': promotion_text
                })
                
        return results

    def save_results(self, results: List[Dict], output_filepath: str):
        """Saves generated promotions to a CSV file."""
        with open(output_filepath, 'w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=[
                'product_name', 
                'original_description', 
                'generated_promotion'
            ])
            writer.writeheader()
            writer.writerows(results)

def main():
    try:
        generator = PromotionGenerator()
        
        input_file = input("Enter the path to your CSV file with product data: ")
        output_file = input("Enter the path for the output CSV file: ")
        
        print("\nProcessing products and generating promotions...")
        results = generator.process_csv_file(input_file)
        
        generator.save_results(results, output_file)
        print(f"\nPromotions generated successfully! Results saved to {output_file}")
        
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main()
