import json
from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from docx import Document

from app.services.document_workflow import new_state, recover_interview_facts, apply_updates, FieldUpdate
from app.services.document_export_contract import clean_requisite, formal_text, EDITOR_VERSION, adds_request
from app.services.document_drafting import canonical_editorial, prepare_document_draft, facts_digest, draft_is_current
from app.services.document_quality import quality_issues
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import load_text_package, render_package_blocks, format_template_fields
from app.services.document_workflow_docx import build_legal_docx
from app.services.document_docx_template import fill_docx_template
from app.services.llm_cost import TokenUsage


def state_for(scenario, **values):
    state = new_state(SCENARIOS[scenario].title)
    state.update(scenario=scenario, phase='ready', last_questions=[])
    state['fields'] = {f.key: {'status': 'unknown', 'value': None} for f in SCENARIOS[scenario].fields}
    state['fields'].update({k: {'status': 'filled', 'value': v} for k, v in values.items()})
    return state


@pytest.mark.parametrize('scenario', ['complaint_labor_agency', 'claim_debt_loan', 'power_of_attorney'])
def test_same_parties_are_blocked_across_document_families(scenario):
    state = state_for(scenario, sender='Иванов Иван Иванович', recipient='Иванов Иван Иванович')
    assert 'same_parties' in {issue['code'] for issue in quality_issues(state)}


def test_employer_and_signer_cannot_be_assigned_to_opposing_roles():
    state = state_for('complaint_labor_agency', sender='Иванов Иван Иванович', employer='Иванов Иван Иванович')
    assert 'self_employer' in {issue['code'] for issue in quality_issues(state)}
    state = state_for('motion_postpone', sender='ООО Ромашка', recipient='Иванов Иван Иванович', signature='Иванов Иван Иванович')
    assert 'opponent_signer' in {issue['code'] for issue in quality_issues(state)}


@pytest.mark.asyncio
async def test_recovery_cannot_reuse_isolated_name_or_address_for_another_role(monkeypatch):
    state = state_for('complaint_labor_agency', sender='Иванов Иван Иванович')
    state['user_turns'] = ['Иванов Иван Иванович', 'Екатеринбург, Мира 10']
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client', AsyncMock())
    monkeypatch.setattr('app.services.document_workflow._structured', AsyncMock(return_value=SimpleNamespace(
        content=json.dumps({'updates': [{'key': 'employer', 'source_turns': [2]}, {'key': 'recipient', 'source_turns': [2]},
                                       {'key': 'employer_address', 'source_turns': [3]}]}), usage=TokenUsage(0,0,0,False))))
    result, _ = await recover_interview_facts(state)
    assert result['fields']['employer']['value'] is None
    assert result['fields']['recipient']['value'] is None
    assert result['fields']['employer_address']['value'] is None
    assert result['fields']['sender']['value'] == 'Иванов Иван Иванович'


def test_direct_role_binding_does_not_change_the_interview_or_raw_source():
    state = state_for('complaint_labor_agency')
    state['last_questions'] = ['employer']
    answer = 'ООО СеверСервис'
    result = apply_updates(state, [FieldUpdate(key='employer', value=answer, status='filled', evidence=answer),
        FieldUpdate(key='sender', value=answer, status='filled', evidence=answer)], answer)
    assert result['fields']['employer']['value'] == answer
    assert result['fields']['sender']['value'] is None
    assert result['answer_bindings'] == [{'field':'employer', 'text':answer}]


def test_old_name_is_not_an_answer_to_the_current_role_question():
    state = state_for('complaint_labor_agency', sender='Иванов Иван Иванович')
    state['last_questions'] = ['employer']
    result = apply_updates(state, [FieldUpdate(key='employer', value='Иванов Иван Иванович',
        status='filled', evidence='Иванов Иван Иванович')], 'Иванов Иван Иванович\nНазвание сейчас не помню', latest_message='Название сейчас не помню')
    assert result['fields']['employer']['value'] is None


@pytest.mark.asyncio
@pytest.mark.parametrize('scenario,values,field', [
    ('complaint_labor_agency', {'sender':'Иванов Иван Иванович','employer':'Иванов Иван Иванович'}, 'employer'),
    ('motion_postpone', {'court':'ну наверное Кировский районный суд'}, 'court'),
])
async def test_invalid_roles_and_uncertain_requisites_never_create_a_file(client, db_session, scenario, values, field):
    from app.models.chat import ChatSession
    from app.models.document import Document as StoredDocument
    from app.api.documents import interview_file_reply
    from sqlalchemy import select
    state = state_for(scenario, **values)
    chat = ChatSession(user_id=1, title='Output contract', document_workflow=state)
    db_session.add(chat)
    await db_session.commit()
    response = await client.post(f'/documents/interviews/{chat.id}/export')
    assert response.status_code == 409
    assert not list((await db_session.execute(select(StoredDocument))).scalars())
    reply = await interview_file_reply(chat, 1, db_session, 'body')
    assert chat.document_workflow['last_questions'] == [field]
    assert '/download' not in reply and reply.count('?') == 1


def test_court_uncertainty_is_not_erased_and_identifiers_are_extracted():
    raw = 'ну наверное Кировский районный суд Екатеринбурга'
    state = state_for('motion_postpone', court=raw)
    assert clean_requisite('court', raw) is None
    assert any(issue['field'] == 'court' for issue in quality_issues(state))
    assert state['fields']['court']['value'] == raw
    assert clean_requisite('case_number', 'аа вот нашла: 2-2451/2026') == '2-2451/2026'
    assert clean_requisite('case_number', 'Дело № А60-12345/2026') == 'А60-12345/2026'


def test_metadata_is_not_published_as_a_legal_ground_even_with_a_pinned_old_template():
    state = state_for('motion_postpone', procedure='касается оплаты ремонта квартиры')
    package = {'blocks':[{'role':'body','text':'Процессуальный порядок: {{procedure}}; {{jurisdiction}}.'}]}
    blocks = render_package_blocks(package, SCENARIOS[state['scenario']], state['fields'], format_template_fields(SCENARIOS[state['scenario']], state['fields']))
    assert blocks == []


def test_legacy_fee_never_prints_an_escaped_catalogue_url_or_revision():
    scenario = SCENARIOS['claim_debt_loan']
    legacy = (
        'Государственная пошлина составляет 5 152 рубля. Основание: НК РФ, '
        'подпункт 1 пункта 1 статьи 333.19 (редакция, действующая с 08.09.2024); '
        'https\\://www\\.consultant.ru/document/cons_doc_LAW_28165/.'
    )
    fields = {field.key: {'status': 'unknown', 'value': None} for field in scenario.fields}
    fields['fee'] = {'status': 'filled', 'value': legacy}

    formatted = format_template_fields(scenario, fields)

    assert 'http' not in formatted['fee'].lower()
    assert 'consultant' not in formatted['fee'].lower()
    assert 'редакц' not in formatted['fee'].lower()
    assert 'подпункт 1 пункта 1 статьи 333.19 НК РФ' in formatted['fee']


def test_legacy_citation_cleanup_also_applies_to_a_docx_asset():
    scenario = SCENARIOS['claim_damage_flood']
    package = load_text_package(scenario)
    fields = {field.key: {'status': 'unknown', 'value': None} for field in scenario.fields}
    fields['fee'] = {
        'status': 'filled',
        'value': ('Государственная пошлина составляет 5 152 рубля. Основание: '
                  'НК РФ, подпункт 1 пункта 1 статьи 333.19 '
                  '(редакция, действующая с 08.09.2024); '
                  'https://www.consultant.ru/document/cons_doc_LAW_28165/.'),
    }

    doc = Document(BytesIO(fill_docx_template(package, scenario, fields)))
    text = '\n'.join(paragraph.text for paragraph in doc.paragraphs)

    assert 'consultant' not in text.lower()
    assert 'редакц' not in text.lower()
    assert 'подпункт 1 пункта 1 статьи 333.19 НК РФ' in text


def test_requests_have_uniform_paragraph_style_and_no_duplicate_boilerplate():
    scenario = SCENARIOS['complaint_labor_agency']
    state = state_for(scenario.key, requests='Прошу проверить обстоятельства невыплаты заработной платы.')
    package = load_text_package(scenario)
    blocks = render_package_blocks(package, scenario, state['fields'], format_template_fields(scenario, state['fields']))
    doc = Document(BytesIO(build_legal_docx(scenario.title, blocks)))
    paragraphs = [p for p in doc.paragraphs if 'Прошу проверить' in p.text]
    assert len(paragraphs) == 1 and 'Ответ на обращение' not in paragraphs[0].text
    assert any(b['text']=='{{payment}}' for b in package['blocks'])
    assert paragraphs[0].paragraph_format.first_line_indent.cm == pytest.approx(1.25, abs=.01)
    assert not any('Прошу рассмотреть изложенные' in p.text for p in doc.paragraphs)


@pytest.mark.parametrize('raw', ['Я работал в фирме, ну зп мне не дали', 'Нахожусь в больнице с 9 по 14 ноября, есть справка'])
def test_factual_paragraphs_cannot_bypass_official_editor(raw):
    assert canonical_editorial('facts', raw, 'complaint_labor_agency') is None
    assert canonical_editorial('reasons', raw, 'motion_postpone') is None


def test_old_editorial_cache_is_invalidated_and_chatter_is_rejected():
    state = state_for('motion_postpone', reasons='Нахожусь в больнице')
    state.update(draft_digest=facts_digest(state['fields']), draft_version=EDITOR_VERSION-1)
    assert not draft_is_current(state)
    assert not formal_text('Ну вроде зп не выплатили.')
    assert adds_request('reasons', 'Заявитель просит отложить заседание.', 'Нахожусь на лечении.')
    assert not adds_request('requests', 'Прошу отложить заседание.', 'Перенести заседание.')
    from app.services.document_drafting import _protect_numbers, validate_edit
    _, protected = _protect_numbers('Работал с 1 февраля по 20 октября 2026 года')
    assert list(protected.values()) == ['с 1 февраля по 20 октября 2026 года']
    assert not validate_edit('Заявитель находился в больнице.', 'Нахожусь в больнице.')
    assert canonical_editorial('agreement', 'Расписка от 01.03.2026', 'pretense_debt_loan') == 'Расписка от 01.03.2026.'
    assert canonical_editorial('agreement', 'ну там договор вроде был', 'pretense_debt_loan') is None


@pytest.mark.asyncio
async def test_editor_receives_locked_roles_and_preserves_original_facts(monkeypatch):
    state = state_for('complaint_labor_agency', sender='Иванов Иван Иванович', employer='ООО Ромашка',
                      violation='ну мне не выплатили зп')
    before = deepcopy(state)
    usage = TokenUsage(1,1,2,False)
    fake = SimpleNamespace(chat_completion=AsyncMock(side_effect=[
        SimpleNamespace(content='Заработная плата мне не выплачена.', usage=usage),
        SimpleNamespace(content='{"supported":{"violation":true}}', usage=usage),
    ]))
    result, _ = await prepare_document_draft(state, fake)
    payload = json.loads(fake.chat_completion.call_args_list[0].args[0][1]['content'])
    assert payload['roles']['employer'] == 'Работодатель'
    assert 'ООО Ромашка' not in json.dumps(payload, ensure_ascii=False)
    assert result['draft_fields']['violation'] == 'Заработная плата мне не выплачена.'
    assert state == before and result['fields'] == before['fields']
