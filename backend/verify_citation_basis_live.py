"""Single local citation check; disposable account, no changes to real chats."""
import json
from pathlib import Path
from uuid import uuid4
import httpx
from verify_new_chat_browser import backend

data = backend('seed', {})
report = {}
try:
    with httpx.Client(base_url='http://127.0.0.1:3000/api', trust_env=False,
                     headers={'Authorization': 'Bearer ' + data['token']}, timeout=180) as client:
        response = client.post('/chat/new')
        response.raise_for_status()
        chat_id = response.json()['id']
        answer = ''
        with client.stream('POST', f'/chat/{chat_id}/send_stream', json={
            'chat_id': chat_id,
            'content': 'В какой срок работодатель должен выплатить компенсацию за неиспользованный отпуск при увольнении по ст. 127 ТК РФ, если работник отработал менее 3 месяцев?\nКонтроль: ' + uuid4().hex,
        }) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line.startswith('data: ') and line[6:] != '[DONE]':
                    answer += json.loads(line[6:]).get('content', '')
        inspected = backend('inspect', {'user_id': data['user_id']})
        report = {
            'article_140_visible': '140' in answer and 'ТК РФ' in answer,
            'external_error': 'Ошибка GigaChat' in answer or 'GigaChat HTTP' in answer,
            'answer_saved': inspected['assistant_saved'],
            'saved_reference_count': inspected['saved_references'],
            'cache_used': inspected['model_cache_used'],
            'answer': answer,
        }
finally:
    backend('cleanup', {'user_id': data['user_id']})
    report['temporary_account_deleted'] = True
    Path('docs/citation_basis_live_check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'answer'}, ensure_ascii=False))
