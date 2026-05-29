import pytest
from pydantic import ValidationError

from app.services.document_draft_validator import (
    extract_json_object,
    format_document_draft_for_user,
    is_document_generation_request,
    process_document_response,
    validate_document_draft_payload,
)


def test_is_document_generation_request_detects_keywords():
    assert is_document_generation_request("Составь претензию по договору")
    assert not is_document_generation_request("Какая статья ГК РФ про неустойку?")


def test_extract_json_object_from_fenced_block():
  payload = extract_json_object(
      '```json\n{"заголовок": "Иск", "текст": "Текст документа достаточной длины.", "реквизиты": {"вид_документа": "иск", "суд": "АС г. Москвы", "дата": "2026-05-12"}}\n```'
  )
  assert payload is not None
  assert payload["заголовок"] == "Иск"


def test_validate_document_draft_payload_requires_legal_requisites():
    with pytest.raises(ValidationError):
        validate_document_draft_payload(
            {
                "заголовок": "Претензия",
                "текст": "Текст претензии с описанием нарушения и требований.",
                "реквизиты": {"вид_документа": "претензия"},
            }
        )


def test_process_document_response_formats_valid_json():
    response = process_document_response(
        "Составь исковое заявление",
        (
            '{"заголовок": "Исковое заявление", '
            '"текст": "Истец просит взыскать задолженность по договору поставки.", '
            '"реквизиты": {"вид_документа": "иск", "суд": "АС г. Москвы", "дата": "2026-05-12"}}'
        ),
    )
    assert "Исковое заявление" in response
    assert "Реквизиты:" in response
    assert "Суд: АС г. Москвы" in response


def test_process_document_response_rejects_invalid_json_for_document_request():
    response = process_document_response("Подготовь договор аренды", "Просто текст без JSON")
    assert "Не удалось оформить документ" in response


def test_format_document_draft_for_user_lists_attachments():
    draft = validate_document_draft_payload(
        {
            "заголовок": "Ходатайство",
            "текст": "Прошу отложить судебное заседание по уважительной причине.",
            "реквизиты": {
                "вид_документа": "ходатайство",
                "суд": "Мосгорсуд",
                "дата": "2026-05-12",
                "приложения": ["Справка", "Копия паспорта"],
            },
        }
    )
    rendered = format_document_draft_for_user(draft)
    assert "Справка" in rendered
    assert "Копия паспорта" in rendered
