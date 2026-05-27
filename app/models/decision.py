from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.enums import Decision, FraudSignal, HaltCode, RejectionCode
from app.models.trace import ClaimTrace


class FinancialBreakdown(BaseModel):
    claimed_amount: Decimal
    network_discount_applied: Decimal = Decimal("0")
    amount_after_discount: Decimal = Decimal("0")
    copay_applied: Decimal = Decimal("0")
    amount_after_copay: Decimal = Decimal("0")
    excluded_line_items_total: Decimal = Decimal("0")
    sub_limit_cap_applied: Decimal = Decimal("0")
    final_approved_amount: Decimal = Decimal("0")


class ClaimDecision(BaseModel):
    claim_id: str
    decision: Decision
    approved_amount: Decimal = Decimal("0")
    confidence_score: float
    reasons: List[str] = Field(default_factory=list)
    rejection_codes: List[RejectionCode] = Field(default_factory=list)
    fraud_signals: List[FraudSignal] = Field(default_factory=list)
    halt_code: Optional[HaltCode] = None
    halt_message: Optional[str] = None
    financial_breakdown: Optional[FinancialBreakdown] = None
    trace: ClaimTrace
    narrative: Optional[str] = None
    decided_at: datetime
    requires_manual_review: bool = False
