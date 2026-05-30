from __future__ import annotations
import asyncio
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from google.genai import types

from app.llm_client import get_client, has_api_key
from app.models.enums import DocumentQuality, DocumentType
from app.models.extraction import ExtractedDocument, LineItem
from app.models.submission import DocumentSubmission
from app.utils.dates import parse_date


def _safe_decimal(value: Any) -> Optional[Decimal]:
    """Convert an LLM-returned value to Decimal, returning None on any failure.

    Handles the full range of values Gemini may produce for 'amount' fields:
      - Proper numbers:        1500, 1500.0, "1500.00"
      - Comma-formatted:       "9,800"  "1,85,000"
      - Currency-prefixed:     "₹1500"  "$200"
      - Non-numeric results:   "NEGATIVE"  "N/A"  "Normal"  "13.0-17.0"
      - Python None / "None":  None  "None"  "null"
      - Empty string:          ""  "  "
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("none", "null", "n/a", "na", "-", "--", "normal", "abnormal"):
        return None
    # Strip leading currency symbols (₹, $, £, €, Rs, INR …)
    s = re.sub(r"^[₹$£€]|^Rs\.?\s*|^INR\.?\s*", "", s, flags=re.IGNORECASE).strip()
    # Remove thousands separators (Indian: 1,85,000  Western: 1,500)
    s = s.replace(",", "")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError, ArithmeticError):
        return None


_MIME_BY_EXT: Dict[str, str] = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}

_EXTRACTION_MODEL = "gemini-2.5-flash"

_EXTRACTION_PROMPT = (
    "Extract structured information from this {doc_type}. "
    "Return a JSON object with these fields: "
    "patient_name (string|null), document_date (YYYY-MM-DD|null), diagnosis (string|null), "
    "secondary_diagnoses (list of strings), medicines (list of strings), "
    "tests_ordered (list of strings), doctor_name (string|null), "
    "doctor_registration (string|null), hospital_name (string|null), "
    "line_items (list of {{description: string, amount: number|null}}), "
    "total_amount (number|null), "
    "extraction_confidence (0.0-1.0), extraction_warnings (list of strings), "
    "treatment (string|null). "
    "IMPORTANT: 'amount' in line_items and 'total_amount' must always be a plain number "
    "(e.g. 1500.00) or null — never a string, unit, range, or non-numeric test result. "
    "For lab reports, list each test in tests_ordered and leave line_items empty. "
    "For any field you cannot find or are uncertain about, use null or empty list. "
    "Return ONLY valid JSON, no markdown fences."
)


class DocumentExtractionAgent:
    name = "DocumentExtraction"

    async def execute(self, documents: List[DocumentSubmission]) -> List[ExtractedDocument]:
        tasks = [self._extract_one(doc) for doc in documents]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        extracted: List[ExtractedDocument] = []
        for doc, result in zip(documents, results):
            if isinstance(result, Exception):
                extracted.append(ExtractedDocument(
                    file_id=doc.file_id,
                    declared_type=doc.actual_type,
                    inferred_type=DocumentType.UNKNOWN,
                    is_readable=False,
                    extraction_confidence=0.0,
                    extraction_warnings=[f"Extraction failed: {result}"],
                ))
            else:
                extracted.append(result)
        return extracted

    async def _extract_one(self, doc: DocumentSubmission) -> ExtractedDocument:
        if doc.quality == DocumentQuality.UNREADABLE:
            return ExtractedDocument(
                file_id=doc.file_id,
                declared_type=doc.actual_type,
                inferred_type=DocumentType.UNKNOWN,
                is_readable=False,
                extraction_confidence=0.0,
                extraction_warnings=["Document marked unreadable on upload."],
            )

        if doc.content is not None:
            return self._build_from_content(doc)

        if doc.patient_name_on_doc is not None:
            return ExtractedDocument(
                file_id=doc.file_id,
                declared_type=doc.actual_type,
                inferred_type=doc.actual_type,
                patient_name=doc.patient_name_on_doc,
                extraction_confidence=0.70,
                is_readable=True,
                extraction_warnings=["Extracted from patient_name_on_doc only; no full content available."],
            )

        if not has_api_key():
            return ExtractedDocument(
                file_id=doc.file_id,
                declared_type=doc.actual_type,
                inferred_type=DocumentType.UNKNOWN,
                is_readable=False,
                extraction_confidence=0.0,
                extraction_warnings=["No GEMINI_API_KEY configured and no pre-extracted content provided."],
            )

        return await self._extract_via_llm(doc)

    def _build_from_content(self, doc: DocumentSubmission) -> ExtractedDocument:
        c: Dict[str, Any] = doc.content or {}

        line_items: List[LineItem] = []
        for item in c.get("line_items", []):
            amt = _safe_decimal(item.get("amount"))
            if amt is not None:
                line_items.append(LineItem(
                    description=item.get("description", ""),
                    amount=amt,
                ))

        total_raw = c.get("total_amount") if c.get("total") is None else c.get("total")
        total = _safe_decimal(total_raw)

        raw_date = c.get("date") or c.get("document_date")
        doc_date: Optional[date] = parse_date(str(raw_date)) if raw_date else None

        patient_name = c.get("patient_name") or doc.patient_name_on_doc

        return ExtractedDocument(
            file_id=doc.file_id,
            declared_type=doc.actual_type,
            inferred_type=doc.actual_type,
            patient_name=patient_name,
            document_date=doc_date,
            diagnosis=c.get("diagnosis"),
            secondary_diagnoses=c.get("secondary_diagnoses", []),
            medicines=c.get("medicines", []),
            tests_ordered=c.get("tests_ordered", []),
            doctor_name=c.get("doctor_name"),
            doctor_registration=c.get("doctor_registration"),
            hospital_name=c.get("hospital_name"),
            line_items=line_items,
            total_amount=total,
            extraction_confidence=0.95,
            is_readable=True,
            treatment=c.get("treatment"),
        )

    async def _extract_via_llm(self, doc: DocumentSubmission) -> ExtractedDocument:
        client = get_client()
        if client is None:
            raise RuntimeError("No LLM client available")

        if not doc.file_path:
            raise ValueError(f"No file_path for doc {doc.file_id}")

        with open(doc.file_path, "rb") as f:
            image_bytes = f.read()

        suffix = (doc.file_name or doc.file_path or "").lower()
        ext = "." + suffix.rsplit(".", 1)[-1] if "." in suffix else ""
        media_type = _MIME_BY_EXT.get(ext, "image/jpeg")

        prompt = _EXTRACTION_PROMPT.format(
            doc_type=doc.actual_type.value.lower().replace("_", " ")
        )

        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=_EXTRACTION_MODEL,
                    contents=[
                        types.Part.from_bytes(data=image_bytes, mime_type=media_type),
                        prompt,
                    ],
                    config=types.GenerateContentConfig(max_output_tokens=4000),
                ),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            return ExtractedDocument(
                file_id=doc.file_id,
                declared_type=doc.actual_type,
                inferred_type=DocumentType.UNKNOWN,
                is_readable=False,
                extraction_confidence=0.0,
                extraction_warnings=["LLM timeout"],
            )

        raw_text = (response.text or "").strip()
        # Strip markdown code fences robustly — handle ```json ... ``` and ``` ... ```
        if "```" in raw_text:
            fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw_text)
            raw_text = fence_match.group(1).strip() if fence_match else raw_text
        raw_text = raw_text.strip()

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            return ExtractedDocument(
                file_id=doc.file_id,
                declared_type=doc.actual_type,
                inferred_type=DocumentType.UNKNOWN,
                is_readable=False,
                extraction_confidence=0.0,
                extraction_warnings=[f"LLM returned non-JSON response: {exc}"],
            )

        line_items = []
        for item in data.get("line_items", []):
            amt = _safe_decimal(item.get("amount"))
            if amt is not None:
                line_items.append(LineItem(
                    description=item.get("description", ""),
                    amount=amt,
                ))

        total_raw = data.get("total_amount")
        total = _safe_decimal(total_raw)

        raw_date = data.get("document_date")
        doc_date = parse_date(str(raw_date)) if raw_date else None

        return ExtractedDocument(
            file_id=doc.file_id,
            declared_type=doc.actual_type,
            inferred_type=doc.actual_type,
            patient_name=data.get("patient_name"),
            document_date=doc_date,
            diagnosis=data.get("diagnosis"),
            secondary_diagnoses=data.get("secondary_diagnoses", []),
            medicines=data.get("medicines", []),
            tests_ordered=data.get("tests_ordered", []),
            doctor_name=data.get("doctor_name"),
            doctor_registration=data.get("doctor_registration"),
            hospital_name=data.get("hospital_name"),
            line_items=line_items,
            total_amount=total,
            extraction_confidence=float(data.get("extraction_confidence", 0.8)),
            extraction_warnings=data.get("extraction_warnings", []),
            is_readable=True,
            treatment=data.get("treatment"),
        )
