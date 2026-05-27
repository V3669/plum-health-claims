import os
from typing import Optional

import anthropic


_client: Optional[anthropic.AsyncAnthropic] = None


def get_client() -> Optional[anthropic.AsyncAnthropic]:
    global _client
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=api_key)
    return _client


def has_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))
