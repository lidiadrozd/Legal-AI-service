from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from io import BytesIO
import pytest
from docx import Document
from app.services.document_workflow import new_state,advance_interview
from app.services.document_dialogue import infer_scenario
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import load_text_package,format_template_fields
from app.services.document_form_composition import prepare_form_document,form_presentation_fields
from app.services.document_docx_template import fill_docx_template
from app.services.chat_titles import suggest_chat_title,update_automatic_title
from complete_form_cases import make_state


@pytest.mark.parametrize('text,key',[
    ('рудовой договор на должность учителя','contract_employment'),
    ('Трудовой договор на должность учителя','contract_employment'),
    ('Нужен трудовой договор между школой и работником на должность учителя','contract_employment'),
    ('У меня уже идёт судебное дело о повреждении ноутбука. Получила заключение сервисного центра и хочу приобщить его к делу.','motion_attach'),
    ('Ходатайство о приобщении документов','motion_attach'),
    ('Хочу подготовить исковое заявление о взыскании ущерба с управляющей компании.','claim_damage_property'),
    ('Получил судебный приказ о взыскании долга за коммунальные услуги, но с долгом не согласен. Нужно подготовить возражения.','motion_order_objection'),
])
@pytest.mark.asyncio
async def test_user_document_purposes_start_correct_intake_without_provider(text,key,monkeypatch):
    provider=AsyncMock(side_effect=AssertionError('This purpose is unambiguous'))
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',provider)
    state,reply,_=await advance_interview(new_state(text),text)
    assert state['scenario']==key and state['phase']=='collecting'
    assert state['last_questions']==['sender']
    assert 'Пока не найден' not in reply and 'Что именно стороны' not in reply
    provider.assert_not_called()
    if key=='contract_employment':
        assert state['fields']['position']['value']=='учитель'
        assert state['fields']['is_pedagogue']['value']=='да'
    if key=='motion_attach' and 'ноутбука' in text:
        assert 'ноутбука' in state['fields']['case_subject']['value']
        assert 'заключение' in state['fields']['documents']['value']


@pytest.mark.asyncio
async def test_followup_changes_document_kind_in_previously_stuck_chat(monkeypatch):
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',AsyncMock(side_effect=AssertionError('no provider')))
    state=new_state('Нужно подготовить документ по судебному делу')
    state.update(unsupported_subject=True,user_turns=['Нужно подготовить документ по судебному делу'],document_kind='claim')
    result,_,_=await advance_interview(state,'Ходатайство о приобщении документов')
    assert result['scenario']=='motion_attach' and result['last_questions']==['sender']


@pytest.mark.asyncio
async def test_missing_contract_has_finite_supported_choices_and_consultation_exit(monkeypatch):
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',AsyncMock(side_effect=AssertionError('no provider')))
    state,reply,_=await advance_interview(new_state('Договор дарения автомобиля'),'Договор дарения автомобиля')
    assert not state['scenario'] and state['unsupported_subject']
    assert 'пока не поддерживается' in reply and 'трудовой договор' in reply
    state,reply,_=await advance_interview(state,'Хочу консультацию')
    assert state['phase']=='cancelled' and 'Перехожу к консультации' in reply


@pytest.mark.asyncio
async def test_mixed_unknown_does_not_erase_explicit_nondelivery(monkeypatch):
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',AsyncMock(side_effect=AssertionError('no provider')))
    state=make_state('pretense_consumer_late_delivery')
    state['fields'].pop('delivery_status');state.update(phase='collecting',last_questions=['delivery_status'])
    state,_,_=await advance_interview(state,'нет, я не знаю где он')
    assert state['fields']['delivery_status']['status']=='filled'
    assert 'не доставлен' in state['fields']['delivery_status']['value']
    assert state['last_questions']!=['delivery_status']


@pytest.mark.asyncio
async def test_recover_legacy_negative_and_format_every_money_appearance():
    state=make_state('pretense_consumer_late_delivery')
    state['fields']['amount']['value']='85000.00'
    state['fields']['purchase']['value']='Приобретён диван за 85000 рублей.'
    state['fields']['delivery_status']={'status':'unknown','value':None,'evidence':'нет, я не знаю где он'}
    state['fields']['payment']['value']='На карту, по которой я платила'
    state['fields']['requests']['value']='возврат оплаты'
    state,_=await prepare_form_document(state,None)
    fields=form_presentation_fields(state)
    assert fields['delivery_status']['status']=='filled' and 'не доставлен' in fields['delivery_status']['value']
    assert 'использованную при оплате' in fields['payment']['value']
    doc=Document(BytesIO(fill_docx_template(state['text_package'],SCENARIOS[state['scenario']],fields)))
    text='\n'.join(p.text for p in doc.paragraphs)
    assert '85000' not in text and text.count('85 000 рублей')>=3
    assert '[состояние исполнения]' not in text


def test_currency_typography_preserves_identifiers_dates_and_originals():
    from app.services.document_presentation import normalize_monetary_text
    raw='85000 рублей; 85 000,50 руб.; паспорт 45 12 345678; телефон +79000339474; 01.09.2026'
    assert normalize_monetary_text(raw)=='85 000 рублей; 85 000,50 руб.; паспорт 45 12 345678; телефон +79000339474; 01.09.2026'


def test_changed_prior_demands_are_a_sequence_not_a_new_condition():
    from app.services.document_drafting import canonical_editorial
    from app.services.document_form_composition import _validate_slot
    raw='доставить диван, а потом и отвенить доставку и вернуть деньги'
    edited=canonical_editorial('seller_response',raw,'pretense_consumer_late_delivery')
    assert 'Первоначально' in edited and 'Впоследствии' in edited
    assert 'отменить доставку' in edited and 'возвратить' in edited
    assert 'В случае' not in edited
    assert not _validate_slot('seller_response','Ранее заявлялось требование о доставке. В случае неисполнения требуется возврат оплаты.',raw,'sentence')


def test_employment_form_has_explicit_labor_terms_and_no_invented_teacher_hours():
    state=make_state('contract_employment');scenario=SCENARIOS[state['scenario']]
    package=load_text_package(scenario)
    required={f.key for f in scenario.fields}
    assert {'start_date','job_function','workplace','amount','work_conditions','schedule','vacation','teaching_load','fixed_term'}<=required
    source=deepcopy(state['fields'])
    state['fields']['teaching_load']={'status':'unknown','value':None}
    state['fields']['vacation']={'status':'unknown','value':None}
    text='\n'.join(p.text for p in Document(BytesIO(fill_docx_template(package,scenario,state['fields']))).paragraphs)
    assert '18 часов' not in text and '56 календарных' not in text
    assert 'обязательному социальному страхованию' in text
    assert 'Исполнитель выполняет' not in text
    assert source['amount']['value']==state['fields']['amount']['value']


def test_chat_titles_describe_document_and_keep_manual_names():
    state=new_state('Трудовой договор на должность учителя')
    assert suggest_chat_title(state)=='Трудовой договор · учитель'
    chat=SimpleNamespace(title='Подготовка документа')
    update_automatic_title(chat,state)
    assert chat.title=='Трудовой договор · учитель'
    chat.title='Мой договор';state['title_manual']=True
    update_automatic_title(chat,state)
    assert chat.title=='Мой договор'


@pytest.mark.asyncio
async def test_chat_list_repairs_old_generic_titles_but_not_manual_ones(db_session):
    from app.models.chat import ChatSession
    state=new_state('Ходатайство о приобщении документов по делу о ноутбуке')
    generic=ChatSession(user_id=1,title='Подготовка документа',document_workflow=state)
    manual=ChatSession(user_id=1,title='Мой спор',document_workflow=state)
    db_session.add_all([generic,manual]);await db_session.commit()
    from app.api.chat import get_chats
    rows=await get_chats(current_user=SimpleNamespace(id=1),db=db_session)
    titles={row.id:row.title for row in rows}
    assert titles[generic.id]=='Приобщение документов · ноутбук'
    assert titles[manual.id]=='Мой спор'
