"""Operator-reviewed change feed tied to the existing curated norm catalog."""
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from app.services.law_change_parser import ParsedLawChange
from app.services.legal_sources import NormIdentity, load_legal_source_catalog

MAX_FILE_BYTES = 2 * 1024 * 1024


class CuratedSourceError(ValueError):
    """Safe diagnostic: no file contents, URLs or credentials in the message."""


def _text(item, key, limit, *, required=True):
    value = item.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise CuratedSourceError(f"Invalid {key}")
    return value.strip()


def _known_norm(norm, catalog):
    return any(norm.document_key == source.norm.document_key and all(
        not left or not right or left == right
        for left, right in zip((norm.article, norm.part, norm.point),
                               (source.norm.article, source.norm.part, source.norm.point)))
        for source in catalog.values())


def load_curated_changes(path: Path, *, catalog_root: Path) -> list[ParsedLawChange]:
    # Validate the complete feed before importing anything: a malformed sibling
    # must not broaden the scope of a partially accepted change.
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise CuratedSourceError("Curated file exceeds size limit")
        payload = json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        if isinstance(exc, CuratedSourceError):
            raise
        raise CuratedSourceError("Cannot read curated JSON file") from None
    entries = payload.get("changes") if isinstance(payload, dict) else None
    if not isinstance(entries, list) or len(entries) > 1000:
        raise CuratedSourceError("Invalid changes list")
    if not entries:
        return []
    catalog = load_legal_source_catalog(catalog_root)
    if not catalog:
        raise CuratedSourceError("Verified norm catalog is empty")
    result = []
    for index, item in enumerate(entries, start=1):
        try:
            if not isinstance(item, dict) or item.get("reviewed") is not True:
                raise CuratedSourceError("Change is not operator-reviewed")
            title = _text(item, "title", 500)
            description = _text(item, "description", 20000)
            source_url = _text(item, "url", 1000)
            url = urlparse(source_url)
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                raise CuratedSourceError("Invalid HTTPS publication URL")
            date = datetime.fromisoformat(_text(item, "date", 50).replace("Z", "+00:00"))
            number = _text(item, "document_number", 50)
            raw_norms = item.get("affected_norms")
            if not isinstance(raw_norms, list) or not raw_norms or len(raw_norms) > 100:
                raise CuratedSourceError("Missing or invalid affected norms")
            norms = tuple(dict.fromkeys(NormIdentity.from_dict(n) for n in raw_norms))
            if not all(_known_norm(norm, catalog) for norm in norms):
                raise CuratedSourceError("Affected norm is absent from the verified catalog")
            result.append(ParsedLawChange(title=title, change_date=date, description=description,
                source_url=source_url, document_number=number,
                document_title=_text(item, "document_title", 500, required=False),
                category=_text(item, "category", 100, required=False), affected_norms=norms,
                old_version=_text(item, "old_version", 100000, required=False),
                new_version=_text(item, "new_version", 100000, required=False)))
        except ValueError as exc:
            message = str(exc) if isinstance(exc, CuratedSourceError) else "Invalid norm or date"
            raise CuratedSourceError(f"Entry {index}: {message}") from None
    return result
