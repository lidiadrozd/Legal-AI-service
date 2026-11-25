"""Curated source metadata. A matching hash proves provenance, not legal accuracy."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse


@dataclass(frozen=True)
class NormIdentity:
    document_key: str
    article: str = ""
    part: str = ""
    point: str = ""

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict):
            raise ValueError("Invalid norm metadata")
        fields = {}
        for key, limit in (("document_key", 200), ("article", 50), ("part", 50), ("point", 50)):
            text = value.get(key, "")
            if not isinstance(text, str) or len(text) > limit:
                raise ValueError("Invalid norm identifier")
            fields[key] = text.strip()
        if not fields["document_key"]:
            raise ValueError("Missing document key")
        if not fields["article"] and (fields["part"] or fields["point"]):
            raise ValueError("Subarticle scope requires an article")
        return cls(**fields)


@dataclass(frozen=True)
class LegalSource:
    norm: NormIdentity
    source_url: str
    revision: str
    sha256: str
    # Only an operator-maintained statute_text entry may expose a direct quote.
    # Unknown/assistant sources and operator summaries remain useful for routing
    # and tracking, but are never presented as verbatim law text.
    content_kind: str = "unknown"
    verbatim_excerpt: str = ""

    @property
    def has_verified_excerpt(self) -> bool:
        return self.content_kind == "statute_text" and bool(self.verbatim_excerpt)


def _sentence_count(text: str) -> int:
    """Count curated sentence endings without trying to parse arbitrary prose."""
    # A numbered statutory paragraph such as ``14. Правило...`` is one
    # sentence, not two merely because its item number ends with a dot.
    candidate = re.sub(r"^\d+(?:\.\d+)*\.\s+", "", text.strip())
    count = len(re.findall(r"[.!?](?=\s|$)", candidate))
    # A statutory lead-in ending with a colon is intentionally usable as the
    # short excerpt when the enumerated list itself would exceed two sentences.
    return count or (1 if candidate.endswith(":") else 0)


def load_legal_source_catalog(root: Path) -> dict[str, LegalSource]:
    """Only operator-maintained files under RAG_DOCS_PATH may define identities."""
    manifest = root / "legal_sources.json"
    if not manifest.exists():
        return {}
    try:
        entries = json.loads(manifest.read_text(encoding="utf-8")).get("sources", [])
    except (OSError, ValueError, AttributeError):
        return {}
    if not isinstance(entries, list):
        return {}
    result = {}
    ambiguous = set()
    for entry in entries:
        try:
            if not isinstance(entry, dict):
                continue
            relative = entry["file"]
            if not isinstance(relative, str):
                continue
            path = (root / relative).resolve()
            path.relative_to(root.resolve())
            if path.suffix.lower() not in {".txt", ".md"}:
                continue
            source = path.relative_to(root.resolve()).as_posix()
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if entry.get("sha256") != digest:
                continue
            document_text = raw.decode("utf-8")
            norm = NormIdentity.from_dict(entry)
            url = entry.get("source_url")
            revision = entry.get("revision")
            if (not isinstance(url, str) or len(url) > 1000
                    or urlparse(url).scheme != "https" or not urlparse(url).netloc
                    or not isinstance(revision, str) or not revision.strip() or len(revision) > 100):
                continue
            content_kind = entry.get("content_kind", "unknown")
            excerpt = entry.get("verbatim_excerpt", "")
            if content_kind not in {"statute_text", "operator_summary", "unknown"}:
                continue
            if not isinstance(excerpt, str) or len(excerpt) > 2000:
                continue
            excerpt = excerpt.strip()
            if content_kind == "statute_text":
                # A manifest label is not enough: the approved quote must be a
                # literal 1-2 sentence substring of the hash-bound document.
                if (not excerpt or excerpt not in document_text
                        or _sentence_count(excerpt) not in {1, 2}):
                    continue
            elif excerpt:
                # In particular, an operator summary must never masquerade as
                # a quote merely because it has a quote-looking manifest field.
                continue
            if source in result or source in ambiguous:
                result.pop(source, None)
                ambiguous.add(source)
                continue
            result[source] = LegalSource(
                norm, url, revision.strip(), digest, content_kind, excerpt,
            )
        except (KeyError, ValueError, OSError, UnicodeError):
            continue
    return result


def cited_legal_sources(text: str, offered: list[dict]) -> tuple[dict, ...]:
    cited = set(re.findall(r"\[Источник ([1-9][0-9]*)\]", text or ""))
    result, seen = [], set()
    for item in offered:
        source = item.get("legal_source")
        if (str(item.get("citation_id")) not in cited or not isinstance(source, LegalSource)
                or source.norm in seen):
            continue
        seen.add(source.norm)
        result.append(item)
    return tuple(result)
