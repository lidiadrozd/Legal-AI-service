"""Regressions from the refrigerator conversation; no live provider required."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.document_workflow import new_state, advance_interview, _capture_contextual_facts, pending_fields
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import load_text_package
from app.services.document_form_composition import prepare_form_document, form_presentation_fields
from app.services.llm_cost import TokenUsage

REQUEST = ('Помоги составить претензию продавцу. 10 октября 2026 года я купила в ООО «ТехноДом» '
           'холодильник за 48 900 рублей. Через две недели он перестал охлаждать. '
           'Хочу вернуть деньги. Чек сохранился.')


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
