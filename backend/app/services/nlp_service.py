"""
NLP Service: GigaChat через REST chat/completions (OAuth как в примерах Сбера).
"""

from app.core.config import settings
from app.core.prompts import get_system_prompt
from app.services.gigachat_client import get_gigachat_client


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
    ) -> str:
        """Генерация ответа с автообновлением токена"""
        client = await get_gigachat_client()
        history_tail = (chat_history or "")[-self.max_history_chars :]
        system_prompt = get_system_prompt(
            context or {}, history_tail, user_query, dialog_state=dialog_state
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query},
        ]

        return await client.chat_completion(
            messages,
            model=settings.GIGACHAT_MODEL,
            temperature=self.temperature,
        )

