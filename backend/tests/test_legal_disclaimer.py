from app.core.legal_disclaimer import LEGAL_DISCLAIMER, with_legal_disclaimer


def test_notice_is_not_appended_to_every_answer():
    assert with_legal_disclaimer("Ответ ассистента.") == "Ответ ассистента."
    assert with_legal_disclaimer("") == ""


def test_legacy_notice_is_removed_without_changing_facts():
    assert with_legal_disclaimer(f"ТК РФ, статья 140.\n\n{LEGAL_DISCLAIMER}") == "ТК РФ, статья 140."


def test_legacy_confidence_is_removed_and_recommendation_preserved():
    result = with_legal_disclaimer("В день увольнения. confidence: high\n[РЕКОМЕНДАЦИЯ] Проверьте расчёт.")
    assert "Уверенность" not in result
    assert "**Рекомендация:** Проверьте расчёт." in result
    assert "В день увольнения." in result
    assert "confidence" not in result
