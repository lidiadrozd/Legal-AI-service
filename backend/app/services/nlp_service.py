"""
NLP Service: GigaChat через REST chat/completions (OAuth как в примерах Сбера).
"""

from dataclasses import dataclass

from app.core.config import settings
from app.core.legal_disclaimer import with_legal_disclaimer
from app.core.prompts import format_chat_context, get_system_prompt
from app.services.document_draft_validator import process_document_response
from app.services.gigachat_client import get_gigachat_client
from app.services.llm_cost import TokenUsage
from app.services.response_cache import build_cache_key, response_cache


@dataclass(frozen=True)
class NLPGenerateResult:
    text: str
    cached: bool
    usage: TokenUsage


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
        history_tail = (chat_history or "")[-self.max_history_chars :]
        cache_key = build_cache_key(
            user_query=user_query,
            context=context,
            chat_history=history_tail,
            dialog_state=dialog_state,
        )
        cached = await response_cache.get(cache_key)
        if cached:
            return NLPGenerateResult(
                text=cached,
                cached=True,
                usage=TokenUsage(0, 0, 0, False),
            )

        client = await get_gigachat_client()
        context_str = format_chat_context(context)
        system_prompt = get_system_prompt(
            context_str,
            history_tail,
            user_query,
            dialog_state=dialog_state,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query},
        ]

        completion = await client.chat_completion(
            messages,
            model=settings.GIGACHAT_MODEL,
            temperature=self.temperature,
        )
        final_response = with_legal_disclaimer(
            process_document_response(user_query, completion.content)
        )
        await response_cache.set(cache_key, final_response)
        return NLPGenerateResult(
            text=final_response,
            cached=False,
            usage=completion.usage,
        )
