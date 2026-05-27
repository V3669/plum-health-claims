from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Any, List, Optional

from pydantic import BaseModel, field_validator

from app.models.enums import DocumentType


class LineItem(BaseModel):
    description: str
    amount: Decimal
    is_excluded: bool = False
    exclusion_reason: Optional[str] = None

    @field_validator("amount", mode="before")
    @classmethod
    def coerce_amount(cls, v: Any) -> Decimal:
        return Decimal(str(v))


class ExtractedDocument(BaseModel):
    file_id: str
    declared_type: DocumentType
    inferred_type: DocumentType = DocumentType.UNKNOWN
    patient_name: Optional[str] = None
    document_date: Optional[date] = None
    diagnosis: Optional[str] = None
    secondary_diagnoses: List[str] = []
    medicines: List[str] = []
    tests_ordered: List[str] = []
    doctor_name: Optional[str] = None
    doctor_registration: Optional[str] = None
    hospital_name: Optional[str] = None
    line_items: List[LineItem] = []
    total_amount: Optional[Decimal] = None
    extraction_confidence: float = 0.95
    extraction_warnings: List[str] = []
    is_readable: bool = True
    treatment: Optional[str] = None

    @field_validator("total_amount", mode="before")
    @classmethod
    def coerce_total(cls, v: Any) -> Optional[Decimal]:
        if v is None:
            return None
        return Decimal(str(v))
