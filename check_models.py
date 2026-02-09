import urllib.request
import json
import os

# 用户提供的 API Key
API_KEY = "AIzaSyABxytI-RrsGtVydOxhisaobG_gSQDYgcw"

def list_models():
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            print(f"{'Model Name':<40} {'Supported Methods'}")
            print("-" * 60)
            
            found_any = False
            if 'models' in data:
                for model in data['models']:
                    name = model['name']
                    methods = model.get('supportedGenerationMethods', [])
                    
                    if 'generateContent' in methods:
                        print(f"{name:<40} {methods}")
                        found_any = True
            
            if not found_any:
                print("No models found supporting generateContent.")
                
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} - {e.reason}")
        print(e.read().decode('utf-8'))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("Checking available Gemini models...")
    list_models()
