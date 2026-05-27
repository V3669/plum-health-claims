"""Integration tests — runs all 12 test cases through process_claim."""
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.enums import ClaimCategory, Decision, DocumentQuality, DocumentType
from app.models.submission import ClaimSubmission, DocumentSubmission, HistoricalClaim
from app.orchestrator import Orchestrator


@pytest.fixture(scope="module")
def orchestrator():
    # All test-case treatment dates are in Oct–Nov 2024.
    # Use a reference_date 10 days after the latest treatment so deadline checks pass.
    return Orchestrator(reference_date=date(2024, 11, 12))


def _load_tc():
    path = Path(__file__).parent.parent.parent / "test_cases.json"
    return {tc["case_id"]: tc for tc in json.loads(path.read_text())["test_cases"]}


TC = _load_tc()


def _build_submission(inp: dict) -> ClaimSubmission:
    docs = []
    for d in inp.get("documents", []):
        quality_str = d.get("quality", "GOOD")
        docs.append(DocumentSubmission(
            file_id=d["file_id"],
            file_name=d.get("file_name"),
            actual_type=DocumentType(d["actual_type"]),
            quality=DocumentQuality(quality_str),
            content=d.get("content"),
            patient_name_on_doc=d.get("patient_name_on_doc"),
        ))
    history = [
        HistoricalClaim(
            claim_id=h["claim_id"],
            date=date.fromisoformat(h["date"]),
            amount=Decimal(str(h["amount"])),
            provider=h.get("provider"),
        )
        for h in inp.get("claims_history", [])
    ]
    return ClaimSubmission(
        member_id=inp["member_id"],
        policy_id=inp["policy_id"],
        claim_category=ClaimCategory(inp["claim_category"]),
        treatment_date=date.fromisoformat(inp["treatment_date"]),
        claimed_amount=Decimal(str(inp["claimed_amount"])),
        hospital_name=inp.get("hospital_name"),
        ytd_claims_amount=Decimal(str(inp.get("ytd_claims_amount", 0))),
        claims_history=history,
        pre_authorization_ref=inp.get("pre_authorization_ref"),
        simulate_component_failure=inp.get("simulate_component_failure", False),
        documents=docs,
    )


@pytest.mark.asyncio
async def test_tc001_wrong_document(orchestrator):
    sub = _build_submission(TC["TC001"]["input"])
    decision = await orchestrator.process_claim(sub)
    assert decision.decision == Decision.HALTED
    assert decision.halt_code is not None
    assert decision.halt_message is not None
    assert "hospital bill" in decision.halt_message.lower()


@pytest.mark.asyncio
async def test_tc002_unreadable_document(orchestrator):
    sub = _build_submission(TC["TC002"]["input"])
    decision = await orchestrator.process_claim(sub)
    assert decision.decision == Decision.HALTED
    assert "blurry_bill" in (decision.halt_message or "").lower() or decision.halt_code is not None
    assert decision.decision != Decision.REJECTED


@pytest.mark.asyncio
async def test_tc003_patient_name_mismatch(orchestrator):
    sub = _build_submission(TC["TC003"]["input"])
    decision = await orchestrator.process_claim(sub)
    assert decision.decision == Decision.HALTED
    assert "Rajesh Kumar" in (decision.halt_message or "") or "Arjun Mehta" in (decision.halt_message or "")


@pytest.mark.asyncio
async def test_tc004_clean_consultation(orchestrator):
    sub = _build_submission(TC["TC004"]["input"])
    decision = await orchestrator.process_claim(sub)
    assert decision.decision == Decision.APPROVED
    assert decision.approved_amount == Decimal("1350.00")
    assert decision.confidence_score > 0.85


@pytest.mark.asyncio
async def test_tc005_waiting_period_diabetes(orchestrator):
    sub = _build_submission(TC["TC005"]["input"])
    decision = await orchestrator.process_claim(sub)
    assert decision.decision == Decision.REJECTED
    assert any("WAITING_PERIOD" in c.value for c in decision.rejection_codes)
    assert any("eligible" in r.lower() or "2024" in r for r in decision.reasons)


@pytest.mark.asyncio
async def test_tc006_dental_partial(orchestrator):
    sub = _build_submission(TC["TC006"]["input"])
    decision = await orchestrator.process_claim(sub)
    assert decision.decision == Decision.PARTIAL
    assert decision.approved_amount == Decimal("8000.00")
    assert decision.financial_breakdown is not None
    assert decision.financial_breakdown.excluded_line_items_total == Decimal("4000.00")


@pytest.mark.asyncio
async def test_tc007_mri_no_preauth(orchestrator):
    sub = _build_submission(TC["TC007"]["input"])
    decision = await orchestrator.process_claim(sub)
    assert decision.decision == Decision.REJECTED
    assert any("PRE_AUTH_MISSING" in c.value for c in decision.rejection_codes)
    assert any("pre-auth" in r.lower() or "resubmit" in r.lower() for r in decision.reasons)


@pytest.mark.asyncio
async def test_tc008_per_claim_limit(orchestrator):
    sub = _build_submission(TC["TC008"]["input"])
    decision = await orchestrator.process_claim(sub)
    assert decision.decision == Decision.REJECTED
    assert any("PER_CLAIM_EXCEEDED" in c.value for c in decision.rejection_codes)
    assert any("5000" in r or "7500" in r for r in decision.reasons)


@pytest.mark.asyncio
async def test_tc009_fraud_manual_review(orchestrator):
    sub = _build_submission(TC["TC009"]["input"])
    decision = await orchestrator.process_claim(sub)
    assert decision.decision == Decision.MANUAL_REVIEW
    assert len(decision.fraud_signals) > 0


@pytest.mark.asyncio
async def test_tc010_network_hospital_discount(orchestrator):
    sub = _build_submission(TC["TC010"]["input"])
    decision = await orchestrator.process_claim(sub)
    assert decision.decision == Decision.APPROVED
    assert decision.approved_amount == Decimal("3240.00")
    assert decision.financial_breakdown is not None
    assert decision.financial_breakdown.network_discount_applied > 0
    assert decision.financial_breakdown.copay_applied > 0


@pytest.mark.asyncio
async def test_tc011_component_failure(orchestrator):
    sub = _build_submission(TC["TC011"]["input"])
    decision = await orchestrator.process_claim(sub)
    assert decision.decision != Decision.HALTED
    degraded = any(e.status.value == "DEGRADED" for e in decision.trace.events)
    assert degraded
    assert decision.confidence_score < 1.0
    assert decision.requires_manual_review


@pytest.mark.asyncio
async def test_tc012_excluded_treatment(orchestrator):
    sub = _build_submission(TC["TC012"]["input"])
    decision = await orchestrator.process_claim(sub)
    assert decision.decision == Decision.REJECTED
    assert any("EXCLUDED_CONDITION" in c.value for c in decision.rejection_codes)
    assert decision.confidence_score >= 0.90
