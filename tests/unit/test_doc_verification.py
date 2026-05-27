import pytest
from app.agents.doc_verification import DocumentVerificationAgent
from app.models.enums import ClaimCategory, DocumentType
from app.models.submission import ClaimSubmission, DocumentSubmission
from app.policy_loader import load_policy


@pytest.fixture
def policy():
    return load_policy()


def make_submission(category, doc_types):
    docs = [DocumentSubmission(file_id=f"F{i}", actual_type=DocumentType(t))
            for i, t in enumerate(doc_types)]
    return ClaimSubmission(
        member_id="EMP001",
        policy_id="PLUM_GHI_2024",
        claim_category=ClaimCategory(category),
        treatment_date="2024-11-01",
        claimed_amount="1500",
        documents=docs,
    )


def test_tc001_wrong_document(policy):
    agent = DocumentVerificationAgent()
    sub = make_submission("CONSULTATION", ["PRESCRIPTION", "PRESCRIPTION"])
    result = agent.execute(sub, policy)
    assert not result.passed
    assert "HOSPITAL_BILL" in result.missing
    assert "hospital bill" in result.message.lower()
    assert "prescription" in result.message.lower()


def test_correct_consultation_docs(policy):
    agent = DocumentVerificationAgent()
    sub = make_submission("CONSULTATION", ["PRESCRIPTION", "HOSPITAL_BILL"])
    result = agent.execute(sub, policy)
    assert result.passed
    assert result.message is None


def test_correct_pharmacy_docs(policy):
    agent = DocumentVerificationAgent()
    sub = make_submission("PHARMACY", ["PRESCRIPTION", "PHARMACY_BILL"])
    result = agent.execute(sub, policy)
    assert result.passed


def test_missing_pharmacy_bill(policy):
    agent = DocumentVerificationAgent()
    sub = make_submission("PHARMACY", ["PRESCRIPTION"])
    result = agent.execute(sub, policy)
    assert not result.passed
    assert "PHARMACY_BILL" in result.missing


def test_extra_docs_allowed(policy):
    agent = DocumentVerificationAgent()
    sub = make_submission("CONSULTATION", ["PRESCRIPTION", "HOSPITAL_BILL", "LAB_REPORT"])
    result = agent.execute(sub, policy)
    assert result.passed


def test_dental_requires_hospital_bill(policy):
    agent = DocumentVerificationAgent()
    sub = make_submission("DENTAL", ["DENTAL_REPORT"])
    result = agent.execute(sub, policy)
    assert not result.passed
    assert "HOSPITAL_BILL" in result.missing


def test_diagnostic_requires_three_docs(policy):
    agent = DocumentVerificationAgent()
    sub = make_submission("DIAGNOSTIC", ["PRESCRIPTION", "LAB_REPORT", "HOSPITAL_BILL"])
    result = agent.execute(sub, policy)
    assert result.passed


def test_message_specificity(policy):
    agent = DocumentVerificationAgent()
    sub = make_submission("CONSULTATION", ["PRESCRIPTION", "PRESCRIPTION"])
    result = agent.execute(sub, policy)
    assert result.message is not None
    assert len(result.message) > 30
    assert "resubmit" in result.message.lower()
