"""Regression of a complete service-debt conversation, not only filled forms."""
from decimal import Decimal
from unittest.mock import AsyncMock
import pytest

from app.services.document_workflow import new_state,advance_interview
from app.services.document_dialogue import asks_for_help,leaves_blank
from app.services.document_form_composition import form_presentation_fields,local_candidate
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import load_text_package
from app.services.document_form_intake import collect_form_turn


@pytest.mark.parametrize('text',['никакие','никаких','никакого','никакой','никак','не определён','неизвестны, это организация'])
def test_negative_answers_are_not_questions(text):
    assert not asks_for_help(text)


@pytest.mark.parametrize('text',['не определён','суд не определен','пока не определён'])
def test_unselected_court_stays_an_explicit_gap(text):
    assert leaves_blank(text)


def test_contract_price_never_overwrites_debt_or_consumes_agreement_answer():
    s=new_state('test');s.update(scenario='claim_debt_services',text_package=load_text_package(SCENARIOS['claim_debt_services']))
    collect_form_turn(s,'Заказчик не выплатил оставшиеся 60 тысяч рублей.',None)
    changed=collect_form_turn(s,'Договор № 18 от 01.08.2026. стоимость — 100 000 рублей.','agreement')
    assert 'agreement' in changed
    assert Decimal(s['fields']['amount']['value'])==60000
    assert Decimal(s['obligation_facts']['contract_price']['value'])==100000
    assert s['fields']['amount']['evidence']=='не выплатил оставшиеся 60 тысяч рублей'


def test_spoken_telegram_reply_and_unedited_sentence_cannot_bypass_editor():
    assert local_candidate('pretrial','да, я ему писал в тг, он не ответил','sentence','claim_debt_services') is None
    assert local_candidate('performance','Разработал сайт. акт подписан 30 сентября.','sentence','claim_debt_services') is None


def test_editor_field_name_is_not_an_extra_document_sentence():
    from app.services.document_form_composition import strip_purpose_echo
    assert strip_purpose_echo('Сайт разработан. Оказанные услуги.','Оказанные услуги','разработал сайт')=='Сайт разработан.'
    assert strip_purpose_echo('Сайт разработан.','Оказанные услуги','разработал сайт')=='Сайт разработан.'


@pytest.mark.asyncio
async def test_service_claim_reuses_initial_amount_advance_and_known_deadline(monkeypatch):
    provider=AsyncMock(side_effect=AssertionError('Explicit answers must not need an LLM'))
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',provider)
    request='Нужен иск: я разработал сайт для заказчика, он принял работу, но не выплатил оставшиеся 60 тысяч рублей.'
    state=new_state(request)
    # Classification is independently tested; start at its selected form so
    # this regression isolates literal intake from model availability.
    state.update(scenario='claim_debt_services',phase='collecting',text_package=load_text_package(SCENARIOS['claim_debt_services']))
    # Each expected key describes the question AFTER the source message.
    turns=[
        (request,'sender'),
        ('Петров Алексей Сергеевич','sender_address'),
        ('Екатеринбург, Московская 57, 67','sender_details'),
        ('12.11.1990 Екатеринбург.','recipient'),
        ('ООО «Тест-Медиа»','recipient_address'),
        ('Екатеринбург, Московская 80','court'),
        ('не определён','party_details'),
        ('не известны, это организация','agreement'),
        ('Договор № 18 от 01.08.2026. стоимость — 100 000 рублей.','performance'),
        ('разработал сайт. акт подписан 30 сентября. Аванс 40 000 получен.','due_date'),
        ('Остаток следовало оплатить до 10 октября. Есть договор, акт и переписка.','procedure'),
        ('предпринимательской деятельностью','pretrial'),
        ('да, я ему писал в тг, он не ответил','calculation'),
        ('основной долг','requests'),
        ('прошу оплатить 60000','other_participants'),
        ('нет','copy_notice'),
        ('нет','facts'),
        ('никакие','contacts'),
        ('+79122423123','attachments'),
        ('договор, акт и переписка','date'),
        ('20.10.26','signature'),
        ('Петров Алексей Сергеевич',None),
    ]
    for text,next_key in turns:
        state,answer,_=await advance_interview(state,text)
        assert not state.get('provider_failure'),(text,answer)
        assert state['last_questions']==([next_key] if next_key else []),(text,state['last_questions'],answer)
    provider.assert_not_called()
    assert state['phase']=='ready'
    assert state['fields']['court']['status']=='unknown'
    assert state['fields']['facts']['status']=='not_applicable'
    assert Decimal(state['fields']['amount']['value'])==60000
    assert '60 000 рублей' in state['fields']['claim_price']['value']
    assert '100 000 рублей − 40 000 рублей = 60 000 рублей' in state['fields']['calculation']['value']
    fields=form_presentation_fields(state)
    assert fields['requests']['value']=='Взыскать с ответчика в пользу истца основную задолженность по оплате оказанных услуг в размере 60 000 рублей.'
