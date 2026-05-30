from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from typing import List

from app.agents.fraud_detection import FraudResult
from app.agents.policy_evaluation import PolicyEvaluation
from app.models.decision import ClaimDecision, FinancialBreakdown
from app.models.enums import Decision, FraudSignal, RejectionCode, StageStatus
from app.models.submission import ClaimSubmission
from app.models.trace import ClaimTrace
from app.utils.money import quantize


class DecisionEngine:
    name = "DecisionEngine"

    def execute(
        self,
        submission: ClaimSubmission,
        evaluation: PolicyEvaluation,
        fraud: FraudResult,
        trace: ClaimTrace,
    ) -> ClaimDecision:
        final_confidence = compute_final_confidence(trace)

        reasons: List[str] = []
        rejection_codes: List[RejectionCode] = []

        if not evaluation.member_active:
            reasons.append("Policy is inactive. Please contact HR to renew the policy.")
            rejection_codes.append(RejectionCode.INACTIVE_POLICY)
            return self._make_decision(
                submission, Decision.REJECTED, Decimal("0"), final_confidence,
                reasons, rejection_codes, [], trace
            )

        if evaluation.deadline_exceeded:
            reasons.append(
                f"Claim submission deadline has passed. Claims must be submitted within "
                f"{evaluation.deadline_days} days of treatment."
            )
            rejection_codes.append(RejectionCode.DEADLINE_EXCEEDED)
            return self._make_decision(
                submission, Decision.REJECTED, Decimal("0"), final_confidence,
                reasons, rejection_codes, [], trace
            )

        if evaluation.below_minimum:
            reasons.append(
                f"Claimed amount ₹{submission.claimed_amount} is below the minimum "
                f"claim amount."
            )
            rejection_codes.append(RejectionCode.BELOW_MIN_AMOUNT)
            return self._make_decision(
                submission, Decision.REJECTED, Decimal("0"), final_confidence,
                reasons, rejection_codes, [], trace
            )

        if evaluation.diagnosis_excluded:
            reasons.append(
                f"The diagnosis/treatment is excluded under your policy: "
                f"{evaluation.excluded_reason}."
            )
            rejection_codes.append(RejectionCode.EXCLUDED_CONDITION)
            conf = max(final_confidence, 0.90)
            return self._make_decision(
                submission, Decision.REJECTED, Decimal("0"), conf,
                reasons, rejection_codes, [], trace
            )

        if evaluation.pre_auth_required and not evaluation.pre_auth_provided:
            threshold_clause = (
                f" (amount exceeds ₹{evaluation.pre_auth_threshold_value:,.0f})"
                if evaluation.pre_auth_threshold_value is not None
                else ""
            )
            reasons.append(
                f"Pre-authorization is required for this diagnostic test{threshold_clause} "
                "but was not obtained. Please get pre-authorization from your insurer before "
                "undergoing the procedure, then resubmit the claim with the pre-authorization "
                "reference number."
            )
            rejection_codes.append(RejectionCode.PRE_AUTH_MISSING)
            return self._make_decision(
                submission, Decision.REJECTED, Decimal("0"), final_confidence,
                reasons, rejection_codes, [], trace
            )

        if not evaluation.specific_waiting_period_passed:
            elig = evaluation.eligible_from_date.isoformat() if evaluation.eligible_from_date else "unknown"
            reasons.append(
                f"Your claim for {evaluation.matched_specific_condition} treatment is within the "
                f"waiting period. You will be eligible for this condition from {elig}."
            )
            rejection_codes.append(RejectionCode.WAITING_PERIOD)
            return self._make_decision(
                submission, Decision.REJECTED, Decimal("0"), final_confidence,
                reasons, rejection_codes, [], trace
            )

        if not evaluation.initial_waiting_period_passed:
            reasons.append(
                f"Your claim is within the initial {evaluation.initial_waiting_period_days}-day "
                "waiting period from your policy join date."
            )
            rejection_codes.append(RejectionCode.WAITING_PERIOD)
            return self._make_decision(
                submission, Decision.REJECTED, Decimal("0"), final_confidence,
                reasons, rejection_codes, [], trace
            )

        if evaluation.per_claim_limit_exceeded:
            reasons.append(
                f"Claimed amount ₹{submission.claimed_amount} exceeds the per-claim limit of "
                f"₹{evaluation.per_claim_limit_value}. Claims above this limit are not eligible."
            )
            rejection_codes.append(RejectionCode.PER_CLAIM_EXCEEDED)
            return self._make_decision(
                submission, Decision.REJECTED, Decimal("0"), final_confidence,
                reasons, rejection_codes, [], trace
            )

        if fraud.route_to_manual_review:
            signal_labels = [s.value for s in fraud.signals]
            reasons.append(
                f"This claim has been flagged for manual review due to: {', '.join(signal_labels)}. "
                "Our team will review it and get back to you."
            )
            decision = self._make_decision(
                submission, Decision.MANUAL_REVIEW, Decimal("0"), final_confidence,
                reasons, [], fraud.signals, trace
            )
            decision.requires_manual_review = True
            return decision

        if final_confidence < 0.60:
            reasons.append("System confidence is too low to auto-decide. Manual review required.")
            decision = self._make_decision(
                submission, Decision.MANUAL_REVIEW, Decimal("0"), final_confidence,
                reasons, [], [], trace
            )
            decision.requires_manual_review = True
            return decision

        # All items excluded → reject, not silent ₹0 approval
        if evaluation.excluded_line_items and not evaluation.eligible_line_items:
            excluded_desc = "; ".join(
                f"{item.description} (₹{item.amount}): {item.exclusion_reason}"
                for item in evaluation.excluded_line_items
            )
            reasons.append(
                f"All line items in this claim are excluded under your policy: {excluded_desc}."
            )
            rejection_codes.append(RejectionCode.EXCLUDED_LINE_ITEM)
            return self._make_decision(
                submission, Decision.REJECTED, Decimal("0"), final_confidence,
                reasons, rejection_codes, [], trace
            )

        fb = _compute_financial_breakdown(submission, evaluation)

        if evaluation.excluded_line_items and evaluation.eligible_line_items:
            excluded_desc = "; ".join(
                f"{item.description} (₹{item.amount}): {item.exclusion_reason}"
                for item in evaluation.excluded_line_items
            )
            reasons.append(f"Partial approval: excluded line items — {excluded_desc}.")
            decision_type = Decision.PARTIAL
        else:
            reasons.append("All eligible items approved.")
            decision_type = Decision.APPROVED

        decision = self._make_decision(
            submission, decision_type, fb.final_approved_amount, final_confidence,
            reasons, rejection_codes, [], trace, fb
        )
        if trace.degraded_stages > 0 or final_confidence < 0.75:
            decision.requires_manual_review = True
        return decision

    def _make_decision(
        self,
        submission: ClaimSubmission,
        decision: Decision,
        approved_amount: Decimal,
        confidence: float,
        reasons: List[str],
        rejection_codes: List[RejectionCode],
        fraud_signals: List[FraudSignal],
        trace: ClaimTrace,
        financial_breakdown=None,
    ) -> ClaimDecision:
        return ClaimDecision(
            claim_id=trace.claim_id,
            decision=decision,
            approved_amount=approved_amount,
            confidence_score=round(confidence, 4),
            reasons=reasons,
            rejection_codes=rejection_codes,
            fraud_signals=fraud_signals,
            financial_breakdown=financial_breakdown,
            trace=trace,
            decided_at=datetime.now(timezone.utc),
        )


def _compute_financial_breakdown(
    submission: ClaimSubmission,
    ev: PolicyEvaluation,
) -> FinancialBreakdown:
    fb = FinancialBreakdown(claimed_amount=submission.claimed_amount)

    if ev.excluded_line_items:
        fb.excluded_line_items_total = quantize(
            sum((item.amount for item in ev.excluded_line_items), Decimal("0"))
        )
        # Provide Decimal("0") start so sum() returns Decimal even when the
        # eligible list is empty (plain sum() would return int 0, which breaks
        # the subsequent quantize() call).
        base = sum((item.amount for item in ev.eligible_line_items), Decimal("0"))
    else:
        base = submission.claimed_amount

    if ev.is_network_hospital and ev.network_discount_percent > 0:
        discount = quantize(base * ev.network_discount_percent / Decimal("100"))
        fb.network_discount_applied = discount
        fb.amount_after_discount = quantize(base - discount)
    else:
        fb.amount_after_discount = quantize(base)

    copay = quantize(fb.amount_after_discount * ev.copay_percent / Decimal("100"))
    fb.copay_applied = copay
    fb.amount_after_copay = quantize(fb.amount_after_discount - copay)

    # sub_limit_value is stored for annual OPD tracking / reporting purposes.
    # It is NOT applied as a per-claim hard cap here; the per-claim hard cap is
    # coverage.per_claim_limit, enforced by the DecisionEngine before this point.
    fb.sub_limit_cap_applied = Decimal("0")
    fb.final_approved_amount = quantize(fb.amount_after_copay)

    return fb


def compute_final_confidence(trace: ClaimTrace) -> float:
    successful = [
        e.confidence for e in trace.events
        if e.status == StageStatus.PASS
    ]
    if not successful:
        return 0.5
    base = min(successful)
    penalty = 0.7 ** trace.degraded_stages
    return round(base * penalty, 4)
