import re
from typing import Optional

DIAGNOSIS_CONDITION_MAP: dict[str, list[str]] = {
    "diabetes": [r"\b(diabetes|t2dm|t1dm|dm\s*type|diabetic)\b"],
    "hypertension": [r"\b(hypertension|htn|high\s*blood\s*pressure)\b"],
    "thyroid_disorders": [r"\b(thyroid|hypothyroid|hyperthyroid|goiter|goitre)\b"],
    "joint_replacement": [r"\b(joint\s*replacement|knee\s*replacement|hip\s*replacement|arthroplasty)\b"],
    "maternity": [r"\b(pregnan|pregnancy|maternity|antenatal|postnatal|delivery|obstetric)\b"],
    "mental_health": [r"\b(depression|anxiety|bipolar|schizo|psychiatric|mental\s*health)\b"],
    "obesity_treatment": [r"\b(obesity|bariatric|morbid\s*obes|weight\s*loss\s*program)\b"],
    "hernia": [r"\bhernia\b"],
    "cataract": [r"\bcataract\b"],
}

EXCLUSION_KEYWORDS: dict[str, list[str]] = {
    "Obesity and weight loss programs": [r"\bobesity\b", r"\bweight\s*loss\b", r"\bmorbid\s*obes"],
    "Bariatric surgery": [r"\bbariatric\b"],
    "Infertility and assisted reproduction": [r"\binfertil", r"\bivf\b", r"\birt\b", r"\bassisted\s*reproduc"],
    "Self-inflicted injuries": [r"\bself[\s-]*inflict"],
    "Substance abuse treatment": [r"\bsubstance\s*abuse\b", r"\bde-?addic", r"\balcohol\s*treatm"],
    "Experimental treatments": [r"\bexperimental\s*treat"],
    "Cosmetic or aesthetic procedures": [r"\bcosmetic\b", r"\baesthetic\b", r"\bbeauty\s*treatment"],
    "War or nuclear hazard": [r"\bnuclear\b", r"\bwar\s*injur"],
    "Vaccination (non-medically necessary)": [r"\bvaccinat"],
    "Health supplements and tonics": [r"\bsupplements?\b", r"\btonics?\b"],
}


def map_diagnosis_to_condition(diagnosis_text: str) -> Optional[str]:
    if not diagnosis_text:
        return None
    text = diagnosis_text.lower()
    for condition, patterns in DIAGNOSIS_CONDITION_MAP.items():
        for pattern in patterns:
            if re.search(pattern, text):
                return condition
    return None


def matches_exclusion(full_text: str) -> Optional[str]:
    text = full_text.lower()
    for exclusion_name, patterns in EXCLUSION_KEYWORDS.items():
        for pattern in patterns:
            if re.search(pattern, text):
                return exclusion_name
    return None
