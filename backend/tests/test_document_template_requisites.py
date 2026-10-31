from app.services.document_form_composition import form_narrative_keys, local_candidate
from app.services.document_quality import quality_issues
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import load_text_package


def _state(key):
    scenario=SCENARIOS[key]
    return {
        'scenario':key,
        'text_package':load_text_package(scenario),
        'fields':{field.key:{'status':'filled','value':'Тестовое значение'} for field in scenario.fields},
    }


def test_template_declared_court_requisite_is_not_sent_to_prose_editor():
    state=_state('appeal_civil')
    assert 'first_court' not in form_narrative_keys(state)


def test_template_declared_property_identifiers_are_not_sent_to_prose_editor():
    state=_state('contract_sale_nonresidential')
    keys=set(form_narrative_keys(state))
    assert {'seller_details','buyer_details','property_address','cadastral_number','payment_details'}.isdisjoint(keys)


def test_unclean_template_requisite_still_blocks_export_quality_gate():
    state={
        'scenario':'appeal_civil',
        'text_package':load_text_package(SCENARIOS['appeal_civil']),
        'fields':{'first_court':{'status':'filled','value':'ну районный суд'}},
    }
    assert 'unclean_template_requisite' in {item['code'] for item in quality_issues(state)}


def test_formal_named_judicial_act_can_use_local_fallback():
    source='Решение Кировского районного суда города Екатеринбурга от 20.09.2026 по делу № 2-1234/2026.'
    assert local_candidate('challenged_act', source, 'sentence', 'appeal_civil') == source


def test_numeric_phrase_slot_is_not_mistaken_for_a_copied_label():
    assert local_candidate('area', '86,4', 'phrase', 'contract_sale_nonresidential') == '86,4'


def test_case_number_is_checked_as_an_identifier_not_a_free_text_label():
    state={
        'scenario':'motion_restore_term',
        'text_package':load_text_package(SCENARIOS['motion_restore_term']),
        'fields':{'case_number':{'status':'filled','value':'2-3456/2026'}},
    }
    assert not [item for item in quality_issues(state) if item['field']=='case_number']


def test_numeric_cadastral_and_area_values_are_not_mistaken_for_labels():
    state={
        'scenario':'contract_sale_nonresidential',
        'text_package':load_text_package(SCENARIOS['contract_sale_nonresidential']),
        'fields':{
            'cadastral_number':{'status':'filled','value':'66:41:0401001:1234'},
            'area':{'status':'filled','value':'86,4'},
        },
    }
    issues=quality_issues(state)
    assert not [item for item in issues if item['field'] in {'cadastral_number','area'}]
