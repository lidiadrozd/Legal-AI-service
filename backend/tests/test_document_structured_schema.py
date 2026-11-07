"""Real intake regressions, branching, unknowns and delivered DOCX contents."""
from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from docx import Document

from app.services.document_scenarios import SCENARIOS, field_is_active, render_scenario
from app.services.document_template_library import load_text_package, render_package_blocks, format_template_fields
from app.services.document_workflow import new_state, advance_interview, pending_fields, sanitize_interview, normalize_field
from app.services.document_schema import catalog_audit, readiness_report, schema_issues
from app.services.document_drafting import canonical_editorial, facts_digest
from app.services.document_export_contract import EDITOR_VERSION
from app.services.document_workflow_docx import build_legal_docx


def filled(value):
    return {'status': 'filled', 'value': value, 'original': value, 'evidence': value, 'error': None}


def flood_state():
    scenario = SCENARIOS['claim_damage_flood']
    state = new_state('Нужен иск о возмещении ущерба от залива квартиры')
    state.update(scenario=scenario.key, phase='collecting', schema_version=2, text_package=load_text_package(scenario))
    return state


@pytest.mark.asyncio
@pytest.mark.parametrize('scenario,key', [('claim_damage_flood', 'recipient_address'), ('complaint_labor_agency', 'employer_address')])
async def test_relative_address_is_confirmed_and_survives_following_turns(monkeypatch, scenario, key):
    state = new_state('Нужен документ')
    state.update(scenario=scenario, phase='collecting', last_questions=[key])
    state['fields'] = {f.key: {'status': 'unknown', 'value': None} for f in SCENARIOS[scenario].fields if f.key != key}
    state['fields']['sender_address'] = filled('г. Екатеринбург, ул. Ленина, д. 25, кв. 12')
    offline = AsyncMock(side_effect=AssertionError('No LLM for address components'))
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client', offline)
    state, answer, _ = await advance_interview(state, 'квартира № 16 в том же доме')
    assert state['fields'][key]['status'] == 'incomplete'
    assert 'Ленина, д. 25, кв. 16?' in answer
    state, _, _ = await advance_interview(state, 'да')
    assert state['fields'][key]['value'] == 'г. Екатеринбург, ул. Ленина, д. 25, кв. 16'
    fixed = sanitize_interview(state)
    assert fixed['fields'][key]['status'] == 'filled'
    assert fixed['fields'][key]['original'] == 'квартира № 16 в том же доме'
    assert fixed['fields'][key]['confirmation'] == 'да'
    offline.assert_not_called()


def test_city_does_not_make_an_unresolved_relative_address_complete():
    spec = next(f for f in SCENARIOS['claim_damage_flood'].fields if f.key == 'recipient_address')
    value, error = normalize_field(spec, 'г. Екатеринбург, Квартира № 16 В Том Же Доме')
    assert error
    value, error = normalize_field(spec, 'Екатеринбург, Блюхера 45, 35')
    assert error is None and value == 'г. Екатеринбург, ул. Блюхера, д. 45, кв. 35'
    assert normalize_field(spec, 'г. Екатеринбург, кв. 16')[1]


@pytest.mark.asyncio
async def test_changed_reference_cannot_be_confirmed_with_old_components():
    state = flood_state()
    state['last_questions'] = ['recipient_address']
    state['fields'] = {f.key: {'status': 'unknown', 'value': None} for f in SCENARIOS[state['scenario']].fields if f.key != 'recipient_address'}
    state['fields']['sender_address'] = filled('г. Екатеринбург, ул. Ленина, д. 25, кв. 12')
    state, _, _ = await advance_interview(state, 'квартира 16 в том же доме')
    state['fields']['sender_address'] = filled('г. Екатеринбург, ул. Мира, д. 10, кв. 5')
    state, answer, _ = await advance_interview(state, 'да')
    assert state['fields']['recipient_address']['status'] == 'incomplete'
    assert 'изменился' in answer


@pytest.mark.asyncio
@pytest.mark.parametrize('answer,expected', [('ремонт ещё не выполнен', 'не восстановлено'), ('ремонт сделан', 'восстановлено'), ('частично', 'частично восстановлено')])
async def test_restoration_branch_controls_next_question_and_rendering(answer, expected):
    state = flood_state()
    state['fields'] = {f.key: {'status': 'unknown', 'value': None} for f in SCENARIOS[state['scenario']].fields}
    for key in ('restoration', 'restoration_costs', 'restoration_estimate'):
        state['fields'].pop(key)
    state['last_questions'] = ['restoration']
    state, reply, _ = await advance_interview(state, answer)
    assert state['fields']['restoration']['value'] == expected
    pending = {f.key for f in pending_fields(state)}
    assert ('restoration_costs' in pending) == (expected != 'не восстановлено')
    assert ('restoration_estimate' in pending) == (expected != 'восстановлено')
    assert len(state['last_questions']) == 1
    rendered = render_scenario(SCENARIOS[state['scenario']], state['fields'], state['text_package'])
    assert ('[выполненный ремонт и расходы]' in rendered) == (expected != 'не восстановлено')
    assert ('[предстоящие восстановительные расходы]' in rendered) == (expected != 'восстановлено')


@pytest.mark.asyncio
async def test_yes_choice_is_data_and_no_choice_does_not_trigger_optional_questions():
    state = flood_state()
    state['last_questions'] = ['expertise']
    state, _, _ = await advance_interview(state, 'да')
    assert state['fields']['expertise']['value'] == 'да'
    assert sanitize_interview(state)['fields']['expertise']['status'] == 'filled'
    assert 'expertise_details' in {f.key for f in pending_fields(state)}
    state['last_questions'] = ['expertise']
    state, _, _ = await advance_interview(state, 'нет')
    assert 'expertise_details' not in {f.key for f in pending_fields(state)}
    assert 'Назначение судебной экспертизы' not in render_scenario(SCENARIOS[state['scenario']], state['fields'], state['text_package'])


@pytest.mark.asyncio
async def test_unknown_choice_is_preserved_without_forcing_an_option():
    state = flood_state()
    state['last_questions'] = ['restoration']
    state, _, _ = await advance_interview(state, 'не знаю')
    assert state['fields']['restoration']['status'] == 'unknown'
    assert not field_is_active(next(f for f in SCENARIOS[state['scenario']].fields if f.key == 'restoration_costs'), state['fields'])
    assert any(item['field'] == 'restoration' for item in readiness_report(state, state['text_package'])['missing'])


@pytest.mark.asyncio
async def test_vague_request_is_clarified_without_losing_other_facts():
    state = flood_state()
    state['last_questions'] = ['requests']
    state['fields']['amount'] = filled('145000.00')
    state, _, _ = await advance_interview(state, 'прошу возместить ущерб и решить проблему со стиральной машиной')
    assert state['fields']['requests']['status'] == 'incomplete'
    assert state['fields']['amount']['value'] == '145000.00'
    assert normalize_field(next(f for f in SCENARIOS[state['scenario']].fields if f.key == 'requests'), 'только возмещение ущерба')[1] is None


def test_catalog_is_audited_without_claiming_every_template_is_complete():
    rows = catalog_audit()
    # The audit includes the three legacy/basic structures in addition to
    # the current public catalog.  The nonresidential-sale form is now a
    # complete structured form, so these counts intentionally grew with the
    # supported library rather than silently excluding the new template.
    assert len(rows) == 55 and not [r for r in rows if r['issues']]
    assert {'claim_damage_flood', 'contract_housing', 'contract_services', 'contract_work', 'contract_loan', 'complaint_consumer_agency'} <= {r['scenario'] for r in rows if r['coverage'] == 'structured'}
    assert next(r for r in rows if r['scenario'] == 'claim_debt_loan')['coverage'] == 'structured'
    assert sum(r['coverage']=='structured' for r in rows)==52
    scenario = SCENARIOS['claim_damage_flood']
    broken = deepcopy(load_text_package(scenario))
    broken['blocks'] = [b for b in broken['blocks'] if '{{property_right}}' not in b['text']]
    assert 'unrendered_field:property_right' in schema_issues(scenario, broken)


def test_incomplete_draft_reports_missing_items_and_dispatch_action():
    state = flood_state()
    state['fields'].update({'court': {'status': 'unknown', 'value': None}, 'copy_status': filled('не направлены')})
    report = readiness_report(state, state['text_package'])
    assert report['status'] == 'incomplete_draft'
    assert any(item['field'] == 'court' for item in report['missing'])
    assert report['actions'] and report['coverage'] == 'structured'
    assert not report['lawyer_reviewed']


def test_source_evidence_and_dispatch_answers_have_safe_official_equivalents():
    assert canonical_editorial('copy_notice', 'предстоит', 'claim_damage_flood').endswith('пока не направлены.')
    assert canonical_editorial('evidence', 'Есть акт от управляющей компании, отчёт оценщика и фото', 'claim_damage_flood') == 'Доказательства: акт от управляющей компании, отчёт оценщика и фото.'
    assert canonical_editorial('evidence', 'Акт, ну я им звонила и наверное оценщик есть', 'claim_damage_flood') is None
    from app.services.document_drafting import validate_edit
    assert validate_edit('Письменная претензия направлена ответчику 16.10.2026. Ответа нет.', 'Письменную претензию направила ответчику 16.10.2026. Ответа нет.')
    assert not validate_edit('Имеется отчёт независимого оценщика.', 'Имеется отчёт оценщика.')


@pytest.mark.asyncio
async def test_editor_rejection_keeps_confirmed_answers_and_interview_cursor(monkeypatch):
    from fastapi import HTTPException
    from app.services.document_drafting import DraftPreparationError
    from app.api.documents import interview_file_reply
    state = flood_state()
    state.update(phase='ready', last_questions=[])
    state['fields']['evidence'] = filled('Есть акт и фото')
    before = deepcopy(state)
    failure = HTTPException(502, 'editor failed')
    failure.__cause__ = DraftPreparationError(['evidence'], state, 'invalid edit')
    monkeypatch.setattr('app.api.documents.prepare_interview_file', AsyncMock(side_effect=failure))
    chat = SimpleNamespace(id=1, document_workflow=state)
    reply = await interview_file_reply(chat, 1, None, '')
    assert chat.document_workflow['fields'] == before['fields']
    assert chat.document_workflow['phase'] == 'ready' and chat.document_workflow['last_questions'] == []
    assert 'Повторять сведения не нужно' in reply and '/download' not in reply


def test_docx_has_real_paragraphs_and_only_selected_branches():
    state = flood_state()
    scenario = SCENARIOS[state['scenario']]
    state['fields'] = {f.key: {'status': 'unknown', 'value': None} for f in scenario.fields}
    state['fields'].update({k: filled(v) for k, v in {
        'sender': 'Иванова Мария Андреевна', 'recipient': 'Кузнецов Сергей Викторович',
        'property_address': 'г. Екатеринбург, ул. Ленина, д. 25, кв. 12',
        'source_address': 'г. Екатеринбург, ул. Ленина, д. 25, кв. 16',
        'amount': '145000.00', 'restoration': 'не восстановлено', 'restoration_estimate': 'Стоимость работ определена отчётом оценщика.',
        'restoration_costs': 'НЕАКТИВНЫЙ СТАРЫЙ ОТВЕТ', 'expertise': 'нет', 'security': 'нет',
        'requests': 'Взыскать с ответчика в пользу истца возмещение материального ущерба.',
        'date': '2026-10-18', 'signature': 'Иванова Мария Андреевна',
    }.items()})
    from app.services.document_form_composition import form_presentation_fields
    fields=form_presentation_fields(state)
    blocks = render_package_blocks(state['text_package'], scenario, fields, format_template_fields(scenario, fields))
    doc = Document(BytesIO(build_legal_docx(scenario.title, blocks)))
    text = '\n'.join(p.text for p in doc.paragraphs)
    assert 'НЕАКТИВНЫЙ' not in text and 'Стиральной Машиной' not in text
    assert 'возмещение имущественного ущерба от залива квартиры в размере 145 000 рублей.' in text
    assert 'Размер возмещения материального ущерба, заявленного ко взысканию:' not in text
    assert '[право истца на квартиру и подтверждение]' in text and 'Выполненные работы' not in text
    assert doc.sections[0].page_width.cm == pytest.approx(21, abs=.01)


@pytest.mark.asyncio
async def test_flood_export_is_persisted_downloadable_and_marked_as_incomplete_draft(client, db_session, monkeypatch, tmp_path):
    from app.models.chat import ChatSession
    from app.models.document import Document as StoredDocument
    from sqlalchemy import select
    state = flood_state()
    scenario = SCENARIOS[state['scenario']]
    state.update(phase='ready', last_questions=[])
    state['fields'] = {f.key: {'status': 'unknown', 'value': None} for f in scenario.fields}
    state['fields'].update({k: filled(v) for k, v in {
        'sender': 'Иванова Мария Андреевна', 'recipient': 'Кузнецов Сергей Викторович',
        'sender_address': 'г. Екатеринбург, ул. Ленина, д. 25, кв. 12',
        'recipient_address': 'г. Екатеринбург, ул. Ленина, д. 25, кв. 16',
        'amount': '145000.00', 'copy_status': 'не направлены',
        'requests': 'только возмещение ущерба', 'date': '2026-10-18',
    }.items()})
    fake = SimpleNamespace(chat_completion=AsyncMock(side_effect=AssertionError('Canonical text needs no model')))
    monkeypatch.setattr('app.services.gigachat_client.get_gigachat_client', AsyncMock(return_value=fake))
    monkeypatch.setattr('app.api.documents._storage_root', lambda: tmp_path)
    chat = ChatSession(user_id=1, title='Structured export QA', document_workflow=state)
    db_session.add(chat)
    await db_session.commit()
    response = await client.post(f'/documents/interviews/{chat.id}/export')
    assert response.status_code == 201, response.text
    doc_id = response.json()['document_id']
    downloaded = await client.get(f'/documents/{doc_id}/download')
    assert downloaded.status_code == 200
    doc = Document(BytesIO(downloaded.content))
    text = '\n'.join(p.text for p in doc.paragraphs)
    assert '[право истца на квартиру и подтверждение]' in text and '[суд и адрес]' in text
    assert 'Квартира № 16 В Том Же Доме' not in text
    stored = (await db_session.execute(select(StoredDocument).where(StoredDocument.id == doc_id))).scalar_one()
    report = stored.generation_meta['readiness']
    assert report['status'] == 'incomplete_draft' and report['actions']
    assert stored.generation_meta['template_version'] == load_text_package(SCENARIOS['claim_damage_flood'])['version']
    fake.chat_completion.assert_not_called()
