from copy import deepcopy
from decimal import Decimal

from app.services.document_form_composition import form_presentation_fields
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import format_template_fields, load_text_package, render_package_blocks
from app.services.document_workflow import new_state, normalize_field


def _state(scenario, **values):
    state=new_state('regression')
    state.update(scenario=scenario,phase='ready',text_package=load_text_package(SCENARIOS[scenario]))
    for spec in SCENARIOS[scenario].fields:
        value=values.get(spec.key)
        if value is None:
            state['fields'][spec.key]={'status':'not_applicable','value':None}
            continue
        if spec.kind in {'money','date','address'}:
            value,error=normalize_field(spec,str(value))
            assert not error,(spec.key,error)
        state['fields'][spec.key]={'status':'filled','value':value,'original':str(values.get(spec.key)),'evidence':str(values.get(spec.key))}
    return state


def _rendered_text(state):
    fields=form_presentation_fields(state)
    blocks=render_package_blocks(state['text_package'],SCENARIOS[state['scenario']],fields,
                                 format_template_fields(SCENARIOS[state['scenario']],fields))
    return '\n'.join(block['text'] for block in blocks),fields


def test_loan_claim_presentation_deduplicates_opening_story_and_normalizes_absences():
    story=('10 марта 2026 года я, Иванова Елена Сергеевна, дала Петрову Андрею Викторовичу '
           'в долг 120 000 рублей. Он написал расписку и обязался вернуть деньги до 10 июня 2026 года. '
           'Деньги не вернул, на сообщения не отвечает. 1 сентября 2026 года я направила ему письменную претензию, но ответа не получила.')
    state=_state('claim_debt_loan',
        sender='Иванова Елена Сергеевна',sender_address='г. Екатеринбург, ул. Мира, д. 77, кв. 90',sender_details='никаких',
        recipient='Петров Андрей Викторович',recipient_address='г. Екатеринбург, ул. Ленина, д. 20, кв. 5',party_details='никаких',
        court='Кировский районный суд города Екатеринбурга',agreement=story,transfer=story,due_date=story,
        payments='нет',order_history='1 сентября 2026 года я направила претензию, ответа не получила.',
        amount='120000 рублей',pretrial=story,calculation='Основной долг.',legal_basis='Статья 309 ГК РФ.',
        fee='Государственная пошлина уплачена.',requests='Взыскать 120000 рублей долга и проценты.',other_participants='никто',
        copy_notice='не направлены',facts=story,attachments='расписку и притензию о взыскании',date='01.10.2026',signature='Иванова Елена Сергеевна')
    state['calculation_ledger']={'status':'confirmed','items':[
        {'kind':'principal','label':'Основная сумма требования','value':'120000.00'},
        {'kind':'expenses','label':'Дополнительные расходы','value':'350.00'},
    ]}
    text,fields=_rendered_text(state)
    assert fields['party_details']['status']=='unknown'
    assert fields['other_participants']['status']=='not_applicable'
    assert 'никаких' not in text.lower() and 'другие участники:' not in text.lower()
    assert '[основание займа]' not in text
    assert 'Фактически полученные в счёт возврата платежи: не поступали.' in text
    assert 'Получение денежных средств подтверждается распиской.' in text
    assert text.count('Письменная претензия была направлена ответчику')==1
    assert 'Письменная претензия была направлена ответчику 1 сентября 2026 года.' in text
    assert 'Письменная претензия была направлена ответчику 10 марта 2026 года.' not in text
    assert text.count('основную задолженность по договору займа в размере 120 000 рублей')==1
    assert 'Взыскать судебные расходы в размере 350 рублей.' in text
    assert '1. Расписку.' in text and '2. Претензию о взыскании.' in text
    assert 'притензи' not in text.lower()


def test_loan_claim_uses_the_transfer_and_claim_dates_from_their_own_events():
    state=_state('claim_debt_loan',
        sender='Иванова Елена Сергеевна',sender_address='г. Екатеринбург, ул. Мира, д. 77, кв. 89',
        recipient='Петров Андрей Викторович',recipient_address='г. Екатеринбург, ул. Мира, д. 77, кв. 90',
        court='Кировский районный суд города Екатеринбурга',agreement='Расписка от 10.03.2026.',
        transfer='я перевела ему их на карту 10 марта 2026 года',due_date='до 10.06.2026',
        payments='нет, пусть всё возвращает',amount='120000 рублей',
        pretrial='1 сентября 2026 года я направила ему письменную претензию, но ответа не получила.',
        calculation='Основной долг.',legal_basis='Статья 309 ГК РФ.',fee='Государственная пошлина уплачена.',
        requests='Взыскать долг.',other_participants='никто',facts='Долг не возвращён.',attachments='расписку',
        date='01.10.2026',signature='Иванова Елена Сергеевна')
    _,fields=_rendered_text(state)
    assert fields['transfer']['value']=='10 марта 2026 года денежные средства в размере 120 000 рублей были перечислены ответчику на банковскую карту в качестве займа.'
    assert fields['payments']['value']=='не поступали'
    assert fields['pretrial']['value']=='Письменная претензия была направлена ответчику 1 сентября 2026 года. Ответ на обращение не получен.'


def test_all_debt_claim_templates_make_a_typed_principal_request_once():
    specifics={
        'claim_debt_loan':{'agreement':'Расписка от 01.03.2026.','transfer':'Деньги переданы 01.03.2026.','due_date':'до 01.04.2026','payments':'нет'},
        'claim_debt_rent':{'agreement':'Договор аренды № 1 от 01.03.2026.','property':'Нежилое помещение за март 2026 года.','due_date':'до 05.04.2026','facts':'Оплата не поступила.'},
        'claim_debt_services':{'agreement':'Договор оказания услуг № 1 от 01.03.2026.','performance':'Услуги оказаны 20.03.2026.','due_date':'до 01.04.2026','payments':'Платежи не поступали.'},
        'claim_debt_supply':{'agreement':'Договор поставки № 1 от 01.03.2026.','goods':'Товар поставлен по накладной № 1.','due_date':'до 01.04.2026','facts':'Оплата не поступила.'},
    }
    for scenario,extra in specifics.items():
        common={
            'sender':'ООО «Истец»','sender_address':'г. Екатеринбург, ул. Мира, д. 1',
            'recipient':'ООО «Ответчик»','recipient_address':'г. Екатеринбург, ул. Ленина, д. 2',
            'court':'Арбитражный суд Свердловской области','party_details':'никаких',
            'other_participants':'нет','amount':'60000 рублей','pretrial':'Претензия направлена 01.05.2026. Ответ не получен.',
            'calculation':'Только основной долг.','legal_basis':'Статья 309 ГК РФ.','fee':'Государственная пошлина уплачена.',
            'requests':'Взыскать основной долг и проценты.', 'payment_details':'Банковский перевод.',
            'copy_notice':'Копии направлены.', 'attachments':'договор и претензию', 'date':'01.06.2026','signature':'Иванова Елена Сергеевна',
            **extra,
        }
        state=_state(scenario,**common)
        state['calculation_ledger']={'status':'confirmed','items':[{'kind':'principal','label':'Основная сумма требования','value':'60000.00'}]}
        text,fields=_rendered_text(state)
        assert text.count('60 000 рублей') >= 1
        assert fields['requests']['value'].count('60 000 рублей')==1
        assert 'проценты за пользование' not in fields['requests']['value'].lower()
        assert fields['party_details']['status']=='unknown'


def test_rent_and_supply_claims_hide_unfilled_optional_blocks_and_use_recovery_title():
    """A missing optional field must remove its whole line, never print a label.

    This covers the older rent/supply assets that used to render such phrases
    as ``Другие участники: [другие участники]`` and an incorrect title about
    "внесении" debt.  It deliberately exercises the same declarative package
    that is used to build the DOCX control template.
    """
    common={
        'sender':'ООО «Истец»','sender_address':'г. Екатеринбург, ул. Мира, д. 1',
        'recipient':'ООО «Ответчик»','recipient_address':'г. Екатеринбург, ул. Ленина, д. 2',
        'court':'Арбитражный суд Свердловской области','amount':'60000 рублей',
        'agreement':'Договор № 1 от 01.03.2026.','due_date':'до 01.04.2026',
        'facts':'Оплата не поступила.','legal_basis':'Статья 309 ГК РФ.',
        'requests':'Взыскать основной долг.','attachments':'договор',
        'date':'01.06.2026','signature':'Иванова Елена Сергеевна',
    }
    for scenario, extra in {
        'claim_debt_rent':{'property':'Нежилое помещение за март 2026 года.'},
        'claim_debt_supply':{'goods':'Товар по накладной № 1.'},
    }.items():
        state=_state(scenario,**common,**extra)
        text,_=_rendered_text(state)
        assert 'иные участники:' not in text.lower()
        assert 'дополнительные сведения:' not in text.lower()
        assert 'госпошлина / льгота:' not in text.lower()
        assert 'досудебное урегулирование и выбор суда' not in text.lower()
        assert 'расчёт взыскиваемых сумм:' not in text.lower()
        assert 'внесении задолженности' not in text.lower()


def test_pending_plan_never_turns_an_unpriced_interest_into_a_money_prayer():
    state=_state('claim_debt_loan',
        sender='Иванова Елена Сергеевна',sender_address='г. Екатеринбург, ул. Мира, д. 77, кв. 90',
        recipient='Петров Андрей Викторович',recipient_address='г. Екатеринбург, ул. Ленина, д. 20, кв. 5',
        court='Кировский районный суд города Екатеринбурга',agreement='Расписка от 01.03.2026.',
        transfer='Денежные средства переданы 01.03.2026.',due_date='до 01.04.2026',payments='нет',amount='120000 рублей',
        pretrial='Претензия направлена 01.05.2026.',calculation='Прошу проценты по статье 395.',legal_basis='Статья 395 ГК РФ.',
        fee='Государственная пошлина уплачена.',requests='Взыскать долг и проценты.',other_participants='нет',facts='Долг не возвращён.',
        attachments='расписку',date='01.06.2026',signature='Иванова Елена Сергеевна')
    state['calculation_plan']={'status':'needs_input','rules':[{'id':'civil_395','status':'needs_input','items':[]}]}
    _,fields=_rendered_text(state)
    assert fields['requests']['value']=='Взыскать с ответчика в пользу истца основную задолженность по договору займа в размере 120 000 рублей.'
    assert 'процент' not in fields['requests']['value'].lower()

