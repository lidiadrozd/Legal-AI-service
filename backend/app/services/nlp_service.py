"""
NLP Service с автоматическим GigaChat токеном
"""

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_gigachat.chat_models import GigaChat
import re

from app.core.prompts import get_system_prompt
from app.core.config import settings
from app.services.gigachat_client import get_gigachat_client
from app.utils.text import capitalize_first_letter


class NLPService:
    def __init__(self):
        self.model = settings.GIGACHAT_MODEL or "GigaChat-Pro"
        self.temperature = 0.1
        # Сильно длинная история замедляет ответы и повышает риск повторов.
        # Берём хвост, чтобы сохранить последние факты/вопросы.
        self.max_history_chars = 6000

    async def _get_llm(self) -> GigaChat:
        """Получаем LLM с валидным токеном"""
        client = await get_gigachat_client()
        token = await client.get_valid_token()

        return GigaChat(
            access_token=token,
            model=self.model,
            temperature=self.temperature,
            verify_ssl_certs=False,  # Для разработки
        )

    async def generate_response(
        self,
        user_query: str,
        context: str = "",
        chat_history: str = "",
        dialog_state: str = "",
    ) -> str:
        """Генерация ответа с автообновлением токена"""
        if not (settings.GIGACHAT_CLIENT_ID and settings.GIGACHAT_CLIENT_SECRET):
            return (
                "GigaChat не настроен: укажите GIGACHAT_CLIENT_ID и GIGACHAT_CLIENT_SECRET в .env "
                "и перезапустите backend."
            )
        llm = await self._get_llm()
        history_tail = (chat_history or "")[-self.max_history_chars :]
        ctx = (context or "").strip() or "—"
        system_prompt = get_system_prompt(ctx, history_tail, user_query, dialog_state=dialog_state)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_query),
        ]

        response = await llm.ainvoke(messages)
        return response.content

    async def generate_chat_title(self, user_query: str) -> str:
        """
        Генерация короткого названия темы диалога.
        Используется один раз при первом сообщении в чате.
        """
        llm = await self._get_llm()

        system_prompt = (
            "Ты — ассистент, который придумывает короткие названия для чатов.\n"
            "Задача: по тексту пользователя сгенерируй ТОЛЬКО название темы диалога.\n"
            "Требования:\n"
            "- язык: русский\n"
            "- длина: 3–7 слов\n"
            "- стиль: нейтральный, как в обычных чатах с нейросетями\n"
            "- без кавычек, без двоеточий, без точки в конце\n"
            "- не повторяй целиком фразу пользователя; перефразируй кратко\n"
            "- верни только название (plain text)"
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_query or ""),
        ]
        response = await llm.ainvoke(messages)
        raw = (response.content or "").strip()

        # Убираем возможные кавычки/служебные префиксы
        raw = raw.strip().strip('"').strip("'").strip()
        raw = re.sub(r"^(тема|название|заголовок)\s*[:-]\s*", "", raw, flags=re.IGNORECASE)
        raw = raw.replace("\n", " ").strip()

        # Мягкая нормализация длины для UI/БД
        if len(raw) > 70:
            raw = raw[:70].rsplit(" ", 1)[0].strip()
        out = capitalize_first_letter(raw) if raw else ""
        return out or "Правовой вопрос"
