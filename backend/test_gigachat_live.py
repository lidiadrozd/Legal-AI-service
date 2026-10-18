
import asyncio

from app.core.config import settings
from app.services.gigachat_client import get_gigachat_client


async def main():
    client = await get_gigachat_client()

    response = await client.chat_completion(
        messages=[
            {
                "role": "system",
                "content": (
                    "Определи, относится ли изменение закона к пользователю. "
                    'Верни только JSON: {"relevant": true, "reason": "причина"} '
                    "или такой же JSON с relevant=false."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Изменение: изменились сроки уплаты страховых взносов ИП. "
                    "Пользователь: индивидуальный предприниматель, "
                    "интересуется налогами и страховыми взносами."
                ),
            },
        ],
        model=settings.GIGACHAT_MODEL,
        temperature=0.1,
    )

    print("Ответ GigaChat:")
    print(response.content)


if __name__ == "__main__":
    asyncio.run(main())