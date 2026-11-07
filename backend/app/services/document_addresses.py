"""Postal components and explicit reference confirmation, shared by all forms."""
import re

RELATIVE = re.compile(r'в (?:том|этом) же доме|там же|тот же адрес|по тому же адресу|мой (?:же )?адрес|адрес (?:истца|заявителя|ответчика)|как у меня', re.I)


def collect_role_addresses(state, message):
    """Apply explicitly assigned addresses together, including corrections."""
    from app.services.document_case_facts import set_field
    from app.services.document_dialogue import normalize_address
    from app.services.document_scenarios import SCENARIOS
    specs={f.key:f for f in SCENARIOS[state['scenario']].fields}
    roles=[(r'прод[ао]в[е]?ц',r'продав'),(r'потребител|покупател',r'потребител|покупател'),
           (r'за[её]мщик',r'за[её]мщик'),(r'займодав[е]?ц',r'займодав'),
           (r'ист[е]?ц',r'истец'),(r'ответчик',r'ответчик'),
           (r'исполнител',r'исполнител'),(r'подрядчик',r'подрядчик'),(r'заказчик',r'заказчик')]
    pattern='|'.join('(?:'+match+r')\w*' for match,_ in roles)
    labels=list(re.finditer(r'(?:это\s+у\s+|адрес\s+|у\s+)?('+pattern+r')(?:\s+[^:;\n.]{1,110})?\s*:\s*',message,re.I))
    consumed=set()
    for i,match in enumerate(labels):
        raw=message[match.end():labels[i+1].start() if i+1<len(labels) else len(message)]
        raw=re.sub(r',?\s*(?:а\s*)?(?:это\s+)?(?:у\s+)?$','',raw).strip(' ,;')
        role=next(label for pattern,label in roles if re.match(pattern,match[1],re.I))
        candidates=[party+'_address' for party in ('sender','recipient','seller','employer')
                    if party in specs and party+'_address' in specs and re.search(role,specs[party].label,re.I)]
        # The form owns party roles: in a sale contract the seller is usually
        # sender, while a consumer demand addresses the seller as recipient.
        if len(candidates)!=1:continue
        key=candidates[0]
        if not address_error(normalize_address(raw)):
            set_field(state,key,raw,match[0]+raw)
            state['fields'][key]['address_components']=components(state['fields'][key]['value'])
            consumed.add(key)
    return consumed


def explicit_component_correction(previous,message):
    """Apply only explicit apartment removal and a named locality to saved parts."""
    if not previous:return None
    remove=re.search(r'(\d+)\s+(?:писать не надо|не нужно|убрать)|(?:убери|удали)\s+(?:квартиру\s*)?(\d+)',message,re.I)
    city=re.search(r'\bгород[ао]?\s+([А-Яа-яЁё-]+(?:\s+[А-Яа-яЁё-]+)?)\s*[.!]*$',message,re.I)
    if not remove or not city:return None
    number=next(x for x in remove.groups() if x)
    if not re.search(r'кв\.\s*'+re.escape(number)+r'\b',previous,re.I):return None
    corrected=re.sub(r',?\s*кв\.\s*'+re.escape(number)+r'\b','',previous,flags=re.I)
    return 'г. '+city[1].strip().title()+', '+corrected


def components(value):
    city = re.search(r'(?:^|,\s*)(?:г\.?|город|село|пос[её]лок|деревня)\s+([^,]+)', value, re.I)
    street = re.search(r'(?:^|,\s*)(?:ул\.?|улица|просп(?:ект)?\.?|пер(?:еулок)?\.?)\s+([^,]+)', value, re.I)
    house = re.search(r'(?:^|[,\s])(?:д\.|дом)\s*(\d+[\w/-]*)', value, re.I)
    flat = re.search(r'(?:кв\.?|квартира)\s*№?\s*(\d+[\w/-]*)', value, re.I)
    if not city and ',' in value:
        first = value.split(',')[0].strip()
        if re.fullmatch(r'[А-Яа-яЁё-]+(?:\s+[А-Яа-яЁё-]+)*', first) and not re.match(r'ул\b|улица\b', first, re.I):
            city = (first, first)
    return {'locality': city[1].strip() if city else None, 'street': street[1].strip() if street else None,
            'house': house[1] if house else None, 'flat': flat[1] if flat else None}


def address_error(value):
    if RELATIVE.search(value):
        return 'Адрес содержит ссылку на ранее указанные сведения. Укажите полный адрес или подтвердите предложенный вариант.'
    parts = components(value)
    if not parts['locality']:
        return f'В адресе не указан населённый пункт. Сохранил указанную часть: {value}. Какой город или другой населённый пункт нужно добавить?'
    if not parts['house'] or not parts['street']:
        # A rural address can explicitly have no street. Do not fabricate one.
        rural = re.search(r'село|деревня|пос[её]лок|хутор|станица|без улицы', value, re.I)
        if not (rural and parts['house']):
            return 'Этого недостаточно для полного адреса: не удалось выделить улицу и номер дома. Какой полный адрес нужно указать? Если улицы у адреса нет, напишите об этом.'
    return None


def reference_candidate(state, key, raw):
    """Propose a full address, never silently infer a party's residence."""
    if not RELATIVE.search(raw):
        return None
    # A labelled, fully written address is not a reference to another party.
    # Extractors keep the label in evidence; on the next turn that evidence
    # must not turn "Адрес истца: ..." into the appellant's own address.
    labelled=re.match(r'^(?:мой\s+(?:почтовый\s+)?адрес|адрес\s+(?:истца|ответчика|заявителя))\s*:\s*(.+)',raw.strip(),re.I|re.S)
    if labelled:
        from app.services.document_dialogue import normalize_address
        if not address_error(normalize_address(labelled[1])):
            return None
    fields = state.get('fields', {})
    if re.search(r'ответчика', raw, re.I):
        source = 'recipient_address'
    elif re.search(r'истца|заявителя|мой|у меня', raw, re.I):
        source = 'sender_address'
    else:
        source = 'property_address' if key == 'source_address' else 'sender_address'
    base = fields.get(source, {})
    value = base.get('value') or ''
    if source == key or base.get('status') != 'filled' or address_error(value):
        return None
    flat = re.search(r'(?:кв\.?|квартира)\s*№?\s*(\d+[\w/-]*)', raw, re.I)
    if flat:
        value = re.sub(r',?\s*(?:кв\.?|квартира)\s*№?\s*\d+[\w/-]*', '', value, flags=re.I).rstrip(' ,')
        value += ', кв. ' + flat[1]
    return {'value': value, 'reference_field': source, 'reference_value': base['value'], 'source_text': raw}


def store_reference(state, key, raw):
    candidate = reference_candidate(state, key, raw)
    if candidate:
        state['fields'][key] = {'status': 'incomplete', 'value': None, 'original': raw, 'evidence': raw,
            'address_candidate': candidate, 'error': f'Правильно понимаю полный адрес: {candidate["value"]}?'}
        return True
    return False


def confirm_reference(state, key, message):
    current = state.get('fields', {}).get(key, {})
    candidate = current.get('address_candidate')
    if not candidate or not re.fullmatch(r'\s*(?:да|верно|в[сеё] верно|правильно|подтверждаю|да[, ]+верно)[.!]?\s*', message, re.I):
        return False
    reference = state['fields'].get(candidate['reference_field'], {})
    if reference.get('value') != candidate['reference_value']:
        current.pop('address_candidate', None)
        current['error'] = 'Адрес, на который вы ссылались, изменился. Какой полный адрес нужно указать?'
        return True
    current.update(status='filled', value=candidate['value'], error=None, origin='confirmed_address_reference',
        confirmation=message, address_reference=candidate, address_components=components(candidate['value']))
    current.pop('address_candidate', None)
    state['revision'] = state.get('revision', 0) + 1
    return True
