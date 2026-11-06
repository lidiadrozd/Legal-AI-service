from copy import deepcopy
from unittest.mock import AsyncMock
import pytest

from app.services.document_workflow import new_state, advance_interview, sanitize_interview, apply_updates, FieldUpdate
from app.services.document_dialogue import infer_scenario, leaves_blank, is_recall_request
from app.services.document_contract_facts import collect_contract_turn
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import load_text_package
from app.services.document_form_composition import prepare_form_document, form_presentation_fields

DETAILS=('Исполнитель должен создать сайт из пяти страниц: главная, услуги, цены, о компании и контакты. '
 'Нужны адаптация для телефона и форма обратной связи. Интернет-магазин и приём платежей в задание не входят. '
 'Цена — 60 000 рублей: аванс 20 000 рублей до 10 ноября 2026 года, остаток 40 000 рублей в течение трёх рабочих дней после приёмки. '
 'Срок передачи результата — 30 ноября 2026 года. Тексты и фотографии передаёт заказчик до 12 ноября. '
 'Исполнитель передаёт исходные файлы и доступы. Заказчик проверяет результат в течение пяти рабочих дней и направляет замечания одним списком. '
 'Дополнительные работы оплачиваются только после письменного согласования. '
 'Публикация сайта в портфолио — только с отдельного письменного согласия заказчика.')

def state(scenario='contract_services'):
    s=new_state('Нужен договор услуг на создание сайта.')
    s.update(scenario=scenario,phase='collecting',text_package=load_text_package(SCENARIOS[scenario]))
    return s

def filled(value):return dict(status='filled',value=value,original=value,evidence=value)

@pytest.mark.parametrize('scenario',['contract_services','contract_work'])
def test_all_website_terms_are_read_from_one_turn(scenario):
    s=state(scenario);collect_contract_turn(s,DETAILS,'scope');f=s['fields']
    assert f['amount']['value']=='60000.00'
    assert all(t in f['payment']['value'] for t in ['20 000','40 000','10 ноября','трёх рабочих дней','после приёмки'])
    assert '60 000' not in f['payment']['value']
    assert all(t in f['scope']['value'] for t in ['пяти страниц','главная','услуги','цены','о компании','контакты','адаптация','обратной связи','не входят','исходные файлы','доступы'])
    assert '12 ноября' in f['materials']['value']
    assert '30 ноября' in f['term']['value']
    assert 'пяти рабочих дней' in f['acceptance']['value']
    assert 'письменного согласования' in f['changes']['value']
    assert 'портфолио' in f['additional_terms']['value']
    assert not {'60 000','20 000','12 ноября'} & set(f['scope']['value'].split('. '))

@pytest.mark.parametrize('phrase',['писала выше','смотри выше','я указал выше','это написано выше'])
def test_reminders_are_control_input(phrase):assert is_recall_request(phrase)

@pytest.mark.parametrize('phrase',['внесу сам','внесу сама','впишу вручную','заполню позже'])
def test_manual_completion_does_not_become_passport_text(phrase):assert leaves_blank(phrase)

def test_manual_material_delivery_is_a_fact_not_a_skip():
    assert not leaves_blank('Тексты внесу сам до 12 ноября.')

def test_unknown_intro_is_not_a_party_name():
    s=state();intro='один человек создаёт сайт, другой принимает выполненную работу'
    s=apply_updates(s,[FieldUpdate(key='sender',status='filled',value='один человек создаёт сайт',evidence=intro)],intro)
    assert s['fields']['sender']['status']=='incomplete'
    from app.services.document_export_contract import clean_requisite
    assert clean_requisite('sender','один человек создаёт сайт') is None
    assert clean_requisite('sender','ООО «Другой человек»')=='ООО «Другой человек»'

@pytest.mark.asyncio
async def test_rich_answer_does_not_reask_known_terms(monkeypatch):
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',AsyncMock(side_effect=RuntimeError('offline')))
    s=state()
    for key in ['sender','sender_address','sender_details','recipient','recipient_address','recipient_details']:
        s['fields'][key]=dict(status='unknown',value=None)
    collect_contract_turn(s,s['request']);s['last_questions']=['scope']
    s,reply,_=await advance_interview(s,DETAILS)
    assert s['last_questions'][0] not in {'scope','materials','term','amount','payment','acceptance','changes','additional_terms'},reply
    assert s['fields']['scope']['status']=='filled'

@pytest.mark.asyncio
async def test_offline_export_preserves_agreed_terms_and_exclusions():
    s=state();collect_contract_turn(s,s['request']);collect_contract_turn(s,DETAILS)
    result,_=await prepare_form_document(s,None)
    assert not set(result['form_review_fields']) & {'subject','scope','term','payment','materials','acceptance','changes'}
    d=result['draft_fields']
    for key in ['scope','payment','materials','acceptance']:
        assert d[key]
    assert 'трёх рабочих дней после приёмки' in d['payment']
    assert 'не входят' in d['scope'] and 'исходные файлы и доступы' in d['scope']
    assert d['acceptance']=='Заказчик проверяет результат в течение пяти рабочих дней и направляет замечания одним списком.'
    from app.services.document_form_composition import _validate_slot
    assert not _validate_slot('acceptance','Результат приемки заказчиком подлежит проверке в течение пяти рабочих дней с направлением замечаний единым списком.',s['fields']['acceptance']['value'],'sentence')

def test_legacy_recovery_does_not_copy_reminders_or_responsibility_into_materials():
    s=state();s['contract_fact_version']=1
    liability='Ответственность заказчика — необходимость своевременно предоставить материалы и исходные данные, а также оплатить выполненные работы согласно условиям договора.'
    s['user_turns']=[DETAILS,'Тексты и фотографии','писала выше',liability]
    s['fields'].update(scope=filled('писала выше'),materials=filled('Тексты и фотографии'),sender_details=filled('внесу сам'),termination=filled('Экстренные ситуации'))
    result=sanitize_interview(s)
    assert 'пяти страниц' in result['fields']['scope']['value']
    assert result['fields']['materials']['value']=='Тексты и фотографии передаёт заказчик до 12 ноября.'
    assert result['fields']['sender_details']['status']=='unknown'
    assert result['fields']['termination']['status']=='incomplete'
    assert sanitize_interview(result)['fields']==result['fields']

@pytest.mark.parametrize('text,expected',[
 ('Нужен договор с исполнителем на создание сайта.','contract_work'),
 ('Нужен договор. выаолнение работ','contract_work'),
 ('Составь договор услуг: один человек создаёт сайт, другой принимает выполненную работу.','contract_services'),
])
def test_contract_intent_and_common_typo(text,expected):assert infer_scenario(new_state(text),'')==expected

def test_saved_contract_keeps_later_explicit_form_choice():
    s=state();s['request']='Нужен договор с исполнителем на создание сайта.'
    s['user_turns']=['выаолнение работ','а трудовые отношения?',
        'составь договор услуг: один человек создаёт сайт, другой принимает выполненную работу.']
    repaired=sanitize_interview(s)
    assert repaired['scenario']=='contract_services'
    assert repaired['text_package']==s['text_package']

@pytest.mark.asyncio
async def test_responsibility_example_does_not_invent_penalty_or_citation(monkeypatch):
    from app.services.document_workflow import _consult_interview
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',AsyncMock(side_effect=AssertionError('Example must be local')))
    s=state();before=deepcopy(s['fields'])
    result,reply,_=await _consult_interview(s,'например?','liability')
    assert '781' not in reply and '%' not in reply
    assert result['fields']==before

@pytest.mark.asyncio
async def test_partial_local_capture_still_extracts_remaining_contract_terms(monkeypatch):
    import json
    from types import SimpleNamespace
    from app.services.llm_cost import TokenUsage
    extra='Навигация должна поддерживать управление с клавиатуры.'
    extra2='Все изображения должны иметь текстовое описание.'
    response=SimpleNamespace(content=json.dumps({'answers':[
        {'key':'scope','quote':extra},{'key':'scope','quote':extra2}]}),usage=TokenUsage(1,1,2,False))
    extractor=AsyncMock(return_value=response)
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',AsyncMock(return_value=object()))
    monkeypatch.setattr('app.services.document_workflow._structured',extractor)
    s=state();s['last_questions']=['scope']
    s,_,_=await advance_interview(s,DETAILS+' '+extra+' '+extra2)
    assert extra in s['fields']['scope']['value']
    assert extra2 in s['fields']['scope']['value']
    assert 'исходные файлы' in s['fields']['scope']['value']
    assert '20 000' in s['fields']['payment']['value']
