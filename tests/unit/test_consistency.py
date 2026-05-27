from app.agents.consistency import ConsistencyAgent
from app.models.enums import DocumentType
from app.models.extraction import ExtractedDocument


def make_doc(file_id, name):
    return ExtractedDocument(
        file_id=file_id,
        declared_type=DocumentType.PRESCRIPTION,
        patient_name=name,
    )


def test_tc003_name_mismatch():
    agent = ConsistencyAgent()
    docs = [make_doc("F1", "Rajesh Kumar"), make_doc("F2", "Arjun Mehta")]
    result = agent.execute(docs, "Rajesh Kumar")
    assert not result.passed
    assert "Rajesh Kumar" in result.message
    assert "Arjun Mehta" in result.message


def test_same_name_passes():
    agent = ConsistencyAgent()
    docs = [make_doc("F1", "Rajesh Kumar"), make_doc("F2", "Rajesh Kumar")]
    result = agent.execute(docs, "Rajesh Kumar")
    assert result.passed


def test_honorific_ignored():
    agent = ConsistencyAgent()
    docs = [make_doc("F1", "Mr. Rajesh Kumar"), make_doc("F2", "Rajesh Kumar")]
    result = agent.execute(docs, "Rajesh Kumar")
    assert result.passed


def test_no_patient_names_degraded():
    agent = ConsistencyAgent()
    docs = [ExtractedDocument(file_id="F1", declared_type=DocumentType.HOSPITAL_BILL)]
    result = agent.execute(docs, "Rajesh Kumar")
    assert result.degraded
    assert result.passed


def test_member_name_mismatch():
    agent = ConsistencyAgent()
    docs = [make_doc("F1", "Priya Singh")]
    result = agent.execute(docs, "Rajesh Kumar")
    assert not result.passed


def test_fuzzy_match_passes():
    agent = ConsistencyAgent()
    docs = [make_doc("F1", "Rajeesh Kumar")]
    result = agent.execute(docs, "Rajesh Kumar")
    assert result.passed
