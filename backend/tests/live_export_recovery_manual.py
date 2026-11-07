"""Opt-in real HTTP and GigaChat checks; only synthetic data is created/deleted."""
import asyncio
from io import BytesIO
import json
from pathlib import Path
import re
import secrets
import httpx
from docx import Document as WordDocument
from sqlalchemy import delete, select
from app.core.security import create_access_token, get_password_hash
from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.models.document import Document

CASES = [
    ('motion_postpone', 'Нужно ходатайство об отложении судебного заседания: я ответчик, не могу прийти из-за госпитализации', {
        'recipient': 'ООО МастерДом', 'procedure': 'Спор об оплате ремонта личной квартиры',
        'court': 'Кировский районный суд г. Екатеринбурга', 'case_number': 'аа вот нашла: 2-2451/2026',
        'hearing_date': '10.11.2026', 'reasons': 'Нахожусь в больнице с 9 по 14 ноября 2026 года, есть справка',
        'requests': 'Перенести заседание на дату после выписки', 'copy_notice': 'нет ещё',
        'other_participants': 'нет', 'attachments': 'справка из больницы',
    }),
    ('complaint_labor_agency', 'Нужно составить жалобу в трудовую инспекцию: после увольнения работодатель не выплатил зарплату 100 тысяч рублей', {
        'recipient': 'Государственная инспекция труда', 'recipient_address': 'не знаю',
        'employer': 'ООО СеверСервис', 'employer_address': 'Екатеринбург, Мира 44',
        'facts': 'Работал кладовщиком с 1 февраля по 20 октября 2026 года по трудовому договору',
        'violation': 'Зарплата за октябрь 2026 года в размере 100000 рублей не выплачена при увольнении 20 октября 2026 года',
        'previous_contact': 'К работодателю с письменным заявлением не обращался',
        'requests': 'Проверить обстоятельства невыплаты и принять меры в пределах полномочий инспекции',
        'attachments': 'Есть трудовой договор, приказ об увольнении, расчётный листок и банковская выписка',
    }),
]

async def main():
    email = f'recovery-probe-{secrets.token_hex(6)}@example.com'
    async with AsyncSessionLocal() as db:
        user = User(email=email, full_name='Тест восстановления', hashed_password=get_password_hash(secrets.token_hex(20)),
                    is_active=True, consent_given=True)
        db.add(user)
        await db.commit()
        uid = user.id
    try:
        async with httpx.AsyncClient(base_url='http://127.0.0.1:8000', trust_env=False, timeout=180,
                headers={'Authorization': 'Bearer ' + create_access_token({'sub': email})}) as client:
            for scenario, prompt, overrides in CASES:
                answers = {'sender': 'Иванов Иван Иванович', 'sender_address': 'Екатеринбург, Мира 10, кв. 79',
                    'recipient_address': 'не знаю', 'party_details': 'не знаю', 'date': '25.10.2026',
                    'signature': 'Иванов Иван Иванович', **overrides}
                response = await client.post('/documents/interviews', json={'prompt': prompt, 'output_format': 'docx'})
                response.raise_for_status()
                cid = response.json()['chat_id']
                seen = {}
                file_id = None
                for step in range(30):
                    response = await client.get(f'/documents/interviews/{cid}')
                    response.raise_for_status()
                    state = response.json()
                    assert state['scenario'] == scenario, state['scenario']
                    if state['phase'] == 'ready' and file_id: break
                    keys = state.get('last_questions', [])
                    assert len(keys) == 1, {k: state.get(k) for k in ('phase','draft_error','draft_failure_fields')}
                    key = keys[0]
                    seen[key] = seen.get(key, 0) + 1
                    assert seen[key] <= 2, key
                    response = await client.post(f'/chat/{cid}/send_stream', json={'content': answers.get(key, 'не знаю')})
                    response.raise_for_status()
                    chunks = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: {')]
                    reply = ''.join(item.get('content', '') for item in chunks)
                    assert 'аренду' not in reply.casefold() and 'договора аренды' not in reply.casefold(), reply
                    link = re.search(r'\]\(/documents/([0-9a-f-]{36})/download\)', reply)
                    if link: file_id = link[1]
                    print(scenario, step, key, 'file' if link else 'next', flush=True)
                assert file_id, 'No real file delivered'
                response = await client.get(f'/documents/{file_id}/download')
                response.raise_for_status()
                doc = WordDocument(BytesIO(response.content))
                text = '\n'.join(p.text for p in doc.paragraphs)
                assert 'Иванов Иван Иванович' in text and '{{' not in text
                assert not re.search(r'\[(?:ДАННЫЕ|СУММА|ДАТА|ФИО)_', text), 'Internal model marker leaked'
                if scenario == 'motion_postpone':
                    assert '2-2451/2026' in text and 'не направлены' in text and '14' in text
                    assert 'ремонт' not in text.casefold() and 'аа вот' not in text.casefold()
                    assert 'заявитель просит' not in text.casefold()
                else:
                    assert 'СеверСервис' in text and '100000' in text
                    assert 'аренд' not in text.casefold()
                    assert 'Работодатель:' in text
                    assert 'Кому: Государственная инспекция труда' in text
                    assert 'Работодатель: Иванов' not in text
                    assert 'Прошу рассмотреть изложенные' not in text
                Path(f'/app/tests/live_{scenario}_recovery.docx').write_bytes(response.content)
                print('SUCCESS', scenario, 'turns', step, 'bytes', len(response.content), flush=True)
    finally:
        async with AsyncSessionLocal() as db:
            paths = (await db.execute(select(Document.file_path).where(Document.user_id == uid))).scalars().all()
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()
            for path in paths:
                if path: Path(path).unlink(missing_ok=True)

if __name__ == '__main__': asyncio.run(main())
