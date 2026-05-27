from decimal import Decimal
import pytest
from app.agents.decision_engine import _compute_financial_breakdown
from app.agents.policy_evaluation import PolicyEvaluation
from app.models.extraction import LineItem
from app.models.submission import ClaimSubmission, DocumentSubmission
from app.models.enums import ClaimCategory, DocumentType


def make_sub(amount, category="CONSULTATION"):
    return ClaimSubmission(
        member_id="EMP001", policy_id="PLUM_GHI_2024",
        claim_category=ClaimCategory(category),
        treatment_date="2024-11-01",
        claimed_amount=str(amount),
        documents=[DocumentSubmission(file_id="F1", actual_type=DocumentType.PRESCRIPTION)],
    )


def base_eval(**kwargs):
    defaults = dict(
        sub_limit_value=Decimal("50000"),
        copay_percent=Decimal("0"),
        network_discount_percent=Decimal("0"),
        is_network_hospital=False,
        excluded_line_items=[],
        eligible_line_items=[],
    )
    defaults.update(kwargs)
    return PolicyEvaluation(**defaults)


def test_tc004_consultation_copay():
    sub = make_sub(1500)
    ev = base_eval(copay_percent=Decimal("10"), sub_limit_value=Decimal("2000"))
    fb = _compute_financial_breakdown(sub, ev)
    assert fb.copay_applied == Decimal("150.00")
    assert fb.final_approved_amount == Decimal("1350.00")


def test_tc010_network_discount_before_copay():
    # sub_limit is annual OPD tracking only, not a per-claim hard cap.
    # Verify: discount applied BEFORE copay, final = 3240 (not capped to sub_limit).
    sub = make_sub(4500)
    ev = base_eval(
        copay_percent=Decimal("10"),
        network_discount_percent=Decimal("20"),
        is_network_hospital=True,
        sub_limit_value=Decimal("2000"),
    )
    fb = _compute_financial_breakdown(sub, ev)
    assert fb.network_discount_applied == Decimal("900.00")
    assert fb.amount_after_discount == Decimal("3600.00")
    assert fb.copay_applied == Decimal("360.00")
    assert fb.sub_limit_cap_applied == Decimal("0")   # not a hard per-claim cap
    assert fb.final_approved_amount == Decimal("3240.00")


def test_tc006_dental_exclusion():
    sub = make_sub(12000, "DENTAL")
    excluded = [LineItem(description="Teeth Whitening", amount=Decimal("4000"), is_excluded=True, exclusion_reason="Excluded")]
    eligible = [LineItem(description="Root Canal Treatment", amount=Decimal("8000"))]
    ev = base_eval(
        copay_percent=Decimal("0"),
        sub_limit_value=Decimal("10000"),
        excluded_line_items=excluded,
        eligible_line_items=eligible,
    )
    fb = _compute_financial_breakdown(sub, ev)
    assert fb.excluded_line_items_total == Decimal("4000.00")
    assert fb.final_approved_amount == Decimal("8000.00")


def test_sublimit_not_a_per_claim_hard_cap():
    # sub_limit is annual OPD tracking; the per-claim cap is coverage.per_claim_limit.
    sub = make_sub(5000)
    ev = base_eval(copay_percent=Decimal("0"), sub_limit_value=Decimal("2000"))
    fb = _compute_financial_breakdown(sub, ev)
    assert fb.sub_limit_cap_applied == Decimal("0")
    assert fb.final_approved_amount == Decimal("5000.00")  # full amount, no sub-limit cap


def test_zero_copay():
    sub = make_sub(3000)
    ev = base_eval(copay_percent=Decimal("0"), sub_limit_value=Decimal("10000"))
    fb = _compute_financial_breakdown(sub, ev)
    assert fb.copay_applied == Decimal("0.00")
    assert fb.final_approved_amount == Decimal("3000.00")


def test_branded_drug_no_network():
    sub = make_sub(2000, "PHARMACY")
    ev = base_eval(copay_percent=Decimal("30"), sub_limit_value=Decimal("15000"))
    fb = _compute_financial_breakdown(sub, ev)
    assert fb.copay_applied == Decimal("600.00")
    assert fb.final_approved_amount == Decimal("1400.00")


def test_network_no_copay():
    sub = make_sub(3000)
    ev = base_eval(
        copay_percent=Decimal("0"),
        network_discount_percent=Decimal("20"),
        is_network_hospital=True,
        sub_limit_value=Decimal("10000"),
    )
    fb = _compute_financial_breakdown(sub, ev)
    assert fb.network_discount_applied == Decimal("600.00")
    assert fb.final_approved_amount == Decimal("2400.00")
