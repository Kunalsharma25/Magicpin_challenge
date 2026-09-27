import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=key)

candidate_models = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.0-flash-exp"
]

for m in candidate_models:
    try:
        resp = client.models.generate_content(model=m, contents="Hello")
        print(f"SUCCESS with model: {m} -> {resp.text.strip()}")
        break
    except Exception as e:
        print(f"FAILED model {m}: {e}")
