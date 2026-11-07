"""Opt-in full flood interview, real GigaChat editor and reproducible DOCX QA."""
import asyncio
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.document_workflow import new_state, advance_interview, pending_fields
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import render_package_blocks, format_template_fields
from app.services.document_drafting import prepare_document_draft, presentation_fields, DraftPreparationError
from app.services.document_quality import quality_issues
from app.services.document_schema import readiness_report
from app.services.document_workflow_docx import build_legal_docx
from app.services.gigachat_client import get_gigachat_client
from app.services.document_export_contract import validate_export_blocks

ANSWERS = {
    'sender': 'Иванова Мария Андреевна', 'sender_address': 'Екатеринбург, Ленина 25, 12',
    'sender_details': 'не знаю', 'recipient': 'Кузнецов Сергей Викторович',
    'recipient_address': 'квартира № 16 в том же доме', 'recipient_details': 'не знаю',
    'court': 'не знаю', 'property_address': 'мой адрес',
    'property_right': 'Я собственник квартиры, право подтверждается выпиской ЕГРН.',
    'flood_date': '12.10.2026', 'source_address': 'адрес ответчика',
    'source_relation': 'Ответчик является собственником квартиры, это указано в выписке ЕГРН.',
    'damage_object': 'Повреждены потолок, обои и ламинат в комнате.',
    'facts': 'По акту управляющей компании от 12.10.2026 причиной залива стала протечка шланга стиральной машины в квартире ответчика.',
    'restoration': 'ремонт ещё не выполнен',
    'restoration_estimate': 'Восстановление потолка, обоев и ламината оценено в 145000 рублей, имеется отчёт оценщика от 15.10.2026.',
    'amount': '145000 рублей',
    'calculation': 'По отчёту оценщика от 15.10.2026 стоимость восстановительного ремонта составляет 145000 рублей. Возмещения не было.',
    'evidence': 'Есть акт от управляющей компании, отчёт оценщика и фото',
    'pretrial': 'Письменную претензию направила ответчику 16.10.2026, ответа пока нет.',
    'litigation_costs': 'нет', 'expertise': 'нет', 'security': 'нет',
    'requests': 'только возмещение ущерба', 'other_participants': 'нет', 'copy_status': 'предстоит',
    'attachments': 'Акт осмотра, фотографии, отчёт оценщика, выписка ЕГРН, копия претензии, подтверждение отправки претензии',
    'date': '18.10.26', 'signature': 'Иванова Мария Андреевна',
}


async def main():
    state = new_state('Нужен иск о возмещении ущерба от залива квартиры: сосед сверху затопил жильё, ущерб 145 тысяч рублей')
    state, reply, _ = await advance_interview(state, state['request'])
    transcript = []
    for _ in range(70):
        if not pending_fields(state): break
        key = state['last_questions'][0]
        value = 'да' if state['fields'].get(key, {}).get('address_candidate') else ANSWERS[key]
        state, reply, _ = await advance_interview(state, value)
        transcript.append({'field': key, 'answer': value, 'reply': reply})
        if state.get('provider_failure'): raise RuntimeError('Interview provider failed')
        print('INTAKE', key, state['fields'].get(key, {}).get('status'), flush=True)
    assert not pending_fields(state) and state['phase'] == 'ready'
    assert not quality_issues(state), quality_issues(state)
    assert state['fields']['recipient_address']['value'].endswith('д. 25, кв. 16')
    client = await get_gigachat_client()
    completion = client.chat_completion
    traces = []
    async def visible_completion(*args, **kwargs):
        result = await completion(*args, **kwargs)
        payload = json.loads(args[0][1]['content'])
        traces.append({'field': payload.get('field', 'review'), 'text': result.content})
        print('EDITOR_REPLY', len(result.content), flush=True)
        return result
    client.chat_completion = visible_completion
    for attempt in range(2):
        try:
            state, _ = await prepare_document_draft(state, client)
            break
        except DraftPreparationError as error:
            state = error.partial_state
            print('EDITOR_RETRY', error.keys, flush=True)
            folder = Path(__file__).parent / 'schema_qa'
            folder.mkdir(exist_ok=True)
            (folder / 'editor-traces.json').write_text(json.dumps(traces, ensure_ascii=False, indent=2), encoding='utf-8')
            if attempt: raise
    scenario = SCENARIOS[state['scenario']]
    fields = presentation_fields(state)
    blocks = render_package_blocks(state['text_package'], scenario, fields, format_template_fields(scenario, fields))
    validate_export_blocks(blocks)
    folder = Path(__file__).parent / 'schema_qa'
    folder.mkdir(exist_ok=True)
    (folder / 'flood-live.docx').write_bytes(build_legal_docx(scenario.title, blocks, review_note='Проект. Требуется проверка юристом.'))
    report = readiness_report(state, state['text_package'])
    (folder / 'flood-live.json').write_text(json.dumps({'readiness': report, 'state': state, 'transcript': transcript}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'result': 'ok', 'turns': len(transcript), 'document': str(folder / 'flood-live.docx'), 'readiness': report}, ensure_ascii=False), flush=True)


if __name__ == '__main__': asyncio.run(main())
