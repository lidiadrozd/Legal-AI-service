from app.services.document_narrator_grammar import (
    align_first_person_gender,
    align_narrator_gender,
    grammatical_gender,
)


def _filled(value):
    return {"status": "filled", "value": value}


def test_male_sender_repairs_only_first_person_past_tense_in_rendered_fields():
    source = (
        "За оценку я заплатила 7 000 рублей. "
        "Претензию в управляющую компанию направила 1 сентября 2026 года."
    )
    fields = {
        "sender": _filled("Егоров Максим Сергеевич"),
        "facts": _filled(source),
    }

    rendered = align_narrator_gender(fields)

    assert source.endswith("направила 1 сентября 2026 года.")
    assert "я заплатил 7 000 рублей" in rendered["facts"]["value"]
    assert "компанию направил 1 сентября 2026 года" in rendered["facts"]["value"]


def test_female_signer_repairs_a_masculine_first_person_form_and_never_guesses_from_a_company():
    fields = {
        "sender": _filled("ООО «Ильич»"),
        "signature": _filled("Соколова Марина Андреевна"),
        "facts": _filled("Я уже заплатил расходы на оценку."),
    }

    rendered = align_narrator_gender(fields)

    assert rendered["facts"]["value"] == "Я уже заплатила расходы на оценку."
    assert grammatical_gender("ООО «Ильич»") is None


def test_grammar_repair_leaves_an_explicit_third_party_action_untouched():
    source = "Управляющая компания направила претензию 1 сентября 2026 года."

    assert align_first_person_gender(source, "male") == source
    assert grammatical_gender("Егоров Максим Сергеевич") == "male"
    assert grammatical_gender("Соколова Марина Андреевна") == "female"
    assert grammatical_gender("Иванов Илья") is None
