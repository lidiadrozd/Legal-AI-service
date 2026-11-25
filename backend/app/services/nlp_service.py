"""
NLP Service: GigaChat через REST chat/completions (OAuth как в примерах Сбера).
"""

import json
import re
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.legal_disclaimer import with_legal_disclaimer
from app.core.prompts import (
    format_chat_context, get_system_prompt, get_document_prompt,
    LEGAL_SCOPE_REFUSAL, DOCUMENT_DRAFT_FUNCTION,
)
from app.services.document_draft_validator import (
    process_document_response, is_document_generation_request,
    is_valid_document_response, DOCUMENT_FORMAT_RETRY,
    has_pending_document_clarification,
)
from app.services.gigachat_client import get_gigachat_client
from app.services.consultant_article_quotes import find_question_quotes
from app.services.llm_cost import TokenUsage
from app.services.consultation_basis import check_reply, needs_basis_review, pack_review, unpack_review
from app.services.answer_norms import (
    answer_references, extract_answer_norms, document_label,
    has_mismatched_source_markers, grounding_issues, legal_quote_issues,
)
from app.services.response_cache import build_cache_key, response_cache
from app.services.live_legal_sources import (
    format_live_legal_sources,
    resolve_live_legal_sources,
)


_QUOTE_SECTION_RE = re.compile(
    r"(?ims)^[ \t]*\*\*Цитата из статьи:\*\*.*?(?=^[ \t]*\*\*[^*\n]+:\*\*|\Z)"
)
_LINK_SECTION_RE = re.compile(
    r"(?ims)^[ \t]*\*\*Ссылка на статью/статьи:\*\*.*?(?=^[ \t]*\*\*[^*\n]+:\*\*|\Z)"
)
_QUOTE_CHECK_RE = re.compile(
    r"(?ims)^\s*\*\*Проверка цитаты:\*\*.*?(?=^\s*\*\*[^*\n]+:\*\*|\Z)"
)


def _fallback_summary(text: str) -> str:
    """Keep the model's useful short answer when source reconciliation fails."""
    match = re.search(
        r"(?is)\*\*Кратко:\*\*\s*(.*?)(?=\n\s*\n\s*\*\*[^*\n]+:\*\*|\Z)",
        text or "",
    )
    summary = re.sub(r"\s+", " ", match.group(1)).strip() if match else ""
    if summary.lower().startswith("не удалось полностью согласовать"):
        return ""
    return summary[:1200]


def sanitize_consultation_quotes(text: str, offered: list[dict]) -> str:
    """Render article links and verbatim excerpts from the evidence actually cited."""
    cleaned = _QUOTE_CHECK_RE.sub("", text or "").strip()
    used_norms = {
        item["legal_source"].norm
        for item in extract_answer_norms(cleaned)
    }
    used_marker_ids = set(re.findall(r"\[Источник\s+([1-9][0-9]*)\]", cleaned))
    used_sources = [
        item for item in offered
        if item.get("legal_source") is not None
        and (
            item["legal_source"].norm in used_norms
            or str(item.get("citation_id")) in used_marker_ids
        )
    ]
    links = []
    quotes = []
    for item in used_sources:
        source = item["legal_source"]
        norm = source.norm
        label = document_label(norm.document_key)
        if norm.article:
            label += f", статья {norm.article}"
        if norm.part:
            label += f", часть {norm.part}"
        if norm.point:
            label += f", пункт {norm.point}"
        marker = f"[Источник {item['citation_id']}]"
        link = f"[{label}]({source.source_url})" if source.source_url else label
        links.append(f"- {link} {marker}")
        if source.has_verified_excerpt:
            quotes.append((label, source.verbatim_excerpt))
    link_replacement = (
        "**Ссылка на статью/статьи:**\n\n" + "\n".join(links)
        if links
        else "**Ссылка на статью/статьи:**\n\nКонкретная статья в ответе не установлена."
    )
    if _LINK_SECTION_RE.search(cleaned):
        cleaned = _LINK_SECTION_RE.sub(lambda _: link_replacement + "\n\n", cleaned).strip()
    elif quotes:
        cleaned += "\n\n" + link_replacement

    quote_text = "\n\n".join(
        f"{label} — «{excerpt}»" if len(quotes) > 1 else f"«{excerpt}»"
        for label, excerpt in quotes
    )
    replacement = "**Цитата из статьи:**\n\n" + (
        quote_text or "Цитата не приведена: дословный текст статьи не получен из правового источника."
    )
    if _QUOTE_SECTION_RE.search(cleaned):
        cleaned = _QUOTE_SECTION_RE.sub(lambda _: replacement + "\n\n", cleaned).strip()
    elif quotes:
        cleaned = f"{cleaned}\n\n{replacement}".strip()
    cleaned = re.sub(
        r"(?m)(^-\s+[^\n]+)[ \t]+(\*\*Цитата из статьи:\*\*)",
        r"\1\n\n\2",
        cleaned,
    )
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


async def _consultation_sources(query: str, answer: str, local_sources: list[dict]) -> tuple[list[dict], list[dict]]:
    live = await resolve_live_legal_sources(query, answer, local_sources)
    # A fetched statute can supply the verified text missing from a local
    # summary. Retain the marker the assistant already used for that source.
    by_id = {str(item["citation_id"]): item for item in (*local_sources, *live)}
    return list(by_id.values()), live


@dataclass(frozen=True)
class NLPGenerateResult:
    text: str
    cached: bool
    usage: TokenUsage
    references: tuple[dict, ...] = ()


class NLPService:
    def __init__(self):
        self.temperature = 0.1
        # Сильно длинная история замедляет ответы и повышает риск повторов.
        # Берём хвост, чтобы сохранить последние факты/вопросы.
        self.max_history_chars = 6000

    async def generate_response(
        self,
        user_query: str,
        context: dict = None,
        chat_history: str = "",
        dialog_state: str = "",
    ) -> NLPGenerateResult:
        """Генерация ответа с автообновлением токена"""
        drafting = (is_document_generation_request(user_query)
                    or has_pending_document_clarification(chat_history))
        history_tail = (chat_history or "")[-self.max_history_chars :]
        cache_key = build_cache_key(
            user_query=user_query,
            context=context,
            chat_history=history_tail,
            dialog_state=("consultation-format-v7-article-links:" if drafting else "consultation-basis-v2:") + dialog_state,
        )
        cached = await response_cache.get(cache_key)
        if cached and not drafting:
            saved = unpack_review(cached)
            if saved is not None:
                text, refs = saved
                return NLPGenerateResult(text, True, TokenUsage(0, 0, 0, False), refs)
            if cached.strip() != LEGAL_SCOPE_REFUSAL and needs_basis_review(
                user_query, cached, (context or {}).get("rag_sources", [])
            ):
                cached = None
        local_sources = (context or {}).get("rag_sources", [])
        cached_sources = local_sources
        if cached and not drafting:
            cached_sources, _ = await _consultation_sources(user_query, cached, local_sources)
            cached = sanitize_consultation_quotes(cached, cached_sources)
        if (cached and not (drafting and cached.startswith("Не удалось оформить документ"))
                and not grounding_issues(cached, cached_sources)):
            return NLPGenerateResult(
                text=cached,
                cached=True,
                usage=TokenUsage(0, 0, 0, False),
                references=answer_references(cached, cached_sources),
            )

        client = await get_gigachat_client()
        context_str = format_chat_context(context)
        # User-controlled material must not be interpolated into the system role.
        system_prompt = (
            get_document_prompt("Определи по юридической просьбе пользователя", "", {})
            if drafting else get_system_prompt()
        )

        system_prompt += ("\nПри использовании закона или статьи указывай полную ссылку рядом с утверждением: "
                          "«ТК РФ, статья 10» либо «Федеральный закон от ДД.ММ.ГГГГ № НН-ФЗ, статья Н». "
                          "Для ГК РФ указывай часть кодекса и реквизиты закона, если это не часть первая. "
                          "Повторяй название закона или кодекса рядом с каждым номером статьи; не заменяй его словами «указанного закона». Не придумывай номера, даты и статьи. Не добавляй неиспользованные нормы ради списка.")
        system_prompt += ("\nПроверь предпосылки вопроса: названная пользователем статья может не регулировать этот случай. "
                          "Явно объясни ошибочную ссылку и укажи применимую норму. Различай право на выплату, размер и срок. "
                          "Не добавляй слово «рабочий» к сроку, если его нет в норме. "
                          "Не обобщай запрет увольнения по одному основанию на другие основания увольнения. "
                          "В разделе правовых оснований перечисли все нормы, на которых основаны выводы, а не только статью из вопроса.")
        if (context or {}).get("rag_sources"):
            system_prompt += ("\nЕсли используешь правовую норму из предоставленного источника, "
                              "укажи рядом с утверждением его метку [Источник N]. "
                              "Если у источника есть поле «Верифицированная дословная цитата», "
                              "приведи эту цитату в кавычках без изменения слов; цитата должна состоять из 1–2 предложений. "
                              "Не называй прямой цитатой авторское изложение и не заключай пересказ в кавычки. "
                              "Если дословная цитата не верифицирована, прямо скажи, что точный текст нормы по доступной базе не подтверждён. "
                              "Используй только метки предоставленных источников. "
                              "Полученный фрагмент, который не использован в ответе, не цитируй.")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps({"user_query": user_query, "context": context_str, "chat_history": history_tail, "dialog_state": dialog_state}, ensure_ascii=False)},
        ]

        try:
            completion = await client.chat_completion(
                messages,
                model=settings.llm_model,
                temperature=self.temperature,
                max_tokens=None if drafting else 800,
            )
        except RuntimeError as exc:
            if drafting or not isinstance(exc.__cause__, httpx.TransportError):
                raise
            quotes = await find_question_quotes(user_query)
            if not quotes:
                raise
            passages = [
                f"[{document_label(q.norm.document_key)}, статья {q.norm.article} · КонсультантПлюс]"
                f"({q.source_url}) — «{q.excerpt}»" for q in quotes
            ]
            text = "GigaChat сейчас недоступен. По вашему вопросу удалось найти текст закона.\n\n" + "\n\n".join(passages)
            return NLPGenerateResult(text, False, TokenUsage(0, 0, 0, False), answer_references(text, []))
        usage = completion.usage
        if (not drafting and completion.content.strip() != LEGAL_SCOPE_REFUSAL
                and needs_basis_review(user_query, completion.content, local_sources)):
            text, refs, usage = await check_reply(
                client, settings.llm_model, user_query, completion, local_sources, history_tail, context_str,
            )
            text = with_legal_disclaimer(text)
            if refs:
                await response_cache.set(cache_key, pack_review(text, refs))
            return NLPGenerateResult(text, False, usage, refs)
        offered = local_sources
        live_sources = []
        if not drafting:
            offered, live_sources = await _consultation_sources(user_query, completion.content, local_sources)
            if live_sources:
                live_context = format_live_legal_sources(live_sources)
                if live_context:
                    messages = messages + [{
                        "role": "user",
                        "content": (
                            "Дополнительные проверенные тексты статей, полученные из правового источника. "
                            "Используй их при исправлении ответа и не меняй дословные цитаты:\n\n"
                            + live_context
                        ),
                    }]
        # Repair an omitted legal basis once, using the same retrieved evidence.
        # Never infer that every retrieved norm was used in the answer.
        basis_retried = False
        # For newly fetched articles, insert the verified text directly. The
        # model need not repeat a successful answer just to copy a quotation.
        draft = sanitize_consultation_quotes(completion.content, offered) if live_sources else completion.content
        issues = grounding_issues(draft, offered)
        quote_issues = legal_quote_issues(draft, offered)
        non_quote_issues = [issue for issue in issues if issue not in quote_issues]
        can_repair_quote = bool(quote_issues and any(
            item["legal_source"].has_verified_excerpt for item in offered
        ))
        # A repair request is useful only when we have curated evidence to
        # repair against.  Without RAG sources, a second model call tends to
        # repeat or expand an answer instead of improving its legal basis.
        if (not drafting and offered
                and completion.content.strip() != LEGAL_SCOPE_REFUSAL
                and ((not any(r["legal_source"].norm.article for r in answer_references(completion.content, offered)))
                     or non_quote_issues or can_repair_quote)):
            basis_retried = True
            first = completion
            completion = await client.chat_completion(
                messages + [
                    {"role": "assistant", "content": first.content},
                    {"role": "user", "content": (
                        "Проверь правовое основание предыдущего ответа по предоставленным источникам. "
                        "Верни полный исправленный ответ: рядом с выводом назови закон и конкретную статью, "
                        "которая регулирует именно этот вопрос, и метку использованного источника. "
                        "Для источника с верифицированной дословной цитатой приведи её в кавычках без изменения слов; "
                        "цитата должна состоять из 1–2 предложений. Авторское изложение не цитируй как закон. "
                        "Если верифицированного текста нет, прямо укажи, что точный текст нормы не подтверждён. "
                        "Не подменяй статью о сроке статьёй о праве на выплату. Сохрани условия и исключения. "
                        "Метка источника должна соответствовать именно статье рядом с ней; проверь каждую метку. "
                        "Если основание не установлено, прямо сообщи об этом. Не придумывай нормы. "
                        + " Выявленные ошибки: " + "; ".join(issues)
                    )},
                ], model=settings.llm_model, temperature=0.0, max_tokens=800,
            )
            usage = TokenUsage(
                first.usage.prompt_tokens + completion.usage.prompt_tokens,
                first.usage.completion_tokens + completion.usage.completion_tokens,
                first.usage.total_tokens + completion.usage.total_tokens,
                first.usage.usage_estimated or completion.usage.usage_estimated,
            )
        if drafting and completion.content.strip() != LEGAL_SCOPE_REFUSAL and not is_valid_document_response(completion.content):
            first = completion
            completion = await client.chat_completion(
                messages + [
                    {"role": "assistant", "content": first.content},
                    {"role": "user", "content": DOCUMENT_FORMAT_RETRY},
                ], model=settings.llm_model, temperature=0.0,
                structured_function=DOCUMENT_DRAFT_FUNCTION,
            )
            usage = TokenUsage(
                first.usage.prompt_tokens + completion.usage.prompt_tokens,
                first.usage.completion_tokens + completion.usage.completion_tokens,
                first.usage.total_tokens + completion.usage.total_tokens,
                first.usage.usage_estimated or completion.usage.usage_estimated,
            )
        final_response = with_legal_disclaimer(
            process_document_response("Составь документ" if drafting else user_query, completion.content)
        )
        if not drafting:
            final_response = sanitize_consultation_quotes(final_response, offered)
        remaining_issues = grounding_issues(final_response, offered) if not drafting else []
        if remaining_issues:
            remaining_quote_issues = legal_quote_issues(final_response, offered)
            remaining_non_quote_issues = [issue for issue in remaining_issues
                                          if issue not in remaining_quote_issues]
            if not offered and remaining_quote_issues and not remaining_non_quote_issues:
                # The final sanitizer removes an unsupported model quotation.
                remaining_issues = []
        if remaining_issues:
            # Fail closed on a known contradiction rather than showing a confident
            # fabricated deadline after an unsuccessful model repair.
            excerpts = []
            unverified = []
            seen = set()
            used_articles = {(r["legal_source"].norm.document_key, r["legal_source"].norm.article)
                             for r in extract_answer_norms(completion.content) if r["legal_source"].norm.article}
            used_marker_ids = set(re.findall(r"\[Источник\s+([1-9][0-9]*)\]", completion.content))
            for item in offered:
                norm = item["legal_source"].norm
                if (used_articles and (norm.document_key, norm.article) not in used_articles
                        or (not used_articles and used_marker_ids
                            and str(item["citation_id"]) not in used_marker_ids)):
                    continue
                if norm in seen:
                    continue
                seen.add(norm)
                source = item["legal_source"]
                label = f"{document_label(norm.document_key)}, статья {norm.article} [Источник {item['citation_id']}]"
                if source.has_verified_excerpt:
                    excerpts.append(f"{label}\n«{source.verbatim_excerpt}»")
                else:
                    unverified.append(label)
            summary = _fallback_summary(completion.content)
            parts = ["**Кратко:** " + (
                f"{summary} Не все детали ответа удалось подтвердить по доступному тексту нормы."
                if summary else
                "По доступным проверенным источникам нельзя подтвердить все детали ответа."
            )]
            if excerpts:
                parts.append("**Ссылка на статью/статьи:**\n\n" + "\n".join(
                    f"- {item.splitlines()[0]}" for item in excerpts
                ))
                parts.append("**Цитата из статьи:**\n\n" + "\n\n".join(
                    item.split("\n", 1)[1] for item in excerpts
                ))
            if unverified:
                parts.append("**Ссылка на статью/статьи:**\n\n" + "\n".join(
                    f"- {item}" for item in unverified
                ))
                parts.append("**Цитата из статьи:**\n\nЦитата не приведена: дословный текст статьи не получен.")
            if not excerpts and not unverified:
                parts.append("Не удалось подтвердить правовое основание ответа по доступным источникам.")
            final_response = "\n\n".join(parts)
        if not drafting and has_mismatched_source_markers(final_response, offered):
            # A failed repair must not expose a source label as verified support.
            final_response = re.sub(r"\[Источник\s+\d+\]", "", final_response)
            final_response += "\n\n**Требуется проверка:** ссылки на источники не удалось согласовать с указанными статьями."
        references = answer_references(final_response, offered)
        if not drafting:
            visible = {r["legal_source"].norm for r in extract_answer_norms(final_response)}
            missing = [r["legal_source"].norm for r in references
                       if r.get("origin") != "assistant_citation"
                       and r["legal_source"].norm.article and r["legal_source"].norm not in visible]
            if missing:
                # Include the main rule already cited in the body as well as
                # additional sourced rules; an addendum must not mislabel the basis.
                missing = list(dict.fromkeys(
                    r["legal_source"].norm for r in references
                    if r.get("origin") != "assistant_citation"
                    and r["legal_source"].norm.article
                ))
                missing = [norm for norm in missing if norm.part or norm.point or not any(
                    other.document_key == norm.document_key and other.article == norm.article
                    and (other.part or other.point) for other in missing)]
                source_by_norm = {
                    item["legal_source"].norm: item
                    for item in offered if item["legal_source"].has_verified_excerpt
                }
                basis_lines = []
                for norm in missing:
                    line = (f"{document_label(norm.document_key)}, статья {norm.article}"
                            + (f", часть {norm.part}" if norm.part else "")
                            + (f", пункт {norm.point}" if norm.point else ""))
                    item = source_by_norm.get(norm)
                    if item:
                        line += f" [Источник {item['citation_id']}]: «{item['legal_source'].verbatim_excerpt}»"
                    else:
                        line += ": точный текст нормы по доступной базе не подтверждён"
                    basis_lines.append(line)
                final_response += "\n\n**Правовое основание:**\n" + "\n".join(f"- {line}" for line in basis_lines)
            if basis_retried and not any(r["legal_source"].norm.article for r in references):
                final_response += "\n\n**Требуется проверка:** не удалось установить конкретную статью, обосновывающую этот ответ."
        if not drafting:
            final_response = sanitize_consultation_quotes(final_response, offered)
            references = answer_references(final_response, offered)
        if not drafting and not any(item.get("origin") != "assistant_citation" for item in references):
            final_response = re.sub(r"(\*\*Уверенность:\*\*\s*)высокая", r"\1средняя", final_response, flags=re.IGNORECASE)
        if ((not drafting and not (basis_retried and not references))
                or (drafting and is_valid_document_response(completion.content))
                or completion.content.strip() == LEGAL_SCOPE_REFUSAL):
            await response_cache.set(cache_key, final_response)
        return NLPGenerateResult(
            text=final_response,
            cached=False,
            usage=usage,
            references=references,
        )
