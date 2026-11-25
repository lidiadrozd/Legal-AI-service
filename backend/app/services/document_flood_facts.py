"""Retain explicit flood-claim facts omitted by document extraction."""
import re
from collections import defaultdict

from app.services.document_addresses import postal_phrase
from app.services.document_case_facts import DATE, set_field
from app.services.document_explicit_facts import NAME
from app.services.document_money_tokens import find_money_quotes
from app.services.document_source_quotes import source_sentences


ASSESSMENT_LOSS_QUALIFIER = r'(?:как|в\s+качестве|в\s+составе)\s+(?:(?:самостоятельн|имущественн|реальн)\w*\s+)*убыт\w*'


def requested_valuation_cost(state):
    """Read an assessment paid by the claimant and expressly included in their demand."""
    from app.services.document_calculation_ledger import extract_components

    fields = state.get('fields', {})
    requests = fields.get('requests', {})
    cost = fields.get('litigation_costs', {})
    if requests.get('status') != 'filled' or cost.get('status') != 'filled':
        return None
    demand = requests.get('value') or ''
    if not (re.search(r'\b(?:взыскать|возместить|компенсировать)\b', demand, re.I)
            and re.search(r'\b(?:расход\w*|затрат\w*)\s+на\s+оценк\w*|\bстоимость\s+оценки', demand, re.I)):
        return None
    if re.search(r'\b(?:не\s+(?:взыск|заяв|прос|прошу|включ)|отказываюсь|исключить|без\s+расходов)', demand, re.I):
        return None
    sources = [cost.get('value'), cost.get('evidence'), *(cost.get('source_quotes') or ())]
    if (not any(find_money_quotes(source or '') for source in sources)
            and not re.search(r'\b(?:нет|отказ\w*|без|не\s+заяв\w*)\b', cost.get('value') or '', re.I)):
        # An older interview could keep the expense amount only in the user's story.
        sources.extend(turn for turn in state.get('user_turns', []) if isinstance(turn, str))
    amounts = {}
    for source in sources:
        for sentence in source_sentences(source or ''):
            if ('?' in sentence or re.search(r'\b(?:не\s+(?:оплат|заплат|уплат)|если|например)', sentence, re.I)
                    or not re.search(r'\b(?:опла(?:тил|чен)|заплатил|уплатил|потратил)\w*', sentence, re.I)):
                continue
            items, _ = extract_components(sentence)
            for item in items:
                if item['kind'] == 'valuation':
                    amounts[item['value']] = item
    if len(amounts) == 1:
        valuation = next(iter(amounts.values()))
        # Preserve the claimant's express theory of recovery. A receipt
        # or the timing of the appraisal alone cannot establish that theory.
        named_loss = re.search(
            r'(?:расход\w*|затрат\w*|стоимость)\s+(?:на\s+)?оценк\w*\s+'
            + ASSESSMENT_LOSS_QUALIFIER,
            demand, re.I)
        if named_loss:
            valuation = {**valuation, 'include_in_claim_price': True}
        return valuation
    return None


def supplement_flood_narrative(state, message):
    """Fill empty slots from affirmative user statements. Leave conflicting choices to the interview."""
    if state.get('scenario') != 'claim_damage_flood' or re.search(
            r'\b(?:исправь|исправление|замени|поправка|ошиб(?:ся|лась)|например|предположим)\b', message, re.I):
        return set()
    fields = state.get('fields', {})
    unrepaired = fields.get('restoration', {}).get('value') == 'не восстановлено'
    estimate = fields.get('restoration_estimate', {})
    if (not unrepaired and estimate.get('from_full_repair_estimate')
            and estimate.get('origin') == 'source_bound_extraction'):
        del fields['restoration_estimate']
        state['revision'] = state.get('revision', 0) + 1
    sentences = source_sentences(message)
    if not sentences:
        return set()
    candidates = defaultdict(list)

    def offer(key, value, evidence):
        if value and (value, evidence) not in candidates[key]:
            candidates[key].append((value, evidence))

    for index, sentence in enumerate(sentences):
        if '?' in sentence or re.search(r'\b(?:если|возможно|не уверен\w*)\b', sentence, re.I):
            continue
        prior = sentences[index - 1] if index else ''
        author = re.search(r'\b(?i:меня зовут|я\s*[—-])\s+(' + NAME + r')\b', sentence)
        if author:
            offer('sender', author[1], sentence)
        ownership = re.match(r'я\s+(?:являюсь\s+)?(?:собственни(?:к|ца|ком|цей)|нанимател(?:ь|ем))\s+(?P<object>квартир[а-я]*\b.*)', sentence, re.I)
        if ownership:
            offer('property_right', sentence, sentence)
            if postal_phrase(ownership['object']):
                offer('property_address', ownership['object'].rstrip('.'), sentence)
        if re.search(r'\b(?:залил[аи]?|затопил[аи]?|произош[её]л\s+залив)\b', sentence, re.I):
            dates = re.findall(DATE, sentence, re.I)
            if len(dates) == 1:
                offer('flood_date', dates[0], sentence)
            neighbour = re.search(r'\b(?i:сосед(?:ка)?(?:\s+из\s+квартиры\s*№?\s*\d+)?\s*[,—-]?\s+)(' + NAME + r')\b', sentence)
            if neighbour:
                offer('recipient', neighbour[1], sentence)
        act = re.search(r'\b(?:состав\w*|оформ\w*|подпис\w*)\s+акт\b|\bакт\b.{0,50}\b(?:составлен|оформлен|зафиксирован)\b', sentence, re.I)
        if act and not re.search(r'\bне\s+(?:был\s+)?(?:состав|оформ|подпис)', sentence, re.I):
            # Relative dates stay in the user's own wording; this slot is prose.
            offer('evidence', sentence, sentence)
        if re.search(r'\b(?:лопнул\w*|прорвал\w*|сорвал[аось]*|протечк\w*|разрыв\w*|разгерметизац\w*)\b', sentence, re.I):
            if re.match(r'в\s+н[ёе]м\b|согласно\s+ему\b', sentence, re.I) and re.search(r'\bакт\b', prior, re.I):
                offer('facts', prior, prior)
            offer('facts', sentence, sentence)
        if re.search(r'\b(?:поврежден[аоы]?|поврежд[её]н\w*|испорчен\w*|намок\w*|вздул\w*|отслоил\w*)\b', sentence, re.I) and not re.search(
                r'\bне\s+(?:поврежд|испорчен|намок|вздул|отслоил)|\bне\s+(?:был|была|были|оказал)\w*', sentence, re.I):
            offer('damage_object', sentence, sentence)

        amounts = find_money_quotes(sentence)
        assessment = re.search(r'\b(?:оценщик\w*|отч[её]т\w*|смет[ауы]|эксперт\w*)\b', sentence, re.I)
        if (len(amounts) == 1 and assessment and re.search(r'\b(?:ремонт\w*|восстановлени\w*|ущерб\w*)\b', sentence, re.I)
                and not re.search(r'\b(?:не\s+стоил?\w*|заплатил\w*|потратил\w*|возместил\w*|оплатил\w*|аванс\w*)\b', sentence, re.I)):
            offer('amount', amounts[0], sentence)
            offer('calculation', sentence, sentence)
            offer('evidence', sentence, sentence)
            if unrepaired and re.search(r'\b(?:ремонт\w*|восстановлени\w*)\b', sentence, re.I):
                offer('restoration_estimate', sentence, sentence)
        if (len(amounts) == 1 and re.search(r'\b(?:за\s+(?:саму\s+)?оценк\w*|услуг\w*\s+оценщик\w*|расход\w*\s+на\s+оценк\w*)\b', sentence, re.I)
                and re.search(r'\b(?:заплатил\w*|уплатил\w*|опла(?:тил|чен)\w*|потратил\w*)\b', sentence, re.I)
                and not re.search(r'\bне\s+(?:заплат|уплат|опла|потрат)', sentence, re.I)):
            offer('litigation_costs', sentence, sentence)
        if re.search(r'\bпретензи\w*\b', sentence, re.I) and re.search(r'\b(?:вручил\w*|направил\w*|отправил\w*|получил\w*|передал\w*)\b', sentence, re.I):
            offer('pretrial', sentence, sentence)
        elif prior and any(proof == prior for _, proof in candidates['pretrial']) and re.search(
                r'\b(?:расписал\w*|отказал\w*|ответил\w*|не\s+(?:ответил|перечислил|возместил|заплатил)\w*)\b', sentence, re.I):
            offer('pretrial', sentence, sentence)
        if re.match(r'(?:я\s+)?(?:прошу|хочу)\s+(?:суд\s+)?(?:взыскать|обязать|возместить)\b', sentence, re.I):
            offer('requests', sentence, sentence)
            # The user may state the expense and the intention to recover it
            # in separate turns. Keep the request itself as evidence for the
            # optional litigation-costs field so the question is not repeated.
            if re.search(r'\b(?:расход\w*|затрат\w*)\s+на\s+оценк\w*|\bоценк\w*\s+расход\w*', sentence, re.I):
                offer('litigation_costs', sentence, sentence)
        attached = re.search(r'\b(?:приложу|прилагаю|приложены|прилагаются)\s+(?:к\s+иску\s+)?(.+)', sentence, re.I)
        if attached:
            offer('attachments', attached[1].rstrip('.'), sentence)

    # An expense is not automatically a demand. Keep it separate from repair.
    if not any(re.search(r'\b(?:оценк\w*|оценщик\w*|судебн\w*\s+расход\w*)\b', value, re.I)
               for value, _ in candidates['requests']):
        candidates.pop('litigation_costs', None)

    filled = set()
    for key, proposals in candidates.items():
        saved = state.get('fields', {}).get(key, {})
        # A previous extractor may have created an empty ``incomplete``
        # placeholder for this slot.  It is still safe to replace that
        # placeholder with an unambiguous literal quote from the user's
        # narrative.  Confirmed, explicitly unknown, and conflict/manual
        # values remain protected from automatic replacement.
        if (not proposals or saved.get('status') not in {None, 'missing', 'incomplete'}
                or saved.get('value')
                or saved.get('origin') == 'narrative_conflict'
                or str(saved.get('origin') or '').startswith('manual')
                or key in state.get('narrative_conflicts', {})):
            continue
        values = list(dict.fromkeys(value for value, _ in proposals))
        if key in {'sender', 'recipient', 'property_address', 'flood_date', 'amount'} and len(values) != 1:
            continue
        quotes = list(dict.fromkeys(evidence for _, evidence in proposals))
        if set_field(state, key, '\n'.join(values), quotes[0]):
            state['fields'][key]['source_quotes'] = quotes
            if key == 'restoration_estimate':
                state['fields'][key]['from_full_repair_estimate'] = True
            filled.add(key)
    return filled
