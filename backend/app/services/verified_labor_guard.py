"""Small fail-safe for labor rules that must not be reversed by the model."""
from __future__ import annotations

from pathlib import Path
import re

from app.core.config import settings
from app.services.answer_norms import TK_KEY
from app.services.legal_sources import LegalSource, load_legal_source_catalog


def _has(text: str, *patterns: str) -> bool:
    return all(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _rule(query: str) -> tuple[str, tuple[str, ...]] | None:
    text = " ".join((query or "").split())
    if (_has(text, r"45\s*[-–]?\s*час", r"рабоч\w*\s+недел")
            and re.search(r"соглас|совершеннолет|обычн", text, re.IGNORECASE)):
        return (
            "Нет. Установить обычному совершеннолетнему работнику 45-часовую рабочую "
            "неделю как нормальную продолжительность нельзя даже с его согласия: предел "
            "нормальной продолжительности — 40 часов в неделю.",
            ("91",),
        )
    if (_has(text, r"(?:заработн\w*\s+плат|зарплат)", r"(?:один|1)\s+раз\w*\s+в\s+месяц")
            and re.search(r"соглас|подписал", text, re.IGNORECASE)):
        return (
            "Нет. Заработная плата должна выплачиваться не реже чем каждые полмесяца; "
            "согласие работников на одну выплату в месяц не отменяет эту гарантию.",
            ("136",),
        )
    if (_has(text, r"отпуск", r"денежн\w*\s+компенсац") and re.search(
        r"(?:все|весь|полност|целиком).{0,80}(?:дн|отпуск)|"
        r"(?:дн|отпуск).{0,80}(?:все|весь|полност|целиком)", text, re.IGNORECASE,
    )):
        return (
            "Нет. Во время работы по письменному заявлению денежной компенсацией можно "
            "заменить только часть ежегодного оплачиваемого отпуска сверх 28 календарных "
            "дней. Вопрос о компенсации при увольнении регулируется отдельным правилом.",
            ("126",),
        )
    if (_has(text, r"увольн", r"(?:срок|когда|в\s+какой\s+день|не\s+позднее)") and re.search(
        r"(?:расч[её]т|компенсац|выплат)", text, re.IGNORECASE,
    )):
        return (
            "Работодатель должен произвести окончательный расчёт в день увольнения. Если "
            "работник в этот день не работал, соответствующие суммы выплачиваются не позднее "
            "следующего дня после предъявления требования о расчёте.",
            ("140",),
        )
    return None


def _catalog_sources(articles: tuple[str, ...], offered: list[dict]) -> list[dict]:
    result = list(offered)
    existing = {
        (item["legal_source"].norm.document_key, item["legal_source"].norm.article)
        for item in result if isinstance(item.get("legal_source"), LegalSource)
    }
    catalog = load_legal_source_catalog(Path(settings.RAG_DOCS_PATH))
    next_id = max((int(item.get("citation_id") or 0) for item in result), default=0) + 1
    for article in articles:
        key = (TK_KEY, article)
        if key in existing:
            continue
        source = next((source for source in catalog.values()
                       if source.norm.document_key == TK_KEY
                       and source.norm.article == article
                       and source.has_verified_excerpt), None)
        if source is None:
            continue
        result.append({
            "citation_id": next_id,
            "legal_source": source,
            "text": source.verbatim_excerpt,
            "origin": "verified_guard",
        })
        existing.add(key)
        next_id += 1
    return result


def verified_labor_answer(query: str, offered: list[dict]) -> tuple[str, list[dict]] | None:
    matched = _rule(query)
    if matched is None:
        return None
    summary, articles = matched
    sources = _catalog_sources(articles, offered)
    by_article = {
        item["legal_source"].norm.article: item
        for item in sources
        if isinstance(item.get("legal_source"), LegalSource)
        and item["legal_source"].norm.document_key == TK_KEY
        and item["legal_source"].norm.article in articles
        and item["legal_source"].has_verified_excerpt
    }
    used = [by_article[article] for article in articles if article in by_article]
    if not used:
        return None
    primary = used[0]
    marker = f" [Источник {primary['citation_id']}]"
    links = "\n".join(
        f"- ТК РФ, статья {item['legal_source'].norm.article} [Источник {item['citation_id']}]"
        for item in used
    )
    answer = (
        f"**Кратко:** {summary} ТК РФ, статья {primary['legal_source'].norm.article}{marker}.\n\n"
        f"**Ссылка на статью/статьи:**\n{links}\n\n"
        f"**Цитата из статьи:**\n\n«{primary['legal_source'].verbatim_excerpt}»"
    )
    return answer, sources
