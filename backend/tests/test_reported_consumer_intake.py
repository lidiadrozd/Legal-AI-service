"""Regressions from the refrigerator conversation; no live provider required."""
import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from docx import Document

from app.services.document_workflow import new_state, advance_interview, _capture_contextual_facts, pending_fields
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import load_text_package
from app.services.document_form_composition import prepare_form_document, form_presentation_fields
from app.services.llm_cost import TokenUsage

REQUEST = ('Помоги составить претензию продавцу. 10 октября 2026 года я купила в ООО «ТехноДом» '
           'холодильник за 48 900 рублей. Через две недели он перестал охлаждать. '
           'Хочу вернуть деньги. Чек сохранился.')

EXACT_REFRIGERATOR = (
    '5 ноября 2026 года я купил холодильник «Север ХК-300» в магазине ООО «ДомТехника» за 40\u202f000 рублей. '
    'Оплатил картой, чек сохранился. Холодильник доставили 6 ноября. '
    '10 ноября холодильная камера перестала охлаждать продукты, хотя морозильная камера работает. '
    'Я снял неисправность на видео. Холодильником пользовался по инструкции, самостоятельно его не ремонтировал. '
    'Я — покупатель, Петров Алексей Сергеевич. '
    'Хочу вернуть неисправный холодильник и получить обратно уплаченные деньги. '
    'В магазин пока не обращался. Адрес продавца и реквизиты для возврата сейчас не знаю.'
)

REPORTED_REFRIGERATOR = (
    '5 ноября 2026 года я купил холодильник «Север ХК-300» у ООО «ДомТехника» за 40 000 рублей. '
    'Доставили 6 ноября. 10 ноября холодильная камера перестала охлаждать, морозильная работает. '
    'Есть чек, гарантийный талон и видео неисправности. Я Петров Алексей Сергеевич. '
    'Хочу вернуть холодильник и деньги.'
)


@pytest.mark.asyncio
async def test_kettle_report_keeps_facts_after_partial_extraction(monkeypatch):
    from app.services.document_docx_template import fill_docx_template
    from app.services.document_fact_provenance import audit_sensitive_fields
    prompt = 'Претензия о возврате денег за товар'
    state = new_state(prompt)
    state.update(scenario='pretense_consumer_defective_goods', phase='collecting',
                 official_rate_lookup=False, last_questions=['recipient'])
    scenario = SCENARIOS[state['scenario']]
    state['text_package'] = load_text_package(scenario)
    narrative = (
        '3 ноября 2026 года купила для дома электрический чайник «Терма K17» в ООО «Северный дом» за 4 790 рублей. '
        'Платила картой, электронный чек сохранился. 8 ноября заметила, что при нагреве из-под ручки течёт вода. '
        'Чайник не роняла, протечку сняла на видео. 10 ноября принесла его в магазин. '
        'Продавец предложил ремонт, я отказалась и забрала чайник. '
        'Хочу вернуть товар и получить 4 790 рублей на карту, с которой платила. Приложу чек и видео.'
    )
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client', AsyncMock(return_value=object()))
    purchase_sentence = narrative.split('. ')[0]
    reply = {'answers': [
        {'key': 'amount', 'quote': '4 790 рублей', 'evidence': purchase_sentence},
        {'key': 'purchase', 'quote': 'электрический чайник «Терма K17»', 'evidence': purchase_sentence},
    ]}
    extractor = AsyncMock(return_value=SimpleNamespace(content=json.dumps(reply), usage=TokenUsage(1, 1, 2, False)))
    monkeypatch.setattr('app.services.document_workflow._structured', extractor)
    state, _, _ = await advance_interview(state, '«Терма K17» в ООО «Северный дом»')
    assert state['fields']['recipient']['value'] == 'ООО «Северный дом»'
    state['last_questions'] = ['purchase']
    state, _, _ = await advance_interview(state, narrative)
    fields = state['fields']
    expected = {'consumer_status', 'goods_category', 'recipient', 'payment_evidence', 'payment', 'amount',
                'purchase', 'defect', 'seller_response', 'attachments', 'defect_evidence', 'requests', 'facts'}
    assert all(fields[k]['status'] == 'filled' for k in expected)
    assert not expected.intersection(f.key for f in pending_fields(state))
    assert fields['amount']['value'] == '4790.00'
    assert fields['amount']['origin'] == 'llm_user_quote'
    assert not state.get('narrative_conflicts')

    failing_editor = SimpleNamespace(chat_completion=AsyncMock(side_effect=RuntimeError('offline')))
    state, _ = await prepare_form_document(state, failing_editor)
    presented, _ = audit_sensitive_fields(state, form_presentation_fields(state))
    draft = fill_docx_template(state['text_package'], scenario, presented)
    body = '\n'.join(p.text for p in Document(BytesIO(draft)).paragraphs)
    for value in ('Терма K17', '3 ноября 2026 года', 'из-под ручки течёт вода', 'Чайник не роняла',
                  'домашнего использования', '10 ноября', 'Продавец предложил ремонт', '1. Чек.', '2. Видео.'):
        assert value in body, value


@pytest.mark.asyncio
async def test_initial_request_retains_all_known_consumer_facts_offline(monkeypatch):
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client', AsyncMock(side_effect=RuntimeError('offline')))
    state, answer, _ = await advance_interview(new_state(REQUEST), REQUEST)
    assert state['scenario'] == 'pretense_consumer_defective_goods'
    expected = {'recipient', 'purchase', 'amount', 'defect', 'requests', 'payment_evidence'}
    assert all(state['fields'][key]['status'] == 'filled' for key in expected)
    assert state['fields']['amount']['value'] == '48900.00'
    assert not expected.intersection(f.key for f in pending_fields(state))
    assert 'Что произошло' not in answer
    # A purpose cannot be invented just because the object is a fridge.
    assert 'consumer_status' not in state['fields']
    assert state['fields']['goods_category']['status']=='incomplete'  # brand/model still unknown
    state, _, _ = await advance_interview(state, 'Анна Сергеевна Миронова')
    assert state['fields']['purchase']['status'] == 'filled'
    assert 'Помоги' not in state['fields']['purchase']['value']


@pytest.mark.asyncio
async def test_exact_refrigerator_narrative_reuses_every_literal_fact_offline(monkeypatch):
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',
                        AsyncMock(side_effect=RuntimeError('offline')))
    prompt = 'Составь претензию продавцу о возврате денег за неисправный холодильник'
    state, _, _ = await advance_interview(new_state(prompt), prompt)

    state, _, _ = await advance_interview(state, EXACT_REFRIGERATOR)

    expected = {
        'sender', 'recipient', 'purchase', 'amount', 'payment_evidence',
        'defect', 'defect_evidence', 'goods_category', 'seller_response', 'requests',
    }
    assert expected.isdisjoint(field.key for field in pending_fields(state))
    assert state['fields']['sender']['value'] == 'Петров Алексей Сергеевич'
    assert state['fields']['recipient']['value'] == 'ООО «ДомТехника»'
    assert state['fields']['amount']['value'] == '40000.00'
    assert state['fields']['goods_category']['value'] == 'холодильник «Север ХК-300»'
    assert state['fields']['sender']['evidence'] == 'Я — покупатель, Петров Алексей Сергеевич'
    assert 'Оплатил картой, чек сохранился' in state['fields']['payment_evidence']['evidence']
    assert 'получить обратно уплаченные деньги' in state['fields']['requests']['evidence']


@pytest.mark.asyncio
async def test_exact_refrigerator_history_is_reused_before_the_first_question(monkeypatch):
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',
                        AsyncMock(side_effect=RuntimeError('offline')))
    prompt = 'Составь претензию продавцу о возврате денег за неисправный холодильник'
    state = new_state(prompt, context=EXACT_REFRIGERATOR)
    state['source_messages'] = [{'id': 1, 'role': 'user', 'content': EXACT_REFRIGERATOR}]

    state, _, _ = await advance_interview(state, prompt)

    assert state['fields']['sender']['value'] == 'Петров Алексей Сергеевич'
    assert state['fields']['recipient']['value'] == 'ООО «ДомТехника»'
    assert state['fields']['amount']['value'] == '40000.00'
    assert state['fields']['goods_category']['value'] == 'холодильник «Север ХК-300»'
    assert (state.get('last_questions') or [None])[0] not in {
        'sender', 'recipient', 'purchase', 'amount', 'payment_evidence',
        'defect', 'defect_evidence', 'goods_category', 'seller_response', 'requests',
    }


@pytest.mark.asyncio
async def test_compound_there_is_a_receipt_phrase_fills_payment_evidence(monkeypatch):
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',
                        AsyncMock(side_effect=RuntimeError('offline')))
    prompt = 'Составь претензию продавцу о возврате денег за неисправный холодильник'
    state, _, _ = await advance_interview(new_state(prompt), prompt)
    state, _, _ = await advance_interview(state, REPORTED_REFRIGERATOR)

    assert state['fields']['payment_evidence']['status'] == 'filled'
    assert state['fields']['payment_evidence']['value'] == 'чек'
    assert 'Есть чек' in state['fields']['payment_evidence']['evidence']
    assert 'payment_evidence' not in {field.key for field in pending_fields(state)}


def test_receipt_fact_survives_a_clarification_question():
    from app.services.document_consumer_facts import receipt_evidence
    assert receipt_evidence('есть чек, а какие реквизиты указать?') == 'есть чек'


@pytest.mark.asyncio
async def test_short_purchase_answer_preserves_impossible_date_for_clarification(monkeypatch):
    """A natural ellipsis is retained, but an impossible year is not accepted."""
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',
                        AsyncMock(side_effect=RuntimeError('offline')))
    prompt = 'Хочу написать претензию о неработающем холодильнике'
    state = new_state(prompt)
    state.update(scenario='pretense_consumer_defective_goods', phase='collecting',
                 last_questions=['purchase'], user_turns=[prompt])
    state['text_package'] = load_text_package(SCENARIOS[state['scenario']])

    state, _, _ = await advance_interview(state, '8.09.4003 в магазине на Парковой 6')

    purchase = state['fields']['purchase']
    assert purchase['status'] == 'incomplete'
    assert '8.09.4003' in purchase['value']
    assert 'Парковой 6' in purchase['value']
    assert 'холодильник' in purchase['value'].lower()
    assert 'невозможной' in purchase['error']
    assert 'purchase' in {field.key for field in pending_fields(state)}


@pytest.mark.asyncio
async def test_short_purchase_answer_with_valid_date_fills_field(monkeypatch):
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',
                        AsyncMock(side_effect=RuntimeError('offline')))
    prompt = 'Хочу написать претензию о неработающем холодильнике'
    state = new_state(prompt)
    state.update(scenario='pretense_consumer_defective_goods', phase='collecting',
                 last_questions=['purchase'], user_turns=[prompt])
    state['text_package'] = load_text_package(SCENARIOS[state['scenario']])

    state, _, _ = await advance_interview(state, '8.09.2026 в магазине на Парковой 6')

    purchase = state['fields']['purchase']
    assert purchase['status'] == 'filled'
    assert '8.09.2026' in purchase['value']
    assert 'холодильник' in purchase['value'].lower()
    assert 'purchase' not in {field.key for field in pending_fields(state)}


@pytest.mark.asyncio
@pytest.mark.parametrize('message', [
    'а какие реквизиты чека указать?',
    'а что надо то? номер чека или как?',
    'дату и сумму писал ранее',
])
async def test_receipt_followup_recovers_existing_fact_instead_of_repeating_question(monkeypatch, message):
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',
                        AsyncMock(side_effect=RuntimeError('offline')))
    state = new_state('Составь претензию продавцу о возврате денег за неисправный холодильник')
    state.update(scenario='pretense_consumer_defective_goods', phase='collecting',
                 last_questions=['payment_evidence'], user_turns=[REPORTED_REFRIGERATOR])
    state['text_package'] = load_text_package(SCENARIOS[state['scenario']])

    state, answer, _ = await advance_interview(state, message)

    assert state['fields']['payment_evidence']['status'] == 'filled'
    assert state['fields']['payment_evidence']['value'] == 'чек'
    assert state['fields']['payment_evidence']['evidence'] != message
    assert 'уже найдено в переписке' in answer
    assert 'Чем подтверждается оплата?' not in answer


@pytest.mark.asyncio
async def test_receipt_assertion_before_followup_question_is_saved(monkeypatch):
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',
                        AsyncMock(side_effect=RuntimeError('offline')))
    state = new_state('Хочу написать претензию о неработающем холодильнике')
    state.update(scenario='pretense_consumer_defective_goods', phase='collecting',
                 last_questions=['payment_evidence'])
    state['text_package'] = load_text_package(SCENARIOS[state['scenario']])

    state, _, _ = await advance_interview(state, 'есть чек, а какие реквизиты указать?')

    evidence = state['fields']['payment_evidence']
    assert evidence['status'] == 'filled'
    assert evidence['value'] == 'чек'
    assert evidence['evidence'].casefold() == 'есть чек'
    assert 'payment_evidence' not in {field.key for field in pending_fields(state)}


def test_receipt_question_alone_is_not_evidence():
    from app.services.document_consumer_facts import receipt_evidence

    assert receipt_evidence('Чек есть?') is None


@pytest.mark.asyncio
async def test_payment_method_survives_manual_card_number_note(monkeypatch):
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',
                        AsyncMock(side_effect=RuntimeError('offline')))
    state = new_state('Хочу написать претензию о неработающем холодильнике')
    state.update(scenario='pretense_consumer_defective_goods', phase='collecting',
                 last_questions=['payment'])
    state['text_package'] = load_text_package(SCENARIOS[state['scenario']])

    state, answer, _ = await advance_interview(state, 'перевод на карту. номер напишу сама')

    payment = state['fields']['payment']
    assert payment['status'] == 'filled'
    assert payment['value'] == 'Банковским переводом; реквизиты будут сообщены отдельно.'
    assert payment['evidence'] == 'перевод на карту. номер напишу сама'
    assert 'payment' not in {field.key for field in pending_fields(state)}
    assert 'Способ возврата сохранён' in answer


@pytest.mark.asyncio
@pytest.mark.parametrize('scenario', ['pretense_consumer_defective_goods','pretense_debt_services','contract_housing'])
async def test_name_question_accepts_address_in_same_turn(monkeypatch, scenario):
    state = new_state('Подготовить документ')
    state.update(scenario=scenario, phase='collecting', last_questions=['sender'])
    state['text_package'] = load_text_package(SCENARIOS[scenario])
    message = 'Меня зовут Анна Сергеевна Миронова. Мой адрес: г. Екатеринбург, ул. Тестовая, д. 15.'
    payload = {'answers': [
        {'key':'sender','quote':'Анна Сергеевна Миронова','evidence':'Меня зовут Анна Сергеевна Миронова.'},
        {'key':'sender_address','quote':'г. Екатеринбург, ул. Тестовая, д. 15.',
         'evidence':'Мой адрес: г. Екатеринбург, ул. Тестовая, д. 15.'},
        {'key':'recipient','quote':'ООО «Выдумка»','evidence':'ООО «Выдумка»'},
    ]}
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client', AsyncMock(return_value=object()))
    monkeypatch.setattr('app.services.document_workflow._structured', AsyncMock(return_value=SimpleNamespace(
        content=json.dumps(payload,ensure_ascii=False),usage=TokenUsage(1,1,2,False))))
    result, _, _ = await advance_interview(state, message)
    assert result['fields']['sender']['value'] == 'Анна Сергеевна Миронова'
    assert 'Тестовая' in result['fields']['sender_address']['value']
    assert 'recipient' not in result['fields']


@pytest.mark.asyncio
async def test_other_facts_survive_even_after_two_fields_captured(monkeypatch):
    state = new_state(REQUEST)
    state.update(scenario='pretense_consumer_defective_goods',phase='collecting',last_questions=['facts'])
    state['text_package'] = load_text_package(SCENARIOS[state['scenario']])
    message = 'Чек сохранился. Хочу вернуть деньги. Для хранения продуктов.'
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client', AsyncMock(return_value=object()))
    monkeypatch.setattr('app.services.document_workflow._structured', AsyncMock(return_value=SimpleNamespace(
        content=json.dumps({'answers':[{'key':'consumer_status','quote':'Для хранения продуктов.'}]}),
        usage=TokenUsage(1,1,2,False))))
    state, _, _ = await advance_interview(state, message)
    assert all(state['fields'][key]['status']=='filled' for key in ('payment_evidence','requests','consumer_status'))


@pytest.mark.asyncio
async def test_prior_contact_is_not_asked_again(monkeypatch):
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client', AsyncMock(side_effect=RuntimeError('offline')))
    state, _, _ = await advance_interview(new_state(REQUEST), REQUEST)
    state['last_questions'] = ['facts']
    message = 'Обнаружение неисправности: 25 октября 2026 года. Обращение к продавцу: пока не обращалась.'
    state, _, _ = await advance_interview(state, message)
    assert state['fields']['seller_response']['status'] == 'filled'
    assert state['fields']['facts']['status'] == 'filled'
    assert '25 октября 2026' in state['fields']['facts']['value']
    assert 'seller_response' not in [f.key for f in pending_fields(state)]


@pytest.mark.asyncio
async def test_answered_slots_and_attachment_cases_survive_export():
    from complete_form_cases import make_state
    state = make_state('pretense_consumer_defective_goods')
    values = {'consumer_status':'для хранения продуктов', 'defect':'Через две недели он перестал охлаждать.',
              'attachments':'чек о покупке и гарантию'}
    for key, value in values.items():
        state['fields'][key] = {'status':'filled','value':value,'evidence':value}
    # These exact grammar transformations also work when GigaChat is down.
    result, _ = await prepare_form_document(state)
    fields = form_presentation_fields(result)
    assert fields['consumer_status']['value'] == 'хранения продуктов'
    assert fields['defect']['value'] == 'Через две недели товар перестал охлаждать.'
    assert fields['attachments']['value'] == '1. Чек о покупке.\n2. Гарантия.'
    assert not set(values).intersection(result['form_review_fields'])


def test_consumer_recording_is_rendered_once_as_evidence():
    from complete_form_cases import make_state
    from app.services.document_form_composition import form_presentation_fields

    state = make_state('pretense_consumer_defective_goods')
    state['fields'].update({
        'defect': {
            'status': 'filled',
            'value': '8 ноября при нагреве из-под ручки течёт вода. Протечку зафиксировала на видео.',
            'evidence': '8 ноября при нагреве из-под ручки течёт вода. Протечку зафиксировала на видео.',
        },
        'defect_evidence': {
            'status': 'filled',
            'value': 'Протечку зафиксировала на видео',
            'evidence': 'Протечку зафиксировала на видео',
        },
    })

    fields = form_presentation_fields(state)

    assert 'течёт вода' in fields['defect']['value']
    assert 'на видео' not in fields['defect']['value']
    assert 'на видео' in fields['defect_evidence']['value']


@pytest.mark.asyncio
async def test_download_keeps_one_copy_of_purchase_model_response_and_application():
    from complete_form_cases import make_state
    from app.services.document_docx_template import fill_docx_template
    state = make_state('pretense_consumer_defective_goods')
    purchase = '3 ноября 2026 года купила для дома электрический чайник «Терма K17» в ООО «Северный дом» за 4 790 рублей.'
    visit = '10 ноября принесла чайник в магазин.'
    decision = 'Продавец предложил ремонт, я отказалась и забрала чайник.'
    refund = 'Хочу вернуть товар и получить 4 790 рублей на карту, с которой платила.'
    supplied = {'purchase': purchase, 'goods_category': purchase, 'consumer_status': purchase, 'recipient': purchase,
                'facts': visit + ' ' + decision, 'seller_response': decision, 'requests': refund, 'payment': refund,
                'attachments': 'чек и видео', 'additional_claims': 'Приложу чек и видео.'}
    state['user_turns'] = [purchase, visit + ' ' + decision, refund, 'Приложу чек и видео.']
    for key, value in supplied.items():
        state['fields'][key] = {'status': 'filled', 'value': value, 'evidence': value, 'origin': 'llm_user_quote'}
    state, _ = await prepare_form_document(state)
    fields = form_presentation_fields(state)
    doc = fill_docx_template(state['text_package'], SCENARIOS[state['scenario']], fields)
    lines = [p.text for p in Document(BytesIO(doc)).paragraphs]
    text = '\n'.join(lines)
    assert lines[0] == 'ООО «Северный дом»'
    assert text.count('Терма K17') == 1
    assert text.casefold().count('предложил ремонт') == 1
    assert 'Товар приобретён для домашнего использования.' in lines
    assert '3 ноября 2026 года' in text and '10 ноября' in text
    assert 'Приложу чек и видео.' not in lines
    assert '1. Чек.' in lines and '2. Видео.' in lines
    assert next(s for s in lines if s.startswith('Способ возврата')).startswith('Способ возврата денежных средств: на карту')


def test_flood_download_prints_repeated_act_and_estimate_once():
    from complete_form_cases import make_state
    from app.services.document_docx_template import fill_docx_template
    state = make_state('claim_damage_flood')
    act = 'На следующий день управляющая компания составила акт.'
    estimate = 'По отчёту оценщика ремонт стоит 86 400 рублей.'
    other = 'К акту приложены снимки повреждений.'
    values = {'facts': act, 'restoration_estimate': estimate, 'evidence': f'{act} {estimate} {other}',
              'sender_details': 'добавлю сама', 'restoration': 'частично восстановлено',
              'property_right': 'Я собственница квартиры № 17 в Екатеринбурге по адресу: ул. Лесная, д. 12.',
              'property_address': 'г. Екатеринбург, ул. Лесная, д. 12, кв. 17'}
    for key, value in values.items():
        state['fields'][key] = {'status': 'filled', 'value': value, 'evidence': value}
    fields = form_presentation_fields(state)
    doc = fill_docx_template(state['text_package'], SCENARIOS[state['scenario']], fields)
    text = '\n'.join(p.text for p in Document(BytesIO(doc)).paragraphs)
    assert text.count(act) == 1 and text.count(other) == 1 and text.count(estimate) == 1
    assert fields['evidence']['value'] == other
    assert 'добавлю сама' not in text
    assert 'Я собственница повреждённой квартиры.' in text


@pytest.mark.parametrize('legacy_conflict', [True, False])
def test_long_seller_field_is_narrowed_to_its_company_without_asking_again(legacy_conflict):
    from app.services.document_consumer_facts import prepare_consumer_facts

    narrative = ('купила для дома чайник «Модель А» в ООО «Магазин» за 4 790 рублей. '
                 'Продавец предложил ремонт, я отказалась и забрала чайник.')
    seller = 'ООО «Магазин»'
    field = ({'status': 'incomplete', 'origin': 'consumer_seller_conflict', 'value': None,
              'seller_choices': [narrative, seller]}
             if legacy_conflict else {'status': 'filled', 'value': narrative, 'evidence': narrative})
    state = {'scenario': 'pretense_consumer_defective_goods', 'fields': {'recipient': field}}
    prepare_consumer_facts(state)
    assert state['fields']['recipient']['value'] == seller
    assert state['fields']['recipient']['status'] == 'filled'
    assert state['fields']['recipient']['evidence'] == narrative


def test_two_distinct_seller_choices_are_kept():
    from app.services.document_consumer_facts import prepare_consumer_facts

    choices = ['купила в ООО «Один» за 200 рублей.', 'ООО «Два»']
    field = {'status': 'incomplete', 'origin': 'consumer_seller_conflict', 'value': None,
             'seller_choices': choices}
    state = {'scenario': 'pretense_consumer_defective_goods', 'fields': {'recipient': field}}
    prepare_consumer_facts(state)
    assert state['fields']['recipient']['status'] == 'incomplete'
    assert state['fields']['recipient']['seller_choices'] == choices


@pytest.mark.asyncio
async def test_reported_consumer_sources_survive_editor_failure():
    """A failed editor must not turn already-bound answers into missing data."""
    from complete_form_cases import make_state
    state = make_state('pretense_consumer_defective_goods')
    values = {
        'purchase':'Холодильник 08.09.2026 в магазине на Парковой 6',
        'defect':'холодильник перестал охлаждать 30 октября. гарантия 5 лет',
        'payment':'перевод на карту. номер напишу сама',
    }
    for key, value in values.items():
        state['fields'][key] = {'status':'filled','value':value,'evidence':value,
                                'origin':'source_bound_extraction'}
    provider = SimpleNamespace(chat_completion=AsyncMock(side_effect=RuntimeError('offline')))

    result, _ = await prepare_form_document(state, provider)
    fields = form_presentation_fields(result)

    assert fields['purchase']['value'] == 'Холодильник 08.09.2026 в магазине на Парковой 6.'
    assert fields['defect']['value'] == 'Холодильник перестал охлаждать 30 октября. Гарантия 5 лет.'
    assert fields['payment']['value'] == 'банковским переводом на карту; реквизиты будут сообщены отдельно'
    assert not set(values).intersection(result['form_review_fields'])
    assert all(result['draft_review'][key]['source_preserved'] for key in values)


@pytest.mark.parametrize('scenario',['contract_housing','pretense_debt_services','claim_damage_property'])
def test_document_list_cases_are_shared(scenario):
    from app.services.document_form_composition import local_candidate
    text = local_candidate('attachments','расписку и претензию и справку','list',scenario)
    assert text == '1. Расписка.\n2. Претензия.\n3. Справка.'


def test_repair_of_product_is_service_not_defective_goods():
    from app.services.document_dialogue import infer_scenario
    text = 'Помоги составить претензию за некачественный ремонт холодильника'
    assert infer_scenario(new_state(text),text) == 'pretense_consumer_defective_service'


def test_editor_cannot_turn_inconclusive_photos_into_proof():
    from app.services.document_form_composition import _validate_slot, local_candidate
    source = 'У меня есть фото, но по ним не скажешь особо, охлаждает холодильник или нет. можно самим прийти и убедиться в этом'
    assert not _validate_slot('defect_evidence','Имеются фотографии, позволяющие установить наличие неисправности.',source,'phrase')
    candidate = local_candidate('defect_evidence',source,'phrase','pretense_consumer_defective_goods')
    assert candidate and 'нельзя определить' in candidate
    assert 'охлаждает ли холодильник' in candidate


@pytest.mark.asyncio
async def test_json_array_instructions_include_element_shape():
    from app.services.document_workflow import _structured
    client = SimpleNamespace(chat_completion=AsyncMock(return_value=object()))
    schema = {'type':'object','properties':{'answers':{'type':'array','items':{
        'type':'object','properties':{'key':{'type':'string'},'quote':{'type':'string'},'evidence':{'type':'string'}}}}}}
    await _structured(client,'Extract facts',{},schema,plain_json=True)
    prompt = client.chat_completion.call_args.args[0][0]['content']
    assert '"answers": [{"key": "", "quote": "", "evidence": ""}]' in prompt
