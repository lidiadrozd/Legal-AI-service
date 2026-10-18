import json
from pathlib import Path

import pytest

from app.services.curated_law_changes import load_curated_changes, CuratedSourceError, MAX_FILE_BYTES

SAMPLE = Path(__file__).resolve().parents[2] / "docs/fixtures/legal_norm_tracking"


@pytest.fixture
def feed(tmp_path):
    for name in ("article_7.txt", "legal_sources.json", "curated_changes.json"):
        (tmp_path / name).write_bytes((SAMPLE / name).read_bytes())
    return tmp_path / "curated_changes.json", tmp_path


def test_reviewed_change_retains_exact_norm_and_both_revisions(feed):
    path, root = feed
    change, = load_curated_changes(path, catalog_root=root)
    assert change.affected_norms[0].document_key == "training:service-rules"
    assert change.affected_norms[0].article == "7"
    assert change.document_number == "TRAINING-AMENDING-1"
    assert "пять дней" in change.old_version
    assert "семь дней" in change.new_version


@pytest.mark.parametrize("field,value", [
    ("reviewed", False), ("reviewed", "true"), ("title", ""), ("description", ""),
    ("url", "javascript:alert(1)"), ("url", "https://user:password@example.org/law"),
    ("date", "invalid"), ("document_number", "x" * 51),
    ("affected_norms", []), ("affected_norms", [{"document_key": "unknown", "article": "7"}]),
    ("affected_norms", [{"document_key": "training:service-rules", "article": "9"}]),
    ("affected_norms", [{"article": "7"}]), ("new_version", {}),
])
def test_invalid_entry_rejects_entire_feed(feed, field, value):
    path, root = feed
    data = json.loads(path.read_text(encoding="utf-8"))
    invalid = dict(data["changes"][0])
    invalid[field] = value
    data["changes"].append(invalid)
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CuratedSourceError) as error:
        load_curated_changes(path, catalog_root=root)
    assert "Entry 2" in str(error.value)
    assert "password" not in str(error.value)
    assert "javascript" not in str(error.value)


def test_changed_catalog_text_prevents_unverified_matching(feed):
    path, root = feed
    (root / "article_7.txt").write_text("Modified content", encoding="utf-8")
    with pytest.raises(CuratedSourceError, match="catalog is empty"):
        load_curated_changes(path, catalog_root=root)


def test_empty_feed_requires_no_catalog(tmp_path):
    path = tmp_path / "changes.json"
    path.write_text('{"changes": []}', encoding="utf-8")
    assert load_curated_changes(path, catalog_root=tmp_path) == []


@pytest.mark.parametrize("content", [b"not JSON", b"\xff", b"x" * (MAX_FILE_BYTES + 1)],
                         ids=["invalid-json", "invalid-utf8", "oversized"])
def test_unreadable_or_oversized_file_has_safe_diagnostics(tmp_path, content):
    path = tmp_path / "changes.json"
    path.write_bytes(content)
    with pytest.raises(CuratedSourceError):
        load_curated_changes(path, catalog_root=tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize("valid", [True, False])
async def test_monitor_uses_standard_local_file_without_http(feed, monkeypatch, valid):
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock
    from app.core.config import settings
    from app.services import law_change_monitor as monitor

    path, root = feed
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["changes"][0]["reviewed"] = valid
    (root / "reviewed_changes.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(settings, "RAG_DOCS_PATH", str(root))
    monkeypatch.setattr(settings, "LAW_CHANGE_CURATED_FILE", "")
    @asynccontextmanager
    async def session():
        yield object()
    monkeypatch.setattr(monitor, "AsyncSessionLocal", session)
    persist = AsyncMock(return_value=[])
    fetch = AsyncMock(side_effect=AssertionError("Explicit empty source list must disable HTTP"))
    monkeypatch.setattr(monitor, "persist_parsed_changes", persist)
    monkeypatch.setattr(monitor, "_fetch_text", fetch)
    assert await monitor.monitor_sources(source_urls=[]) == []
    fetch.assert_not_called()
    if valid:
        persist.assert_awaited_once()
        change, = persist.call_args.args[1]
        assert change.affected_norms[0].article == "7"
    else:
        persist.assert_not_called()
