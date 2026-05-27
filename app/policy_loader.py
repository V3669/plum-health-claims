import json
import os
from pathlib import Path
from typing import Optional

from app.models.policy import PolicyConfig

_cache: Optional[PolicyConfig] = None
_cache_mtime: float = 0.0

_POLICY_PATH = Path(__file__).parent.parent / "policy_terms.json"


def _policy_path() -> Path:
    env_path = os.environ.get("POLICY_FILE")
    if env_path:
        return Path(env_path)
    return _POLICY_PATH


def load_policy() -> PolicyConfig:
    global _cache, _cache_mtime
    path = _policy_path()
    mtime = path.stat().st_mtime
    if _cache is None or mtime != _cache_mtime:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        _cache = PolicyConfig.model_validate(data)
        _cache_mtime = mtime
    return _cache


def invalidate_cache() -> None:
    global _cache, _cache_mtime
    _cache = None
    _cache_mtime = 0.0
