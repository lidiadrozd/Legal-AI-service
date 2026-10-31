from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
import json
import pytest
from complete_form_cases import make_state
from app.services.document_form_intake import prepare_form_intake
from app.services.document_question_policy import asks_user_to_determine_law, is_legal_help
from app.services.document_quality import quality_issues
from app.services.document_conversation import conversational_interview_turn
from app.services.llm_cost import TokenUsage


@pytest.mark.parametrize('text', ['Какие гарантии предусмотрены законодательством?', 'Какие квалификационные требования установлены законом?', 'Какие статьи нужно указать?'])
def test_law_is_not_a_user_fact(text):
    assert asks_user_to_determine_law(text)


@pytest.mark.parametrize('text', ['Сам посмотри', 'я не знаю, ты скажи', 'посмотри сам закон и скажи'])
def test_delegating_legal_analysis_is_help(text):
    assert is_legal_help(text)


@pytest.mark.parametrize('setting,days', [('Обычные общеразвивающие группы',42), ('Работа с детьми с ОВЗ',56), ('Группы без ОВЗ',42)])
def test_vacation_rule_uses_facts_not_user_knowledge(setting,days):
    state=make_state('contract_employment')
    state['request']='Трудовой договор с воспитателем детского сада'
    for key,value in [('position','воспитатель'),('leave_context',setting)]:state['fields'][key]={'status':'filled','value':value}
    state['fields'].pop('vacation')
    prepare_form_intake(state)
    assert state['fields']['vacation']['value']==f'{days} календарных дней'
    assert state['fields']['vacation']['sources']


def test_agreed_more_favorable_vacation_is_not_overwritten():
    state=make_state('contract_employment');state['request']='Договор с воспитателем детского сада'
    state['fields']['position']['value']='воспитатель'
    state['fields']['leave_context']['value']='Общеразвивающие группы'
    prepare_form_intake(state)
    assert state['fields']['vacation']['value']=='56 календарных дней'


def test_cashier_in_store_never_enters_pedagogical_branch():
    state=make_state('contract_employment')
    state['request']='Нужен трудовой договор между продуктовым магазином «Монетка» и кассиром'
    state['fields']['sender']={'status':'filled','value':'Магазин «Монетка»'}
    state['fields']['position']={'status':'filled','value':'кассир'}
    state['fields']['recipient']={'status':'filled','value':'Берёзава Анна Викторовна'}
    for key in ('is_pedagogue','vacation','counterparty_signature'):
        state['fields'].pop(key,None)
    prepare_form_intake(state)
    assert state['fields']['is_pedagogue']['value']=='нет'
    assert state['fields']['vacation']['value']=='28 календарных дней'
    assert state['fields']['counterparty_signature']['value']=='Берёзава Анна Викторовна'


def test_explicit_cashier_request_sets_position_without_reasking():
    from app.services.document_form_intake import collect_form_turn
    state=make_state('contract_employment');state['fields'].pop('position',None)
    consumed=collect_form_turn(state,'Нужен трудовой договор между продуктовым магазином и кассиром',None)
    assert 'position' in consumed
    assert state['fields']['position']['value']=='кассир'


def test_manager_title_is_not_accepted_as_authority_document():
    state=make_state('contract_employment')
    state['fields']['authority_basis']={'status':'filled','value':'Менеджер магазина'}
    assert 'authority_document_required' in {issue['code'] for issue in quality_issues(state)}


def test_pedagogical_legal_text_is_only_added_for_pedagogical_work():
    from app.services.document_form_rules import prepare_form_rules
    cashier=make_state('contract_employment')
    cashier['fields']['is_pedagogue']={'status':'filled','value':'нет'}
    prepare_form_rules(cashier)
    assert 'главы 52' not in cashier['fields']['legal_basis']['value']
    teacher=make_state('contract_employment')
    teacher['fields']['is_pedagogue']={'status':'filled','value':'да'}
    prepare_form_rules(teacher)
    assert 'главы 52' in teacher['fields']['legal_basis']['value']


@pytest.mark.parametrize('position,role', [('воспитатель','воспитателя'),('бухгалтер','бухгалтера'),('водитель','водителя')])
def test_mixed_representative_and_employee_address_are_separate_facts(position,role):
    from app.services.document_form_intake import collect_form_turn
    state=make_state('contract_employment')
    state['fields']['position']['value']=position
    for key in ('sender_details','recipient_address'):state['fields'].pop(key)
    consumed=collect_form_turn(state,f'Руководитель организации: Орлова Анна Ивановна. Адрес {role}: Екатеринбург Мира 67, 89','sender_details')
    assert consumed>={'sender_details','recipient_address'}
    assert 'Орлова' in state['fields']['sender_details']['value']
    assert 'Мира' in state['fields']['recipient_address']['value']
    assert 'Орлова' not in state['fields']['recipient_address']['value']


def test_real_clause_number_is_not_a_placeholder_letter():
    from app.services.document_docx_template import _value,docx_review_fields
    fields={'delivery_due':{'format':'sentence'}}
    source='Срок — до 20.10.2026, согласно пункту 2 договора.'
    assert _value('delivery_due',{'delivery_due':source},{'fields':fields},{})==source
    assert docx_review_fields({'delivery_due':{'status':'filled','value':source}})==[]


def test_personal_purpose_is_in_the_case_required_by_the_template():
    from app.services.document_drafting import canonical_editorial
    assert canonical_editorial('consumer_status','личное употребление в пищу','pretense_consumer_defective_goods')=='личного употребления в пищу'


def test_one_salary_payment_per_month_is_not_accepted():
    state=make_state('contract_employment');state['fields']['payment']['value']='5 числа каждого месяца'
    assert 'salary_twice_monthly' in {i['code'] for i in quality_issues(state)}


def test_city_and_date_use_page_width_tab_in_every_native_contract():
    from app.services.document_scenarios import SCENARIOS
    from app.services.document_template_library import load_text_package
    from app.services.document_docx_template import load_docx_asset,NS,W
    from zipfile import ZipFile
    from io import BytesIO
    from lxml import etree
    checked=[]
    for scenario in SCENARIOS.values():
        package=load_text_package(scenario)
        if not package or not package.get('docx_asset'):continue
        payload,_=load_docx_asset(package,scenario)
        with ZipFile(BytesIO(payload)) as z:root=etree.fromstring(z.read('word/document.xml'))
        for paragraph in root.findall('.//w:p',NS):
            tags=paragraph.xpath('.//w:sdtPr/w:tag/@w:val',namespaces=NS)
            if 'field:place' in tags and 'field:date' in tags:
                assert paragraph.find('.//w:tab',NS) is not None,scenario.key
                assert paragraph.xpath('w:pPr/w:tabs/w:tab[@w:val="right"]',namespaces=NS),scenario.key
                checked.append(scenario.key)
    assert 'contract_employment' in checked and 'contract_housing' in checked


def test_iso_dates_in_prose_are_formatted_but_identifiers_remain_exact():
    from app.services.document_presentation import normalize_prose_dates
    assert normalize_prose_dates('Заседание назначено на 2026-11-10.')=='Заседание назначено на 10.11.2026.'
    assert normalize_prose_dates('договор № 2026-11-10, дело 2-2026-11-10')=='договор № 2026-11-10, дело 2-2026-11-10'


def test_legacy_fallback_uses_right_tab_for_city_and_date():
    from app.services.document_scenarios import SCENARIOS
    from app.services.document_template_library import load_text_package,render_package_blocks
    scenario=SCENARIOS['act_services'];package=load_text_package(scenario)
    blocks=render_package_blocks(package,scenario,{},dict(place='Екатеринбург',date='29.10.2026'))
    assert any(b['role']=='place_date' and b['text']=='Екатеринбург\t29.10.2026' for b in blocks)


def test_ambiguous_vacation_is_resolved_after_group_facts():
    state=make_state('contract_employment');state['request']='Договор воспитателя детского сада'
    state['fields']['position']['value']='воспитатель'
    state['fields']['vacation']['value']='42 или 56 календарных дней'
    state['fields']['leave_context']['value']='Обычные общеразвивающие группы'
    prepare_form_intake(state)
    assert state['fields']['vacation']['value']=='42 календарных дней'
    assert not any(i['code']=='vacation_category_required' for i in quality_issues(state))


@pytest.mark.parametrize('key,value,code', [
    ('place','Детский сад «Будущее»','locality_required'),
    ('workplace','на данный момент в поисках работы','future_workplace'),
    ('schedule','пн-пт 7:30-19:30','working_time_clarification'),
    ('work_conditions','Стандартные условия регулируются законодательством и СанПиН','sout_facts_missing'),
    ('pay_conditions','Сверхурочные 5000 рублей в неделю','overtime_not_flat_fee'),
])
def test_reported_wrong_contract_terms_require_clarification(key,value,code):
    state=make_state('contract_employment');state['fields'][key]['value']=value
    assert code in {x['code'] for x in quality_issues(state)}


@pytest.mark.asyncio
async def test_legal_help_does_not_become_contract_term_and_rule_question_is_retried(monkeypatch):
    state=make_state('contract_employment');state['fields'].pop('compensations')
    state.update(phase='collecting',last_questions=['compensations'])
    before=deepcopy(state['fields']);calls=[]
    async def generate(client,prompt,data,*args,**kwargs):
        calls.append(data)
        assert data['verified_legal_context'] and data['help_requested']
        question='Какие гарантии предусмотрены законодательством?' if len(calls)==1 else 'Есть ли дополнительные согласованные выплаты сверх обязательных гарантий?'
        return SimpleNamespace(content=json.dumps(dict(field='compensations',question=question,explanation='Обязательные гарантии применяются по ТК РФ. Нужны только дополнительные договорённости.')),usage=TokenUsage(1,1,2,False))
    monkeypatch.setattr('app.services.document_conversation.get_gigachat_client',AsyncMock(return_value=object()))
    monkeypatch.setattr('app.services.document_conversation._structured',generate)
    updated,answer,_=await conversational_interview_turn(state,'Сам посмотри')
    assert updated['fields']==before
    assert len(calls)==2 and 'дополнительные' in answer
    assert updated['question_origin']=='gigachat'


@pytest.mark.asyncio
async def test_signature_question_cannot_ask_which_signature_to_put(monkeypatch):
    state=make_state('contract_employment');state['fields'].pop('signature')
    state.update(phase='collecting',last_questions=['signature'])
    calls=[]
    async def generate(client,prompt,data,*args,**kwargs):
        calls.append(data)
        question='Какую подпись должен поставить представитель работодателя?' if len(calls)==1 else 'Укажите полное ФИО представителя работодателя, который подпишет договор?'
        return SimpleNamespace(content=json.dumps(dict(field='signature',question=question,explanation='')),usage=TokenUsage(1,1,2,False))
    monkeypatch.setattr('app.services.document_conversation.get_gigachat_client',AsyncMock(return_value=object()))
    monkeypatch.setattr('app.services.document_conversation._structured',generate)
    _,answer,_=await conversational_interview_turn(state,'продолжить')
    assert len(calls)==2
    assert 'какую подпись' not in answer.casefold()


@pytest.mark.asyncio
async def test_question_planner_failure_continues_with_template_question(monkeypatch):
    state=make_state('contract_employment');state['fields'].pop('authority_basis')
    state.update(phase='collecting',last_questions=['authority_basis'])
    monkeypatch.setattr('app.services.document_conversation.get_gigachat_client',AsyncMock(side_effect=RuntimeError('network')))
    updated,answer,_=await conversational_interview_turn(state,'продолжить')
    assert updated['question_origin']=='fallback'
    assert updated['last_questions']==['authority_basis']
    assert 'Не удалось получить следующий вопрос' not in answer
    assert 'документ подтверждает' in answer
