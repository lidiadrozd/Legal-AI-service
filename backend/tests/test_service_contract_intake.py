from copy import deepcopy
from unittest.mock import AsyncMock
import pytest

from app.services.document_workflow import new_state, advance_interview, sanitize_interview
from app.services.document_dialogue import infer_scenario
from app.services.document_template_library import load_text_package
from app.services.document_scenarios import SCENARIOS
from app.services.document_contract_facts import collect_contract_turn, repair_contract_facts
from app.services.document_explicit_facts import reuse_personal_signer
from app.services.document_form_composition import _validate_slot
from app.services.document_drafting import canonical_editorial
from app.services.document_workflow import apply_updates, FieldUpdate

PROMPT='Нужен договор с фотографом на съёмку мероприятия.'
DETAILS=('Мероприятие состоится 20 ноября 2026 года в Екатеринбурге, ул. Праздничная, д. 10. '
         'Съёмка нужна с 17:00 до 20:00. Фотограф должен передать не менее 100 обработанных фотографий в формате JPEG, '
         'из них 15 — с дополнительной ретушью. Срок передачи — не позднее 27 ноября 2026 года, способом отправки ссылки на скачивание. '
         'Ссылка должна работать минимум 30 дней. Публиковать фотографии в портфолио и социальных сетях можно только '
         'с отдельного письменного согласия заказчика. Дополнительные часы оплачиваются только после письменного согласования стоимости.')
PRICE=('Стоимость — 18 000 рублей. Предоплата 6 000 рублей вносится при подписании договора, '
       'оставшиеся 12 000 рублей — после передачи фотографий. Дополнительные часы оплачиваются только после '
       'письменного согласования стоимости. Договор подписываем 3 ноября 2026 года.')


def state():
    value=new_state(PROMPT)
    value.update(scenario='contract_services',phase='collecting',text_package=load_text_package(SCENARIOS['contract_services']))
    return value


def filled(value):return dict(value=value, original=value, evidence=value, status='filled')


def test_photographer_routes_without_generic_transaction_question():
    assert infer_scenario(new_state(PROMPT),'')=='contract_services'


def test_rich_answer_populates_distinct_contract_clauses():
    s=state()
    collect_contract_turn(s,PROMPT)
    keys=collect_contract_turn(s,DETAILS,'subject')
    assert {'scope','term','changes','additional_terms'} <= keys
    f=s['fields']
    assert '100' in f['scope']['value'] and '15' in f['scope']['value'] and 'JPEG' in f['scope']['value']
    assert all(x in f['term']['value'] for x in ['20 ноября','27 ноября','17:00','20:00','30 дней','ссылки'])
    assert 'портфолио' in f['additional_terms']['value']
    assert 'письменного согласования' in f['changes']['value']
    assert len(f['subject']['value'])<70
    assert 'портфолио' not in f['term']['value'] and 'дополнительные часы' not in f['scope']['value'].lower()
    assert 'acceptance' not in f  # Delivery format does not establish acceptance.


def test_price_instalments_and_date_survive_payment_method_followup():
    s=state();collect_contract_turn(s,PRICE,'amount')
    assert s['fields']['amount']['value']=='18000.00'
    assert s['fields']['date']['value']=='2026-11-03'
    collect_contract_turn(s,'безнал','payment')
    assert all(x in s['fields']['payment']['value'] for x in ['6 000','12 000','после передачи','Безналичный'])


@pytest.mark.parametrize('scenario',['contract_services','contract_work','contract_loan','contract_housing'])
def test_individual_contract_signatories_reuse_both_known_names(scenario):
    s=state();s['scenario']=scenario
    s['fields'].update(sender=filled('Анна Сергеевна Миронова'),recipient=filled('Максим Олегович Соколов'))
    reuse_personal_signer(s)
    assert s['fields']['signature']['value']=='Анна Сергеевна Миронова'
    assert s['fields']['counterparty_signature']['value']=='Максим Олегович Соколов'


def test_company_and_representative_require_their_own_signatory():
    s=state();s['fields'].update(sender=filled('ООО «Заказчик»'),recipient=filled('Максим Олегович Соколов'))
    reuse_personal_signer(s)
    assert 'signature' not in s['fields']
    s['request']+=' За меня подпишет представитель по доверенности.'
    s['fields'].update(sender=filled('Анна Сергеевна Миронова'),signature=filled('Олег Иванович Петров'))
    reuse_personal_signer(s)
    assert s['fields']['signature']['value']=='Олег Иванович Петров'


@pytest.mark.asyncio
async def test_dense_reply_does_not_reask_scope_and_price(monkeypatch):
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',AsyncMock(side_effect=RuntimeError('offline')))
    s=state()
    for key in ['sender','sender_address','sender_details','recipient','recipient_address','recipient_details']:
        s['fields'][key]=dict(status='unknown',value=None)
    s['last_questions']=['subject']
    s,reply,_=await advance_interview(s,DETAILS)
    assert not s.get('pending_answer'),reply
    assert s['last_questions']==['materials']
    s,reply,_=await advance_interview(s,'в смысле')
    assert s['last_questions']==['materials']
    assert s['fields'].get('materials',{}).get('value') is None
    s['last_questions']=['amount']
    s,reply,_=await advance_interview(s,PRICE)
    assert s['fields']['amount']['value']=='18000.00'
    assert s['fields']['payment']['status']=='filled'


def test_negative_quality_answer_never_becomes_a_past_defect_report():
    text=canonical_editorial('quality','никаких','contract_services')
    assert 'не согласованы' in text
    assert not _validate_slot('quality','Недостатки оказанных услуг не выявлены. Женщина указал, что доказательств нет.','никаких','sentence')


def test_legacy_fields_recover_from_user_history_only():
    s=state();s['user_turns']=[DETAILS,PRICE,'безнал']
    s['fields'].update(subject=filled(DETAILS),term=filled(DETAILS),scope=filled('в предыдущем сообщении всё есть'),
                       materials=filled('в смысле'),payment=filled('безнал'))
    repair_contract_facts(s)
    assert len(s['fields']['subject']['value'])<70
    assert '100' in s['fields']['scope']['value']
    assert '6 000' in s['fields']['payment']['value']
    assert 'materials' not in s['fields']
    copy=deepcopy(s);repair_contract_facts(s)
    assert s==copy


def test_format_alone_does_not_answer_acceptance_question():
    s=state();collect_contract_turn(s,'в формате JPEG','acceptance')
    assert s['fields']['acceptance']['status']=='incomplete'
    s=apply_updates(s,[FieldUpdate(key='acceptance',value='в формате JPEG',evidence='в формате JPEG',status='filled')],'в формате JPEG')
    assert s['fields']['acceptance']['status']=='incomplete'


def test_no_additional_terms_does_not_cancel_publication_restriction():
    s=state();collect_contract_turn(s,DETAILS)
    previous=deepcopy(s['fields']['additional_terms'])
    collect_contract_turn(s,'никаких','additional_terms')
    assert s['fields']['additional_terms']==previous


def test_passport_dates_and_signature_date_never_become_service_deadlines():
    s=state()
    for text in ['серия 1234, номер 567890, выдан МВД города Екатеринбурга, 23.09.2022', '3 ноября 2026 года']:
        collect_contract_turn(s,text)
    assert 'term' not in s['fields']
    collect_contract_turn(s,DETAILS)
    assert '20 ноября' in s['fields']['term']['value']


def test_whole_turn_from_extractor_cannot_duplicate_contract_sections():
    s=state();collect_contract_turn(s,PROMPT)
    s=apply_updates(s,[FieldUpdate(key='subject',status='filled',value=DETAILS,evidence=DETAILS)],DETAILS)
    assert len(s['fields']['subject']['value'])<70
    assert '100' in s['fields']['scope']['value']
    assert 'портфолио' not in s['fields']['term']['value']
    forged=DETAILS.replace('100','900')
    s=apply_updates(s,[FieldUpdate(key='scope',status='filled',value=forged,evidence=DETAILS)],DETAILS)
    assert '900' not in s['fields']['scope']['value']


def test_late_representative_removes_only_inferred_signatures():
    s=state();s['fields'].update(sender=filled('Анна Сергеевна Миронова'),recipient=filled('Максим Олегович Соколов'))
    reuse_personal_signer(s)
    s['user_turns']=['Договор подпишет представитель по доверенности.']
    reuse_personal_signer(s)
    assert 'signature' not in s['fields']


@pytest.mark.asyncio
async def test_known_photographer_terms_export_without_losing_facts_offline():
    from app.services.document_form_composition import prepare_form_document
    s=state();collect_contract_turn(s,PROMPT);collect_contract_turn(s,DETAILS);collect_contract_turn(s,PRICE)
    s['fields']['payment']['value']='безнал. '+s['fields']['payment']['value']
    result,_=await prepare_form_document(s,None)
    assert not set(result['form_review_fields']) & {'subject','scope','term','changes','payment'}
    text=result['draft_fields']
    assert 'обработанных' in text['scope'] and '100' in text['scope'] and '15' in text['scope']
    assert all(v in text['term'] for v in ['20 ноября','27 ноября','17:00','20:00','30 дней'])
    assert 'требуются дополнительные часы' not in text['changes'].lower()
    assert not _validate_slot('scope','Передаются 100 фотографий.','Передаются 100 обработанных фотографий.','sentence')
