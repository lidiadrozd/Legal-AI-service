import pytest
from app.services.article_change_detection import build_article_snapshot, compare_article_snapshots, snapshot_change

KEY = "ru:197-fz:2001-12-30"
URL = "https://www.consultant.ru/document/cons_doc_LAW_34683/"

def page(text="Срок десять дней.", revision="01.10.2026", extra=""):
    return '<div class="document-page__content"><p>Трудовой кодекс Российской Федерации от 30.12.2001 N 197-ФЗ (ред. от '+revision+')</p><p>Статья 80. Увольнение</p><p>'+text+'</p>'+extra+'</div>'

def snapshot(**kwargs):
    return build_article_snapshot(page(**kwargs), URL, KEY)

def test_first_read_is_baseline_not_change():
    assert compare_article_snapshots(None, snapshot()) == ("baseline_created", [])

def test_whitespace_does_not_change_article():
    assert compare_article_snapshots(snapshot(), snapshot(text="Срок   десять\n дней.")) == ("unchanged", [])

def test_changed_article_has_both_hashes_and_exact_law():
    status, evidence = compare_article_snapshots(snapshot(), snapshot(text="Срок двадцать дней."))
    assert status == "confirmed" and len(evidence) == 1
    assert evidence[0]["article"] == "80" and evidence[0]["document_key"] == KEY
    assert evidence[0]["old_sha256"] != evidence[0]["new_sha256"]
    change = snapshot_change(snapshot(text="Срок двадцать дней."), evidence)
    assert change.affected_norms[0].article == "80"

def test_added_decimal_article():
    status, evidence = compare_article_snapshots(snapshot(), snapshot(extra='<p>Статья 80.1. Новый порядок</p><p>Норма.</p>'))
    assert status == "confirmed" and evidence[0]["article"] == "80.1"
    assert evidence[0]["operation"] == "added"

def test_missing_article_is_not_automatically_repealed():
    old = snapshot(extra='<p>Статья 81. Основания</p><p>Норма.</p>')
    assert compare_article_snapshots(old, snapshot()) == ("incomplete_or_removed_articles", [])

def test_older_edition_does_not_roll_back_baseline():
    assert compare_article_snapshots(snapshot(), snapshot(revision="01.09.2026")) == ("older_edition_ignored", [])

@pytest.mark.parametrize("content,reason", [
    ('<div class="document-page__content"><p>Ошибка доступа</p></div>', "document_identity_unconfirmed"),
    (page().replace('Статья 80.', 'Раздел 80.'), "article_structure_unrecognized"),
    (page()[:-6], "incomplete_document"),
    (page(extra='<p>Статья 80. Повтор</p>'), "duplicate_article_headings"),
])
def test_invalid_page_cannot_replace_baseline(content, reason):
    with pytest.raises(ValueError, match=reason):
        build_article_snapshot(content, URL, KEY)

def test_same_article_number_in_other_law_does_not_match():
    other = snapshot()
    other["document_key"] = "ru:51-fz:1994-11-30"
    with pytest.raises(ValueError, match="different_document"):
        compare_article_snapshots(snapshot(), other)


def test_replayed_snapshot_has_stable_change_identity_and_source_texts():
    previous, current = snapshot(), snapshot(text="Другой срок.")
    _, evidence = compare_article_snapshots(previous, current)
    first = snapshot_change(current, evidence)
    current["captured_at"] = "2026-10-12T12:00:00+00:00"
    replay = snapshot_change(current, evidence)
    assert (first.title, first.change_date, first.source_url) == (replay.title, replay.change_date, replay.source_url)
    assert "Срок десять дней." in first.old_version and "Другой срок." in first.new_version
