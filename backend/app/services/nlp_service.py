"""
NLP Service с автоматическим GigaChat токеном
"""

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_gigachat.chat_models import GigaChat

from app.core.prompts import get_system_prompt
from app.services.gigachat_client import get_gigachat_client

class NLPService:
    def __init__(self):
        self.model = "GigaChat-Pro"
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
            verify_ssl_certs=False  # Для разработки
        )
    
    async def generate_response(
        self,
        user_query: str,
        context: dict = None,
        chat_history: str = "",
        dialog_state: str = "",
    ) -> str:
        """Генерация ответа с автообновлением токена"""
        llm = await self._get_llm()
        history_tail = (chat_history or "")[-self.max_history_chars :]
        system_prompt = get_system_prompt(context or {}, history_tail, user_query, dialog_state=dialog_state)
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_query),
        ]

        response = await llm.ainvoke(messages)
        return response.content

