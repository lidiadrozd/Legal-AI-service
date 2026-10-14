from pathlib import Path

import pytest

from app.core.config import settings
from app.services import rag_context


@pytest.mark.parametrize("query", [
    "В какой срок работодатель должен выплатить компенсацию за неиспользованный отпуск при увольнении по ст. 127 ТК РФ, если работник отработал менее 3 месяцев?",
    "Когда выплатят компенсацию за неиспользованный отпуск при увольнении?",
])
def test_labor_payment_question_receives_entitlement_and_deadline_sources(monkeypatch, query):
    monkeypatch.setattr(settings, "RAG_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_DOCS_PATH", str(Path(__file__).resolve().parents[1] / "rag_docs"))
    monkeypatch.setattr(rag_context, "_INDEX", None)
    text, sources = rag_context.build_rag_bundle(query)
    articles = {item["legal_source"].norm.article for item in sources
                if item["legal_source"].norm.document_key == "ru:197-fz:2001-12-30"}
    assert {"127", "140"} <= articles
    assert "не позднее следующего дня" in text


@pytest.mark.asyncio
async def test_missing_basis_retried_and_used_source_stays_visible(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.services import nlp_service
    from app.services.legal_sources import LegalSource, NormIdentity
    from app.services.llm_cost import TokenUsage

    sources = [{"citation_id": index, "legal_source": LegalSource(
        NormIdentity("ru:197-fz:2001-12-30", article),
        "https://www.consultant.ru/document/cons_doc_LAW_34683/", "2026-05-25", "a" * 64),
        "text": "Текст нормы"} for index, article in enumerate(("140", "127"), 1)]
    client = SimpleNamespace(chat_completion=AsyncMock(side_effect=[
        SimpleNamespace(content="Расчёт в день увольнения.", usage=TokenUsage(1, 2, 3, False)),
        SimpleNamespace(content="Расчёт в день увольнения. [Источник 1]", usage=TokenUsage(3, 4, 7, False)),
    ]))
    monkeypatch.setattr(nlp_service, "get_gigachat_client", AsyncMock(return_value=client))
    monkeypatch.setattr(nlp_service.response_cache, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(nlp_service.response_cache, "set", AsyncMock())
    result = await nlp_service.NLPService().generate_response("Когда выплатят компенсацию?", {"rag_sources": sources})
    assert client.chat_completion.call_count == 2
    assert result.usage.total_tokens == 10
    assert "ТК РФ, статья 140" in result.text
    assert "статья 127" not in result.text  # Retrieved but not used.
    assert {r["legal_source"].norm.article for r in result.references} == {"140"}


@pytest.mark.asyncio
async def test_existing_explicit_basis_does_not_trigger_retry(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.services import nlp_service
    from app.services.llm_cost import TokenUsage
    client = SimpleNamespace(chat_completion=AsyncMock(return_value=SimpleNamespace(
        content="Срок устанавливает ТК РФ, статья 140.", usage=TokenUsage(1, 2, 3, False))))
    monkeypatch.setattr(nlp_service, "get_gigachat_client", AsyncMock(return_value=client))
    monkeypatch.setattr(nlp_service.response_cache, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(nlp_service.response_cache, "set", AsyncMock())
    result = await nlp_service.NLPService().generate_response("Когда выплатят компенсацию?")
    assert client.chat_completion.call_count == 1
    assert "статья 140" in result.text
