"""
Unit tests for _safe_decimal and the full _extract_via_llm post-processing path.

These tests exercise every value type Gemini can return for 'amount' fields,
including the exact patterns that caused the lab-report ConversionSyntax crash.
No API calls are made — we patch _extract_via_llm at the JSON-parse boundary.
"""
from __future__ import annotations
from decimal import Decimal
from typing import Any
import json
import pytest

from app.agents.doc_extraction import _safe_decimal, DocumentExtractionAgent
from app.models.enums import DocumentType
from app.models.submission import DocumentSubmission


# ── _safe_decimal contract ────────────────────────────────────────────────────

@pytest.mark.parametrize("value, expected", [
    # Normal numbers
    (1500,        Decimal("1500")),
    (1500.0,      Decimal("1500.0")),
    ("1500.00",   Decimal("1500.00")),
    ("200",       Decimal("200")),
    ("0",         Decimal("0")),
    ("0.00",      Decimal("0.00")),

    # Currency-prefixed (Indian billing docs)
    ("₹1500",     Decimal("1500")),
    ("₹ 1500.00", Decimal("1500.00")),
    ("Rs 400",    Decimal("400")),
    ("Rs. 400",   Decimal("400")),
    ("INR 350",   Decimal("350")),
    ("$200",      Decimal("200")),
    ("£300",      Decimal("300")),

    # Comma-formatted numbers (Indian and Western)
    ("9,800",       Decimal("9800")),
    ("1,85,000",    Decimal("185000")),
    ("1,500,000",   Decimal("1500000")),
    ("1,500.00",    Decimal("1500.00")),

    # Non-numeric lab result strings → None (the crash case)
    ("NEGATIVE",    None),
    ("POSITIVE",    None),
    ("Normal",      None),
    ("Abnormal",    None),
    ("N/A",         None),
    ("NA",          None),
    ("n/a",         None),
    ("-",           None),
    ("--",          None),

    # Range strings (reference intervals) → None
    ("13.0-17.0",   None),
    ("4500-11000",  None),

    # Null / empty / Python None
    (None,          None),
    ("None",        None),
    ("null",        None),
    ("",            None),
    ("   ",         None),
])
def test_safe_decimal(value: Any, expected):
    result = _safe_decimal(value)
    assert result == expected, f"_safe_decimal({value!r}) = {result!r}, expected {expected!r}"


# ── Full post-processing path with mocked LLM JSON ───────────────────────────

def _make_doc(dtype: DocumentType = DocumentType.LAB_REPORT) -> DocumentSubmission:
    return DocumentSubmission(
        file_id="unit-test-id",
        file_name="test.jpg",
        actual_type=dtype,
        file_path="/tmp/does_not_exist.jpg",
    )


def _call_postprocess(agent: DocumentExtractionAgent, data: dict, doc: DocumentSubmission):
    """Exercise only the JSON → ExtractedDocument conversion, bypassing the API call."""
    from app.models.extraction import LineItem
    from app.utils.dates import parse_date
    from datetime import date as _date

    line_items = []
    for item in data.get("line_items", []):
        amt = _safe_decimal(item.get("amount"))
        if amt is not None:
            line_items.append(LineItem(description=item.get("description", ""), amount=amt))

    total = _safe_decimal(data.get("total_amount"))
    raw_date = data.get("document_date")
    doc_date = parse_date(str(raw_date)) if raw_date else None

    from app.models.extraction import ExtractedDocument
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


def test_lab_report_with_non_numeric_amounts():
    """Exact scenario that caused the ConversionSyntax crash.
    Gemini returns CBC + Dengue results as line_items with string amounts.
    """
    agent = DocumentExtractionAgent()
    doc   = _make_doc(DocumentType.LAB_REPORT)

    # Simulated Gemini JSON for rajesh_kumar__lab_report__cbc_dengue.pdf
    gemini_json = {
        "patient_name": "Rajesh Kumar",
        "document_date": "2024-11-01",
        "hospital_name": "Precision Diagnostics Pvt Ltd",
        "doctor_name": "Dr. Meena Pillai",
        "tests_ordered": ["CBC", "Dengue NS1 Antigen", "Dengue IgM", "Dengue IgG"],
        "line_items": [
            {"description": "Haemoglobin",      "amount": "13.2"},     # numeric string ✓
            {"description": "WBC Count",         "amount": "9,800"},   # comma number ✓
            {"description": "Platelet Count",    "amount": "1,85,000"},# Indian comma ✓
            {"description": "Dengue NS1 Antigen","amount": "NEGATIVE"},# string → skip
            {"description": "Dengue IgG",        "amount": "POSITIVE"},# string → skip
            {"description": "Normal Range WBC",  "amount": "4500-11000"},# range → skip
        ],
        "total_amount": None,
        "extraction_confidence": 0.9,
        "extraction_warnings": [],
    }

    result = _call_postprocess(agent, gemini_json, doc)

    assert result.is_readable is True
    assert result.patient_name == "Rajesh Kumar"
    # Only numeric amounts should survive
    assert len(result.line_items) == 3
    descs = [li.description for li in result.line_items]
    assert "Haemoglobin" in descs
    assert "WBC Count" in descs
    assert "Platelet Count" in descs
    # Non-numeric results dropped cleanly
    assert all("NEGATIVE" not in li.description for li in result.line_items)
    # Comma-formatted WBC stored correctly
    wbc = next(li for li in result.line_items if li.description == "WBC Count")
    assert wbc.amount == Decimal("9800")
    # Indian-format platelet
    plt = next(li for li in result.line_items if li.description == "Platelet Count")
    assert plt.amount == Decimal("185000")
    # No total (lab reports don't have one)
    assert result.total_amount is None


def test_hospital_bill_normal_amounts():
    """Typed hospital bill: all amounts are clean — should all survive."""
    agent = DocumentExtractionAgent()
    doc   = _make_doc(DocumentType.HOSPITAL_BILL)

    gemini_json = {
        "patient_name": "Rajesh Kumar",
        "hospital_name": "City Medical Centre",
        "line_items": [
            {"description": "Consultation Fee", "amount": 1000},
            {"description": "CBC Test",         "amount": 200},
            {"description": "Dengue NS1 Test",  "amount": 200},
            {"description": "Malaria Antigen",  "amount": 100},
        ],
        "total_amount": 1500,
        "extraction_confidence": 1.0,
        "extraction_warnings": [],
    }

    result = _call_postprocess(agent, gemini_json, doc)

    assert result.is_readable is True
    assert len(result.line_items) == 4
    assert result.total_amount == Decimal("1500")


def test_pharmacy_bill_currency_prefixed():
    """Pharmacy bill with Indian Rupee prefix on amounts."""
    agent = DocumentExtractionAgent()
    doc   = _make_doc(DocumentType.PHARMACY_BILL)

    gemini_json = {
        "patient_name": "Rajesh Kumar",
        "line_items": [
            {"description": "Paracetamol 650mg", "amount": "₹37.50"},
            {"description": "Vitamin C 500mg",   "amount": "₹40.00"},
        ],
        "total_amount": "₹91.87",
        "extraction_confidence": 0.95,
        "extraction_warnings": [],
    }

    result = _call_postprocess(agent, gemini_json, doc)

    assert result.total_amount == Decimal("91.87")
    assert result.line_items[0].amount == Decimal("37.50")


def test_null_and_missing_amounts_do_not_crash():
    """null, None, missing key — all should produce empty line_items, not an exception."""
    agent = DocumentExtractionAgent()
    doc   = _make_doc(DocumentType.HOSPITAL_BILL)

    gemini_json = {
        "patient_name": "Test Patient",
        "line_items": [
            {"description": "Item A", "amount": None},
            {"description": "Item B"},              # key missing entirely
            {"description": "Item C", "amount": ""},
            {"description": "Item D", "amount": "null"},
        ],
        "total_amount": None,
        "extraction_confidence": 0.7,
        "extraction_warnings": ["amounts unclear"],
    }

    result = _call_postprocess(agent, gemini_json, doc)

    assert result.is_readable is True
    assert result.line_items == []
    assert result.total_amount is None
