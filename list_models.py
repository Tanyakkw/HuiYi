import urllib.request
import json
import os

# Get API key from environment or prompt
API_KEY = os.environ.get("GEMINI_API_KEY", "")
if not API_KEY:
    API_KEY = input("Enter your Gemini API Key: ").strip()

url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"

try:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as response:
        result = json.loads(response.read().decode('utf-8'))
        
        print("\n=== Available Models for generateContent ===\n")
        for model in result.get('models', []):
            name = model.get('name', '')
            methods = model.get('supportedGenerationMethods', [])
            if 'generateContent' in methods:
                # Only show models that support content generation
                display_name = model.get('displayName', '')
                print(f"  {name}")
        print()
except Exception as e:
    print(f"Error: {e}")
