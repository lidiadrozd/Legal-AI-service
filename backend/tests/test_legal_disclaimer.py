from app.core.legal_disclaimer import LEGAL_DISCLAIMER, with_legal_disclaimer


def test_with_legal_disclaimer_appends_once():
    rendered = with_legal_disclaimer("Ответ ассистента.")
    assert rendered.endswith(LEGAL_DISCLAIMER)
    assert rendered.count(LEGAL_DISCLAIMER) == 1


def test_with_legal_disclaimer_keeps_existing_disclaimer():
    text = f"Ответ.\n\n{LEGAL_DISCLAIMER}"
    assert with_legal_disclaimer(text) == text
