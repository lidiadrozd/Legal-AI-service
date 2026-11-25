"""Literal loan facts and repayment arithmetic, independent of the active question."""
from decimal import Decimal
import re

NUMBER = r'\d+(?:[ \u00a0]\d{3})*(?:[.,]\d{1,2})?\s*(?:тыс\.?|тысяч(?:а|и)?|млн\.?)?'
_NO_OTHER_PAYMENTS = re.compile(
    r'(?:(?:больше|других|иных)\s+(?:переводов|платежей|возвратов)\s+не\s+(?:было|поступало)'
    r'|(?:другие|иные)\s+(?:переводы|платежи)\s+не\s+поступали)[.! ]*', re.I)
PAYMENT_DATE_QUESTION = 'Какой датой прошёл перевод, сумму которого нужно исправить?'


def _loan_values(facts):
    """Views shared by initial intake, revisions and the export audit."""
    from app.services.document_case_composition import _money

    principal = facts.get('principal')
    events = facts.get('payments', [])
    amounts = {}
    if events:
        amounts['payments'] = '\n'.join('Возвращено ' + _money(item['amount']) +
            (' ' + item['date_text'] if item.get('date_text') else '') + '.' for item in events)
        if facts.get('no_other_payments_evidence'):
            amounts['payments'] += ' Других платежей не было.'
    if not principal or not (events or facts.get('no_payments')):
        return amounts
    paid = sum((Decimal(item['amount']) for item in events), Decimal(0))
    balance = Decimal(principal) - paid
    if balance >= 0:
        amounts['amount'] = format(balance, '.2f')
        amounts['facts'] = (f'Сумма займа: {_money(principal)}. Возвращено: {_money(paid)}. '
                           f'Остаток основного долга: {_money(balance)}.')
        if events:
            amounts['calculation'] = _money(principal) + ' − ' + _money(paid) + ' = ' + _money(balance) + '.'
    return amounts


def _single_amount(quote):
    from app.services.document_money_tokens import find_money_quotes
    from app.services.document_workflow import normalize_money

    if not quote:
        return None
    amount = normalize_money(quote.strip(' .'))
    if amount is not None:
        return amount
    matches = find_money_quotes(quote)
    return normalize_money(matches[0]) if len(matches) == 1 else None


def explicit_loan_payment_quote(state, message):
    """Offline fallback for an explicit correction with one completed payment."""
    if not (state.get('loan_facts') or {}).get('payments'):
        return ''
    if not re.search(r'ошиб|поправк|перепутал|исправ|замени|тот\s+же\s+(?:перевод|плат[её]ж)', message, re.I):
        return ''
    if re.search(r'\b(?:если|возможно|обещал|планир\w*|должен\s+был|не\s+(?:исправ|замен|меня|перев[её]л|вернул|погасил))', message, re.I):
        return ''
    matches = list(re.finditer(
        r'\b(?:перев[её]л[аи]?|вернул[аи]?|погасил[аи]?|возвратил[аи]?)\s+(?:мне\s+)?'
        r'(?P<amount>' + NUMBER + r'(?:\s*руб\w*)?)(?![\w\d])', message, re.I))
    return matches[0]['amount'].strip() if len(matches) == 1 else ''


def _payment_dates(text):
    from app.services.document_case_facts import DATE, MONTH
    return [m[0] for m in re.finditer(DATE + r'|\b\d{1,2}\s+' + MONTH + r'\b', text, re.I)]


def reconcile_loan_payment_conflict(state):
    """A recorded payment and an explicit absence of others are compatible."""
    from app.services.document_case_facts import set_field

    choices = state.get('narrative_conflicts', {}).get('payments', {}).get('choices', [])
    facts = state.get('loan_facts') or {}
    events = facts.get('payments') or []
    if not choices or not events:
        return
    evidence = [event.get('event_evidence') or event.get('evidence') or '' for event in events]
    saw_payment = saw_absence = False
    for choice in choices:
        quote = (choice.get('field', {}).get('original') or choice.get('value') or '').strip()
        if _NO_OTHER_PAYMENTS.fullmatch(quote):
            saw_absence = True
        elif quote and any(quote.casefold().strip(' .') in source.casefold() for source in evidence):
            saw_payment = True
        else:
            return
    if saw_payment and saw_absence:
        set_field(state, 'payments', _loan_values(facts)['payments'], '\n'.join(evidence))
        state['fields']['payments'].update(origin='loan_arithmetic', inputs=['loan_facts'])
        state['narrative_conflicts'].pop('payments')


def reconcile_saved_loan_edit(state):
    """Migrate a user-confirmed payment saved only in the legacy display field."""
    field = state.get('fields', {}).get('payments') or {}
    events = (state.get('loan_facts') or {}).get('payments') or []
    if field.get('origin') != 'user_correction' or len(events) != 1:
        return False
    turns = [*state.get('user_turns', []), *(m.get('content', '') for m in state.get('source_messages', [])
                                            if m.get('role') == 'user')]
    for source in (field.get('original'), field.get('evidence'), field.get('value')):
        if not source or source not in turns:
            continue
        match = re.fullmatch(r'(?:фактически полученные в сч[её]т возврата платежи|частичный возврат|'
                             r'сумма (?:возврата|перевода|платежа))\s*[-—:]\s*'
                             r'(' + NUMBER + r'(?:\s*руб\w*)?)[.! ]*', source, re.I)
        # A source-bound, explicitly labelled replacement is safe even in an older
        # chat where the previous editor did not persist the selected event ID.
        if match:
            handled, question = apply_ready_loan_edit(state, 'payments', match[1].strip(), message=source)
            return handled and not question
    return False


def _refresh_loan_fields(state, evidence):
    from app.services.document_case_facts import set_field
    for key, value in _loan_values(state['loan_facts']).items():
        if set_field(state, key, value, evidence):
            state['fields'][key].update(origin='loan_arithmetic', inputs=['loan_facts'])


def apply_ready_loan_edit(state, key, quote, previous_quote='', message='', *, operation='replace'):
    """Apply a source-bound change to one bank event and refresh its dependants."""
    from app.services.document_case_facts import set_field
    from app.services.document_case_composition import _money
    from app.services.document_source_quotes import literal_evidence

    facts = state.get('loan_facts') or {}
    events = facts.get('payments') or []
    if state.get('scenario') not in {'claim_debt_loan', 'pretense_debt_loan'} or not facts.get('principal'):
        return False, ''
    if key not in {'payments', 'amount', 'transfer'}:
        return False, ''
    new_amount = _single_amount(quote)
    if key == 'transfer':
        if not new_amount:
            # A transfer record also contains the date, method and payee. Allow
            # the generic editor to handle non-monetary edits to that field.
            return False, ''
        if not literal_evidence(quote, message):
            return True, 'Какую сумму вы фактически передали заёмщику?'
        total_paid = sum((Decimal(event['amount']) for event in events), Decimal(0))
        if Decimal(new_amount) < total_paid:
            return True, 'Общая сумма возвратов превышает указанную сумму займа. Какую сумму вы передали?'
        from app.services.document_money_tokens import find_money_quotes
        transfer = state['fields'].get('transfer', {})
        original = transfer.get('value') or facts.get('principal_evidence') or ''
        matches = [v for v in find_money_quotes(original) if _single_amount(v) == facts['principal']]
        if len(matches) != 1:
            return True, 'Укажите исправленные обстоятельства передачи займа вместе с переданной суммой.'
        previous_source = transfer.get('evidence') or facts.get('principal_evidence') or original
        revised = original.replace(matches[0], _money(new_amount), 1)
        set_field(state, 'transfer', revised, quote)
        state['fields']['transfer'].update(origin='user_correction', source_quotes=[previous_source, quote])
        facts.update(principal=new_amount, principal_evidence=quote, principal_edited=True)
        _refresh_loan_fields(state, quote)
        return True, ''
    if key == 'amount':
        computed = _loan_values(facts).get('amount')
        if new_amount and new_amount == computed:
            return True, ''
        if not computed:
            return False, ''
        return True, ('По сохранённым сумме займа и платежам остаток составляет ' + _money(computed) +
                      '. Какую исходную сумму займа или какой платёж нужно исправить?')
    if not new_amount or Decimal(new_amount) <= 0 or not literal_evidence(quote, message):
        return True, 'Какая сумма фактически поступила по исправляемому переводу?'
    # Equal amounts can refer to separate payments. Match the previous value
    # and any stated date before touching one event in the ledger.
    old_amount = _single_amount(previous_quote)
    candidates = events
    if old_amount and old_amount != new_amount:
        candidates = [item for item in candidates if item['amount'] == old_amount or
                      (item['amount'] == new_amount and old_amount in item.get('superseded_amounts', []))]
    dates = _payment_dates(quote) or _payment_dates(message)
    if dates:
        candidates = [item for item in candidates if not item.get('date_text') or any(
            item['date_text'].casefold() == day.casefold() or
            (item['date_text'] + ' ').casefold().startswith(day.casefold() + ' ') or
            (day + ' ').casefold().startswith(item['date_text'].casefold() + ' ') for day in dates)]
    adding = operation == 'add'
    if adding:
        # Do not turn a correction into a second event if the model
        # misclassifies a sentence that explicitly identifies the transfer.
        if re.search(r'(?:тот|один)\s+(?:и\s+тот\s+)?же\s+(?:самый\s+)?(?:перевод|плат[её]ж)', message, re.I):
            return True, 'Это исправление суммы прежнего перевода или отдельный платёж?'
        if len(set(dates)) > 1:
            return True, 'Какой датой прошёл дополнительный перевод?'
        if any(item.get('added_in') == message and item['amount'] == new_amount for item in events):
            return True, ''
        ambiguous = any(item['amount'] == new_amount and
                        (not dates or not item.get('date_text') or item['date_text'] in dates) for item in events)
        if ambiguous and not re.search(r'\b(?:ещ[её]|второ\w*|другой|отдельн\w*|дополнительн\w*)\b', message, re.I):
            return True, 'Это ещё один перевод той же суммы или ранее учтённый платёж?'
        from app.services.document_formula_intake import _dates
        raw_date = dates[0] if dates else ''
        parsed = _dates(raw_date)
        event = {'amount': new_amount, 'date_text': raw_date, 'date': parsed[0].isoformat() if parsed else None,
                 'added_in': message, 'event_evidence': message, 'evidence': message}
    elif len(candidates) != 1:
        if len(candidates) > 1 and old_amount:
            return True, PAYMENT_DATE_QUESTION
        return True, 'Каковы дата и прежняя сумма перевода, который нужно исправить?'
    else:
        event = candidates[0]
    others = sum((Decimal(item['amount']) for item in events if item is not event), Decimal(0))
    if others + Decimal(new_amount) > Decimal(facts['principal']):
        return True, 'Сумма возвратов превысит выданный заём. Какая часть этого перевода погашает основной долг?'
    # Store the user quote for the new amount separately from the original
    # bank-event evidence, which can also be the only source for its date.
    if adding:
        facts.setdefault('payments', []).append(event)
        facts.pop('no_payments', None)
        facts.pop('no_other_payments_evidence', None)
    else:
        history = event.setdefault('superseded_amounts', [])
        if event['amount'] != new_amount and event['amount'] not in history:
            history.append(event['amount'])
        if new_amount in history:
            history.remove(new_amount)
    event.setdefault('event_evidence', event.get('evidence', ''))
    event.update(amount=new_amount, evidence=quote, edited=True)
    _refresh_loan_fields(state, quote)
    return True, ''


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
    clauses = re.split(r'(?<=[.!?;])\s+(?=[А-ЯЁ\d])', text.strip(' .'))
    short_date = r'\d{1,2}\s+' + MONTH + r'(?:\s+\d{4}(?:\s*года)?)?'
    for clause in clauses:
        agreement = re.search(r'(?:письменн\w*\s+)?договор[ау]?\s+займа\s*№\s*[\w/-]+(?:\s+от\s+' + DATE + r')?', clause, re.I)
        if agreement:
            reference = re.sub(r'^договор[ау]\b', 'договор', agreement[0], flags=re.I)
            if re.search(r'беспроцент', text, re.I):
                reference += '. Заём беспроцентный.'
            put('agreement', reference, text)
        if re.search(r'\bподписал[аи]?\s+расписку\b', clause, re.I):
            put('agreement', 'Заёмщик подписал расписку.', clause)
        due = re.search(r'(?:срок\s+возврата\s*(?:займа\s*)?[-—–:]?\s*|(?:вернуть|возврат\w*).{0,65}?(?:не позднее|до)\s+)(' + DATE + '|' + short_date + r')', clause, re.I)
        if due:
            put('due_date', due[1] if _dates(due[1]) else 'до ' + due[1] + ' (год не указан)', due[0])
        if re.search(r'\b(?:хочу|прошу)\s+взыскать\s+только\s+остаток\s+(?:основного\s+)?долга\b', clause, re.I):
            put('requests', clause, clause)
        if re.search(r'\bрасписка\s+и\s+банковская\s+выписка\s+(?:у\s+меня\s+)?есть\b', clause, re.I):
            put('evidence', clause, clause)
        transfer = re.search(r'\b(?:передал[аи]?|одолжил[аи]?|предоставил[аи]?)\b', clause, re.I)
        if transfer:
            money = re.search(MONEY, clause, re.I)
            if money and not facts.get('principal_edited'):
                facts['principal'] = number(money[0])
                facts['principal_evidence'] = clause
                put('transfer', clause, clause)
            person = re.search(r'\b(?:передал[аи]?|одолжил[аи]?|предоставил[аи]?)\s+(' + NAME + r')', clause)
            if person:
                put('recipient', nominative_name(person[1]), person[0])
        if _NO_OTHER_PAYMENTS.fullmatch(clause.strip()):
            facts['no_other_payments_evidence'] = clause
        elif re.search(r'ничего не возвращено|платежей не было|не возвращал', clause, re.I):
            facts['no_payments'] = True
            put('payments', 'Платежи в счёт возврата займа не поступали.', clause)

    # Monetary context is explicit here, so currencies may be omitted:
    # "из 60000 он вернул 20000 11 октября" is not a malformed amount.
    pair = re.search(r'\bиз\s+(' + NUMBER + r')\s*(?:руб\w*\.?\s*)?(?:(?:он|она|за[её]мщик)\s+)?(?:вернул[аи]?|погасил[аи]?|возвратил[аи]?)\s+(' + NUMBER + r')', text, re.I)
    if pair and not facts.get('principal_edited'):
        facts['principal'] = number(pair[1])
        facts['principal_evidence'] = pair[0]
    new_payments = False
    for clause in clauses:
        payment = re.search(r'\b(?:вернул[аи]?|погасил[аи]?|возвратил[аи]?|перев[её]л[аи]?\s+мне)\s+(' + NUMBER + r')(?:\s*руб\w*\.?)?', clause, re.I)
        if not payment or re.search(r'\bне\s*$', clause[:payment.start()], re.I):
            continue
        amount = number(payment[1])
        if amount is None:
            continue
        # Store a yearless date literally; it does not prevent subtracting the
        # payment, but the penalty calculator must ask for its year.
        dates = list(re.finditer(DATE + '|' + short_date, clause, re.I))
        payment_date = min(dates, key=lambda m: min(abs(m.start()-payment.end()), abs(m.end()-payment.start()))) if dates else None
        raw_date = payment_date[0] if payment_date else ''
        full_dates = _dates(raw_date)
        event = {'amount': amount, 'date': full_dates[0].isoformat() if full_dates else None,
                 'date_text': raw_date, 'evidence': clause}
        events = facts.setdefault('payments', [])
        if any(e.get('date_text') == raw_date and amount in e.get('superseded_amounts', []) for e in events):
            continue
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
            if (facts.get('no_other_payments_evidence') or '') not in text:
                facts.pop('no_other_payments_evidence', None)
        elif not duplicate.get('date') and event['date']:
            duplicate.update(event)
        facts.pop('no_payments', None)
        new_payments = True
    correction = re.fullmatch(
        r'\s*(?:исправь(?:те)?|измени(?:те)?|поправка)[:, ]+'
        r'(?:сумму\s+)?(?:частичного\s+)?(?:плат[её]ж[а]?|перевод[а]?|возврат[а]?)'
        r'\s*(?:на|до|—|:)\s*(' + NUMBER + r')(?:\s*руб\w*)?[.! ]*', text, re.I)
    if correction and len(facts.get('payments', [])) == 1:
        events = facts['payments']
        amount = number(correction[1])
        if amount and Decimal(amount) <= Decimal(facts.get('principal') or amount):
            if amount != events[0]['amount']:
                events[0].setdefault('superseded_amounts', []).append(events[0]['amount'])
            events[0].update(amount=amount, evidence=text)
            new_payments = True
    if current in {'requests', 'calculation', 'payments'} and re.fullmatch(r'\s*(?:в\s+)?(?:19|20)\d{2}(?:\s*(?:году|год|г\.))?\s*[.]?\s*', text):
        year = re.search(r'\d{4}', text)[0]
        for event in facts.get('payments', []):
            if not event.get('date') and event.get('date_text'):
                dates = _dates(event['date_text'] + ' ' + year + ' года')
                if dates:
                    event.update(date=dates[0].isoformat(), date_text=event['date_text'] + ' ' + year + ' года')
                    consumed.add('payments')
    if new_payments or pair or consumed & {'transfer', 'payments'}:
        source = '\n'.join([facts.get('principal_evidence', ''), *(e['evidence'] for e in facts.get('payments', []))])
        for field_key, value in _loan_values(facts).items():
            put(field_key, value, source or text, derived=True)
    return consumed
