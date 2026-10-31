"""
NLP Service: GigaChat через REST chat/completions (OAuth как в примерах Сбера).
"""

import json
import re
from dataclasses import dataclass

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
from app.services.llm_cost import TokenUsage
from app.services.answer_norms import answer_references, extract_answer_norms, document_label, has_mismatched_source_markers, grounding_issues
from app.services.response_cache import build_cache_key, response_cache


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
            dialog_state="document-clarifications-v3:" + dialog_state,
        )
        cached = await response_cache.get(cache_key)
        if (cached and not (drafting and cached.startswith("Не удалось оформить документ"))
                and not grounding_issues(cached, (context or {}).get("rag_sources", []))):
            return NLPGenerateResult(
                text=cached,
                cached=True,
                usage=TokenUsage(0, 0, 0, False),
                references=answer_references(cached, (context or {}).get("rag_sources", [])),
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
                              "Используй только метки предоставленных источников. "
                              "Полученный фрагмент, который не использован в ответе, не цитируй.")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps({"user_query": user_query, "context": context_str, "chat_history": history_tail, "dialog_state": dialog_state}, ensure_ascii=False)},
        ]

        completion = await client.chat_completion(
            messages,
            model=settings.GIGACHAT_MODEL,
            temperature=self.temperature,
        )
        usage = completion.usage
        offered = (context or {}).get("rag_sources", [])
        # Repair an omitted legal basis once, using the same retrieved evidence.
        # Never infer that every retrieved norm was used in the answer.
        basis_retried = False
        issues = grounding_issues(completion.content, offered)
        if (not drafting and completion.content.strip() != LEGAL_SCOPE_REFUSAL
                and ((offered and not any(r["legal_source"].norm.article for r in answer_references(completion.content, offered)))
                     or issues)):
            basis_retried = True
            first = completion
            completion = await client.chat_completion(
                messages + [
                    {"role": "assistant", "content": first.content},
                    {"role": "user", "content": (
                        "Проверь правовое основание предыдущего ответа по предоставленным источникам. "
                        "Верни полный исправленный ответ: рядом с выводом назови закон и конкретную статью, "
                        "которая регулирует именно этот вопрос, и метку использованного источника. "
                        "Не подменяй статью о сроке статьёй о праве на выплату. Сохрани условия и исключения. "
                        "Метка источника должна соответствовать именно статье рядом с ней; проверь каждую метку. "
                        "Если основание не установлено, прямо сообщи об этом. Не придумывай нормы. "
                        + " Выявленные ошибки: " + "; ".join(issues)
                    )},
                ], model=settings.GIGACHAT_MODEL, temperature=0.0,
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
                ], model=settings.GIGACHAT_MODEL, temperature=0.0,
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
        remaining_issues = grounding_issues(final_response, offered) if not drafting else []
        if remaining_issues:
            # Fail closed on a known contradiction rather than showing a confident
            # fabricated deadline after an unsuccessful model repair.
            excerpts = []
            seen = set()
            used_articles = {(r["legal_source"].norm.document_key, r["legal_source"].norm.article)
                             for r in extract_answer_norms(completion.content) if r["legal_source"].norm.article}
            for item in offered:
                norm = item["legal_source"].norm
                if used_articles and (norm.document_key, norm.article) not in used_articles:
                    continue
                if norm in seen:
                    continue
                seen.add(norm)
                excerpts.append(f"{document_label(norm.document_key)}, статья {norm.article} [Источник {item['citation_id']}]\n{item['text']}")
            final_response = ("Не удалось согласовать полный ответ с проверенными источниками. "
                              "Ниже приведены доступные фрагменты; применимость к вашей ситуации требует проверки.\n\n"
                              + "\n\n".join(excerpts)) if excerpts else "Не удалось подтвердить правовое основание ответа по доступным источникам. Для надёжного вывода требуется проверка применимых норм и обстоятельств."
        if not drafting and has_mismatched_source_markers(final_response, offered):
            # A failed repair must not expose a source label as verified support.
            final_response = re.sub(r"\[Источник\s+\d+\]", "", final_response)
            final_response += "\n\n**Требуется проверка:** ссылки на источники не удалось согласовать с указанными статьями."
        references = answer_references(final_response, (context or {}).get("rag_sources", []))
        if not drafting:
            visible = {r["legal_source"].norm for r in extract_answer_norms(final_response)}
            missing = [r["legal_source"].norm for r in references
                       if r.get("origin") != "assistant_citation"
                       and r["legal_source"].norm.article and r["legal_source"].norm not in visible]
            if missing:
                # Include the main rule already cited in the body as well as
                # additional sourced rules; an addendum must not mislabel the basis.
                missing = list(dict.fromkeys(r["legal_source"].norm for r in references
                                             if r["legal_source"].norm.article))
                missing = [norm for norm in missing if norm.part or norm.point or not any(
                    other.document_key == norm.document_key and other.article == norm.article
                    and (other.part or other.point) for other in missing)]
                final_response += "\n\n**Правовое основание:** " + "; ".join(
                    f"{document_label(norm.document_key)}, статья {norm.article}"
                    + (f", часть {norm.part}" if norm.part else "")
                    + (f", пункт {norm.point}" if norm.point else "") for norm in missing
                ) + "."
            if basis_retried and not any(r["legal_source"].norm.article for r in references):
                final_response += "\n\n**Требуется проверка:** не удалось установить конкретную статью, обосновывающую этот ответ."
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
