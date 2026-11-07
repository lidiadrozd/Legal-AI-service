"""Acceptance cases for the two maintained document composers.

Assertions cover source roles, missing facts, arithmetic, dialogue and real DOCX
downloads. Passing an OOXML checksum alone is not document acceptance.
"""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from decimal import Decimal
from unittest.mock import AsyncMock
import pytest
from docx import Document

from app.services.document_workflow import new_state, advance_interview, pending_fields
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import load_text_package, render_package_blocks, format_template_fields
from app.services.document_case_facts import collect_case_turn, set_field, fact
from app.services.document_case_composition import prepare_case_document, case_presentation_fields, prepare_case_rules
from app.services.document_docx_template import fill_docx_template
from app.services.document_export_contract import validate_export_blocks, formal_text


def state_for(key):
    state=new_state(SCENARIOS[key].title)
    state.update(scenario=key,phase='collecting',text_package=load_text_package(SCENARIOS[key]))
    return state


def put(state,key,text):
    consumed=collect_case_turn(state,text,key)
    if key not in consumed:set_field(state,key,text,text)


def labor_case():
    state=state_for('complaint_labor_agency')
    for key,text in [
        ('sender','Орлов Дмитрий Николаевич'),('sender_address','Екатеринбург, Мира 55, 89'),
        ('recipient','Государственная инспекция труда'),('recipient_address','нет'),
        ('employer','ООО «Пример-Сервис»'),('employer_address','Место работы: Екатеринбург Мира 68'),
        ('employment','Работодатель: ООО «Пример-Сервис». Работал кладовщиком с 1 февраля по 20 октября 2026 года. Трудовой договор № 45-ТД'),
        ('dismissal','Уволился по собственному желанию'),('wages','Начисленная, но не выплаченная зарплата — 100 000 рублей за октябрь.'),
        ('evidence','Есть трудовой договор, приказ об увольнении, расчётный листок и банковская выписка.'),
        ('previous_contact','Да, ответа не было'),('requests','Выплатить зп'),('payment','По почте'),
        ('contacts','Екатеринбург, Мира 55, 89'),('attachments','трудовой договор, приказ об увольнении, расчётный листок и банковская выписка'),
        ('date','26.10.2026'),('signature','Орлов Дмитрий Николаевич')]:put(state,key,text)
    prepare_case_rules(state)
    return state


def alimony_case():
    state=state_for('claim_alimony_fixed')
    for key,text in [
        ('sender','Ершина Ольга Ивановна'),('sender_address','Екатеринбург, Мира 78, 89'),
        ('recipient','Сайнудинов Олег Михайлович'),('recipient_address','Екатеринбург, Вилонова 6, 22'),
        ('court','Кировский районный суд города Екатеринбурга'),
        ('sender_details','Дата рождения: 12.03.1990; место рождения: Екатеринбург; ИНН 678409964723'),
        ('party_details','Дата рождения: 01.02.1988; место рождения: Пермь; ИНН 657899903211'),
        ('children','Сайнудинова Анна Олеговна, 12.03.2019. Отцовство подтверждается свидетельством о рождении, не оспаривается. Ребёнок проживает с матерью. Ранее алименты не устанавливались, нотариального соглашения нет.'),
        ('other_dependants','Других детей нет'),('assistance','Нет'),
        ('fixed_grounds','У отца нерегулярный доход, выполняет разовые заказы'),('monthly_amount','20000 рублей ежемесячно'),
        ('maintenance_calculation','Общие расходы на ребёнка — 40000 рублей в месяц.'),
        ('maintenance_calculation','пополам'),('start','С настоящего времени'),
        ('contacts','Телефон: +78905678776. Адрес: Екатеринбург, Мира 78, 89'),
        ('copy_notice','Нет'),('attachments','свидетельство о рождении, справка о проживании ребёнка, чеки на питание'),
        ('date','26.10.2026'),('signature','Ершина Ольга Ивановна')]:put(state,key,text)
    prepare_case_rules(state)
    return state


def artifact(state):
    scenario=SCENARIOS[state['scenario']];fields=case_presentation_fields(state)
    blocks=render_package_blocks(state['text_package'],scenario,fields,format_template_fields(scenario,fields))
    validate_export_blocks(blocks)
    docx=fill_docx_template(state['text_package'],scenario,fields)
    text='\n'.join(p.text for p in Document(BytesIO(docx)).paragraphs)
    return text,docx


def test_labor_composition_roles_contacts_period_and_evidence():
    state=labor_case();before=deepcopy(state)
    text,_=artifact(state)
    assert state==before
    assert 'Работодатель не выплатил мне заработную плату за октябрь в размере 100 000 рублей.' in text
    assert 'мною не выплач' not in text
    assert '45-ТД' in text and '20 октября 2026' in text and 'кладовщиком' in text
    assert 'письменн' not in text
    assert 'Источник' not in text and 'Source_text' not in text
    assert 'Контакты:' not in text and 'Телефон:' not in text
    assert 'Адрес работодателя или места работы: г. Екатеринбург, ул. Мира, д. 68' in text
    assert 'статьёй 356 ТК РФ' in text and 'Статья 140 ТК РФ' in text
    assert '1. Проверить' in text and 'полномочий инспекции' in text
    assert text.count('Обращение к работодателю')==1
    assert '1. Трудовой договор.' in text and '4. Банковская выписка.' in text


def test_alimony_has_operative_amount_law_price_indexation_and_no_quotes():
    state=alimony_case();before=deepcopy(state)
    text,_=artifact(state)
    assert state==before
    prayer=text.split('На основании изложенного прошу суд')[1]
    assert '20 000 рублей ежемесячно' in prayer
    assert '[отношение суммы алиментов' not in text
    assert 'со дня обращения в суд' in prayer and 'до достижения ребёнком совершеннолетия' in prayer
    assert 'статьи 117 СК РФ' in prayer and 'прожиточного минимума для детей' in prayer
    assert 'Цена иска: 240 000 рублей' in text and 'статьи 333.36 НК РФ' in text
    assert 'Статья 83 СК РФ' in text and 'статей 131 и 132 ГПК РФ' in text
    assert '40 000 рублей / 2 = 20 000 рублей' in text
    assert 'половин' in text and 'половины заработка' not in text
    for junk in ('Банковская карта','Отсутствовал','С настоящего времени','Контакты:','года года','Source_text','&DNR'):
        assert junk not in text
    assert text.count('Телефон: +78905678776')==1
    assert text.count('г. Екатеринбург, ул. Мира, д. 78, кв. 89')==1
    assert text.count('Нотариально удостоверенное соглашение')==1


def test_editor_cache_is_not_a_source_and_source_fields_stay_immutable():
    state=labor_case();state['draft_fields']={'debt_period':'Работником мною зарплата не выплачена.'}
    source=deepcopy(state['fields']);result=prepare_case_document(state)
    assert result['fields']==source and state['fields']==source
    assert 'Работодатель не выплатил мне' in result['draft_fields']['debt_period']


def test_corrected_amount_and_period_are_not_restored_from_older_answers():
    from app.services.document_workflow import apply_updates,FieldUpdate
    state=labor_case()
    for key,text in [('amount','90000'),('debt_period','ноябрь')]:
        state=apply_updates(state,[FieldUpdate(key=key,status='filled',value=text,evidence=text)],text)
    original=deepcopy(state['fields']);text,_=artifact(state)
    assert state['fields']==original
    assert 'за ноябрь в размере 90 000 рублей' in text
    assert '100 000 рублей' not in text


def test_one_absence_does_not_establish_both_no_agreement_and_no_judgment():
    state=state_for('claim_alimony_fixed')
    collect_case_turn(state,'Нотариального соглашения нет','existing_support')
    assert not fact(state,'existing_support_absent')
    assert state['fields']['existing_support']['status']=='incomplete'


def test_ambiguous_expenses_are_not_accepted_as_fathers_support():
    state=state_for('claim_alimony_fixed')
    collect_case_turn(state,'Уходит примерно 40 тыс в месяц','assistance')
    assert state['fields']['assistance']['status']=='incomplete'
    collect_case_turn(state,'Это мои общие расходы','assistance')
    assert Decimal(fact(state,'child_budget'))==40000
    assert state['fields']['assistance']['status']=='unknown'
    collect_case_turn(state,'пополам','maintenance_calculation')
    assert fact(state,'half_child_budget')


def test_arithmetic_conflict_is_blocked():
    state=alimony_case();set_field(state,'monthly_amount','30000','30000')
    with pytest.raises(ValueError,match='не совпадает'):artifact(state)


@pytest.mark.asyncio
async def test_multi_fact_wage_reply_skips_period_and_amount_without_provider(monkeypatch):
    state=labor_case()
    for key in ('amount','debt_period','wages'):state['fields'].pop(key,None)
    state.update(last_questions=['wages'],phase='collecting')
    offline=AsyncMock(side_effect=AssertionError('No provider needed for explicit facts'))
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',offline)
    result,answer,_=await advance_interview(state,'Начисленная, но не выплаченная зарплата — 100 000 рублей за октябрь.')
    assert Decimal(result['fields']['amount']['value'])==100000
    assert result['fields']['debt_period']['value']=='октябрь'
    assert result['last_questions'] not in [['debt_period'],['amount'],['wages']]
    offline.assert_not_called()


@pytest.mark.asyncio
async def test_receiving_reply_help_answers_the_question_without_filing_advice(monkeypatch):
    state=labor_case();state.update(last_questions=['payment'],phase='collecting')
    state['fields'].pop('payment',None)
    offline=AsyncMock(side_effect=AssertionError('Local specific explanation'))
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',offline)
    result,answer,_=await advance_interview(state,'А как можно отправить ответ?')
    assert 'инспекция направит вам ответ' in answer and 'электронную почту' in answer
    assert 'электронную подпись' not in answer and result['last_questions']==['payment']
    offline.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('key',['complaint_labor_agency','claim_alimony_fixed'])
async def test_sequential_intake_reaches_ready_and_skips_facts_already_supplied(key,monkeypatch):
    state=state_for(key)
    answers={
        'sender':'Орлов Дмитрий Николаевич' if key=='complaint_labor_agency' else 'Ершина Ольга Ивановна',
        'sender_address':'Екатеринбург, Мира 55, 89','recipient':'Государственная инспекция труда' if key=='complaint_labor_agency' else 'Сайнудинов Олег Михайлович',
        'recipient_address':'не знаю','employer':'ООО «Пример-Сервис»','employer_address':'Место работы: Екатеринбург Мира 68',
        'employment':'Работал кладовщиком с 1 февраля по 20 октября 2026 года. Трудовой договор № 45-ТД',
        'dismissal':'По собственному желанию','wages':'Начисленная, но не выплаченная зарплата — 100 000 рублей за октябрь.',
        'debt_period':'Не выплачена заработная плата за октябрь в сумме 100000 рублей',
        'evidence':'Есть трудовой договор, приказ об увольнении, расчётный листок и банковская выписка.',
        'previous_contact':'Да, ответа не было','requests':'нет','payment':'По почте','contacts':'Телефон: +78905678776',
        'court':'не знаю','sender_details':'Дата рождения: 12.03.1990; место рождения: Екатеринбург; ИНН 678409964723',
        'party_details':'Не знаю','children':'Сайнудинова Анна Олеговна, 12.03.2019. Отцовство подтверждается свидетельством о рождении, не оспаривается. Ребёнок проживает с матерью. Ранее алименты не устанавливались, нотариального соглашения нет.',
        'other_dependants':'нет','assistance':'нет','fixed_grounds':'У отца нерегулярный доход, выполняет разовые заказы',
        'monthly_amount':'20000 рублей в месяц','maintenance_calculation':'Общие расходы на ребёнка — 40000 рублей в месяц.',
        'start':'С настоящего времени','copy_notice':'Нет','attachments':'свидетельство о рождении, справка о проживании ребёнка',
        'date':'27.10.2026','signature':'подпишу сам'}
    offline=AsyncMock(side_effect=RuntimeError('Supplemental extraction unavailable'))
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',offline)
    seen=[]
    for _ in range(40):
        pending=pending_fields(state)
        if not pending:break
        field=pending[0].key
        assert field not in seen,(field,seen,state.get('provider_failure'))
        assert field in answers,field
        seen.append(field)
        state.update(last_questions=[field],phase='collecting')
        state,answer,_=await advance_interview(state,answers[field])
    assert state['phase']=='ready' and not pending_fields(state)
    if key=='complaint_labor_agency':assert 'amount' not in seen and 'violation' not in seen
    else:assert not set(seen)&{'parentage','living','existing_support','payment','requests','pretrial','claim_price','indexation'}
    text,_=artifact(state)
    assert 'Я добавила' not in text and 'Source_text' not in text
    assert not state.get('provider_failure')


@pytest.mark.asyncio
@pytest.mark.parametrize('key',['complaint_labor_agency','claim_alimony_fixed'])
async def test_real_case_download_does_not_depend_on_editor_provider(key,client,db_session,tmp_path,monkeypatch):
    from app.models.chat import ChatSession
    state=labor_case() if key=='complaint_labor_agency' else alimony_case()
    # Explicitly mark only unanswered source questions unknown, as a user can.
    for field in SCENARIOS[key].fields:state['fields'].setdefault(field.key,{'status':'unknown','value':None})
    state.update(phase='ready',last_questions=[])
    monkeypatch.setattr('app.core.config.settings.DOCUMENTS_STORAGE_DIR',str(tmp_path))
    unavailable=AsyncMock(side_effect=RuntimeError('Provider unavailable'))
    monkeypatch.setattr('app.services.gigachat_client.get_gigachat_client',unavailable)
    chat=ChatSession(user_id=1,title=key,document_workflow=state)
    db_session.add(chat);await db_session.commit()
    response=await client.post(f'/documents/interviews/{chat.id}/export')
    assert response.status_code==201,response.text
    download=await client.get('/documents/'+response.json()['document_id']+'/download')
    assert download.status_code==200 and download.content.startswith(b'PK')
    text='\n'.join(p.text for p in Document(BytesIO(download.content)).paragraphs)
    assert '100 000 рублей' in text if key=='complaint_labor_agency' else '20 000 рублей ежемесячно' in text
    unavailable.assert_not_called()


@pytest.mark.parametrize('text',['Source_text\nЗарплата мною не выплачена.','&DNR данные','Я добавила необходимые роли в текст.'])
def test_service_markers_never_pass_export(text):
    assert not formal_text(text)
