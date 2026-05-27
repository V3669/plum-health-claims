from app.utils.diagnosis_map import map_diagnosis_to_condition, matches_exclusion


def test_diabetes():
    assert map_diagnosis_to_condition("Type 2 Diabetes Mellitus") == "diabetes"
    assert map_diagnosis_to_condition("T2DM") == "diabetes"


def test_hypertension():
    assert map_diagnosis_to_condition("Hypertension grade 2") == "hypertension"
    assert map_diagnosis_to_condition("High blood pressure") == "hypertension"


def test_obesity():
    assert map_diagnosis_to_condition("Morbid Obesity BMI 37") == "obesity_treatment"


def test_cataract():
    assert map_diagnosis_to_condition("Senile Cataract") == "cataract"


def test_maternity():
    assert map_diagnosis_to_condition("Pregnancy 28 weeks") == "maternity"
    assert map_diagnosis_to_condition("Antenatal care") == "maternity"


def test_mental_health():
    assert map_diagnosis_to_condition("Major Depression") == "mental_health"
    assert map_diagnosis_to_condition("Anxiety disorder") == "mental_health"


def test_hernia():
    assert map_diagnosis_to_condition("Inguinal hernia") == "hernia"


def test_no_match():
    assert map_diagnosis_to_condition("Viral Fever") is None
    assert map_diagnosis_to_condition("Gastroenteritis") is None
    assert map_diagnosis_to_condition("") is None


def test_exclusion_bariatric():
    assert matches_exclusion("Bariatric Consultation") is not None


def test_exclusion_obesity():
    assert matches_exclusion("Obesity treatment program") is not None


def test_no_exclusion():
    assert matches_exclusion("Viral Fever treatment") is None
