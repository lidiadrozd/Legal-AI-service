import pytest

from complete_form_cases import make_state
from app.services.document_drafting import canonical_editorial
from app.services.document_form_composition import prepare_form_document, form_presentation_fields
from app.services.document_form_intake import prepare_form_intake


def _filled(value):
    return {"status": "filled", "value": value, "original": value, "evidence": value}


def test_pretension_rejects_a_response_deadline_that_precedes_its_document_date():
    state = {
        "scenario": "pretense_debt_services",
        "fields": {
            "date": _filled("2026-10-31"),
            "response_term": _filled("до 30 сентября 2026 года"),
        },
    }

    prepare_form_intake(state)

    term = state["fields"]["response_term"]
    assert term["status"] == "incomplete"
    assert "истёк" in term["error"]


def test_pretension_keeps_a_future_or_relative_response_deadline():
    for value in ("до 10 ноября 2026 года", "в течение 10 календарных дней со дня получения претензии"):
        state = {
            "scenario": "pretense_debt_services",
            "fields": {"date": _filled("2026-10-31"), "response_term": _filled(value)},
        }
        prepare_form_intake(state)
        assert state["fields"]["response_term"]["status"] == "filled"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2 недели", "в течение 2 недель со дня получения настоящей претензии"),
        ("10 дней", "в течение 10 календарных дней со дня получения настоящей претензии"),
        ("1 месяц", "в течение 1 месяца со дня получения настоящей претензии"),
    ],
)
def test_relative_voluntary_deadline_is_made_unambiguous_without_inventing_a_date(raw, expected):
    assert canonical_editorial("response_term", raw, "pretense_debt_services") == expected


@pytest.mark.asyncio
async def test_relative_deadline_is_presented_formally_in_all_debt_pretenses():
    state = make_state("pretense_debt_services")
    state["fields"]["response_term"] = _filled("2 недели")

    prepared, _ = await prepare_form_document(state, None)
    presented = form_presentation_fields(prepared)

    assert presented["response_term"]["value"] == "в течение 2 недель со дня получения настоящей претензии"
