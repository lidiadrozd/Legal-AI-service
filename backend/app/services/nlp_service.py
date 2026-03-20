"""
NLP Service с автоматическим GigaChat токеном
"""
import asyncio
from langchain.schema import HumanMessage, SystemMessage
from langchain_gigachat import GigaChat
from app.core.prompts import get_system_prompt
from app.services.gigachat_client import get_gigachat_client

class NLPService:
    def __init__(self):
        self.model = "GigaChat-Pro"
        self.temperature = 0.1
    
    async def _get_llm(self) -> GigaChat:
        """Получаем LLM с валидным токеном"""
        client = await get_gigachat_client()
        token = await client.get_valid_token()
        
        return GigaChat(
            credentials=token,
            model=self.model,
            temperature=self.temperature,
            verify_ssl_certs=False  # Для разработки
        )
    
    async def generate_response(
        self,
        user_query: str,
        context: dict = None,
        chat_history: str = ""
    ) -> str:
        """Генерация ответа с автообновлением токена"""
        llm = await self._get_llm()
        system_prompt = get_system_prompt(context or {}, chat_history, user_query)
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_query)
        ]
        
        response = await llm.agenerate_messages([messages])
        return response.generations[0][0].text
