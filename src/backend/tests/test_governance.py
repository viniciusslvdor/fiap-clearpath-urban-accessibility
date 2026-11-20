from clearpath.governance import anonymize, pseudonym, reduce_coordinate_precision


def test_masks_cpf_phone_email():
    r = anonymize("my cpf is 123.456.789-09, phone (11) 98765-4321 and email ana.lima@example.com")
    assert "123.456" not in r.text and "98765" not in r.text and "@" not in r.text
    assert r.found == {"EMAIL": 1, "CPF": 1, "PHONE": 1}


def test_unformatted_cpf_is_not_taken_as_phone():
    r = anonymize("cpf 12345678909")
    assert r.text == "cpf [CPF]"


def test_masks_plate_and_name():
    r = anonymize("My name is Carla Souza and the car ABC1D23 parked on the ramp")
    assert "Carla" not in r.text and "ABC1D23" not in r.text
    assert r.found["NAME"] == 1 and r.found["PLATE"] == 1


def test_no_false_positive_on_ordinary_text():
    text = "I am a wheelchair user and the sidewalk on Rua Augusta number 1500 has been broken for 3 months"
    r = anonymize(text)
    assert r.text == text
    assert not r.had_personal_data


def test_pseudonym_is_deterministic_and_irreversible():
    a, b = pseudonym("Text X"), pseudonym("  text x ")
    assert a == b and len(a) == 16 and "text" not in a


def test_reduces_coordinate_precision():
    assert reduce_coordinate_precision(-23.561234567, -46.655987654) == (-23.5612, -46.656)
    assert reduce_coordinate_precision(None, None) == (None, None)
