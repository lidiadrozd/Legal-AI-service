"""Regression: grammatical-looking answers still require a business editor."""
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from complete_form_cases import make_state
from app.services.document_form_composition import prepare_form_document, _validate_slot
from app.services.llm_cost import TokenUsage


def sofa_state():
    state = make_state('pretense_consumer_late_delivery')
    values = {
        'purchase': 'Диван', 'amount': '85000.00',
        'payment_evidence': 'Есть договор, чек и переписка с магазином.',
        'consumer_status': 'лежать',
        'delivery_due': 'доставка обещана до 25 сентября, прописано в договоре',
        'delivery_status': 'Диван не доставлен. Я не знаю где он. Уже 28 октября',
        'facts': 'Договор заключен 01.09.2026. Номер 45633. Оплачено 01.09.2026. Обращалась в магазин с вопросом о сроке доставки, ответа нет. Дивана тоже нет.',
        'seller_response': 'Обращалась в магазин с вопросом о сроке доставки, ответа нет. Дивана тоже нет.',
        'requests': 'возврат оплаты',
        'payment': 'переводом на карту, с которой был произведён платёж',
        'attachments': 'договор, чек и переписка с магазином',
    }
    for key, value in values.items():
        state['fields'][key] = {'status': 'filled', 'value': value, 'original': value}
    state['fields']['additional_claims'] = {'status': 'not_applicable', 'value': None}
    return state


@pytest.mark.asyncio
@pytest.mark.parametrize('scenario,key,raw,edited', [
    ('pretense_consumer_late_delivery', 'payment', 'Хочу чтобы вернули деньги на мою банковскую карту', 'путём перечисления денежных средств на банковскую карту плательщика'),
    ('contract_services', 'subject', 'сделать сайт', 'создание сайта'),
    ('claim_debt_loan', 'facts', 'Мне не вернули деньги.', 'Денежные средства мне не возвращены.'),
])
async def test_free_text_reaches_editor_even_if_local_heuristic_accepts_it(monkeypatch, scenario, key, raw, edited):
    state = make_state(scenario)
    state['fields'][key] = {'status': 'filled', 'value': raw, 'original': raw}
    original = deepcopy(state['fields'])
    seen = []

    async def structured(client, prompt, data, schema, **kwargs):
        seen.append((kwargs['name'], data))
        values = {k: {'meaning_preserved': True, 'business_style': True, 'fits_context': True, 'reason': 'checked'} for k in data['slots']}
        return SimpleNamespace(content=json.dumps(values), usage=TokenUsage(1, 1, 2, False))

    monkeypatch.setattr('app.services.document_workflow._structured', structured)
    async def complete(messages, **kwargs):
        data = json.loads(messages[1]['content'])
        seen.append(('edit_slot', data))
        return SimpleNamespace(content=edited if data['source_text'] == raw else data['source_text'], usage=TokenUsage(1, 1, 2, False))
    provider = SimpleNamespace(chat_completion=AsyncMock(side_effect=complete))
    result, _ = await prepare_form_document(state, provider)
    assert any(name == 'edit_slot' and data['source_text'] == raw for name, data in seen)
    assert any(name == 'verify_official_slots' and key in data['slots'] for name, data in seen)
    assert result['draft_fields'][key] == edited
    assert state['fields'] == original


@pytest.mark.parametrize('key,raw,mode', [
    ('consumer_status', 'лежать', 'phrase'),
    ('delivery_status', 'Диван не доставлен. Я не знаю где он. Уже 28 октября', 'sentence'),
    ('seller_response', 'Ответа нет. Дивана тоже нет.', 'sentence'),
])
def test_literal_colloquial_echo_cannot_pass_slot_validation(key, raw, mode):
    assert not _validate_slot(key, raw, raw, mode)


def test_new_editor_version_invalidates_old_draft_and_cache():
    from app.services.document_drafting import draft_is_current, facts_digest, editorial_digest
    state = sofa_state()
    state.update(draft_version=12, draft_digest=facts_digest(state['fields']))
    assert not draft_is_current(state)
    import hashlib
    old = hashlib.sha256(json.dumps([12, state['scenario'], 'consumer_status', 'лежать'], ensure_ascii=False).encode()).hexdigest()
    assert editorial_digest(state['scenario'], 'consumer_status', 'лежать') != old


@pytest.mark.asyncio
async def test_case_composer_retained_prose_uses_same_editor_and_survives_recomposition(monkeypatch):
    from test_document_case_composition import labor_case
    from app.services.document_drafting import prepare_document_draft, narrative_keys
    from app.services.document_case_composition import case_presentation_fields, prepare_case_document
    state=labor_case()
    raw='Мне так и не ответили.'
    state['fields']['facts']={'status':'filled','value':raw,'original':raw}
    assert 'facts' in narrative_keys(state)
    edited='Ответ на обращение мне не предоставлен.'
    async def complete(messages,**kwargs):
        return SimpleNamespace(content=edited,usage=TokenUsage(1,1,2,False))
    async def review(client,prompt,data,schema,**kwargs):
        return SimpleNamespace(content=json.dumps({k:{'meaning_preserved':True,'business_style':True,'fits_context':True,'reason':'checked'} for k in data['slots']}),usage=TokenUsage(1,1,2,False))
    monkeypatch.setattr('app.services.document_workflow._structured',review)
    result,_=await prepare_document_draft(state,SimpleNamespace(chat_completion=AsyncMock(side_effect=complete)))
    assert case_presentation_fields(prepare_case_document(result))['facts']['value']==edited
    assert result['fields']['facts']['value']==raw


@pytest.mark.parametrize('raw,edited',[
    ('Обращалась в магазин, ответа нет.','В магазин направлено уведомление. Ответ не получен.'),
    ('Диван не доставлен.','Диван не доставлен. Его местонахождение мне неизвестно.'),
    ('Диван','Я приобрёл диван.'),
    ('возврат оплаты','Прошу вернуть оплату в связи с нарушением срока доставки.'),
])
def test_grammatical_prose_cannot_add_events_uncertainty_gender_or_reasons(raw,edited):
    assert not _validate_slot('facts' if raw!='возврат оплаты' else 'requests',edited,raw,'sentence')


def test_working_days_are_restored_only_at_equal_numeric_value():
    from app.services.document_editorial_grammar import restore_spelled_source_numbers
    assert restore_spelled_source_numbers('в течение 5 рабочих дней','в течение пяти рабочих дней')=='в течение 5 рабочих дней'
    assert restore_spelled_source_numbers('не позднее 5 числа','не позднее пятого числа')=='не позднее 5 числа'
    assert restore_spelled_source_numbers('в течение 5 рабочих дней','в течение десяти рабочих дней')=='в течение десяти рабочих дней'


def test_editor_must_preserve_reference_to_contract():
    assert not _validate_slot('delivery_due','до 25 сентября','доставка обещана до 25 сентября, прописано в договоре','phrase')
