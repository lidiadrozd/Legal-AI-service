"""Literal loan facts and repayment arithmetic, independent of the active question."""
from decimal import Decimal
import re

NUMBER = r'\d+(?:[ \u00a0]\d{3})*(?:[.,]\d{1,2})?\s*(?:тыс\.?|тысяч(?:а|и)?|млн\.?)?'


def collect_loan_facts(state, text, current=None):
    from app.services.document_case_facts import DATE, MONEY, MONTH, set_field
    from app.services.document_explicit_facts import NAME, nominative_name
    from app.services.document_scenarios import SCENARIOS
    from app.services.document_formula_intake import _dates
    if state.get('scenario') not in {'pretense_debt_loan', 'claim_debt_loan'}:
        return set()
    available = {f.key for f in SCENARIOS[state['scenario']].fields}
    facts = state.setdefault('loan_facts', {})
    consumed = set()

    def put(key, value, evidence, *, derived=False):
        if key not in available or not value:
            return
        previous = state['fields'].get(key, {})
        if previous.get('value') == value and previous.get('status') == 'filled':
            return
        if previous.get('status') == 'filled' and key != current and not derived:
            return
        set_field(state, key, value, evidence)
        if derived:
            state['fields'][key].update(origin='loan_arithmetic', inputs=['loan_facts'])
        else:
            state['fields'][key]['origin'] = 'literal_loan_fact'
        consumed.add(key)

    def number(value):
        from app.services.document_workflow import normalize_money
        return normalize_money(value)

    # Clause boundaries must not split numeric dates or decimal amounts.
    clauses = re.split(r'(?<=[.!?;])\s+(?=[А-ЯЁ])', text.strip(' .'))
    for clause in clauses:
        agreement = re.search(r'(?:письменн\w*\s+)?договор[ау]?\s+займа\s*№\s*[\w/-]+(?:\s+от\s+' + DATE + r')?', clause, re.I)
        if agreement:
            reference = re.sub(r'^договор[ау]\b', 'договор', agreement[0], flags=re.I)
            if re.search(r'беспроцент', text, re.I):
                reference += '. Заём беспроцентный.'
            put('agreement', reference, text)
        due = re.search(r'(?:срок\s+возврата\s*(?:займа\s*)?[-—–:]?\s*|(?:вернуть|возврат\w*).{0,65}?(?:не позднее|до)\s+)(' + DATE + r')', clause, re.I)
        if due:
            put('due_date', due[1], due[0])
        transfer = re.search(r'\b(?:передал[аи]?|одолжил[аи]?|предоставил[аи]?)\b', clause, re.I)
        if transfer:
            money = re.search(MONEY, clause, re.I)
            if money:
                facts['principal'] = number(money[0])
                facts['principal_evidence'] = clause
                put('transfer', clause, clause)
            person = re.search(r'\b(?:передал[аи]?|одолжил[аи]?|предоставил[аи]?)\s+(' + NAME + r')', clause)
            if person:
                put('recipient', nominative_name(person[1]), person[0])
        if re.search(r'ничего не возвращено|платежей не было|не возвращал', clause, re.I):
            facts['no_payments'] = True
            put('payments', 'Платежи в счёт возврата займа не поступали.', clause)

    # Monetary context is explicit here, so currencies may be omitted:
    # "из 60000 он вернул 20000 11 октября" is not a malformed amount.
    pair = re.search(r'\bиз\s+(' + NUMBER + r')\s*(?:руб\w*\.?\s*)?(?:(?:он|она|за[её]мщик)\s+)?(?:вернул[аи]?|погасил[аи]?|возвратил[аи]?)\s+(' + NUMBER + r')', text, re.I)
    if pair:
        facts['principal'] = number(pair[1])
        facts['principal_evidence'] = pair[0]
    new_payments = False
    for clause in clauses:
        payment = re.search(r'\b(?:вернул[аи]?|погасил[аи]?|возвратил[аи]?)\s+(' + NUMBER + r')(?:\s*руб\w*\.?)?', clause, re.I)
        if not payment or re.search(r'\bне\s*$', clause[:payment.start()], re.I):
            continue
        amount = number(payment[1])
        if amount is None:
            continue
        # Store a yearless date literally; it does not prevent subtracting the
        # payment, but the penalty calculator must ask for its year.
        short_date = r'\d{1,2}\s+' + MONTH + r'(?:\s+\d{4}(?:\s*года)?)?'
        dates = list(re.finditer(DATE + '|' + short_date, clause, re.I))
        payment_date = min(dates, key=lambda m: min(abs(m.start()-payment.end()), abs(m.end()-payment.start()))) if dates else None
        raw_date = payment_date[0] if payment_date else ''
        full_dates = _dates(raw_date)
        event = {'amount': amount, 'date': full_dates[0].isoformat() if full_dates else None,
                 'date_text': raw_date, 'evidence': clause}
        events = facts.setdefault('payments', [])
        def same_payment(previous):
            if previous['amount'] != event['amount']:
                return False
            if previous.get('date') and event['date']:
                return previous['date'] == event['date']
            # Clarifying a year or repeating a yearless answer is one event.
            before = re.sub(r'\s+\d{4}(?:\s*года)?', '', previous.get('date_text', '')).strip()
            after = re.sub(r'\s+\d{4}(?:\s*года)?', '', raw_date).strip()
            return before == after
        duplicate = next((e for e in events if same_payment(e)), None)
        if duplicate is None:
            events.append(event)
        elif not duplicate.get('date') and event['date']:
            duplicate.update(event)
        facts.pop('no_payments', None)
        new_payments = True
    if new_payments:
        put('payments', '\n'.join('Возвращено ' + e['amount'] + ' рублей' + (' ' + e['date_text'] if e['date_text'] else '') + '.' for e in events), text, derived=True)
    if current in {'requests', 'calculation', 'payments'} and re.fullmatch(r'\s*(?:в\s+)?(?:19|20)\d{2}(?:\s*(?:году|год|г\.))?\s*[.]?\s*', text):
        year = re.search(r'\d{4}', text)[0]
        for event in facts.get('payments', []):
            if not event.get('date') and event.get('date_text'):
                dates = _dates(event['date_text'] + ' ' + year + ' года')
                if dates:
                    event.update(date=dates[0].isoformat(), date_text=event['date_text'] + ' ' + year + ' года')
                    consumed.add('payments')
        if 'payments' in consumed:
            put('payments', '\n'.join('Возвращено ' + e['amount'] + ' рублей ' + e['date_text'] + '.' for e in facts['payments']), text, derived=True)

    principal = facts.get('principal')
    if principal and (facts.get('payments') or facts.get('no_payments')):
        paid = sum((Decimal(e['amount']) for e in facts.get('payments', [])), Decimal('0'))
        balance = Decimal(principal) - paid
        if balance >= 0:
            evidence = '\n'.join([facts.get('principal_evidence', ''), *(e['evidence'] for e in facts.get('payments', []))])
            put('amount', format(balance, '.2f'), evidence, derived=True)
            put('facts', f'Сумма займа: {principal} рублей. Возвращено: {paid:.2f} рублей. Остаток основного долга: {balance:.2f} рублей.', evidence, derived=True)
    return consumed
