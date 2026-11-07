from app.services.document_form_rules import prepare_form_rules


def _state(key, *, total='145500.00'):
    return {
        'scenario': key,
        'calculation_ledger': {'status': 'confirmed', 'total': total},
        'fields': {
            'amount': {'status': 'filled', 'value': '128500.00'},
            'calculation': {'status': 'filled', 'value': 'Расчёт заявленных денежных требований.'},
            'consumer_status': {'status': 'filled', 'value': 'Товар приобретён для личных домашних нужд.'},
        },
    }


def test_consumer_claim_uses_confirmed_ledger_for_price_and_fee():
    state=_state('claim_consumer_late_delivery')
    prepare_form_rules(state)
    assert state['fields']['claim_price']['value']=='145 500 рублей'
    assert state['fields']['claim_price']['status']=='filled'
    assert 'освобождён' in state['fields']['fee']['value']
    assert '1 000 000' in state['fields']['fee']['value']


def test_consumer_fee_is_not_assumed_without_personal_use_or_with_large_claim():
    state=_state('claim_consumer_defective_goods',total='1000001')
    state['fields']['consumer_status']['value']='Товар приобретён для перепродажи.'
    prepare_form_rules(state)
    assert state['fields']['claim_price']['value']=='1 000 001 рублей'
    assert state['fields']['fee']['status']=='review_required'


def test_universal_consumer_claim_uses_the_real_purpose_field_for_the_fee_exemption():
    state=_state('claim_consumer')
    state['fields'].pop('consumer_status',None)
    state['fields']['procedure']={'status':'filled','value':'Для личных домашних нужд'}

    prepare_form_rules(state)

    assert state['fields']['fee']['status']=='filled'
    assert 'освобожд' in state['fields']['fee']['value'].lower()


def test_user_confirmed_fee_receipt_is_retained_when_no_automatic_exemption_applies():
    state={
        'scenario':'appeal_civil',
        'fields':{
            'fee':{
                'status':'filled',
                'value':'Государственная пошлина уплачена в размере 3 000 рублей; квитанция от 28.10.2026 прилагается.',
                'original':'Госпошлина 3000, квитанция есть',
                'evidence':'Госпошлина 3000, квитанция есть',
                'origin':'source_bound_extraction',
            },
        },
    }
    prepare_form_rules(state)
    assert state['fields']['fee']['status']=='filled'
    assert state['fields']['fee']['value']=='Государственная пошлина уплачена в размере 3 000 рублей; квитанция от 28.10.2026 прилагается.'
    assert state['fields']['fee']['origin']=='source_bound_extraction'
