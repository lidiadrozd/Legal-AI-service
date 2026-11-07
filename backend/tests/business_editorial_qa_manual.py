"""Exercise the real GigaChat editor and save source and presentation separately."""
import asyncio, json
from pathlib import Path
from test_business_editorial import sofa_state
from complete_form_cases import make_state
from app.services.document_form_composition import prepare_form_document, form_presentation_fields
from app.services.gigachat_client import get_gigachat_client


async def main():
    client = await get_gigachat_client()
    cases = {'sofa': sofa_state()}
    for scenario, key, text in [
        ('contract_services', 'subject', 'сделать сайт'),
        ('claim_debt_loan', 'facts', 'Ну мне не вернули деньги. Жду уже давно.'),
    ]:
        state = make_state(scenario)
        state['fields'][key] = {'status': 'filled', 'value': text, 'original': text}
        cases[scenario] = state
    out = Path('/app/tests/business-editorial-qa')
    out.mkdir(exist_ok=True)
    for name, state in cases.items():
        prepared, usage = await prepare_form_document(state, client)
        report = {'state': prepared, 'fields': form_presentation_fields(prepared), 'tokens': usage.total_tokens}
        (out / (name + '.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(name, 'unverified:', prepared['form_review_fields'], 'tokens:', usage.total_tokens, flush=True)


if __name__ == '__main__':
    asyncio.run(main())
