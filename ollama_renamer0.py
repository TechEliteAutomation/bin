#!/usr/bin/env python3

import requests
import json
from pathlib import Path
from bs4 import BeautifulSoup

# Ollama configuration
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma3:1b"

def query_ollama(prompt: str) -> str:
    """Query local Ollama instance."""
    try:
        response = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1}
        }, timeout=30)
        
        if response.status_code == 200:
            return response.json()["response"].strip()
        return ""
    except Exception as e:
        print(f"Ollama query failed: {e}")
        return ""

def suggest_filename_ollama(html_content: str, original_name: str) -> str:
    """Generate filename using local AI."""
    prompt = f"""Based on this HTML content, suggest a descriptive filename (without extension).
Requirements:
- Use only lowercase letters, numbers, underscores
- Maximum 50 characters
- Be descriptive of the main content/purpose
- Output only the filename

HTML Title/Content: {html_content[:1000]}
Current filename: {original_name}

Suggested filename:"""
    
    suggestion = query_ollama(prompt)
    if suggestion:
        # Clean and validate
        import re
        clean = re.sub(r'[^a-z0-9_]', '', suggestion.lower())
        return clean[:50] if clean else ""
    return ""

def process_with_ollama(directory: Path):
    """Process HTML files using Ollama."""
    for filepath in directory.rglob("*.htm*"):
        if not filepath.is_file():
            continue
            
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                soup = BeautifulSoup(f.read(), 'html.parser')
            
            content = ""
            if soup.title:
                content += f"Title: {soup.title.string}\n"
            
            # Get main content
            for tag in soup.find_all(['h1', 'h2', 'main', 'article']):
                content += tag.get_text(strip=True)[:500]
                break
            
            if content:
                suggestion = suggest_filename_ollama(content, filepath.name)
                if suggestion and suggestion != filepath.stem:
                    print(f"{filepath.name} → {suggestion}.html")
                    
        except Exception as e:
            print(f"Error processing {filepath}: {e}")

if __name__ == "__main__":
    # Check if Ollama is running
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            print("Ollama detected, processing files...")
            process_with_ollama(Path('.'))
        else:
            print("Ollama not running. Start with: ollama serve")
    except:
        print("Ollama not available. Install: https://ollama.ai")
