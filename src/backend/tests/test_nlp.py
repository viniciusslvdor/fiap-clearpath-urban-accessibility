import pytest

from clearpath import nlp


def test_normalize_removes_accents_markers_and_digits():
    assert nlp.normalize("Sidewalk on Rua da Consolação BROKEN at no. 123! [CPF]") == \
        "sidewalk on rua da consolacao broken at no"


def test_tokenize_removes_stopwords():
    assert nlp.tokenize("the ramp at the corner is broken") == ["ramp", "corner", "broken"]


@pytest.mark.parametrize("text,expected", [
    ("there is a huge hole in the sidewalk on my street", "damaged_sidewalk"),
    ("car parked on top of the sidewalk every day", "sidewalk_obstruction"),
    ("the corner has no ramp for wheelchairs", "ramp_access"),
    ("the tactile paving ends at a pole", "tactile_paving"),
    ("pedestrian traffic light without an audible signal", "crossing_signal"),
    ("the metro station elevator is broken", "accessible_transit"),
])
def test_classifies_clear_reports(text, expected):
    c = nlp.classify(text)
    assert c.category == expected
    assert 0 <= c.confidence <= 1


def test_meaningless_text_goes_to_human_review():
    c = nlp.classify("blablabla xyz qwerty")
    assert c.human_review


def test_urgency_rises_with_risk_signals():
    base, _ = nlp.score_urgency("broken sidewalk", "damaged_sidewalk")
    high, reasons = nlp.score_urgency("broken sidewalk, my elderly mother fell near the hospital", "damaged_sidewalk")
    assert high > base
    assert "fall or accident reported" in reasons and "near an essential service" in reasons


@pytest.mark.parametrize("text,expected", [
    ("hole on Rua Augusta, 1500 near the metro", "Rua Augusta, 1500"),
    ("broken ramp on Av. Paulista in front of the bank", "Av. Paulista"),
    ("cracked sidewalk at 220 Oak Street near the school", "Oak Street, 220"),
    ("I had to walk into the street among the cars", None),
])
def test_extract_address(text, expected):
    assert nlp.extract_address(text) == expected
