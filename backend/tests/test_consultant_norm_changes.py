import hashlib
import json
from pathlib import Path

import httpx
import pytest

from app.core.config import settings
from app.services.consultant_norm_changes import extract_linked_amendments, catalog_document_keys, consultant_document_id
from app.services.law_change_parser import parse_consultant_category
from app.services.law_change_monitor import collect_changes_from_source
from app.services.legal_sources import LegalSource, NormIdentity

ROOT_URL = "https://www.consultant.ru/document/cons_doc_LAW_500/"
PUBLICATION = "https://www.consultant.ru/document/cons_doc_LAW_600/"
HASH = "a" * 40


def html(paragraph):
    return f'<div class="document-page__content"><p>{paragraph}</p></div>'


def target(label="Часть 1 статьи 7", doc_id="500"):
    return f'<a href="/document/cons_doc_LAW_{doc_id}/{HASH}/">{label}</a>'


def overview():
    return ('<div class="document-page__content">'
            f'<p>Федеральный <a href="{ROOT_URL}">закон</a> от 01.01.2020 N 100-ФЗ</p>'
            '<p>(ред. от 11.10.2026)</p><p>"Учебные правила"</p>'
            f'<p>(изменения, внесенные Федеральным <a href="{PUBLICATION}">законом</a> от 11.10.2026 N 200-ФЗ, '
            f'<a href="{PUBLICATION}{HASH}/">вступают</a> в силу позднее)</p></div>')


def catalog(tmp_path):
    text = "Учебная статья 7"
    (tmp_path / "article.txt").write_text(text, encoding="utf-8")
    (tmp_path / "legal_sources.json").write_text(json.dumps({"sources": [{
        "file": "article.txt", "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "document_key": "training:rules", "article": "7", "part": "1",
        "source_url": ROOT_URL + HASH + "/", "revision": "v1",
    }]}), encoding="utf-8")


def test_explicit_target_is_separate_from_inserted_cross_reference():
    page = html(target() + ' учебного закона дополнить пунктом следующего содержания:')
    page += html('"Вопрос регулируется ' + target("статьей 9") + '."')
    found = extract_linked_amendments(page, PUBLICATION, {"500": "training:rules"})
    assert [r.norm for r in found] == [NormIdentity("training:rules", "7", "1")]
    assert found[0].evidence["target_label"] == "Часть 1 статьи 7"
    assert len(found[0].evidence["source_sha256"]) == 64


@pytest.mark.parametrize("paragraph", [
    target() + " используется в решении вопроса.",
    'Согласно ' + target() + " другую статью следует дополнить.",
    '"' + target() + ' дополнить обязанность читателя."',
    target("статьи 9–7") + " изложить в новой редакции.",
    target(doc_id="999") + " изложить в новой редакции.",
    target() + ' содержит слова "дополнить пунктом".',
])
def test_mentions_ambiguous_scopes_and_unknown_laws_do_not_create_changes(paragraph):
    assert extract_linked_amendments(html(paragraph), PUBLICATION, {"500": "training:rules"}) == []


def test_navigation_is_not_source_content():
    assert extract_linked_amendments('<p>' + target() + ' дополнить</p>', PUBLICATION,
                                     {"500": "training:rules"}) == []


def test_ambiguous_catalog_and_external_urls_are_excluded():
    source = LegalSource(NormIdentity("training:one", "7"), ROOT_URL, "v1", "0" * 64)
    second = LegalSource(NormIdentity("training:two", "8"), ROOT_URL, "v1", "0" * 64)
    assert catalog_document_keys({"one": source, "two": second}) == {}
    assert consultant_document_id("https://evilconsultant.ru/document/cons_doc_LAW_500/") is None


def test_overview_retains_amendment_link_after_quoted_title():
    change, = parse_consultant_category(overview(), PUBLICATION)
    assert change.document_number == "100-ФЗ"
    assert change.amendment_source_urls == (PUBLICATION,)
    assert change.affected_norms == ()
    assert change.document_key == "ru:100-fz:2020-01-01"


@pytest.mark.asyncio
async def test_collection_follows_revision_redirect_and_requires_matching_original_law(tmp_path, monkeypatch):
    catalog(tmp_path)
    monkeypatch.setattr(settings, "RAG_DOCS_PATH", str(tmp_path))
    requests = []
    category = "https://www.consultant.ru/document/cons_doc_LAW_33770/" + HASH + "/"
    def handler(request):
        requests.append(str(request.url))
        if str(request.url) == category:
            return httpx.Response(200, text=overview())
        if str(request.url) == PUBLICATION:
            return httpx.Response(200, text=html(target(doc_id="501") + " дополнить пунктом."))
        if "/cons_doc_LAW_501/" in str(request.url):
            return httpx.Response(302, headers={"location": ROOT_URL + HASH + "/"})
        return httpx.Response(200, text=html("Учебный источник"))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        change, = await collect_changes_from_source(client, category)
    assert change.affected_norms == (NormIdentity("training:rules", "7", "1"),)
    assert change.norm_evidence[0]["method"] == "consultant_explicit_link"
    assert "Подтверждённые поправки" in change.description
    assert any("LAW_501" in url for url in requests)


@pytest.mark.asyncio
async def test_unavailable_publication_does_not_infer_scopes(tmp_path, monkeypatch):
    catalog(tmp_path)
    monkeypatch.setattr(settings, "RAG_DOCS_PATH", str(tmp_path))
    category = "https://www.consultant.ru/document/cons_doc_LAW_33770/" + HASH + "/"
    def handler(request):
        return httpx.Response(200, text=overview()) if str(request.url) == category else httpx.Response(403)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        change, = await collect_changes_from_source(client, category)
    assert change.affected_norms == (NormIdentity("ru:100-fz:2020-01-01"),)
    assert change.norm_evidence[0]["scope"] == "document"


@pytest.mark.asyncio
async def test_fetch_limit_is_respected(tmp_path, monkeypatch):
    catalog(tmp_path)
    monkeypatch.setattr(settings, "RAG_DOCS_PATH", str(tmp_path))
    monkeypatch.setattr(settings, "LAW_CHANGE_MAX_AMENDMENT_PAGES", 0)
    category = "https://www.consultant.ru/document/cons_doc_LAW_33770/" + HASH + "/"
    requests = []
    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(200, text=overview())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        change, = await collect_changes_from_source(client, category)
    assert change.affected_norms == (NormIdentity("ru:100-fz:2020-01-01"),) and requests == [category]


@pytest.mark.parametrize("attribute,expected", [
    ('{&quot;type&quot;:&quot;editions&quot;,&quot;base&quot;:&quot;LAW&quot;,&quot;num&quot;:500}', ROOT_URL),
    ('{&quot;type&quot;:&quot;editions&quot;,&quot;base&quot;:&quot;OTHER&quot;,&quot;num&quot;:500}', "https://www.consultant.ru/law/review/fed/updprof/"),
    ('{&quot;type&quot;:&quot;editions&quot;,&quot;base&quot;:&quot;LAW&quot;,&quot;num&quot;:&quot;500&quot;}', "https://www.consultant.ru/law/review/fed/updprof/"),
    ('broken-json', "https://www.consultant.ru/law/review/fed/updprof/"),
])
def test_original_document_metadata_is_not_confused_with_amending_link(attribute, expected):
    page = overview().replace(f'href="{ROOT_URL}"', f'href="#" data-document-link="{attribute}"')
    change, = parse_consultant_category(page, "https://www.consultant.ru/law/review/fed/updprof/")
    assert change.source_url == expected
    assert change.amendment_source_urls == (PUBLICATION,)


@pytest.mark.asyncio
@pytest.mark.parametrize("failures", [1, 2])
async def test_amendment_read_timeout_is_retried_once(tmp_path, monkeypatch, failures):
    catalog(tmp_path)
    monkeypatch.setattr(settings, "RAG_DOCS_PATH", str(tmp_path))
    category = "https://www.consultant.ru/document/cons_doc_LAW_33770/" + HASH + "/"
    attempts = 0
    def handler(request):
        nonlocal attempts
        if str(request.url) == category:
            return httpx.Response(200, text=overview())
        if str(request.url) == PUBLICATION:
            attempts += 1
            if attempts <= failures:
                raise httpx.ReadTimeout("Timed-out test response", request=request)
            return httpx.Response(200, text=html(target() + " дополнить пунктом."))
        raise AssertionError("Unexpected source request")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        change, = await collect_changes_from_source(client, category)
    assert attempts == 2
    assert change.affected_norms == ((NormIdentity("training:rules", "7", "1"),) if failures == 1 else (NormIdentity("ru:100-fz:2020-01-01"),))


@pytest.mark.parametrize("label,articles,part,point", [
    ("статьи 7 и 9", ["7", "9"], "", ""),
    ("статьи 7, 9 и 10", ["7", "9", "10"], "", ""),
    ("статьи 7–9", ["7", "8", "9"], "", ""),
    ("статья 10.1", ["10.1"], "", ""),
    ("пункт 2 части 1 статьи 7", ["7"], "1", "2"),
])
def test_explicit_multiple_and_subarticle_targets(label, articles, part, point):
    found = extract_linked_amendments(html(target(label) + " изложить в новой редакции."),
        PUBLICATION, {"500": "training:rules"})
    assert [r.norm for r in found] == [NormIdentity("training:rules", a, part, point) for a in articles]


@pytest.mark.parametrize("label", ["статьи 1–10000", "часть 1 статьи 7 и 9", "статьи 1.1–2.3"])
def test_unbounded_or_ambiguous_scope_is_rejected(label):
    assert extract_linked_amendments(html(target(label)+" дополнить."), PUBLICATION,
        {"500":"training:rules"}) == []


def test_plain_instruction_without_hyperlink_uses_full_law_identity():
    page = html('Внести в Федеральный закон от 3 июня 2009 года N 103-ФЗ следующие изменения:')
    page += html('1) часть 16 статьи 4 дополнить пунктом 2.1 следующего содержания:')
    page += html('"Ссылка на статью 10 другого закона."')
    found = extract_linked_amendments(page, PUBLICATION, {})
    assert [r.norm for r in found] == [NormIdentity("ru:103-fz:2009-06-03", "4", "16")]
    assert found[0].evidence["method"] == "consultant_formal_instruction"


def test_plain_instruction_does_not_inherit_law_across_amending_articles():
    page = html('Внести в Федеральный закон от 03.06.2009 N 103-ФЗ следующие изменения:')
    page += html('Статья 2') + html('Статью 10 изложить в новой редакции.')
    assert extract_linked_amendments(page, PUBLICATION, {}) == []


def test_plain_quoted_inserted_law_header_is_not_a_target():
    page = html('"Внести в Федеральный закон от 03.06.2009 N 103-ФЗ следующие изменения:')
    page += html('Статью 10 изложить в новой редакции."')
    assert extract_linked_amendments(page, PUBLICATION, {}) == []


def test_plain_cross_reference_between_scope_and_action_is_not_a_target():
    page = html('Статью 7 согласно статье 10 Федерального закона от 03.06.2009 N 103-ФЗ дополнить.')
    assert extract_linked_amendments(page, PUBLICATION, {}) == []


def test_linked_scope_inside_multiline_inserted_quote_is_ignored():
    page = html(target()+ ' дополнить следующим текстом: "')
    page += html(target("статья 9")+' изложить в новой редакции."')
    found = extract_linked_amendments(page, PUBLICATION, {"500":"training:rules"})
    assert [r.norm.article for r in found] == ["7"]
