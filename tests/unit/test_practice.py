from app.services.practice import prompt_parts


def test_prompt_parts_maps_casefold_expansion_back_to_nfc_source():
    before, after = prompt_parts("ß cible", "cible")

    assert before == "ß "
    assert after == ""
