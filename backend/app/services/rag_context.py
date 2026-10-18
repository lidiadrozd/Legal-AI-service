from __future__ import annotations

import logging
import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from app.core.config import settings
from app.services.legal_sources import LegalSource, load_legal_source_catalog

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[\wа-яА-ЯёЁ]+", re.UNICODE)


@dataclass(frozen=True)
class RagChunk:
    source: str
    text: str
    score: float = 0.0
    legal_source: LegalSource | None = None


class RagIndex:
    def __init__(self, chunks: list[RagChunk]) -> None:
        self._chunks = chunks
        self._vectors = [self._vectorize(chunk.text) for chunk in chunks]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return _TOKEN_RE.findall((text or "").lower())

    @classmethod
    def _vectorize(cls, text: str) -> Counter[str]:
        return Counter(cls._tokenize(text))

    @staticmethod
    def _cosine(left: Counter[str], right: Counter[str]) -> float:
        if not left or not right:
            return 0.0
        common = set(left) & set(right)
        numerator = sum(left[token] * right[token] for token in common)
        left_norm = math.sqrt(sum(value * value for value in left.values()))
        right_norm = math.sqrt(sum(value * value for value in right.values()))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return numerator / (left_norm * right_norm)

    def vector_search(self, query: str, *, top_k: int) -> list[RagChunk]:
        if not self._chunks:
            return []
        query_vector = self._vectorize(query)
        ranked = sorted(
            (
                replace(chunk, score=self._cosine(query_vector, vector))
                for chunk, vector in zip(self._chunks, self._vectors)
            ),
            key=lambda item: item.score,
            reverse=True,
        )
        return ranked[:top_k]

    @staticmethod
    def rerank(query: str, chunks: list[RagChunk], *, threshold: float) -> list[RagChunk]:
        if not chunks:
            return []
        query_terms = set(RagIndex._tokenize(query))
        rescored: list[RagChunk] = []
        for chunk in chunks:
            chunk_terms = set(RagIndex._tokenize(chunk.text))
            overlap = len(query_terms & chunk_terms) / max(len(query_terms), 1)
            score = (chunk.score * 0.7) + (overlap * 0.3)
            if score >= threshold:
                rescored.append(replace(chunk, score=score))
        return sorted(rescored, key=lambda item: item.score, reverse=True)


_INDEX: RagIndex | None = None


def _chunk_text(text: str, *, source: str, max_chars: int) -> list[RagChunk]:
    normalized = re.sub(r"\n{3,}", "\n\n", (text or "").strip())
    if not normalized:
        return []
    paragraphs = [part.strip() for part in normalized.split("\n\n") if part.strip()]
    chunks: list[RagChunk] = []
    buffer = ""
    for paragraph in paragraphs:
        candidate = f"{buffer}\n\n{paragraph}".strip() if buffer else paragraph
        if len(candidate) <= max_chars:
            buffer = candidate
            continue
        if buffer:
            chunks.append(RagChunk(source=source, text=buffer))
        if len(paragraph) <= max_chars:
            buffer = paragraph
            continue
        for start in range(0, len(paragraph), max_chars):
            chunks.append(RagChunk(source=source, text=paragraph[start : start + max_chars]))
        buffer = ""
    if buffer:
        chunks.append(RagChunk(source=source, text=buffer))
    return chunks


def _load_chunks() -> list[RagChunk]:
    root = Path(settings.RAG_DOCS_PATH)
    if not root.exists():
        return []
    chunks: list[RagChunk] = []
    catalog = load_legal_source_catalog(root)
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".txt", ".md"}:
            continue
        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeError):
            logger.warning("Failed to read RAG document: %s", path)
            continue
        source_name = path.relative_to(root).as_posix()
        legal_source = catalog.get(source_name)
        if legal_source and hashlib.sha256(raw).hexdigest() != legal_source.sha256:
            legal_source = None
        chunks.extend(replace(chunk, legal_source=legal_source) for chunk in
                      _chunk_text(text, source=source_name, max_chars=settings.RAG_CHUNK_MAX_CHARS))
    return chunks


def get_rag_index() -> RagIndex:
    global _INDEX
    if _INDEX is None:
        _INDEX = RagIndex(_load_chunks())
    return _INDEX


def build_rag_bundle(query: str) -> tuple[str, list[dict]]:
    if not settings.RAG_ENABLED:
        return "", []
    index = get_rag_index()
    if not index._chunks:
        return "", []

    candidates = index.vector_search(query, top_k=settings.RAG_VECTOR_TOP_K)
    ranked = RagIndex.rerank(
        query,
        candidates,
        threshold=settings.RAG_RERANK_THRESHOLD,
    )
    selected = ranked[: settings.RAG_MAX_CONTEXT_CHUNKS]
    if not selected:
        return "", []

    lines = ["Релевантные фрагменты базы знаний (сжатый контекст):"]
    sources = []
    for idx, chunk in enumerate(selected, start=1):
        label = f"[Источник {idx}]" if chunk.legal_source else ""
        metadata = ""
        if chunk.legal_source:
            source = chunk.legal_source
            metadata = f"\nСтатья: {source.norm.article}; часть: {source.norm.part}; пункт: {source.norm.point}; редакция: {source.revision}; ссылка: {source.source_url}"
            sources.append({"citation_id": idx, "legal_source": source, "text": chunk.text})
        lines.append(f"[{idx}] {label} {chunk.source}{metadata}\n{chunk.text.strip()}")
    return "\n\n".join(lines), sources


def build_rag_context(query: str) -> str:
    return build_rag_bundle(query)[0]


def serialize_chat_context(context: dict | str | None) -> str:
    if context is None:
        return "Нет дополнительного контекста."
    if isinstance(context, str):
        return context.strip() or "Нет дополнительного контекста."

    parts: list[str] = []
    # Cache identity must include the curated norm metadata, not only its text.
    for item in context.get("rag_sources", []):
        source = item.get("legal_source")
        if isinstance(source, LegalSource):
            parts.append(json.dumps({"citation_id": item["citation_id"], "source": asdict(source)},
                                    ensure_ascii=False, sort_keys=True))
    rag = (context.get("rag") or "").strip()
    if rag:
        parts.append(rag)
    docs = context.get("docs") or []
    if docs:
        parts.append("Недавние изменения законодательства:\n" + "\n".join(f"- {item}" for item in docs))
    return "\n\n".join(parts) if parts else "Нет дополнительного контекста."
