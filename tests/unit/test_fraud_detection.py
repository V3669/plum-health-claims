from datetime import date
from decimal import Decimal
import pytest
from app.agents.fraud_detection import FraudDetectionAgent
from app.models.enums import ClaimCategory, DocumentType, FraudSignal
from app.models.submission import ClaimSubmission, DocumentSubmission, HistoricalClaim
from app.policy_loader import load_policy


@pytest.fixture
def policy():
    return load_policy()


def make_sub(amount, history=None):
    docs = [DocumentSubmission(file_id="F1", actual_type=DocumentType.PRESCRIPTION)]
    return ClaimSubmission(
        member_id="EMP008",
        policy_id="PLUM_GHI_2024",
        claim_category=ClaimCategory.CONSULTATION,
        treatment_date=date(2024, 10, 30),
        claimed_amount=str(amount),
        claims_history=history or [],
        documents=docs,
    )


def test_tc009_same_day_fraud(policy):
    history = [
        HistoricalClaim(claim_id="C1", date=date(2024, 10, 30), amount=Decimal("1200")),
        HistoricalClaim(claim_id="C2", date=date(2024, 10, 30), amount=Decimal("1800")),
        HistoricalClaim(claim_id="C3", date=date(2024, 10, 30), amount=Decimal("2100")),
    ]
    sub = make_sub(4800, history)
    agent = FraudDetectionAgent()
    result = agent.execute(sub, policy)
    assert FraudSignal.SAME_DAY_LIMIT in result.signals
    assert result.route_to_manual_review


def test_no_fraud_signals(policy):
    sub = make_sub(1000)
    agent = FraudDetectionAgent()
    result = agent.execute(sub, policy)
    assert not result.route_to_manual_review
    assert result.score == 0.0


def test_high_value_signal(policy):
    sub = make_sub(30000)
    agent = FraudDetectionAgent()
    result = agent.execute(sub, policy)
    assert FraudSignal.HIGH_VALUE in result.signals
    assert result.route_to_manual_review


def test_fraud_never_rejects(policy):
    history = [HistoricalClaim(claim_id=f"C{i}", date=date(2024, 10, 30), amount=Decimal("1000")) for i in range(5)]
    sub = make_sub(30000, history)
    agent = FraudDetectionAgent()
    result = agent.execute(sub, policy)
    assert result.route_to_manual_review
