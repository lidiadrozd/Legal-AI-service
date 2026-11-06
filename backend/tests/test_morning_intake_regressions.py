from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from app.services.document_workflow import new_state, advance_interview, pending_fields
from app.services.document_conversation import conversational_interview_turn
from app.services.document_contract_facts import collect_contract_turn
from app.services.document_form_intake import collect_form_turn
from app.services.document_explicit_facts import reuse_personal_signer


ROOM = ('Нужен договор с мастером на ремонт комнаты. Заказчик — Ирина Павловна Зайцева, '
        'исполнитель — Артём Сергеевич Ковалёв. Оба действуем лично, без представителей. '
        'Нужно покрасить стены и потолок комнаты площадью 18 м² по адресу: Екатеринбург, '
        'ул. Учебная, д. 16, кв. 24. Подготовка поверхностей входит в работу, замена проводки не входит. '
        'Работы с 10 по 20 ноября 2026 года. Цена — 45 000 рублей: аванс 15 000 при подписании, '
        'остаток после приёмки. Краску покупаю я, инструменты предоставляет мастер. '
        'Результат проверяю в течение двух рабочих дней. Недостатки покраски мастер исправляет '
        'бесплатно за пять рабочих дней. Дополнительные работы — только после письменного согласования цены. '
        'Договор составляем 5 ноября 2026 года в Екатеринбурге. Паспортные данные и адрес мастера '
        'внесём вручную. Мой адрес совпадает с адресом ремонта.')


def room_state():
    from app.services.document_template_library import load_text_package
    from app.services.document_scenarios import SCENARIOS
    s = new_state(ROOM)
    s.update(scenario='contract_work', phase='collecting', last_questions=['sender'],
             text_package=load_text_package(SCENARIOS['contract_work']))
    return s


def assert_room(s):
    f = s['fields']
    assert f['sender']['value'] == 'Ирина Павловна Зайцева'
    assert f['recipient']['value'] == 'Артём Сергеевич Ковалёв'
    assert f['signature']['value'] == f['sender']['value']
    assert f['counterparty_signature']['value'] == f['recipient']['value']
    assert f['sender_address']['status'] == 'filled'
    assert 'Учебная' in f['sender_address']['value'] and '24' in f['sender_address']['value']
    for k in ['sender_details', 'recipient_details', 'recipient_address']:
        assert f[k]['status'] == 'unknown'
    assert len(f['subject']['value']) < 60
    assert all(x in f['scope']['value'] for x in ['18 м²', 'подготовка'.capitalize(), 'проводки не входит'])
    assert 'Краску' in f['materials']['value'] and 'инструменты' in f['materials']['value']
    assert 'двух рабочих дней' in f['acceptance']['value']
    assert 'пять рабочих дней' in f['quality']['value']
    assert f['amount']['value'] == '45000.00'
    assert '15 000' in f['payment']['value'] and 'после приёмки' in f['payment']['value']
    assert f['date']['value'] == '2026-11-05'
    assert f['place']['value'] == 'Екатеринбурге'
    assert not set(x.key for x in pending_fields(s)) & {
        'sender', 'recipient', 'sender_address', 'sender_details', 'recipient_details',
        'recipient_address', 'subject', 'scope', 'materials', 'term', 'amount', 'payment',
        'acceptance', 'changes', 'quality', 'place', 'date', 'signature', 'counterparty_signature'}


def test_whole_room_turn_is_split_without_copying_story_into_names():
    s = room_state()
    collect_form_turn(s, ROOM, 'sender')
    collect_contract_turn(s, ROOM, 'sender')
    reuse_personal_signer(s)
    assert_room(s)


@pytest.mark.asyncio
async def test_room_opening_and_later_rich_answer_work_when_provider_is_offline(monkeypatch):
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client', AsyncMock(side_effect=RuntimeError('offline')))
    for s in [new_state(ROOM), room_state()]:
        result, answer, _ = await advance_interview(s, ROOM)
        assert answer and not result.get('pending_answer')
        assert_room(result)


@pytest.mark.asyncio
async def test_retry_processes_saved_answer_instead_of_returning_empty(monkeypatch):
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client', AsyncMock(side_effect=RuntimeError('offline')))
    s = room_state()
    s['request'] = 'Нужен договор с мастером на ремонт комнаты.'
    s['pending_answer'] = {'message': 'Ирина Павловна Зайцева', 'questions': ['sender']}
    s['provider_failure'] = {'kind': 'invalid_response', 'attempts': 1}
    result, answer, _ = await conversational_interview_turn(s, 'повтори')
    assert answer.strip()
    assert result['fields']['sender']['value'] == 'Ирина Павловна Зайцева'
    assert not result.get('pending_answer') and not result.get('provider_failure')
    assert 'sender' not in result['last_questions']


@pytest.mark.asyncio
async def test_reminder_recovers_room_facts_without_reasking_known_scope(monkeypatch):
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client', AsyncMock(side_effect=RuntimeError('offline')))
    s = room_state()
    s['last_questions'] = ['scope']
    s['user_turns'] = [ROOM]
    result, answer, _ = await conversational_interview_turn(s, 'посмотри выше')
    assert_room(result)
    assert result['last_questions'] != ['scope']
    assert 'вручного' not in answer


@pytest.mark.asyncio
async def test_unresolved_reminder_has_manual_exit_instead_of_question_loop(monkeypatch):
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client', AsyncMock(side_effect=RuntimeError('offline')))
    s = room_state()
    s['request'] = 'Нужен договор с мастером на ремонт комнаты.'
    s['last_questions'] = ['sender']
    result, answer, _ = await conversational_interview_turn(s, 'посмотри выше')
    assert '?' not in answer and 'ручного заполнения' in answer
    result, answer, _ = await conversational_interview_turn(result, 'уже писала')
    assert '?' not in answer and 'приостановлен' in answer
    result, answer, _ = await conversational_interview_turn(result, 'оставь для ручного заполнения')
    assert result['fields']['sender']['status'] == 'unknown'
    assert result['last_questions'] != ['sender']


@pytest.mark.asyncio
async def test_facts_before_a_help_question_are_still_captured(monkeypatch):
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client', AsyncMock(side_effect=RuntimeError('offline')))
    s, answer, _ = await advance_interview(new_state(ROOM + ' Что ещё нужно?'), ROOM + ' Что ещё нужно?')
    assert_room(s)
    assert answer


def test_editor_does_not_publish_grammar_instructions_or_invent_acceptance_start():
    from app.services.document_form_composition import _validate_slot, local_candidate
    source='Результат проверяю в течение двух рабочих дней.'
    assert local_candidate('acceptance',source,'sentence','contract_work') == 'Заказчик проверяет результат в течение двух рабочих дней.'
    assert not _validate_slot('acceptance', 'Результат проверяется в течение двух рабочих дней. Заказчик и Подрядчик обозначаются в мужском роде.', source, 'sentence')
    assert not _validate_slot('acceptance', 'Результат проверяется в течение двух рабочих дней с момента выполнения работ.', source, 'sentence')
