"""Postal components and explicit reference confirmation, shared by all forms."""
import re

_OWN_ADDRESS = re.compile(r'(?:это\s+)?мой(?:\s+(?:(?:указанный(?:\s+выше)?|прежний|же)\s+)?адрес)?[.!]?', re.I)
RELATIVE = re.compile(r'в (?:том|этом) же доме|там же|тот же адрес|по тому же адресу|мой (?:же |указанный (?:выше )?)?адрес|адрес (?:истца|заявителя|ответчика)|как у меня', re.I)

# The model chooses the address and its role. Format only the isolated,
# labelled address fragment. Keep inflected street names with their original
# preposition: «по улице Ахматовой» does not imply a street called «Ахматовая».
_NUMBER = r'\d+[А-Яа-яЁёA-Za-z]?(?:[/–-]\d+[А-Яа-яЁёA-Za-z]?)?'
_NAME = r'[А-ЯЁ][\w-]*(?:\s+[А-ЯЁ][\w-]*){0,3}'
_POSTAL_PART = re.compile(r'(?<!\w)(?:'
    rf'(?P<flat>(?i:квартир[аеыу]|кв\.?)\s*№?\s*(?P<flat_number>{_NUMBER}))|'
    rf'(?P<house>(?i:(?:в\s+)?доме|дом(?:а)?|д\.)\s*№?\s*(?P<house_number>{_NUMBER}))|'
    rf'(?P<street>(?i:по улице|на улице|улица|ул\.)\s+(?P<street_name>{_NAME}))|'
    rf'(?P<locality>(?i:в\s+(?:городе\s+)?|г\.\s*|город\s+)(?P<city_name>{_NAME})))'
)
_PART_SEPARATOR = re.compile(r'\s*,?\s*(?:по\s+адресу\s*:?\s*)?', re.I)


def _locality_value(name, locative):
    if not locative:
        return 'г. ' + name
    if ' ' not in name and name.casefold().endswith(('бурге', 'граде', 'городе', 'ске')):
        return 'г. ' + name[:-1]
    # Several city names can share a case ending. Keep the supplied spelling.
    return 'в ' + name


def postal_phrase(raw):
    """Format a set of labelled components supplied in any order."""
    text = raw.strip(' .')
    if not re.search(r'\b(?:квартиры|доме|по улице|на улице)\b', text, re.I):
        return None
    text = re.sub(r'^(?:вот\s+(?:тут|здесь)\s+есть\s*:\s*)?(?:(?:я\s+)?собственни(?:ца|к)\s+)?', '', text, flags=re.I)
    parts = {}
    offset = 0
    for match in _POSTAL_PART.finditer(text):
        if not _PART_SEPARATOR.fullmatch(text[offset:match.start()]) or match.lastgroup in parts:
            return None
        kind = match.lastgroup
        if kind == 'locality':
            parts[kind] = _locality_value(match['city_name'], match[0].casefold().startswith('в '))
        elif kind == 'street':
            parts[kind] = (match[0] if re.match('по |на ', match[0], re.I) else 'ул. ' + match['street_name'])
        else:
            parts[kind] = ('д. ' if kind == 'house' else 'кв. ') + match[kind + '_number']
        offset = match.end()
    if text[offset:].strip(' ,') or not {'house', 'street'} <= parts.keys():
        return None
    return ', '.join(parts[key] for key in ('locality', 'street', 'house', 'flat') if key in parts)


def complete_address_quote(quote, source):
    """Expand a truncated model quote only within one unambiguous series of postal components."""
    if source.count(quote) != 1:
        return quote
    start = source.index(quote)
    end = start + len(quote.rstrip(' .'))
    group = []
    for part in _POSTAL_PART.finditer(source):
        if group and (not _PART_SEPARATOR.fullmatch(source[group[-1].end():part.start()])
                      or any(old.lastgroup == part.lastgroup for old in group)):
            if group[0].start() <= start and end <= group[-1].end():
                break
            group = []
        group.append(part)
    if group and group[0].start() <= start and end <= group[-1].end():
        full = source[group[0].start():group[-1].end()]
        if len(full) > len(quote) and postal_phrase(full):
            return full
    return quote


def add_missing_locality(previous, message):
    """Merge a city-only reply into a saved address without replacing the street/house."""
    from app.services.document_dialogue import has_locality
    if not previous or has_locality(previous):
        return None
    parts = components(previous)
    if not (parts['house'] or parts['street']):
        return None
    reply = re.sub(r'[\s,.;—-]+(?:написано(?:\s+же)?|уже\s+(?:писала?|указывала?)(?:\s+выше)?)\s*[.!]*$', '', message.strip(), flags=re.I)
    city = re.fullmatch(rf'(?P<prefix>(?i:в\s+(?:городе\s+)?|город\s+|г\.\s*))?(?P<name>{_NAME}|[а-яё-]+)[.!]?', reply)
    if not city:
        return None
    locality = _locality_value(city['name'].title(), (city['prefix'] or '').casefold().startswith('в '))
    return f'{locality}, {previous}'


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
    street = re.search(r'(?:^|,\s*)(?:ул\.?|улица|по улице|на улице|просп(?:ект)?\.?|пер(?:еулок)?\.?)\s+([^,]+)', value, re.I)
    house = re.search(r'(?:^|[,\s])(?:д\.|дом)\s*(\d+[\w/-]*)', value, re.I)
    flat = re.search(r'(?:кв\.?|квартира)\s*№?\s*(\d+[\w/-]*)', value, re.I)
    if not city and ',' in value:
        first = value.split(',')[0].strip()
        if re.fullmatch(r'[А-Яа-яЁё-]+(?:\s+[А-Яа-яЁё-]+)*', first) and not re.match(r'ул\b|улица\b|(?:на|по) улице\b', first, re.I):
            city = (first, re.sub(r'^в\s+', '', first, flags=re.I))
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
    own = _OWN_ADDRESS.fullmatch(raw.strip())
    if not (own or RELATIVE.search(raw)):
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
    elif own or re.search(r'истца|заявителя|мой|у меня', raw, re.I):
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
        if key == 'property_address' and _OWN_ADDRESS.fullmatch(raw.strip()):
            # The property-address question explicitly offers the claimant's
            # address. Their reply already identifies the reference.
            _accept_reference(state, key, candidate, raw)
        return True
    return False


def prepare_property_address_reference(state):
    """Ask permission to reuse a known property address as the claimant's address."""
    if state.get('scenario') != 'claim_damage_flood':
        return
    fields = state.get('fields', {})
    target = fields.get('sender_address', {})
    address = fields.get('property_address', {})
    candidate = target.get('address_candidate') or {}
    if candidate.get('reference_field') == 'property_address' and candidate.get('reference_value') != address.get('value'):
        target.pop('address_candidate')
        target.pop('error', None)
    if (address.get('status') != 'filled' or not address.get('value') or target.get('value')
            or target.get('status') in {'filled', 'not_applicable', 'unknown', 'review_required'}
            or target.get('address_candidate') or target.get('error') or target.get('declined_reference')):
        return
    value = address['value']
    fields['sender_address'] = {
        **target, 'status': 'incomplete',
        'address_candidate': {'value': value, 'reference_value': value, 'reference_field': 'property_address'},
        'error': f'Указать для связи с истцом адрес повреждённой квартиры — {value}?',
    }


def confirm_reference(state, key, message):
    current = state.get('fields', {}).get(key, {})
    if key == 'source_address' and current.get('origin') == 'source_address_conflict':
        choice = re.fullmatch(r'\s*(?:нет[, ]+)?(?:остав(?:ь|ьте)|укаж(?:и|ите))\s+(?:(?:квартир[уа]|кв\.?)\s*)?'
                              r'№?\s*(\d+[\w/-]*)[.!\s]*', message, re.I)
        if choice:
            addresses = [state['fields'].get(k, {}) for k in ('property_address', 'recipient_address')]
            matches = [item['value'] for item in addresses if item.get('status') == 'filled'
                       and components(item['value']).get('flat') == choice[1]]
            if len(matches) == 1:
                current.update(status='filled', value=matches[0], origin='confirmed_flood_source',
                               original=matches[0], evidence=message, confirmed_source=True,
                               address_components=components(matches[0]), error=None)
                current.pop('address_candidate', None)
                state['revision'] = state.get('revision', 0) + 1
                return True
    candidate = current.get('address_candidate')
    if not candidate:
        return False
    if re.fullmatch(r'\s*(?:нет|другой|адрес другой)[.!]?\s*', message, re.I):
        current.pop('address_candidate')
        current.update(declined_reference=candidate['reference_value'], error='Какой адрес указать в этом поле?')
        state['revision'] = state.get('revision', 0) + 1
        return True
    if not re.fullmatch(r'\s*(?:да|верно|в[сеё] верно|правильно|подтверждаю|да[, ]+верно|'
                        r'(?:да[, ]+)?(?:укаж(?:и|ите)\s+)?(?:тот|этот)\s+же(?:\s+адрес)?)[.!]?\s*', message, re.I):
        return False
    reference = state['fields'].get(candidate['reference_field'], {})
    if reference.get('value') != candidate['reference_value']:
        current.pop('address_candidate', None)
        current['error'] = 'Адрес, на который вы ссылались, изменился. Какой полный адрес нужно указать?'
        return True
    _accept_reference(state, key, candidate, message)
    return True


def _accept_reference(state, key, candidate, message):
    current = state['fields'][key]
    current.update(status='filled', value=candidate['value'], error=None, origin='confirmed_address_reference',
        confirmation=message, address_reference=candidate, address_components=components(candidate['value']))
    current.pop('address_candidate', None)
    state['revision'] = state.get('revision', 0) + 1
