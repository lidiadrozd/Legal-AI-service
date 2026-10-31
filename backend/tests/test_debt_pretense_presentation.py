from copy import deepcopy
from io import BytesIO

from docx import Document

from app.services.document_docx_template import fill_docx_template
from app.services.document_form_composition import form_presentation_fields
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import (
    format_template_fields,
    load_text_package,
    render_package_blocks,
)
from app.services.document_workflow import new_state, normalize_field


def _state(**values):
    scenario = SCENARIOS['pretense_debt_services']
    state = new_state('regression')
    state.update(scenario=scenario.key, phase='ready', text_package=load_text_package(scenario))
    for spec in scenario.fields:
        value = values.get(spec.key)
        if value is None:
            state['fields'][spec.key] = {'status': 'not_applicable', 'value': None}
            continue
        if spec.kind in {'money', 'date', 'address'}:
            value, error = normalize_field(spec, str(value))
            assert not error, (spec.key, error)
        state['fields'][spec.key] = {
            'status': 'filled',
            'value': value,
            'original': str(values[spec.key]),
            'evidence': str(values[spec.key]),
        }
    return state


def _example_state():
    return _state(
        sender='Завьялова Анна Викторовна',
        sender_address='г. Екатеринбург, ул. Мира, д. 66, кв. 78',
        recipient='ООО «Вектор»',
        recipient_address='г. Екатеринбург, ул. Ленина, д. 55',
        agreement=('Я разработала для ООО «Вектор» дизайн сайта по договору № 17 от 1 сентября 2026 года. '
                   'Цена услуг 80 000 рублей, аванс 30 000 рублей получен. Акт подписан 20 сентября 2026 года, '
                   'остаток 50 000 рублей должен был быть оплачен до 30 сентября 2026 года, но деньги не поступили.'),
        performance='разработка сайта',
        due_date='до 30 сентября 2026 года',
        facts=('Цена услуг 80 000 рублей, аванс 30 000 рублей получен. Остаток 50 000 рублей должен был быть '
               'оплачен до 30 сентября 2026 года, но деньги не поступили.'),
        amount='50000 рублей',
        requests='Прошу уплатить задолженность по договору оказания услуг.',
        response_term='в течение 10 календарных дней со дня получения претензии',
        payment_details='переводом на банковскую карту 7892098273',
        legal_basis=None,
        attachments='договор и работах',
        date='31.10.2026',
        signature='Завьялова Анна Викторовна',
    )


def test_services_pretense_compiler_separates_agreement_service_and_violation():
    state = _example_state()
    # Simulate a cached model edit from the reported regression.  Export must
    # stay source-bound and grammatical even when that old edit was poor.
    state['draft_fields'] = {
        'agreement': ('Основанием обязательства является договор оказания услуг № 17 от 1 сентября 2026 года. '
                      'Согласно условиям указанного договора, мной была разработана для ООО «Вектор» дизайн сайта.'),
        'performance': 'Исполнение обязательств: разработка сайта.',
        'due_date': 'Согласованный срок исполнения: до 30 сентября 2026 года.',
        'facts': 'Обстоятельства нарушения: цена услуг 80 000 рублей; деньги не поступили.',
    }

    fields = form_presentation_fields(state)
    rendered = '\n'.join(block['text'] for block in render_package_blocks(
        state['text_package'], SCENARIOS[state['scenario']], fields,
        format_template_fields(SCENARIOS[state['scenario']], fields),
    ))

    assert fields['agreement']['value'] == 'Договор № 17 от 1 сентября 2026 года.'
    assert fields['performance']['value'].startswith('Выполнена разработка сайта.')
    assert 'Акт подписан 20 сентября 2026 года.' in fields['performance']['value']
    assert fields['due_date']['value'] == 'до 30 сентября 2026 года'
    assert fields['facts']['value'] == 'Оплата оказанных услуг не поступила.'
    assert 'мной была разработана' not in rendered.lower()
    assert 'Исполнение обязательств: Исполнение обязательств:' not in rendered
    assert 'Согласованный срок исполнения: Согласованный срок исполнения:' not in rendered
    assert 'Обстоятельства нарушения: Обстоятельства нарушения:' not in rendered
    assert '1. Договор и документы о выполненных работах.' in rendered


def test_docx_renderer_strips_template_label_echoes_for_inline_controls():
    state = _example_state()
    fields = deepcopy(state['fields'])
    fields['performance']['value'] = 'Исполнение обязательств: разработка сайта.'
    fields['due_date']['value'] = 'Согласованный срок исполнения: до 30 сентября 2026 года.'
    fields['facts']['value'] = 'Обстоятельства нарушения: оплата не поступила.'

    document = Document(BytesIO(fill_docx_template(
        state['text_package'], SCENARIOS[state['scenario']], fields,
    )))
    text = '\n'.join(paragraph.text for paragraph in document.paragraphs)

    assert text.count('Исполнение обязательств:') == 1
    assert text.count('Согласованный срок исполнения:') == 1
    assert text.count('Обстоятельства нарушения:') == 1
    assert 'Исполнение обязательств: разработка сайта.' in text
    assert 'Согласованный срок исполнения: до 30 сентября 2026 года.' in text
    assert 'Обстоятельства нарушения: оплата не поступила.' in text
