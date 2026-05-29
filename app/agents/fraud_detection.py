from datetime import timedelta
from typing import Any, Dict, List

from pydantic import BaseModel

from app.models.enums import FraudSignal
from app.models.policy import PolicyConfig
from app.models.submission import ClaimSubmission


class FraudResult(BaseModel):
    signals: List[FraudSignal]
    score: float
    route_to_manual_review: bool
    details: Dict[str, Any]


class FraudDetectionAgent:
    name = "FraudDetection"

    WEIGHTS = {
        FraudSignal.SAME_DAY_LIMIT: 0.5,
        FraudSignal.MONTHLY_LIMIT: 0.3,
        FraudSignal.HIGH_VALUE: 0.25,
    }

    def execute(self, submission: ClaimSubmission, policy: PolicyConfig) -> FraudResult:
        thresholds = policy.fraud_thresholds
        treatment_date = submission.treatment_date

        same_day_count = sum(
            1 for h in submission.claims_history
            if h.date == treatment_date
        ) + 1

        cutoff = treatment_date - timedelta(days=30)
        monthly_count = sum(
            1 for h in submission.claims_history
            if cutoff <= h.date <= treatment_date
        ) + 1

        signals: List[FraudSignal] = []
        details: Dict[str, Any] = {
            "same_day_count": same_day_count,
            "same_day_limit": thresholds.same_day_claims_limit,
            "monthly_count": monthly_count,
            "monthly_limit": thresholds.monthly_claims_limit,
            "claimed_amount": str(submission.claimed_amount),
            "high_value_threshold": str(thresholds.high_value_claim_threshold),
        }

        if same_day_count > thresholds.same_day_claims_limit:
            signals.append(FraudSignal.SAME_DAY_LIMIT)

        if monthly_count > thresholds.monthly_claims_limit:
            signals.append(FraudSignal.MONTHLY_LIMIT)

        if submission.claimed_amount > thresholds.high_value_claim_threshold:
            signals.append(FraudSignal.HIGH_VALUE)

        score = min(sum(self.WEIGHTS.get(s, 0.0) for s in signals), 1.0)

        if score >= thresholds.fraud_score_manual_review_threshold:
            signals.append(FraudSignal.SCORE_THRESHOLD)

        route = len(signals) > 0
        return FraudResult(signals=signals, score=score, route_to_manual_review=route, details=details)
