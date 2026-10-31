from decimal import Decimal
from copy import deepcopy
from unittest.mock import AsyncMock
import pytest
from app.services.document_workflow import new_state,advance_interview
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import load_text_package
from app.services.document_drafting import validate_edit,canonical_editorial
from app.services.document_form_composition import prepare_form_document,form_presentation_fields,local_candidate,_validate_slot
from app.services.document_intake_checks import identity_suggestion


@pytest.mark.parametrize('source,edited',[
    ('35 тыс руб.','35 000 рублей.'),
    ('35,5 тыс. рублей','35 500 рублей'),
    ('да, 2.10.26. ответа нет. есть сообщение','Обращение состоялось 02.10.2026. Ответ не получен. Имеется сообщение.'),
])
def test_valid_numeric_formatting_is_not_a_fact_change(source,edited):
    assert validate_edit(edited,source)


@pytest.mark.parametrize('source,edited',[
    ('35 тыс руб.','35 рублей.'),
    ('35 тыс руб.','350 000 рублей.'),
    ('2.10.26','02.10.2025'),
    ('Паспорт 45 12 345678','Паспорт 45 12 345679'),
])
def test_numeric_fact_changes_are_still_rejected(source,edited):
    assert not validate_edit(edited,source)


@pytest.mark.parametrize('raw,suggestion',[
    ('Волкова Елена Игоревн','Волкова Елена Игоревна'),
    ('Морозов Андрей Павловичм','Морозов Андрей Павлович'),
    ('Волкова Елена Игоревна',None),
    ('Али Закир Мамедоглы',None),
])
def test_only_likely_typos_are_suggested_not_silently_rewritten(raw,suggestion):
    assert identity_suggestion(raw)==suggestion


def rental_state():
    request='После выезда из съёмной квартиры собственник не возвращает обеспечительный платёж — 35 тысяч рублей. Хочу составить иск.'
    state=new_state(request)
    state.update(scenario='claim_rent_deposit',phase='collecting',text_package=load_text_package(SCENARIOS['claim_rent_deposit']))
    return state


RENTAL_TURNS=[
    ('После выезда из съёмной квартиры собственник не возвращает обеспечительный платёж — 35 тысяч рублей. Хочу составить иск.','sender'),
    ('Волкова Елена Игоревн','sender'),
    ('да','sender_address'),
    ('Екатеринбург, Мира 33, 78','sender_details'),
    ('Серия и номер: 45 12 345678; Дата выдачи: 15.05.2018; Кем выдан: Отделом УФМС России по гор. Москве по району Хамовники; Код подразделения: 770-021','recipient'),
    ('Морозов Андрей Павловичм','recipient'),
    ('да','recipient_address'),
    ('не знаю','court'),
    ('Районный суд Кировского района','party_details'),
    ('не известны','agreement'),
    ('1.10.25 номер 16','property'),
    ('Екатеринбург, Блюхера 67, 12','deposit_payment'),
    ('35 тыс руб. Это был аванс. есть чек','deposit_payment'),
    ('В договоре это обеспечительный платёж. Авансом назвала по ошибке.','deposit_terms'),
    ('К\\вартира возвращена 01.10.2026 по подписанному акту без замечаний. По договору платёж возвращается в течение пяти дней. Долгов по оплате нет.','withholding'),
    ('аванс, никак не объясняет','pretrial'),
    ('да, 2.10.26. ответа нет. есть сообщение','calculation'),
    ('основной долг только','requests'),
    ('прошу вернуть 35000','other_participants'),
    ('нет','copy_notice'),
    ('нет','contacts'),
    ('+79882726289','attachments'),
    ('договор, переписку','date'),
    ('28.10.26','signature'),
    ('сам',None),
]


@pytest.mark.asyncio
async def test_rental_dialogue_confirms_names_once_reuses_return_and_builds_official_fields(monkeypatch):
    provider=AsyncMock(side_effect=AssertionError('Literal answers do not need the provider'))
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',provider)
    state=rental_state()
    for text,next_key in RENTAL_TURNS:
        try:state,answer,_=await advance_interview(state,text)
        except AssertionError as exc:raise AssertionError((text,state.get('last_questions'))) from exc
        assert state['last_questions']==([next_key] if next_key else []),(text,state['last_questions'],answer)
    assert state['phase']=='ready'
    assert state['fields']['sender']['value']=='Волкова Елена Игоревна'
    assert state['fields']['recipient']['value']=='Морозов Андрей Павлович'
    assert state['fields']['signature']['value']==state['fields']['sender']['value']
    assert state['fields']['agreement']['value']=='Договор найма № 16 от 01.10.2025.'
    assert 'без замечаний' in state['fields']['return_facts']['value']
    assert 'пяти дней' in state['fields']['deposit_terms']['value']
    assert 'возвращена' not in state['fields']['deposit_terms']['value']
    assert Decimal(state['fields']['amount']['value'])==35000
    assert state['fields']['claim_price']['value']=='35 000 рублей'
    prepared,_=await prepare_form_document(state,None)
    assert prepared['form_review_fields']==[],prepared['form_review_fields']
    fields=form_presentation_fields(prepared)
    assert fields['deposit_payment']['value']=='Внесён обеспечительный платёж в размере 35 000 рублей. Имеется чек.'
    assert 'Основной долг составляет 35 000 рублей' in fields['calculation']['value']
    assert 'Переписка.' in fields['attachments']['value']
    assert all('требуется редакция' not in str(x.get('value')) for x in fields.values())
    provider.assert_not_called()


@pytest.mark.asyncio
async def test_date_plus_no_requires_specific_clarification(monkeypatch):
    state=rental_state()
    state['fields']={f.key:{'status':'unknown','value':None} for f in SCENARIOS[state['scenario']].fields}
    state['fields'].pop('return_facts');state['last_questions']=['return_facts']
    state,answer,_=await advance_interview(state,'01.10.2026 нет')
    assert state['last_questions']==['return_facts']
    assert 'акту' in answer and 'замечаниям' in answer
    assert not _validate_slot('return_facts','01.10.2026 нет.','01.10.2026 нет','sentence')


@pytest.mark.asyncio
async def test_names_can_be_confirmed_as_written_without_imposed_correction():
    state=rental_state();state['last_questions']=['sender']
    state,_,_=await advance_interview(state,'Волкова Елена Игоревн')
    assert state['fields']['sender']['status']=='incomplete'
    state,_,_=await advance_interview(state,'так в документе')
    assert state['fields']['sender']['value']=='Волкова Елена Игоревн'
