from app.services.document_quality import quality_issues


def test_canonical_target_is_not_rejected_as_a_copied_field_label():
    state={
        'scenario': 'complaint_labor_agency',
        'fields': {
            'recipient': {
                'status': 'filled',
                'value': 'Государственная инспекция труда',
                'origin': 'explicit_request_target',
            },
        },
    }
    assert not [item for item in quality_issues(state) if item['code']=='label_echo']


def test_user_copying_a_field_label_is_still_rejected():
    state={
        'scenario': 'claim_damage_property',
        'fields': {
            'property': {'status': 'filled', 'value': 'Повреждено имущество', 'origin': 'user'},
        },
    }
    assert any(item['code']=='property_is_generic' for item in quality_issues(state))


def test_fractional_alimony_share_is_not_rejected_as_a_label_echo():
    state={
        'scenario': 'order_alimony',
        'fields': {
            'share': {'status': 'filled', 'value': '1/4', 'origin': 'user'},
        },
    }
    assert not [item for item in quality_issues(state) if item['field']=='share' and item['code']=='label_echo']


def test_iso_hearing_date_is_not_rejected_as_a_label_echo():
    state={
        'scenario': 'motion_postpone',
        'fields': {
            'hearing_date': {'status': 'filled', 'value': '2026-11-10', 'origin': 'user'},
        },
    }
    assert not [item for item in quality_issues(state) if item['field']=='hearing_date' and item['code']=='label_echo']
