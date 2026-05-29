from typing import Optional

from google import genai

from app.config import GEMINI_API_KEY


_client: Optional[genai.Client] = None


def get_client() -> Optional[genai.Client]:
    global _client
    if not GEMINI_API_KEY:
        return None
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def has_api_key() -> bool:
    return bool(GEMINI_API_KEY)
