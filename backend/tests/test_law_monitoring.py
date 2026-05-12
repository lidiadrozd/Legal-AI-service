from datetime import datetime
from pathlib import Path

from app.services.law_change_parser import (
    parse_consultant_category,
    parse_consultant_index,
    parse_consultant_period_categories,
    parse_json_changes,
)
from app.services.law_topic_service import change_matches_interest, extract_topics_from_text


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_parse_json_changes():
    payload = {
        "changes": [
            {
                "title": "Изменение в ЖК РФ",
                "date": "2026-05-02",
                "description": "Поправки по аренде жилья",
                "url": "https://example.com/law/1",
                "document_number": "564-ФЗ",
            }
        ]
    }
    parsed = parse_json_changes(payload, "https://example.com/changes")
    assert len(parsed) == 1
    assert parsed[0].title == "Изменение в ЖК РФ"
    assert parsed[0].document_number == "564-ФЗ"


def test_parse_consultant_category_fixture():
    html = (FIXTURES_DIR / "consultant_category_sample.html").read_text(encoding="utf-8")
    parsed = parse_consultant_category(
        html,
        "https://www.consultant.ru/document/cons_doc_LAW_33770/sample/",
        category="Федеральные законы",
    )
    assert parsed
    assert any("Жилищный кодекс" in item.title for item in parsed)


def test_parse_consultant_index_and_period_links():
    index_html = (FIXTURES_DIR / "consultant_index_sample.html").read_text(encoding="utf-8")
    period_url = parse_consultant_index(index_html, "https://www.consultant.ru/law/review/fed/updprof/")
    assert period_url is not None
    assert "cons_doc_LAW_33770" in period_url

    period_html = (FIXTURES_DIR / "consultant_period_sample.html").read_text(encoding="utf-8")
    categories = parse_consultant_period_categories(period_html, period_url)
    assert categories
    assert categories[0][0] == "Федеральные (конституционные) законы, кодексы"


def test_topic_extraction_and_matching():
    topics = extract_topics_from_text("Как оформить договор аренды квартиры и что говорит ЖК РФ?")
    assert any(topic.topic_key == "housing_rental" for topic in topics)
    assert change_matches_interest(
        "о внесении изменений в жилищный кодекс российской федерации",
        topics[0].keywords,
    )
