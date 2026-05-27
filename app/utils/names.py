import re
from typing import Optional

from rapidfuzz import fuzz

HONORIFICS = {"mr.", "mrs.", "ms.", "miss", "dr.", "shri", "smt.", "mr", "mrs", "ms", "dr"}
_MULTI_SPACE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    name = name.lower().strip()
    tokens = name.split()
    if tokens and tokens[0] in HONORIFICS:
        tokens = tokens[1:]
    return _MULTI_SPACE.sub(" ", " ".join(tokens)).strip()


def names_match(a: str, b: str, threshold: int = 85) -> bool:
    na, nb = normalize_name(a), normalize_name(b)
    if na == nb:
        return True
    return fuzz.token_set_ratio(na, nb) >= threshold


def hospital_name_match(submission_name: str, policy_name: str) -> bool:
    s = submission_name.lower().strip()
    p = policy_name.lower().strip()
    return p in s or s in p
