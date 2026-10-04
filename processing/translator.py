import os

import requests

from dotenv import load_dotenv

load_dotenv()

DEEPL_API_URL = "https://api-free.deepl.com/v2/translate"

def translate_text(text, target_language, api_key=None):
    if not text or target_language == "de":
        return None

    api_key = api_key or os.getenv("DEEPL_API_KEY")

    if not api_key:
        return None

    response = requests.post(
        DEEPL_API_URL,
        headers={
            "Authorization": f"DeepL-Auth-Key {api_key}",
        },
        data={
            "text": text,
            "source_lang": "DE",
            "target_lang": target_language.upper(),
        },
        timeout=20,
    )

    response.raise_for_status()

    result = response.json()

    return result["translations"][0]["text"]