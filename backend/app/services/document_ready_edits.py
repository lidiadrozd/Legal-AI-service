"""Apply a user's factual corrections to an already downloadable interview."""
from copy import deepcopy
import asyncio
import re

from pydantic import BaseModel, Field
from typing import Literal

from app.services.document_case_facts import normalize_contacts
from app.services.document_loan_facts import PAYMENT_DATE_QUESTION, apply_ready_loan_edit, explicit_loan_payment_quote
from app.services.document_money_tokens import MONEY_INTEGER, MONEY_START, find_money_quotes, money_token_starts_here
from app.services.document_scenarios import SCENARIOS, field_is_active


class Replacement(BaseModel):
    key: str
    quote: str = Field(min_length=1, max_length=12000)
    operation: Literal['replace', 'add'] = 'replace'
    previous_quote: str = ''


class EditDecision(BaseModel):
    intent: Literal['edit', 'clarify', 'other']
    replacements: list[Replacement] = Field(default_factory=list, max_length=30)
    question: str = Field(default='', max_length=500)


EDIT_REQUEST = re.compile(r'\b(?:поменяй\w*|меняй\w*|замени\w*|исправ\w*|измен[иия]\w*|перепутал[аи]?|'
                          r'ошиб(?:ся|лась)|поправ\w*|правильн\w+|вместо|добавь\w*|дозаполни\w*|дополни\w*)\b', re.I)
_MANAGED = {'legal_basis', 'fee', 'jurisdiction', 'claim_price', 'calculation'}

_RUBLES = MONEY_INTEGER + r'(?:[.,]\d{1,2})?(?:\s*(?:тыс\.?|тысяч(?:а|и)?|млн\.?))?(?:\s*(?:руб(?:лей|ля|ль|\.)?|₽))?'
_CHANGE = r'(?:поменяй(?:те)?|замени(?:те)?|измени(?:те)?|исправь(?:те)?)'
_AMOUNT_PAIR = re.compile(
    rf'(?:(?P<before>{_CHANGE})\s+)?(?P<old>{_RUBLES})\s+на\s+(?P<new>{_RUBLES})(?:\s+(?P<after>{_CHANGE}))?[.! ]*', re.I)
_SET_AMOUNT = re.compile(
    rf'(?:(?:я\s+)?(?:перепутал[аи]?|неверно\s+указал[аи]?)\s+сумму[,!. ]+{_CHANGE}|{_CHANGE}\s+сумму)\s+на\s+(?P<new>{_RUBLES})[.! ]*', re.I)


def _shorthand_amount_edit(state, specs, message, previous):
    """Resolve an explicit numeric replacement against editable source facts."""
    from app.services.document_workflow import normalize_money

    pair = _AMOUNT_PAIR.fullmatch(message.strip())
    if pair and not (pair['before'] or pair['after'] or previous):
        pair = None
    change = pair or _SET_AMOUNT.fullmatch(message.strip())
    if not change and previous:
        # Older saved chats may already be asking for a value supplied in the
        # original replacement. Keep the direction even if the answer is X.
        prior = _AMOUNT_PAIR.fullmatch((previous.get('request') or '').strip())
        if prior and (prior['before'] or prior['after']):
            old, new = normalize_money(prior['old']), normalize_money(prior['new'])
            answer = normalize_money(message.strip())
            question = (previous.get('question') or '').casefold()
            if answer and ((answer == old and 'прежн' in question)
                           or (answer == new and 'прежн' not in question)):
                change = pair = prior
    if not change:
        return None
    old_quote = pair['old'] if pair else ''
    old = normalize_money(old_quote) if pair else None
    if not normalize_money(change['new']) or (pair and not old):
        return None

    fields = state['fields']
    current = {key: [fields[key]['value']] for key, spec in specs.items()
               if spec.kind == 'money' and fields.get(key, {}).get('value')}
    ledger = state.get('loan_facts') or {}
    if ledger.get('principal'):
        current['transfer'] = [ledger['principal']]
        current['payments'] = [item['amount'] for item in ledger.get('payments', [])]
    candidates = [key for key, values in current.items() if values and
                  (not old or any(normalize_money(v) == old for v in values))]
    if len(candidates) == 1:
        key = candidates[0]
        if not ledger.get('principal'):
            # A free-text demand can describe independent charges as well as
            # the price. Don't decide which one changed merely by its number.
            price = normalize_money(current[key][0])
            for field_key, field in fields.items():
                amounts = [normalize_money(q) for q in find_money_quotes(field.get('value') or '')]
                if ((field_key == 'additional_claims' and any(not old or amount == old for amount in amounts))
                        or (not old and any(amount != price for amount in amounts))):
                    return EditDecision(intent='clarify', question='Какую сумму нужно изменить: уплаченную цену или размер отдельного требования?')
        return EditDecision(intent='edit', replacements=[
            Replacement(key=key, quote=change['new'], previous_quote=old_quote)])
    if ledger.get('principal') and pair:
        if candidates:
            labels = ', '.join(specs[k].label for k in candidates)
            question = f'К какому полю относится сумма {old_quote}: {labels}?'
        else:
            question = f'Сумма {old_quote} не совпадает с сохранёнными суммами займа. Какой платёж или сумму займа нужно исправить?'
        return EditDecision(intent='clarify', question=question)
    return None


def _contact_replacement(message, fields):
    if 'contacts' not in fields or re.search(r'\b(?:ответчик|продавц|исполнител|представител|контрагент)\w*', message, re.I):
        return None
    if not re.search(r'телефон|почт[ауые]|e-?mail|контакт', message, re.I):
        return None
    parts = normalize_contacts(message).splitlines()
    if len(parts) == 1:
        return Replacement(key='contacts', quote=parts[0].split(': ', 1)[1])
    return None


def _loan_amount_quote(proposal, turns):
    """Anchor a model-formatted amount to a complete numeric token in a user reply."""
    from app.services.document_loan_facts import NUMBER, _single_amount
    from app.services.document_workflow import normalize_money

    expected = _single_amount(proposal)
    if not expected:
        return ''
    for turn in reversed(turns):
        tokens = find_money_quotes(turn)
        if normalize_money(turn):
            tokens.append(turn)
        pair = _AMOUNT_PAIR.fullmatch(turn.strip())
        single = _SET_AMOUNT.fullmatch(turn.strip())
        if pair:
            tokens.extend([pair['old'], pair['new']])
        if single:
            tokens.append(single['new'])
        if normalize_money(proposal):
            for m in re.finditer(MONEY_START + re.escape(proposal.strip()) +
                                 r'(?!\w|[.,]\d|[ \u00a0\u202f\u2009]\d)', turn, re.I):
                if (money_token_starts_here(turn, m.start())
                        and re.search(r'(?:\b(?:сумм\w*|оплат\w*|долг\w*|возв\w*|цен\w*|стоимост\w*)|[:—])\s*$', turn[:m.start()], re.I)):
                    tokens.append(m[0])
        # A user contrasting two amounts may omit the currency on either side.
        # Only accept a bare number explicitly introduced as the old/new value.
        tokens.extend(match[1].strip() for match in re.finditer(
            r'\b(?:было|стало|вместо|на|написал[аи]?|указал[аи]?|долг|остаток|сумм[ау]|'
            r'(?:вернул[аи]?|перев[её]л[аи]?|передал[аи]?)(?:\s+мне)?|'
            r'(?:плат[её]ж\w*|перевод\w*|возврат\w*)\s*[-—:]?)\s+(' + NUMBER + r')(?=[.!?,;:]\s|[.!?]?$)',
            turn, re.I))
        for token in tokens:
            if normalize_money(token) == expected:
                return token
    return ''


async def edit_completed_fields(state, message):
    from app.services import document_workflow as workflow

    from app.services.document_loan_facts import reconcile_saved_loan_edit
    from app.services.document_source_quotes import literal_evidence

    state = deepcopy(state)
    reconcile_saved_loan_edit(state)
    previous = state.get('pending_document_edit') or {}
    history = list(previous.get('messages') or ([previous['request']] if previous.get('request') else []))
    sources = [*history, message]
    loan = bool(state.get('loan_facts', {}).get('principal'))
    specs = {}
    for field in SCENARIOS[state['scenario']].fields:
        origin = state['fields'].get(field.key, {}).get('origin') or ''
        if field.key in _MANAGED or not field_is_active(field, state['fields']):
            continue
        if loan and field.key == 'facts' and origin == 'loan_arithmetic':
            continue
        if origin.startswith('calculation_') and not (loan and field.key in {'amount', 'payments'}):
            continue
        specs[field.key] = field
    data = {'message': message, 'previous_clarification': previous,
            'fields': [{'key': k, 'label': f.label, 'question': f.question,
                        'current_value': state['fields'].get(k, {}).get('value')} for k, f in specs.items()]}
    if loan:
        ledger = state['loan_facts']
        data['loan'] = {'principal': ledger['principal'], 'payments': [
            {'amount': entry['amount'], 'date': entry.get('date_text')} for entry in ledger.get('payments', [])]}
    prompt = ('Определи, меняет ли пользователь сведения в уже готовом документе. Для явной поправки '
              'или дополнения верни intent edit и отдельные replacements с ключом поля и точной '
              'минимальной цитатой НОВОГО значения из сообщения или предыдущих реплик этой поправки. '
              'Сопоставь короткий ответ с предыдущим уточняющим вопросом. Выдели все изменяемые '
              'исходные факты. Рассчитанные на их основе суммы сервис обновит сам. '
              'При исправлении одного фрагмента в обстоятельствах укажи в previous_quote точный '
              'заменяемый фрагмент current_value и в quote его замену. Когда пользователь добавляет '
              'ещё одно обстоятельство к сохранённым, выбери add. '
              'Для займа различай выданную сумму (transfer), фактически полученный возврат (payments) '
              'и остаток задолженности (amount). Поправка по выписке к одному и тому же переводу — '
              'operation replace, другой фактически полученный перевод — add. Для такого исправления '
              'quote и previous_quote скопируй из сообщения вместе с исходными пробелами. '
              'В короткой команде «поменяй X на Y» сопоставь X с текущими исходными фактами, '
              'quote — это Y, previous_quote — X. Валюта и пробелы между тысячами необязательны. '
              'Если пользователь написал «8 500 рублей», верни «8 500 рублей», сохранив это написание. '
              'previous_quote — прежняя сумма, только если она в реплике. '
              'Различай сведения заявителя и другой стороны. Не включай прежнее значение, указание изменить, '
              'домыслы, поля из примеров или дублирующие правки. Суммы и даты не вычисляй. '
              'Если адресат правки или новое значение неоднозначны, верни clarify и один узкий вопрос. '
              'Для вопроса о праве, условного примера или просьбы оставить документ как есть верни other.')

    async def decide():
        client = await workflow.get_gigachat_client()
        response = await workflow._structured(client, prompt, data, EditDecision.model_json_schema(),
                                              name='edit_completed_document')
        return EditDecision.model_validate_json(response.content), response.usage

    usage = None
    try:
        decision, usage = await asyncio.wait_for(decide(), timeout=12)
    except (RuntimeError, ValueError, TimeoutError):
        decision = EditDecision(intent='other')
        if (previous or EDIT_REQUEST.search(message)) and not re.search(
                r'\bне\s+(?:надо\s+)?(?:меня|замен|исправ|измен|помен)', message, re.I):
            edits = [Replacement(key=item.key, quote=item.value)
                     for item in workflow._ready_labelled_updates(state, message)]
            if not edits:
                contact = _contact_replacement(message, specs)
                loan_quote = explicit_loan_payment_quote(state, message)
                if contact:
                    edits.append(contact)
                if loan_quote:
                    edits.append(Replacement(key='payments', quote=loan_quote))
            decision = EditDecision(intent='edit' if edits else 'clarify', replacements=edits)

    # GigaChat gets the first decision on every correction.  The numeric
    # resolver is a recovery path for a provider timeout or an unresolved
    # model answer, so it cannot overwrite a valid semantic edit returned by
    # the model.
    numeric_edit = _shorthand_amount_edit(state, specs, message, previous)
    if numeric_edit and decision.intent != 'edit':
        decision = numeric_edit
    elif previous.get('payment_to_identify'):
        from app.services.document_case_facts import DATE, MONTH
        if re.fullmatch(r'\s*(?:от\s+)?(?:' + DATE + r'|\d{1,2}\s+' + MONTH + r')[. !]*', message, re.I):
            decision = EditDecision(intent='edit', replacements=[
                Replacement.model_validate(previous['payment_to_identify'])])
    if decision.intent == 'other':
        state.pop('pending_document_edit', None)
        return state, None, usage

    attempts = previous.get('attempts', 1 if previous else 0)

    def clarify(question, **pending):
        # A completed file already has accepted values. An unresolved revision
        # must not silently erase one of them or create an endless edit loop.
        if attempts >= 3:
            state.pop('pending_document_edit', None)
            return state, ('Поправку не удалось однозначно применить. Последний черновик доступен '
                           'для ручного исправления. Можно также прислать новую поправку.'), usage
        if not question or question.count('?') != 1:
            question = 'Какое поле нужно исправить и какое значение в нём указать?'
        state['pending_document_edit'] = {'request': sources[0], 'question': question,
                                          'messages': sources, 'attempts': attempts + 1, **pending}
        return state, question, usage

    if decision.intent == 'clarify' or not decision.replacements:
        return clarify(decision.question)

    result = deepcopy(state)
    from app.services.document_drafting import narrative_keys
    narratives = set(narrative_keys(result))
    seen = set()
    # Apply the source facts before validating any explicitly quoted balance.
    replacements = sorted(decision.replacements, key=lambda item: loan and item.key == 'amount')
    for replacement in replacements:
        key, quote = replacement.key, replacement.quote.strip()
        if key not in specs or key in seen:
            return clarify('')
        seen.add(key)
        source = next((turn for turn in reversed(sources) if literal_evidence(quote, turn)), '')
        loan_field = loan and key in {'payments', 'amount', 'transfer'}
        if (loan_field or specs[key].kind == 'money') and (not source or workflow.normalize_money(quote)):
            quote = _loan_amount_quote(quote, sources)
            source = next((turn for turn in reversed(sources) if quote and quote in turn), '')
        if not source:
            return clarify(f'Какое новое значение указать в поле «{specs[key].label}»?')
        if loan_field:
            old = replacement.previous_quote
            if old:
                # The model may quote the existing ledger as its comparison.
                # Only user-supplied amounts can select between several events.
                # Without one the ledger editor identifies the event by date,
                # or asks which event was meant if that is still ambiguous.
                old = _loan_amount_quote(old, sources)
            handled, question = apply_ready_loan_edit(
                result, key, quote, old, '\n'.join(sources), operation=replacement.operation)
            if handled:
                if question:
                    if question == PAYMENT_DATE_QUESTION:
                        return clarify(question, payment_to_identify=replacement.model_dump())
                    return clarify(question)
                continue
        if key == 'contacts' and re.search(r'(?:телефон|почта|адрес)\s+(?:продавц|исполнител|ответчик)\w*', source, re.I):
            return clarify('Чьи контактные данные нужно исправить?')
        tentative = workflow.apply_updates(result, [workflow.FieldUpdate(key=key, value=quote,
            evidence=quote, status='filled')], source, latest_message=message, semantic_evidence=True)
        field = tentative['fields'].get(key, {})
        if field.get('original') != quote or field.get('status') != 'filled':
            return clarify(f'Какое значение указать в поле «{specs[key].label}»?')
        field['origin'] = 'user_correction'
        before = result['fields'].get(key, {})
        old_text = before.get('value') or ''
        if key in narratives and (replacement.previous_quote or (old_text and replacement.operation == 'add')):
            if replacement.operation == 'add':
                revised = old_text if quote in old_text else old_text.rstrip() + '\n' + quote
            else:
                fragment = replacement.previous_quote.strip()
                if not fragment or old_text.count(fragment) != 1:
                    return clarify(f'Какой фрагмент в поле «{specs[key].label}» нужно заменить?')
                revised = old_text.replace(fragment, quote, 1)
            normalized, error = workflow.normalize_field(specs[key], revised)
            if error:
                return clarify(error)
            proof = before.get('source_quotes') or [before.get('evidence') or before.get('original') or old_text]
            field.update(value=normalized, original=revised, source_quotes=[*proof, quote])
        if key == 'contacts':
            # Replacing a phone leaves the previously supplied email in the document.
            incoming = field['value'].splitlines()
            changed = {line.partition(':')[0] for line in incoming}
            old = result['fields'].get(key, {}).get('value') or ''
            retained = [line for line in normalize_contacts(old).splitlines()
                        if line.partition(':')[0] not in changed]
            field['value'] = '\n'.join(incoming + retained)
        result = tentative
    if 'amount' in seen:
        from app.services.document_consumer_facts import sync_consumer_amount_correction
        sync_consumer_amount_correction(state, result, seen)
    result.pop('pending_document_edit', None)
    return result, '', usage
