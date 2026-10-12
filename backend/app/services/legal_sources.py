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
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if entry.get("sha256") != digest:
                continue
            norm = NormIdentity.from_dict(entry)
            url = entry.get("source_url")
            revision = entry.get("revision")
            if (not isinstance(url, str) or len(url) > 1000
                    or urlparse(url).scheme != "https" or not urlparse(url).netloc
                    or not isinstance(revision, str) or not revision.strip() or len(revision) > 100):
                continue
            if source in result or source in ambiguous:
                result.pop(source, None)
                ambiguous.add(source)
                continue
            result[source] = LegalSource(norm, url, revision.strip(), digest)
        except (KeyError, ValueError, OSError):
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
