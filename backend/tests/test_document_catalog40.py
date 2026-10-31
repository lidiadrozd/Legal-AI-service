"""Catalog-wide invariants at the intake and actual API/download boundary."""
from io import BytesIO
from zipfile import ZipFile
from unittest.mock import AsyncMock
import pytest
from docx import Document
from app.services.document_catalog import catalog_forms
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import load_text_package
from app.services.document_docx_template import load_docx_asset,fill_docx_template
from app.services.document_workflow import new_state,advance_interview,pending_fields
from app.services.document_dialogue import infer_scenario,scenario_candidates
from app.services.document_quality import quality_issues

KEYS=[row['scenario'] for row in catalog_forms()]


@pytest.mark.parametrize('key',KEYS)
def test_every_catalog_form_has_complete_assets_and_field_coverage(key):
    scenario=SCENARIOS[key];package=load_text_package(scenario)
    original,schema=load_docx_asset(package,scenario)
    assert package['coverage']=='structured' and len(original)>15000
    assert schema['lawyer_reviewed'] is False
    fields={f.key:{'status':'unknown','value':None} for f in scenario.fields}
    docx=fill_docx_template(package,scenario,fields)
    with ZipFile(BytesIO(docx)) as z:
        xml=z.read('word/document.xml').decode()
        assert '{{' not in xml and 'w:sdt' not in xml
    text='\n'.join(p.text for p in Document(BytesIO(docx)).paragraphs)
    assert text.strip() and '[' in text
    assert schema['fields'].keys() <= {f.key for f in scenario.fields}


@pytest.mark.parametrize('key',KEYS)
@pytest.mark.asyncio
async def test_each_intake_finishes_one_question_at_a_time_without_provider(key,monkeypatch):
    offline=AsyncMock(side_effect=AssertionError('Unknown facts do not need a model'))
    monkeypatch.setattr('app.services.document_workflow.get_gigachat_client',offline)
    state=new_state(SCENARIOS[key].title)
    state.update(scenario=key,phase='collecting',progress_recovered=True)
    for _ in range(80):
        pending=pending_fields(state)
        if not pending:break
        state['last_questions']=[pending[0].key]
        state,reply,_=await advance_interview(state,'не знаю')
        assert not state.get('pending_answer'),reply
        assert len(state['last_questions'])<=1
    assert state['phase']=='ready' and not pending_fields(state)
    offline.assert_not_called()


@pytest.mark.parametrize('key',KEYS)
@pytest.mark.asyncio
async def test_each_form_downloads_as_docx_via_api(key,client,db_session,tmp_path,monkeypatch):
    from app.models.chat import ChatSession
    monkeypatch.setattr('app.core.config.settings.DOCUMENTS_STORAGE_DIR',str(tmp_path))
    state=new_state(SCENARIOS[key].title)
    state.update(scenario=key,phase='ready',progress_recovered=True)
    state['fields']={f.key:{'status':'unknown','value':None} for f in SCENARIOS[key].fields}
    chat=ChatSession(user_id=1,title=key,document_workflow=state)
    db_session.add(chat);await db_session.commit()
    reply=await client.post(f'/documents/interviews/{chat.id}/export')
    assert reply.status_code==201,reply.text
    download=await client.get(f"/documents/{reply.json()['document_id']}/download")
    assert download.status_code==200 and download.content.startswith(b'PK')
    assert Document(BytesIO(download.content)).paragraphs


@pytest.mark.parametrize('prompt,key',[
    ('Нужен акт приёма-передачи квартиры','act_housing_handover'),
    ('Нужен акт возврата квартиры','act_housing_return'),
    ('Нужно дополнительное соглашение к договору найма жилья','contract_housing_addendum'),
    ('Иск о возврате обеспечительного платежа за квартиру','claim_rent_deposit'),
    ('Нужен иск о взыскании зарплаты','claim_labor_salary'),
    ('Нужен иск о восстановлении на работе','claim_labor_reinstatement'),
    ('Заявление об увольнении по собственному желанию','labor_resignation'),
    ('Претензия работодателю о расчёте при увольнении','pretense_labor_settlement'),
    ('Заявление о судебном приказе о взыскании алиментов','order_alimony'),
    ('Иск о взыскании алиментов в долях к доходу','claim_alimony_share'),
    ('Иск о взыскании алиментов в твёрдой сумме','claim_alimony_fixed'),
    ('Заявление приставу об определении задолженности по алиментам','bailiff_alimony_arrears'),
    ('Иск о взыскании неустойки по алиментам','claim_alimony_penalty'),
    ('Иск о расторжении брака','claim_divorce'),
    ('Возражения относительно исполнения судебного приказа','motion_order_objection'),
    ('Заявление о восстановлении процессуального срока','motion_restore_term'),
    ('Заявление о выдаче исполнительного листа','motion_enforcement_writ'),
    ('Жалоба старшему приставу на бездействие пристава','complaint_bailiff_superior'),
    ('Претензия о задолженности по договору аренды за нежилое помещение','pretense_debt_rent'),
    ('Иск о взыскании долга по аренде помещения','claim_debt_rent'),
    ('Претензия заказчику об оплате оказанных услуг','pretense_debt_services'),
    ('Претензия покупателю о задолженности по договору поставки','pretense_debt_supply'),
    ('Иск о взыскании задолженности по поставке товара','claim_debt_supply'),
    ('Претензия о возмещении ущерба за повреждённый автомобиль','pretense_damage_property'),
    ('Иск о возврате предоплаты за товар, который не доставили в срок','claim_consumer_late_delivery'),
    ('Иск о возврате предоплаты за диван: доставка просрочена','claim_consumer_late_delivery'),
    ('Иск о возврате денег за некачественный ноутбук с недостатком','claim_consumer_defective_goods'),
    ('Иск о возврате денег за сломанный диван','claim_consumer_defective_goods'),
    ('Апелляционная жалоба на решение районного суда','appeal_civil'),
    ('Договор купли-продажи нежилого помещения','contract_sale_nonresidential'),
])
def test_specific_purposes_do_not_fall_into_adjacent_forms(prompt,key):
    state=new_state(prompt)
    assert infer_scenario(state,'')==key
    assert key in scenario_candidates(state)


def test_existing_alimony_and_lost_writ_are_not_initial_requests():
    state=dict(scenario='claim_alimony_fixed',fields={'existing_support':{'status':'filled','value':'Решение суда от 12.03.2025, алименты уже установлены.'}})
    assert any(i['code']=='form_applicability' for i in quality_issues(state))
    state=dict(scenario='motion_enforcement_writ',fields={'previous_writ':{'status':'filled','value':'Лист выдан и утрачен.'}})
    assert any(i['code']=='form_applicability' for i in quality_issues(state))


def test_labor_form_has_no_rent_transaction():
    s=SCENARIOS['complaint_labor_agency'];p=load_text_package(s)
    text=' '.join(f.question for f in s.fields)+' '.join(b['text'] for b in p['blocks'])
    assert 'аренд' not in text.lower() and 'наймодател' not in text.lower()
    assert {'sender','recipient','employer'} <= {f.key for f in s.fields}
    assert len(KEYS)==51 and 'contract_employment' in KEYS
    assert {'pretense_debt_rent','claim_debt_rent','pretense_debt_services','pretense_debt_supply',
            'claim_debt_supply','pretense_damage_property','claim_consumer_late_delivery',
            'claim_consumer_defective_goods','appeal_civil','contract_sale_nonresidential'} <= set(KEYS)


@pytest.mark.asyncio
async def test_public_catalog_lists_only_complete_supported_forms(client):
    response=await client.get('/documents/catalog')
    assert response.status_code==200 and len(response.json()['forms'])==len(KEYS)
    response=await client.get('/documents/scenarios')
    assert response.status_code==200 and len(response.json())==len(KEYS)
    assert all(r['coverage']=='structured' and r['docx_template'] for r in response.json())


def test_editor_cannot_invert_wage_roles_or_invent_document_submission():
    from app.services.document_drafting import validate_edit
    assert not validate_edit('Работником не произведена выплата заработной платы за октябрь 2026. Задолженность составляет 100000 рублей.', 'ну мне не выплатили зп за октябрь 2026, долг 100000 рублей')
    assert not validate_edit('Я ежемесячно расходую 15000 рублей на питание. К заявлению прилагаются чеки.', 'на питание трачу 15000 рублей, есть чеки')
    assert not validate_edit('Истец ежемесячно расходует 15000 рублей на питание.', 'на питание трачу 15000 рублей')
    assert validate_edit('Одновременно с заявлением подаю возражения относительно исполнения судебного приказа.', 'вместе с заявлением подаю возражения на исполнение судебного приказа')


def test_request_sentence_is_separated_from_fixed_reply_instruction():
    key='complaint_labor_agency';scenario=SCENARIOS[key];package=load_text_package(scenario)
    fields={f.key:{'status':'unknown','value':None} for f in scenario.fields}
    fields['requests']={'status':'filled','value':'Прошу проверить невыплату зарплаты и принять меры в пределах полномочий инспекции.'}
    payload=fill_docx_template(package,scenario,fields)
    text=' '.join(p.text for p in Document(BytesIO(payload)).paragraphs)
    assert 'инспекции.' in text and 'инспекции. Ответ на обращение' not in text
    assert any(b['text']=='{{payment}}' for b in package['blocks'])


def test_grammatical_candidate_preserves_recipient_and_literals():
    from app.services.document_editorial_grammar import formal_source_candidate
    from app.services.document_drafting import validate_edit
    source='ну мне не выплатили зп за октябрь 2026, долг 100000 рублей'
    candidate=formal_source_candidate(source)
    assert candidate=='Заработная плата мне не выплачена за октябрь 2026. Задолженность составляет 100000 рублей.'
    assert validate_edit(candidate,source)
    assert formal_source_candidate('Работодатель получил заявление.')=='Работодатель получил заявление.'
