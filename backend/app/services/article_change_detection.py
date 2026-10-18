"""Compare verified complete article snapshots; never infer scopes from keywords."""
import hashlib
import re
from datetime import datetime, timezone
from app.services.answer_norms import heading_document_key
from app.services.consultant_norm_changes import _Paragraphs, consultant_document_id
from app.services.legal_sources import NormIdentity
from app.services.law_change_parser import ParsedLawChange

ARTICLE_HEADING = re.compile(r"^Статья\s+(\d+(?:\.\d+)*)(?:\.|\s|$)", re.I)
REVISION = re.compile(r"ред\.\s*от\s*(\d{2}\.\d{2}\.\d{4})", re.I)

def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_article_snapshot(html, source_url, document_key):
    if not consultant_document_id(source_url):
        raise ValueError("unsupported_source")
    parser = _Paragraphs()
    parser.feed(html)
    if parser.content_depth is not None:
        raise ValueError("incomplete_document")
    paragraphs = [" ".join(p["text"].split()) for p in parser.paragraphs]
    heading = " ".join(paragraphs[:8])[:3000]
    # URL aliases are not enough: require dated/numbered identity in the document.
    if heading_document_key(heading) != document_key:
        raise ValueError("document_identity_unconfirmed")
    articles, current, buffer = {}, None, []
    def flush():
        if current is not None:
            if current in articles:
                raise ValueError("duplicate_article_headings")
            text = "\n".join(buffer)
            articles[current] = {"sha256": _hash(text), "text": text}
    for paragraph in paragraphs:
        match = ARTICLE_HEADING.match(paragraph)
        if match:
            flush()
            current, buffer = match[1], [paragraph]
        elif current is not None:
            buffer.append(paragraph)
    flush()
    if not articles:
        raise ValueError("article_structure_unrecognized")
    revision = REVISION.search(heading)
    revision_date = datetime.strptime(revision[1], "%d.%m.%Y").date().isoformat() if revision else None
    return {"algorithm_version": 1, "document_key": document_key,
            "source_url": source_url, "revision_date": revision_date,
            "articles": articles, "captured_at": datetime.now(timezone.utc).isoformat()}


def compare_article_snapshots(previous, current):
    if previous is None:
        return "baseline_created", []
    if previous.get("algorithm_version") != current["algorithm_version"]:
        return "baseline_version_changed", []
    if previous.get("document_key") != current["document_key"]:
        raise ValueError("different_document")
    old_date, new_date = previous.get("revision_date"), current.get("revision_date")
    if old_date and new_date and new_date < old_date:
        return "older_edition_ignored", []
    old, new = previous["articles"], current["articles"]
    # Missing headings could mean a truncated response rather than a repeal.
    # Removed articles require an explicit repeal instruction, not absence alone.
    if set(old) - set(new):
        return "incomplete_or_removed_articles", []
    changed = [article for article in new if article not in old or new[article]["sha256"] != old[article]["sha256"]]
    evidence = [{"method": "article_snapshot_diff", "document_key": current["document_key"],
        "article": article, "operation": "added" if article not in old else "modified",
        "old_sha256": old.get(article, {}).get("sha256"), "new_sha256": new[article]["sha256"],
        "old_text": old.get(article, {}).get("text", ""), "new_text": new[article]["text"],
        "publication_url": current["source_url"], "previous_captured_at": previous.get("captured_at"),
        "captured_at": current["captured_at"]} for article in changed]
    return "confirmed" if evidence else "unchanged", evidence


def snapshot_change(snapshot, evidence):
    identity = snapshot["document_key"]
    digest = _hash(str([(e["article"], e["old_sha256"], e["new_sha256"]) for e in evidence]))[:16]
    return ParsedLawChange(title="Изменение текста статей: " + identity + " [" + digest + "]",
        change_date=datetime.fromisoformat(snapshot["revision_date"]) if snapshot["revision_date"] else None,
        description="Изменение подтверждено сравнением сохранённых текстов статей. "
                    "Причина и дата вступления в силу требуют проверки публикации.",
        source_url=snapshot["source_url"], document_number=identity, document_key=identity,
        affected_norms=tuple(NormIdentity(identity, e["article"]) for e in evidence),
        old_version="\n\n".join(e["old_text"] for e in evidence),
        new_version="\n\n".join(e["new_text"] for e in evidence),
        norm_evidence=tuple({k:v for k,v in e.items() if k not in {"old_text", "new_text"}} for e in evidence),
        scope_resolution={"status": "confirmed", "method": "article_snapshot_diff"})
