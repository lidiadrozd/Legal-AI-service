"""Real HTTP + GigaChat regression; only disposable synthetic user data."""
import asyncio
from pathlib import Path
from io import BytesIO
import json
import re
import secrets

import httpx
from docx import Document as WordDocument
from sqlalchemy import delete, select
from app.core.security import create_access_token, get_password_hash
from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.models.document import Document


async def main():
    email = 'controller-' + secrets.token_hex(8) + '@example.com'
    async with AsyncSessionLocal() as db:
        user = User(email=email, full_name='Тест контроллера', hashed_password=get_password_hash(secrets.token_hex(24)),
                    is_active=True, consent_given=True)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        uid = user.id
    try:
        async with httpx.AsyncClient(base_url='http://127.0.0.1:8000', trust_env=False, timeout=180,
                                     headers={'Authorization': 'Bearer ' + create_access_token({'sub': email})}) as client:
            async def send(cid, text):
                response = await client.post(f'/chat/{cid}/send_stream', json={'content': text})
                response.raise_for_status()
                answer = ''.join(json.loads(line[6:]).get('content', '') for line in response.text.splitlines() if line.startswith('data: {'))
                assert 'Ошибка GigaChat' not in answer and 'Ваш ответ сохранён.' not in answer, answer
                return answer
            response = await client.post('/documents/interviews', json={'prompt': 'Жалоба на товар с истекшим сроком годности', 'output_format': 'docx'})
            response.raise_for_status()
            cid = response.json()['chat_id']
            await send(cid, 'Продавцу в магазин')
            answers = {'sender': 'Петров Иван Сергеевич', 'sender_address': 'Мира 45', 'recipient': 'Магазин Ромашка',
                'recipient_address': 'Сам магазин на Блюхера 41, екатеринбург',
                'purchase': 'Замороженная сёмга для личных нужд за 500 рублей, 20.10.2026, в магазине Ромашка',
                'defect': 'После покупки обнаружен истёкший срок годности на упаковке. Экспертиза не проводилась.',
                'goods_category': 'Замороженные продукты, рыба', 'consumer_status': 'Для личных нужд',
                'facts': 'При покупке сёмги 20.10.2026 срок годности уже истёк; стоимость составила 500 рублей.',
                'requests': 'Вернуть 500 рублей за сёмгу', 'payment_details': 'не знаю',
                'attachments': 'Копия кассового чека, фотография упаковки', 'date': '24.10.2026', 'signature': 'Петров Иван Сергеевич'}
            helped = False
            final = ''
            seen = {}
            for _ in range(25):
                state = (await client.get(f'/documents/interviews/{cid}')).json()
                if state['phase'] == 'ready': break
                key = state['last_questions'][0]
                seen[key] = seen.get(key, 0) + 1
                assert seen[key] <= 2, ('loop', key)
                if key == 'goods_category' and not helped:
                    answer = await send(cid, 'Поясни, что здесь указать?')
                    after_help = (await client.get(f'/documents/interviews/{cid}')).json()
                    assert after_help['last_questions'] == [key] and 'госпошлин' not in answer.lower()
                    assert '500' in after_help['fields']['purchase']['value']
                    answer = await send(cid, 'Хорошо')
                    after_ack = (await client.get(f'/documents/interviews/{cid}')).json()
                    assert after_ack['last_questions'] == [key]
                    assert 'госпошлин' not in answer.lower() and answer.count('?') <= 1
                    helped = True
                final = await send(cid, answers.get(key, 'не знаю'))
                state = (await client.get(f'/documents/interviews/{cid}')).json()
                if key == 'sender_address' and state['last_questions'] == [key]:
                    await send(cid, 'Екатеринбург')
                print(json.dumps({'step': key, 'next': state.get('last_questions'), 'phase': state['phase']}, ensure_ascii=False), flush=True)
            assert state['phase'] == 'ready' and helped
            assert state['fields']['amount']['value'] == '500.00'
            assert state['fields']['goods_category']['value'] == 'Замороженные продукты, рыба'
            link = re.search(r'/documents/([0-9a-f-]{36})/download', final)
            assert link, final
            response = await client.get(link[0])
            response.raise_for_status()
            doc = WordDocument(BytesIO(response.content))
            text = '\n'.join(p.text for p in doc.paragraphs)
            assert '500 рублей' in text and 'Ромашка' in text and '{{' not in text
            print('SUCCESS: complaint destination -> intake -> help -> acknowledgement -> same field -> next field -> actual DOCX download', flush=True)
    finally:
        async with AsyncSessionLocal() as db:
            paths = (await db.execute(select(Document.file_path).where(Document.user_id == uid))).scalars().all()
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()
            for file in paths:
                if file: Path(file).unlink(missing_ok=True)

if __name__ == '__main__': asyncio.run(main())
