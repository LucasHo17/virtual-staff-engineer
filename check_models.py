# check_models.py
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client()

print("🔍 Querying available models from your API key...")
for m in client.models.list():
    if "embed" in m.name.lower() or "embed" in m.supported_actions:
        print(f"✅ Name: {m.name} | Actions: {m.supported_actions}")