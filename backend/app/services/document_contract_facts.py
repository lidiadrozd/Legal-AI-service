"""Keep agreed contract terms in their own slots, with literal user evidence."""
import re
from copy import deepcopy

SERVICE_CONTRACTS = {'contract_services', 'contract_work'}
VERSION = 5
TERM_KEYS = {'subject', 'scope', 'materials', 'term', 'payment', 'acceptance',
             'changes', 'quality', 'liability', 'termination', 'additional_terms'}


def _clauses(text):
    from app.services.document_form_intake import _protect_abbreviations
    protected = _protect_abbreviations(text)
    return [s.replace('\uFFF0', '.').strip(' .;\n')
            for s in re.split(r'(?<=[.!?;])\s+|\n+', protected) if s.strip(' .;\n')]


def _merge_clauses(prior, incoming):
    parts=[]
    seen=set()
    for part in _clauses(prior) + _clauses(incoming):
        normalized=re.sub(r'\s+', ' ', part).casefold().replace('ё','е')
        if normalized not in seen:
            parts.append(part);seen.add(normalized)
    return '. '.join(parts) + '.'


def contract_fragments(text):
    """Classify clauses, never a whole multi-topic reply as the subject."""
    from app.services.document_case_facts import DATE, MONEY
    result = {}
    def add(key, value):
        value = value.strip(' .;\n')
        if value:
            result.setdefault(key, [])
            if value not in result[key]: result[key].append(value)
    section = None
    for clause in _clauses(text):
        if '?' in clause: continue
        heading=re.match(r'По\s+(ответственности|изменению и прекращению договора)\s*:\s*(.*)',clause,re.I)
        if heading:
            section='liability' if heading[1].lower()=='ответственности' else 'termination'
            clause=heading[2]
        if section:
            add(section,clause)
            if section=='liability' and re.search(r'устран\w*.{0,25}недостат|исправ\w*.{0,25}дефект',clause,re.I):
                add('quality',clause)
            continue
        if re.search(r'недостат\w*.{0,50}(?:исправля|устраня)\w*', clause, re.I):
            add('quality', clause)
            continue
        if re.search(r'\bрезультат\w*\s+проверя\w*', clause, re.I):
            add('acceptance', clause)
            continue
        if re.search(r'\b(?:краск\w*|инструмент\w*)\b.{0,55}(?:покупа|предостав|приобрета)\w*', clause, re.I):
            add('materials', clause)
            continue
        if re.search(r'\b(?:нужно|надо)\s+(?:покрасить|оклеить|уложить|смонтировать|отремонтировать)\b|\bподготовк\w*\s+поверхност\w*|\bзамен\w*\s+проводк\w*.{0,20}не\s+вход', clause, re.I):
            add('scope', clause)
            continue
        if re.search(r'договор\s+составля\w*', clause, re.I):
            day = re.search(DATE, clause, re.I)
            if day:
                add('date', day[0])
                place = re.search(r'\s+в\s+(.+)$', clause[day.end():])
                if place: add('place', place[1])
            continue
        # Total price and payment schedule may share a sentence. Capture both
        # before selecting a narrative slot; an advance is never the total.
        price = re.match(r'\s*(?:стоимость|цена)(?:\s+(?:договора|услуг|работ|съ[её]мки))?\s*[—–:-]?\s*(' + MONEY + r')',clause,re.I)
        if price:
            add('amount',price[1])
            clause=clause[price.end():].strip(' :;—–-')
            if not clause:continue
        if re.search(r'устран\w*.{0,25}недостат|исправ\w*.{0,25}дефект',clause,re.I):
            add('quality',clause)
        elif re.search(r'(?:прекрат|расторг|расторжен)\w*\s+договор|договор\w*.{0,45}(?:прекращ|расторж)|штраф\w*.{0,30}не\s+согласован',clause,re.I):
            add('liability' if re.search(r'штраф',clause,re.I) else 'termination',clause)
        elif re.match(r'Ответственность\s+(?:заказчика|исполнителя|сторон)',clause,re.I):
            add('liability',clause)
        elif re.search(r'портфолио|соц(?:иальн\w*\s+сет|сет)|публиков|публикаци|размещени\w*\s+фотограф', clause, re.I):
            add('additional_terms', clause)
        elif re.search(r'дополнительн\w*\s+(?:час|работ|услуг)|изменени\w*\s+(?:задани|цен|срок)', clause, re.I):
            add('changes', clause)
        elif re.search(r'предоплат|аванс|оставш\w*\s+\d|остаток\s+(?:оплат|\d)|окончательн\w*\s+расч[её]т|порядок\s+расч[её]тов|способ\s+оплаты', clause, re.I):
            add('payment', clause)
        elif re.search(r'(?:договор\w*\s+(?:подписываем|заключаем|подписан|заключ[её]н)|дата\s+(?:договора|подписания|заключения))', clause, re.I):
            day = re.search(DATE, clause, re.I)
            if day: add('date', day[0])
        elif re.search(r'(?:текст|фотограф|логотип|контент|материал|оборудовани|исходн\w*\s+данн).{0,60}(?:переда[её]т|предоставля[её]т)\s+заказчик|заказчик\s+(?:переда[её]т|предоставля[её]т).{0,60}(?:текст|фотограф|логотип|контент|материал|оборудовани|исходн\w*\s+данн)',clause,re.I):
            add('materials',clause)
        elif re.search(r'исполнитель\s+(?:переда[её]т|предоставля[её]т).{0,50}(?:исходн\w*\s+файл|доступ|исходник)',clause,re.I):
            add('scope',clause)
        elif re.search(r'при[её]мк|подпис\w*\s+акт|провер\w*.{0,30}(?:результат|фотограф)|замечани\w*.{0,30}(?:дн|срок)', clause, re.I):
            add('acceptance', clause)
        elif re.search(r'(?:оборудовани|материал|исходн\w*\s+данн).{0,70}(?:предостав|обеспеч|сво)|(?:предостав|обеспеч|использует).{0,70}(?:оборудовани|материал|программ\w*\s+(?:праздник|мероприяти)|исходн\w*\s+данн)', clause, re.I):
            add('materials', clause)
        elif (re.search(r'срок\s+(?:передачи|сдачи|выполнения)|\bс\s+\d{1,2}:\d{2}\s+до\s+\d{1,2}:\d{2}|ссылк\w*.{0,50}(?:действ|работать|доступ|актив)', clause, re.I)
              or (re.search(DATE, clause, re.I) and re.search(r'мероприяти|ероприяти|съ[её]мк|выполн|оказани|переда|этап|работ', clause, re.I))):
            add('term', clause)
        elif re.search(r'\b(?:\d+|одн\w*|двух|тр[её]х|четыр[её]х|пяти|шести|семи|восьми|девяти|десяти)\s+(?:(?:обработанн\w*|готов\w*|итогов\w*)\s+)?(?:фотограф|снимк|страниц|ролик|видеозапис|макет|квадратн)|формат\w*\s+(?:JPEG|JPG|PNG|PDF|MP4)|ретуш|адаптаци\w*\s+для|форма\s+обратной\s+связи|в\s+задание\s+(?:не\s+)?вход', clause, re.I):
            add('scope', clause)
    # The object of a requested shoot is sufficient to name the service;
    # its dates, delivery terms and price still have independent fields.
    subject = re.search(r'\b((?:фото|видео)?съ[её]мк\w*\s+(?:мероприяти\w*|свадьб\w*|конференци\w*|дня\s+рождения))', text, re.I)
    if subject: add('subject', subject[1])
    subject = re.search(r'\b((?:создание|разработка|изготовление)\s+(?:веб[- ]?)?сайта)\b',text,re.I)
    if subject:add('subject',subject[1])
    subject = re.search(r'\b((?:ремонт|покраска|окраска)\s+(?:комнаты|квартиры|помещения|стен|потолка))\b', text, re.I)
    if subject: add('subject', subject[1])
    return {key: '. '.join(v[:1].upper()+v[1:] if key in TERM_KEYS else v for v in values) + ('.' if key in TERM_KEYS else '') for key, values in result.items()}


def collect_contract_turn(state, text, current=None):
    if state.get('scenario') not in SERVICE_CONTRACTS: return set()
    from app.services.document_case_facts import set_field, absence_reply
    from app.services.document_dialogue import conversational_value
    if conversational_value(text):
        factual = [clause for clause in _clauses(text) if not conversational_value(clause)]
        if not factual: return set()
        text = '. '.join(factual)
    fragments = contract_fragments(text)
    consumed = set()
    for clause in _clauses(text):
        if re.search(r'паспортн\w*\s+данн\w*\s+и\s+адрес\s+(?:мастера|исполнителя|подрядчика).{0,30}(?:внес[её]м|заполню|внесу)\s+вручн', clause, re.I):
            for blank in ('sender_details', 'recipient_details', 'recipient_address'):
                if state['fields'].get(blank, {}).get('status') not in {'filled', 'unknown', 'not_applicable'}:
                    if set_field(state, blank, None, clause, 'unknown'): consumed.add(blank)
    if re.search(r'мой\s+адрес\s+совпадает\s+с\s+адресом\s+ремонт', text, re.I):
        addresses = [re.split(r'по\s+адресу\s*:\s*', clause, flags=re.I)[1]
                     for clause in _clauses(text) if re.search(r'по\s+адресу\s*:', clause, re.I)]
        if len(addresses) == 1 and state['fields'].get('sender_address', {}).get('status') != 'filled':
            if set_field(state, 'sender_address', addresses[0], addresses[0]): consumed.add('sender_address')
    if current=='additional_terms' and absence_reply(text) and state['fields'].get(current,{}).get('status')=='filled':
        return {current}  # No *other* conditions does not cancel an earlier one.
    if current in {'quality', 'liability', 'materials'} and absence_reply(text):
        fragments[current] = text
    if current == 'payment' and re.fullmatch(r'безнал(?:ичный\s+расч[её]т)?[.! ]*', text, re.I):
        fragments['payment'] = 'Безналичный расчёт.'
    if current == 'acceptance' and re.fullmatch(r'(?:в\s+формате\s+)?(?:JPEG|JPG|PNG|PDF|MP4)[.! ]*', text, re.I):
        state['fields']['acceptance'] = dict(status='incomplete', value=None, evidence=text,
            error='Формат файла указан. В какой срок и каким способом Заказчик подтвердит приёмку результата или сообщит о замечаниях?')
        return {'acceptance'}
    for key, value in fragments.items():
        old = state['fields'].get(key, {})
        prior = old.get('value') or ''
        if old.get('status') == 'filled':
            if key not in TERM_KEYS - {'subject'}: continue
            if value.rstrip('. ').casefold() in prior.casefold(): continue
            # A payment method supplements agreed instalments, never erases them.
            if prior.rstrip('. ').casefold() not in value.casefold():
                value = _merge_clauses(prior, value)
            if value == prior: continue
        if set_field(state, key, value, value):
            state['fields'][key].update(source_field=current, origin='contract_clause_extraction')
            consumed.add(key)
    return consumed


def contract_candidate(key, source):
    """Exact grammatical transformations for explicit agreements/negatives."""
    from app.services.document_case_facts import absence_reply
    text = source.strip(' .')
    if key=='acceptance' and re.fullmatch(r'Результат\s+проверяю\s+в\s+течение\s+.+',text,re.I):
        return re.sub(r'^Результат\s+проверяю', 'Заказчик проверяет результат', text, flags=re.I)+'.'
    if key=='materials' and re.fullmatch(r'Краску\s+покупаю\s+я,\s*инструменты\s+предоставляет\s+мастер',text,re.I):
        return 'Краску приобретает Заказчик. Инструменты предоставляет Исполнитель.'
    if key=='changes' and re.fullmatch(r'Дополнительные\s+работы\s*[—–-]\s*только\s+после\s+письменного\s+согласования\s+цены',text,re.I):
        return 'Дополнительные работы выполняются только после письменного согласования их цены.'
    if key=='quality' and re.fullmatch(r'Недостатки\s+покраски\s+мастер\s+исправляет\s+бесплатно\s+за\s+.+',text,re.I):
        return re.sub(r'^Недостатки\s+покраски\s+мастер\s+исправляет\s+бесплатно\s+за\s+',
                      'Исполнитель бесплатно устраняет недостатки покраски за ',text,flags=re.I)+'.'
    if key=='additional_terms':
        forbidden=re.fullmatch(r'Публиковать\s+(.+?)\s+без\s+отдельного\s+письменного\s+согласия\s+заказчика\s+нельзя',text,re.I)
        if forbidden:return 'Публиковать '+forbidden[1]+' допускается только с отдельного письменного согласия Заказчика.'
    formal_starts={
        'acceptance':r'Заказчик\s+проверяет\s+(?:результат|фотографии)',
        'materials':r'(?:Фотограф|Исполнитель)\s+использует|Заказчик\s+предоставляет|(?:Тексты|Фотографии)\s+',
        'quality':r'Исполнитель\s+(?:бесплатно|обязан\s+бесплатно)',
        'liability':r'(?:Исполнитель|Заказчик)\s+обязан|Дополнительные\s+штрафы',
        'termination':r'Если\s+|Новый\s+срок\s+стороны|Автоматически\s+он\s+не\s+продлевается|Стороны\s+могут\s+прекратить|Заказчик\s+оплачивает|Исполнитель\s+переда[её]т',
    }
    if key in formal_starts:
        clauses=_clauses(text)
        if clauses and all(re.match(formal_starts[key],c,re.I) for c in clauses):
            return '. '.join(c[:1].upper()+c[1:] for c in clauses)+'.'
    if key in {'quality', 'liability', 'materials'} and absence_reply(text):
        return {
            'quality': 'Дополнительные условия устранения недостатков и гарантийные обязательства сторонами не согласованы.',
            'liability': 'Дополнительные условия ответственности сторонами не согласованы.',
            'materials': 'Дополнительные условия предоставления материалов, оборудования и исходных данных сторонами не согласованы.',
        }[key]
    if key == 'subject' and re.fullmatch(r'(?:фото|видео)?съ[её]мк\w*\s+(?:мероприяти\w*|свадьб\w*|конференци\w*|дня\s+рождения)', text, re.I):
        return 'Исполнитель оказывает услуги по ' + re.sub(r'съ[её]мк\w*', 'съёмке', text, count=1, flags=re.I).lower() + '.'
    if key == 'payment' and re.fullmatch(r'безнал(?:ичный\s+расч[её]т)?', text, re.I):
        return 'Оплата производится безналичным расчётом.'
    if key == 'payment' and re.match(r'^безнал\.\s+Предоплата\b', text, re.I):
        return re.sub(r'^безнал\.\s*', 'Оплата производится безналичным расчётом. ', text, flags=re.I) + '.'
    if key == 'scope' and re.fullmatch(r'(?:Фотограф|Исполнитель)\s+(?:должен|обязан)\s+передать\s+не\s+менее\s+\d+\s+обработанных\s+фотографий\s+в\s+формате\s+[A-Z]+,\s+из\s+них\s+\d+\s*[—–-]?\s*с\s+дополнительной\s+ретушью', text, re.I):
        return re.sub(r'^Фотограф', 'Исполнитель', text, flags=re.I) + '.'
    if key == 'changes':
        # An optional extension does not mean extra hours are already ordered.
        text=re.sub(r'^(?:только\s+)?доп(?:олнительные|\.?)\s+часы\.?\s*',
                    'Изменения задания ограничиваются дополнительными часами. ', text, flags=re.I).strip()
        if re.fullmatch(r'(?:Изменения задания ограничиваются дополнительными часами\.\s*)?Дополнительные (?:часы|работы|услуги) оплачиваются только после письменного согласования(?: стоимости)?', text, re.I):
            return text + '.'
    if key=='payment':
        from app.services.document_case_facts import MONEY
        # Expand only the omitted predicate, preserving amounts, dates,
        # working/calendar days and the event which triggers final payment.
        match=re.fullmatch(r'(?:аванс|предоплата)\s+('+MONEY+r')\s+до\s+([^,]+),\s*остаток\s+('+MONEY+r')\s+(в течение\s+.+)',text,re.I)
        if match:
            return ('Аванс в размере '+match[1]+' уплачивается до '+match[2]+'. Остаток в размере '+match[3]+' уплачивается '+match[4]+'.')
    if key=='scope':
        parts=[]
        for clause in _clauses(text):
            if re.match(r'^Нужны\s+',clause,re.I):
                clause=re.sub(r'^Нужны\s+','В задание входят ',clause,flags=re.I)
            if not re.match(r'^(?:Исполнитель\s+(?:должен|обязан|переда[её]т)|В задание входят|.+\s+в задание не входят)',clause,re.I):break
            parts.append(clause)
        else:
            if parts:return '. '.join(parts)+'.'
    if key=='materials' and re.fullmatch(r'(?:Тексты|Фотографии|Материалы|Оборудование|Исходные данные)\b.{0,200}\b(?:переда[её]т|предоставля[её]т)\s+заказчик(?:\s+до\s+.+)?',text,re.I):
        return text+'.'
    if key=='term' and re.fullmatch(r'Срок передачи результата\s*[—–-]?\s*.+',text,re.I):
        return re.sub(r'^Срок передачи результата\s*[—–-]?\s*','Срок передачи результата — ',text,flags=re.I)+'.'
    if key=='acceptance' and re.fullmatch(r'Заказчик проверяет результат в течение .+ и направляет замечания одним списком',text,re.I):
        return text+'.'
    if key=='quality' and re.fullmatch(r'если что-то не устроит, заказчик попросит переделать',text,re.I):
        return 'Если результат не устраивает Заказчика, он обращается к Исполнителю с просьбой о доработке.'
    if key=='liability':
        parts=[]
        for clause in _clauses(text):
            duty=re.fullmatch(r'Ответственность\s+(исполнителя|заказчика)\s*(?:за ненадлежащее исполнение обязательств\s*)?[-—–:]\s*(?:обязанность|необходимость)\s+(.+)',clause,re.I)
            if not duty:break
            role={'исполнителя':'Исполнитель','заказчика':'Заказчик'}[duty[1].lower()]
            condition='При ненадлежащем исполнении обязательств '+role.lower() if 'за ненадлежащее исполнение' in clause.lower() else role
            parts.append(condition+' обязан '+duty[2])
        else:
            if parts:return '. '.join(parts)+'.'
    if key == 'term':
        parts=[]
        for clause in _clauses(text):
            if re.match(r'^м?ероприятие состоится\b',clause,re.I):
                clause=re.sub(r'^м?ероприятие', 'Мероприятие', clause, flags=re.I)
            elif re.fullmatch(r'Съёмка нужна с \d{1,2}:\d{2} до \d{1,2}:\d{2}',clause,re.I):
                clause=re.sub(r'^Съёмка нужна', 'Съёмка проводится', clause, flags=re.I)
            elif re.fullmatch(r'Срок передачи\s*[—–-]?\s*не позднее .+, способом отправки ссылки на скачивание',clause,re.I):
                clause=re.sub(r'^Срок передачи\s*[—–-]?\s*', 'Результат передаётся ', clause, flags=re.I)
                clause=clause.replace(', способом отправки ссылки на скачивание', ' по ссылке для скачивания')
            elif re.fullmatch(r'Ссылка должна работать минимум \d+ дней',clause,re.I):
                clause=re.sub(r'^Ссылка должна работать минимум', 'Ссылка для скачивания должна быть доступна не менее', clause, flags=re.I)
            else:
                break
            parts.append(clause)
        else:
            if parts:return _merge_clauses('', '. '.join(parts))
    if key == 'subject' and re.match(r'^(?:разработка|ремонт|изготовление|создание|подготовка|обслуживание)\b', text, re.I) and not re.search(r'[.!?;]|\b(?:я|хочу|нужно|надо)\b', text, re.I):
        return 'Предмет договора — ' + text[:1].lower() + text[1:] + '.'
    compact=re.sub(r'\b(?:кв|м)\.', '', text, flags=re.I)
    if key == 'scope' and re.match(r'^(?:\d+\s+(?:страниц|снимк|фотограф|макет|ролик)\w*|окраска|оклейка|укладка|монтаж)\b', text, re.I) and not re.search(r'[.!?;]|\b(?:я|хочу|нужно|надо)\b', compact, re.I):
        return 'Согласованный объём и требования: ' + text + '.'
    return None


def repair_contract_facts(state):
    """Repair old interviews from user turns, without trusting editor prose."""
    if state.get('scenario') not in SERVICE_CONTRACTS or state.get('contract_fact_version', 0) >= VERSION: return
    from app.services.document_dialogue import conversational_value
    fields = state['fields']
    before = deepcopy(fields)
    from app.services.document_field_safety import field_value_problem, problem_question
    for key in ('sender','recipient','termination'):
        item=fields.get(key,{})
        source=item.get('value') or ''
        problem=field_value_problem(key,source) if source else None
        if problem in {'identity_is_description','termination_is_vague'}:
            item.update(status='incomplete',error=problem_question(problem))
    # A user's reminder is not a replacement for the original detailed terms.
    # Only multi-topic values and control replies are cleared for recovery.
    for key in TERM_KEYS:
        item = fields.get(key, {})
        source = item.get('original') or item.get('evidence') or item.get('value') or ''
        if conversational_value(source) or (key in {'subject', 'term'} and len(contract_fragments(source)) >= 3):
            fields.pop(key, None)
        elif key == 'acceptance':
            collect_contract_turn(state, source, key)
        elif key == 'payment':
            parts=contract_fragments(source)
            if set(parts)=={'amount','payment'}:
                # Old parser included the total price in the payment slot.
                # Narrow the value while preserving the original user proof.
                item.update(value=parts['payment'],original=parts['payment'])
    for text in dict.fromkeys([state.get('request', ''), state.get('context', ''), *state.get('user_turns', [])]):
        collect_contract_turn(state, text)
    if fields != before:
        state['contract_previous_fields'] = before
        for key in ('draft_fields', 'draft_cache', 'draft_digest', 'generated_document'):
            state.pop(key, None)
    state['contract_fact_version'] = VERSION
