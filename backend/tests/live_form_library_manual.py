"""Opt-in synthetic interviews and DOCX QA using the configured real GigaChat.

Run in the API container; never writes to real conversations or customer data.
"""
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

COMMON = dict(sender='Иванова Ирина Фёдоровна', sender_address='Екатеринбург Мира 33 67',
    sender_details='не знаю', recipient='Горева Мира Юрьевна', recipient_address='Екатеринбург, Мира 50, 70',
    recipient_details='не знаю', place='Екатеринбург', date='27.10.2026',
    signature='Иванова Ирина Фёдоровна', counterparty_signature='Горева Мира Юрьевна',
    additional_terms='нет', attachments='нет')
HOUSING = dict(COMMON, property='Екатеринбург, Мира 33, 67',
    property_description='Квартира площадью 45 квадратных метров, две комнаты.',
    ownership='Право собственности подтверждается выпиской ЕГРН.', residents='нет',
    start_date='01.11.26', term='на 2 года', amount='45000',
    payment='перевод на банковский счёт наймодателя до 5 числа каждого месяца',
    utilities='наниматель оплачивает воду и электричество по счётчикам, остальные платежи оплачивает наймодатель',
    deposit='нет', handover='Квартира передаётся 01.11.2026 по акту с описью имущества, ключей и показаний счётчиков.',
    repairs='текущий ремонт делает наниматель за свой счёт, капитальный ремонт делает наймодатель',
    access='наймодатель может прийти по предварительному согласованию с нанимателем',
    liability='Стороны отвечают за причинённый ими ущерб в соответствии с законом.',
    termination='Изменение и расторжение договора оформляются письменным соглашением сторон.',
    return_terms='В день прекращения договора наниматель возвращает квартиру, имущество и ключи по акту.')
COMPLAINT = dict(sender='Смирнова Анна Павловна', sender_address='Екатеринбург, Мира 18, 24',
    contacts='Ответ прошу направить по почтовому адресу заявителя.',
    recipient='Управление Роспотребнадзора по Свердловской области', recipient_address='не известен',
    seller='Магазин «Пример»', seller_address='Екатеринбург, Блюхера 44',
    purchase='Я купила йогурт 22 октября 2026 года в магазине «Пример» за 180 рублей.',
    facts='На упаковке указан срок годности до 19 октября 2026 года. Йогурт я не употребляла.',
    previous_contact='23 октября 2026 года я обратилась к администратору магазина, в возврате денег отказали.',
    requests='рассмотреть нарушение и принять меры в пределах полномочий ведомства',
    attachments='Чек, фотографии упаковки и письменного обращения', date='24.10.26', signature='Смирнова Анна Павловна')


async def run_case(prompt, expected, answers):
    folder = Path(__file__).parent / 'form_library_qa'
    folder.mkdir(exist_ok=True)
    state = new_state(prompt)
    state, reply, _ = await advance_interview(state, prompt)
    assert state['scenario'] == expected, state['scenario']
    transcript = []
    for _ in range(65):
        if not pending_fields(state): break
        key = state['last_questions'][0]
        value = 'да' if state['fields'].get(key, {}).get('address_candidate') else answers[key]
        state, reply, _ = await advance_interview(state, value)
        transcript.append(dict(field=key, answer=value, reply=reply))
        if state.get('provider_failure'): raise RuntimeError('Interview provider failed')
        print('INTAKE', expected, key, state['fields'].get(key, {}).get('status'), flush=True)
    assert not pending_fields(state) and state['phase'] == 'ready'
    assert not quality_issues(state), quality_issues(state)
    assert state['template_selection']['scenario'] == expected
    client = await get_gigachat_client()
    completion = client.chat_completion
    traces = []
    async def traced_completion(*args, **kwargs):
        result = await completion(*args, **kwargs)
        traces.append(dict(input=args[0], output=result.content))
        (folder / (expected + '-editor-traces.json')).write_text(json.dumps(traces,ensure_ascii=False,indent=2),encoding='utf-8')
        return result
    client.chat_completion = traced_completion
    for attempt in range(2):
        try:
            state, _ = await prepare_document_draft(state, client)
            break
        except DraftPreparationError as error:
            state = error.partial_state
            print('EDITOR_RETRY', expected, error.keys, flush=True)
            if attempt:
                (folder / (expected + '-failure.json')).write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
                raise
    scenario = SCENARIOS[expected]
    fields = presentation_fields(state)
    blocks = render_package_blocks(state['text_package'], scenario, fields, format_template_fields(scenario, fields))
    validate_export_blocks(blocks)
    (folder / (expected + '.docx')).write_bytes(build_legal_docx(scenario.title, blocks, review_note='Проект. Требуется проверка юристом.'))
    report = readiness_report(state, state['text_package'])
    (folder / (expected + '.json')).write_text(json.dumps(dict(readiness=report,state=state,transcript=transcript),ensure_ascii=False,indent=2),encoding='utf-8')
    print('DOCUMENT_OK', expected, 'turns', len(transcript), flush=True)
    client.chat_completion = completion


async def main():
    if '--complaint-only' not in sys.argv:
        await run_case('хочу сдавать свою вторую квартиру, нужен договор', 'contract_housing', HOUSING)
    await run_case('Нужна жалоба в Роспотребнадзор: магазин продал просроченный йогурт и отказался возвращать деньги',
        'complaint_consumer_agency', COMPLAINT)


if __name__ == '__main__': asyncio.run(main())
