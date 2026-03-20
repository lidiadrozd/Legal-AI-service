from typing import Optional, Dict
from langchain_gigachat import GigaChat
from langchain.schema import HumanMessage, SystemMessage
from app.core.prompts import get_system_prompt
from app.core.config import settings

class NLPService:
    def __init__(self):
        self.llm = GigaChat(
            credentials=settings.GIGACHAT_API_KEY,
            model=settings.GIGACHAT_MODEL,  # "GigaChat-Pro"
            temperature=0.1,
            verify_ssl_certs=False
        )

    async def generate_response(
        self,
        user_query: str,
        context: Optional[Dict] = None,
        chat_history: str = ""
    ) -> str:
        system_prompt = get_system_prompt(context or {}, chat_history, user_query)
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_query)
        ]
        
        response = await self.llm.agenerate_messages([messages])
        return response.generations[0][0].text
