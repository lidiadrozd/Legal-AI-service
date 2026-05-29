from datetime import datetime, timedelta, timezone

from app.models.law_changes import LawChange
from app.services.law_change_publication import assess_law_change_publishability


def _change(**kwargs) -> LawChange:
    defaults = {
        "document_id": 1,
        "change_title": "Изменения в ГК РФ",
        "change_date": datetime.now(timezone.utc) - timedelta(days=1),
        "description": "Описание изменения достаточной длины для публикации.",
        "source_url": "https://pravo.gov.ru/example",
    }
    defaults.update(kwargs)
    return LawChange(**defaults)


def test_publishable_change_passes_validation():
    ok, reason = assess_law_change_publishability(_change())
    assert ok is True
    assert reason == ""


def test_change_without_description_is_not_publishable():
    ok, reason = assess_law_change_publishability(_change(description="", new_version=""))
    assert ok is False
    assert "описания" in reason


def test_future_change_is_not_publishable():
    ok, reason = assess_law_change_publishability(
        _change(change_date=datetime.now(timezone.utc) + timedelta(days=3))
    )
    assert ok is False
    assert "будущем" in reason
