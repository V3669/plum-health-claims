from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.enums import ClaimCategory, DocumentQuality, DocumentType


class DocumentSubmission(BaseModel):
    file_id: str
    file_name: Optional[str] = None
    actual_type: DocumentType
    quality: DocumentQuality = DocumentQuality.GOOD
    file_path: Optional[str] = None
    content: Optional[Dict[str, Any]] = None
    patient_name_on_doc: Optional[str] = None


class HistoricalClaim(BaseModel):
    claim_id: str
    date: date
    amount: Decimal
    provider: Optional[str] = None

    @field_validator("amount", mode="before")
    @classmethod
    def coerce_amount(cls, v: Any) -> Decimal:
        return Decimal(str(v))


class ClaimSubmission(BaseModel):
    claim_id: Optional[str] = None
    member_id: str
    policy_id: str
    claim_category: ClaimCategory
    treatment_date: date
    claimed_amount: Decimal
    hospital_name: Optional[str] = None
    ytd_claims_amount: Decimal = Decimal("0")
    claims_history: List[HistoricalClaim] = Field(default_factory=list)
    pre_authorization_ref: Optional[str] = None
    documents: List[DocumentSubmission]
    simulate_component_failure: bool = False

    @field_validator("claimed_amount", "ytd_claims_amount", mode="before")
    @classmethod
    def coerce_decimal(cls, v: Any) -> Decimal:
        return Decimal(str(v))
