"""Shared source-bound intake for complete forms; no routing by similarity."""
from copy import deepcopy
from datetime import date
import re
from app.services.document_form_rules import uses_form_composer


_DAMAGE_OBJECT = (
    r"квартир\w*|комнат\w*|жил\w*\s+помещен\w*|дом\w*|гараж\w*|"
    r"автомобил\w*|машин\w*|мотоцикл\w*|велосипед\w*|ноутбук\w*|телефон\w*|"
    r"планшет\w*|мебел\w*|диван\w*|техник\w*|вещ\w*"
)


def _protect_abbreviations(value):
    return re.sub(
        r"\b(г|д|кв|ул|пр|пер|стр|корп|т\.\s*д)\.",
        lambda item: item[1] + "\uFFF0",
        value,
        flags=re.I,
    )


def is_dense_damage_narrative(value):
    """Whether a reply contains several damage-case facts, not one object.

    A phrase slot such as ``property`` is rendered inside a fixed sentence.
    Saving a complete chronology there turns later facts (the estimate, a
    pre-trial notice, etc.) into one malformed paragraph.  We only activate
    this guard for clearly dense answers; a normal description of a damaged
    item remains a normal answer to the current field.
    """
    source = str(value or "").strip()
    markers = re.findall(
        r"\b(?:стоимост\w*|оценк\w*|смет\w*|претензи\w*|ответа?\s+не\s+получ|"
        r"почтов\w*\s+расход|возмест\w*|акт\w*|собственник\w*|выписк\w*|"
        r"управляющ\w*\s+компан\w*|прорыв\w*|залив\w*)\b",
        source,
        re.I,
    )
    sentences = len(re.findall(r"[.!?](?:\s|$)", source))
    return len(source) >= 180 and sentences >= 2 and len(markers) >= 2


def damage_property_phrase(value):
    """Return an existing, compact object phrase from a factual chronology.

    The result is always a literal fragment of ``value``.  It intentionally
    does not decide who is liable or how much must be awarded: those facts
    have their own fields and paragraphs in a damage claim.
    """
    source = re.sub(r"\s+", " ", str(value or "")).strip()
    if not source:
        return None
    # A real-estate address is the most common form of a property story.  The
    # look-ahead prevents facts about the event from being glued to the object
    # in cases such as "квартира по адресу ... была затоплена".
    protected = _protect_abbreviations(source)
    apartment = re.search(
        r"(?P<property>(?:(?:моя|принадлежащая\s+мне|собственная)\s+)?"
        r"(?:квартир\w*|жил\w*\s+помещен\w*)\s+по\s+адресу\s*:\s*"
        r".+?)(?=(?:\s+(?:был[аио]?\s+)?(?:затоплен\w*|поврежд\w*)|"
        r"\s+(?:произош[её]л|возник)\w*|[.!?]|$))",
        protected,
        re.I,
    )
    if apartment:
        return apartment["property"].replace("\uFFF0", ".").strip(" ,.;")
    # For movable property use the compact noun phrase before the sentence
    # changes to the accident or the calculation.  This handles, for example,
    # "мой ноутбук серийный номер ... был повреждён" without importing the
    # surrounding narrative into the property slot.
    movable = re.search(
        r"(?P<property>(?:(?:мой|моя|мо[её]|принадлежащ(?:ий|ая|ее)\s+мне)\s+)?"
        r"(?:" + _DAMAGE_OBJECT + r")"
        r"(?:\s*(?:№|N)\s*[A-Za-zА-Яа-яЁё0-9-]+|\s*,\s*(?:марки|модели|серийный\s+номер)\s+[^,.;]+)?)(?="
        r"(?:\s+(?:был[аио]?\s+)?(?:затоплен\w*|поврежд\w*|разбит\w*|залит\w*|"
        r"уничтожен\w*|похищен\w*)|\s+(?:из-за|вследствие)|[,.;]|$)",
        protected,
        re.I,
    )
    return movable["property"].replace("\uFFF0", ".").strip(" ,.;") if movable else None


def _narrative_sentence(value, pattern):
    """Extract a single literal sentence containing a known factual marker."""
    source = re.sub(r"\s+", " ", str(value or "")).strip()
    if not source:
        return None
    # ``г. Екатеринбург`` is an abbreviation, therefore a simple split on
    # every full stop is unsafe.  Protect the ordinary address abbreviations
    # first, then select one complete sentence only.
    protected = _protect_abbreviations(source)
    for sentence in re.split(r"(?<=[.!?])\s+(?=[А-ЯЁ])", protected):
        restored = sentence.replace("\uFFF0", ".").strip(" .;,")
        if re.search(pattern, restored, re.I):
            return restored or None
    return None


def _pretrial_narrative_sentence(value):
    """Find the actual pre-trial action, not a cost of posting it."""
    source = re.sub(r"\s+", " ", str(value or "")).strip()
    if not source:
        return None
    protected = _protect_abbreviations(source)
    for sentence in re.split(r"(?<=[.!?])\s+(?=[А-ЯЁ])", protected):
        restored = sentence.replace("\uFFF0", ".").strip(" .;,")
        if re.search(
            r"(?:\bпретензи\w*\b.{0,90}\bнаправ(?:ил|ила|лено|лял)\w*|"
            r"\bнаправ(?:ил|ила|лено|лял)\w*.{0,90}\bпретензи\w*\b)",
            restored,
            re.I,
        ):
            return restored or None
    return None


def _collect_damage_property_narrative(state, text, current, put):
    """Split a rich property-damage account into its matching form slots.

    This is a deterministic safety net for the form family when the remote
    contextual extractor is unavailable or elects not to split a message.
    Each stored value remains a literal quote from the user's answer.  It is
    deliberately conservative: absent details stay for the next question.
    """
    if state.get("scenario") != "claim_damage_property" or current != "property":
        return set()
    if not is_dense_damage_narrative(text):
        return set()
    property_value = damage_property_phrase(text)
    if not property_value:
        return set()
    before = set()

    def save(key, value):
        if not value:
            return
        previous = state.get("fields", {}).get(key, {})
        put(key, value, value)
        if state.get("fields", {}).get(key, {}).get("status") == "filled" and previous.get("value") != state["fields"][key].get("value"):
            before.add(key)

    save("property", property_value)
    ownership = _narrative_sentence(text, r"\b(?:собственник\w*|собственност\w*|нанимател\w*|выписк\w*\s+ЕГРН)\b")
    save("property_right", ownership)
    event = _narrative_sentence(text, r"\b(?:затоплен\w*|залив\w*|прорыв\w*|поврежд\w*)\b")
    if event:
        # The property has already been recorded in its own compact field.
        # Do not repeat a possibly long address in the event sentence.
        event = re.sub(r"\s+по\s+адресу\s*:\s*.*$", "", event, flags=re.I).strip(" ,.;")
    save("event", event)
    responsibility = _narrative_sentence(
        text,
        r"\b(?:управляющ\w*\s+компан\w*|ответчик\w*|составил[аио]?\s+акт|"
        r"не\s+возмест\w*)\b",
    )
    save("responsibility", responsibility)
    # Keep the whole contiguous cost segment together.  It belongs to the
    # template's separate restoration paragraph, rather than to the damaged
    # object paragraph.
    costs = _narrative_sentence(
        text,
        r"\b(?:стоимост\w*|расход\w*\s+на\s+восстановлен\w*|ремонт\w*\s+составля\w*)\b",
    )
    # An adjacent cost sentence (usually "За оценку ...") is part of the
    # same restoration account.  It never absorbs the later actual notice.
    following_cost = _narrative_sentence(
        text,
        r"\b(?:за\s+оценк\w*|расход\w*\s+на\s+(?:оценк\w*|экспертиз\w*)|"
        r"почтов\w*\s+расход\w*)\b",
    )
    if costs and following_cost and following_cost not in costs:
        costs = costs.rstrip(" .") + ". " + following_cost
    save("restoration", costs)
    pretrial = _pretrial_narrative_sentence(text)
    save("pretrial", pretrial)
    # A reference to an act is useful evidence but does not justify putting an
    # entire liability sentence into the evidence list.
    act = re.search(r"\bакт(?:\s+о\s+[^,.;!?]+)?", text, re.I)
    if act:
        save("evidence", act[0].strip(" .;,"))
    amount = re.search(
        r"(?:стоимост\w*\s+(?:восстановительн\w*\s+)?(?:ремонт\w*)?[^.!?]{0,90}?)"
        r"(?P<amount>\d+(?:[ \u00a0]\d{3})*(?:[.,]\d{1,2})?\s*(?:руб(?:лей|ля|ль|\.)?|₽))",
        text,
        re.I,
    )
    if amount:
        save("amount", amount["amount"])
    return before


def _stored_date(field):
    """Read an explicitly stored document date without assigning a missing year."""
    if not isinstance(field, dict) or field.get('status') != 'filled':
        return None
    value = str(field.get('value') or '').strip()
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    from app.services.document_interest_395 import parse_dates
    dates = parse_dates(value)
    return dates[0] if dates else None


def _validate_pretension_response_deadline(state):
    """Do not render a voluntary deadline that expired before the document date."""
    if not str(state.get('scenario') or '').startswith('pretense_'):
        return
    fields = state.get('fields') or {}
    response = fields.get('response_term')
    document_date = _stored_date(fields.get('date'))
    deadline = _stored_date(response)
    if not response or not document_date or not deadline or deadline > document_date:
        return
    response.update(
        status='incomplete',
        error=(
            'Указанный срок уже истёк к дате претензии. Укажите будущую дату либо срок, '
            'например: в течение 10 календарных дней со дня получения претензии.'
        ),
        origin='response_deadline_validation',
    )


def prepare_form_intake(state):
    # A reference to an appraiser, estimate or report is useful evidence but
    # is not itself a numerical calculation.  This shared repair keeps legacy
    # chats from exporting a vague sentence such as "calculations were made by
    # an appraiser" in place of the actual arithmetic.
    from app.services.document_calculation_ledger import sanitize_calculation
    sanitize_calculation(state)
    _validate_pretension_response_deadline(state)
    # Formula planning is coordinated by ``document_formula_intake`` after a
    # factual answer or an explicit calculation request.  Do not build a plan
    # merely because an ordinary form happens to contain one amount: doing so
    # fills a calculation slot before the interview reaches it and then causes
    # later identity/contract answers to be skipped.
    if not uses_form_composer(state):return
    from app.services.document_contract_facts import repair_contract_facts
    repair_contract_facts(state)
    from app.services.document_explicit_facts import reuse_personal_signer
    reuse_personal_signer(state)
    from app.services.document_consumer_facts import prepare_consumer_facts
    prepare_consumer_facts(state)
    if state['scenario']=='contract_employment':
        role=(state['fields'].get('position',{}).get('value') or '').lower()
        context=' '.join([state.get('request',''),state['fields'].get('sender',{}).get('value') or '']).lower()
        # This is a classification of the *job*, not a question for the user to
        # answer.  In particular, a cashier does not become a pedagogical
        # worker merely because an employment template also supports teachers.
        # Keep the positive rule deliberately narrow: a pedagogical title plus
        # an educational setting.  The negative rule covers ordinary roles and
        # clear non-educational workplaces, so those users never see the
        # pedagogical branch at all.
        pedagogical_role=bool(re.search(r'учител|воспитател|педагог|преподавател',role) and not re.search(r'помощник|младш',role))
        ordinary_role=bool(re.search(r'кассир|продав|товаровед|мерчендайзер|кладовщик|грузчик|охранник|сторож|уборщ|дворник|повар|официант|барист|водител|курьер|бухгалтер|юрист|экономист|менеджер|администратор|оператор|секретар',role))
        non_education_context=bool(re.search(r'магазин|супермаркет|торгов|кафе|ресторан|банк|салон|склад|производств|завод|фабрик|офис',context))
        if pedagogical_role and re.search(r'детск\w* сад|школ|образоват',context):
            state['fields']['is_pedagogue']={'status':'filled','value':'да','origin':'verified_role_classification','evidence':role,'sources':['https://www.consultant.ru/document/cons_doc_LAW_34683/']}
        elif ordinary_role or (role and non_education_context and not pedagogical_role) or re.search(r'помощник воспитател|младш\w* воспитател',role):
            state['fields']['is_pedagogue']={'status':'filled','value':'нет','origin':'verified_role_classification','evidence':role}
        is_pedagogue=state['fields'].get('is_pedagogue',{}).get('value')
        vacation=state['fields'].get('vacation',{})
        generic_vacation=bool(re.search(r'(?:по|с)\s+закону|как положено|стандартн',vacation.get('value') or '',re.I))
        if is_pedagogue=='нет' and (vacation.get('status') not in {'filled','unknown'} or generic_vacation):
            # The ordinary statutory minimum is a legal rule, not a fact the
            # employee has to know or formulate.
            state['fields']['vacation']={'status':'filled','value':'28 календарных дней','origin':'verified_rule','inputs':['is_pedagogue'],
                'sources':['https://www.consultant.ru/document/cons_doc_LAW_34683/']}
        worker=state['fields'].get('recipient',{})
        if worker.get('status')=='filled' and worker.get('value') and state['fields'].get('counterparty_signature',{}).get('status')!='filled':
            # The employee normally signs their own employment contract.  Do
            # not ask the nonsensical question "which signature should the
            # cashier put" after their full name is already known.
            state['fields']['counterparty_signature']={'status':'filled','value':worker['value'],'origin':'worker_personal_signature','evidence':worker.get('evidence') or worker['value']}
        for key in ('teaching_load','contacts'):
            item=state['fields'].get(key,{})
            if re.fullmatch(r'нет|никакие|отсутствуют',item.get('value') or '',re.I):item.update(status='not_applicable',value=None)
        setting=state['fields'].get('leave_context',{}).get('value') or ''
        if re.search(r'воспитател',role) and not re.search(r'помощник|младш',role) and re.search(r'дошколь|детск\w* сад',context+' '+setting):
            special=re.search(r'(?:работ\w*|групп\w*|воспитанник\w*|дет\w*)[^.!?]{0,35}(?:с ОВЗ|с ограниченными возможностями)',setting,re.I)
            ordinary=re.search(r'без ОВЗ|нет (?:детей|групп) с ОВЗ|общеразвивающ|обычн\w* групп',setting,re.I)
            vacation=state['fields'].get('vacation',{})
            ambiguous=bool(re.search(r'\b\d+\s*(?:или|либо)\s*\d+\b',vacation.get('value') or '',re.I))
            if (special or ordinary) and (vacation.get('status')!='filled' or vacation.get('origin')=='verified_rule' or ambiguous):
                days=56 if special and not re.search(r'без ОВЗ|нет (?:детей|групп) с ОВЗ',setting,re.I) else 42
                state['fields']['vacation']={'status':'filled','value':f'{days} календарных дней','origin':'verified_rule','inputs':['position','leave_context'],
                    'sources':['https://www.consultant.ru/document/cons_doc_LAW_473897/da2e5f8e6a3a82c536265580c834f3108d21856d/']}
            elif not (special or ordinary) and vacation.get('status') not in {'filled','unknown'}:
                state['fields']['vacation']={'status':'review_required','value':None,'origin':'leave_category_review','error':None}
        vacation=state['fields'].get('vacation',{})
        ambiguous=bool(re.search(r'\b\d+\s*(?:или|либо)\s*\d+\b',vacation.get('value') or '',re.I))
        if re.search(r'^учитель(?:\s|$)',role) and re.search(r'общеобразовательн\w* школ|общеобразовательн\w* организац',setting,re.I) and (vacation.get('status')!='filled' or ambiguous):
            state['fields']['vacation']={'status':'filled','value':'56 календарных дней','origin':'verified_rule','inputs':['position','leave_context'],
                'sources':['https://www.consultant.ru/document/cons_doc_LAW_473897/c86e302722b2664b97e84274ea649013a3aff6ec/']}
        elif ambiguous:
            vacation.update(status='review_required',value=None,original=vacation.get('original') or vacation.get('value'),origin='leave_category_review',error=None)
    delivery=state['fields'].get('delivery_status',{})
    source=delivery.get('evidence') or delivery.get('original') or ''
    if delivery.get('status')=='unknown' and re.match(r'^\s*нет\b',source,re.I) and re.search(r'не знаю.{0,15}где',source,re.I):
        delivery.update(status='filled',value='Товар не доставлен. Сведения о его местонахождении мне неизвестны.',original=source,origin='source_bound_recovery')
    if state['scenario'] in {'order_alimony','claim_alimony_share'}:
        state['fields'].setdefault('payment',{'status':'not_applicable','value':None,'origin':'post_judgment_preference'})
    # Complete a confirmed principal-only calculation from separate typed
    # facts. An advance alone does not imply that no other payments exist.
    calculation=state['fields'].get('calculation',{})
    if calculation.get('status')=='filled' and re.search(r'дополнительные начисления не заявляются|^(?:только )?основной долг(?: только)?[.! ]*$',calculation.get('value') or '',re.I):
        from decimal import Decimal
        from app.services.document_case_composition import _money
        amount=state['fields'].get('amount',{})
        if amount.get('status')=='filled':
            principal=Decimal(amount['value']);ledger=state.get('obligation_facts',{})
            total=ledger.get('contract_price',{}).get('value');advance=ledger.get('advance',{}).get('value')
            prefix=''
            if total and advance and Decimal(total)-Decimal(advance)==principal:
                prefix='Стоимость услуг составляет '+_money(total)+'. Получен аванс '+_money(advance)+'. Остаток: '+_money(total)+' − '+_money(advance)+' = '+_money(principal)+'. '
            calculation.update(value=prefix+'Основной долг составляет '+_money(principal)+'. Дополнительные начисления не заявляются.',origin='source_bound_arithmetic')
            # A clear statement that only the principal is claimed is enough
            # to create a one-line, source-bound ledger.  This is not inferred
            # from the amount question itself: it appears only after the
            # person has expressly excluded other monetary components.  The
            # shared formula plan can then calculate the claim price and a
            # verified duty tariff for every property-claim template.
            existing_ledger=state.get('calculation_ledger')
            if not isinstance(existing_ledger,dict) or existing_ledger.get('status') != 'confirmed':
                state['calculation_ledger']={
                    'version':1,
                    'items':[{
                        'id':'field:amount','kind':'principal','label':'Основная сумма требования',
                        'value':format(principal.quantize(Decimal('0.01')),'f'),
                        'evidence':str(amount.get('original') or amount.get('evidence') or amount['value']),
                    }],
                    'total':format(principal.quantize(Decimal('0.01')),'f'),
                    'calculation':calculation['value'],
                    'status':'confirmed','origin':'principal_only_confirmation',
                    'evidence':str(calculation.get('original') or calculation.get('evidence') or calculation['value']),
                }


def collect_form_turn(state,text,current):
    if not uses_form_composer(state):return set()
    from app.services.document_scenarios import SCENARIOS
    from app.services.document_case_facts import set_field,collect_case_turn,normalize_contacts,MONTH,MONEY,DATE,NEGATIVE
    specs={f.key:f for f in SCENARIOS[state['scenario']].fields};consumed=set()
    def put(key,value,evidence,status='filled'):
        existing=state['fields'].get(key,{})
        # An answer to another question cannot silently overwrite an earlier
        # sum or party. Explicit corrections have a separate workflow.
        if key!=current and existing.get('status')=='filled':return
        if key in specs and set_field(state,key,value,evidence,status):
            consumed.add(key);state['fields'][key]['source_field']=current
    if state['scenario']=='appeal_civil' and state['fields'].get('grounds',{}).get('status')!='filled':
        for source in dict.fromkeys([state.get('request',''),text]):
            sentence=_narrative_sentence(source,r'суд\w*.{0,60}взыск\w*.{0,50}(?:долг|задолжен)')
            if sentence and re.search(r'хотя|не уч[её]л|без уч[её]та',sentence,re.I) and re.search(r'вернул|погасил|оплатил|плат[её]ж',sentence,re.I):
                put('grounds',sentence,sentence)
    from app.services.document_consumer_facts import collect_consumer_facts
    collect_consumer_facts(state, text, put)
    from app.services.document_contract_facts import collect_contract_turn
    contract_fields = collect_contract_turn(state, text, current)
    consumed.update(contract_fields)
    # A dense description of a damage event often already contains the
    # object, the event, a repair estimate and a pre-trial notice.  Split it
    # before the generic single-field fallback can put the entire chronology
    # into the short ``property`` phrase slot.
    if _collect_damage_property_narrative(state,text,current,put):
        return consumed
    # A reference is a typed date and number, even if entered without the word
    # «договор». Never require the user to rewrite it as a legal sentence.
    if current=='agreement':
        ref=re.fullmatch(r'\s*(\d{1,2}[./]\d{1,2}[./]\d{2,4})\s*(?:номер|№)\s*([\w/-]+)[. ]*',text,re.I)
        if ref:
            from app.services.document_workflow import normalize_field
            from types import SimpleNamespace
            day,error=normalize_field(SimpleNamespace(kind='date',key='agreement_date'),ref[1])
            if not error:
                from datetime import date
                put(current,specs[current].label+' № '+ref[2]+' от '+date.fromisoformat(day).strftime('%d.%m.%Y')+'.',text)
                return consumed
    if current=='calculation' and re.fullmatch(r'\s*(?:только )?основной долг(?: только)?[.! ]*',text,re.I):
        amount=state['fields'].get('amount',{})
        if amount.get('status')=='filled':
            from app.services.document_case_composition import _money
            put(current,'Основной долг составляет '+_money(amount['value'])+'. Дополнительные начисления не заявляются.',text)
            return consumed
    if current in specs and specs[current].kind=='date':
        dates=re.findall(DATE,text,re.I)
        if len(dates)==1:put(current,dates[0],text)
    if current in specs and specs[current].kind=='money':
        amounts=re.findall(MONEY,text,re.I)
        if len(amounts)==1:put(current,amounts[0],text)
    if current=='signature' and re.fullmatch(r'(?:я|сам|сама|лично|подпишу (?:сам|сама|лично)|я лично|мо[йёя])[.! ]*',text,re.I):
        sender=state['fields'].get('sender',{})
        if sender.get('status')=='filled':put('signature',sender['value'],text)
        return consumed
    if current=='delivery_status' and re.match(r'^\s*нет\b',text,re.I) and re.search(r'не знаю.{0,15}где',text,re.I):
        put(current,'Товар не доставлен. Сведения о его местонахождении мне неизвестны.',text)
        return consumed
    if state['scenario']=='contract_employment':
        source=' '.join([state.get('request',''),text if current in {None,'position'} else ''])
        # Recognise an explicitly named occupation in the initial request. It
        # removes needless repetitions such as asking a user who requested a
        # cashier contract what the cashier's position is.  These are facts
        # stated in the request, not guessed job duties.
        known_roles=(
            ('учител', 'учитель'), ('воспитател', 'воспитатель'),
            ('кассир', 'кассир'), ('продав', 'продавец'),
            ('бухгалтер', 'бухгалтер'), ('водител', 'водитель'),
            ('менеджер', 'менеджер'), ('юрист', 'юрист'), ('повар', 'повар'),
        )
        explicit_role=next((canonical for stem,canonical in known_roles if re.search(r'\b'+stem+r'[а-яё-]*\b',source,re.I)),None)
        if explicit_role and state['fields'].get('position',{}).get('status')!='filled':
            put('position',explicit_role,source)
        if explicit_role=='учитель' and state['fields'].get('is_pedagogue',{}).get('status')!='filled':
            put('is_pedagogue','да',source)
        if current=='term_type' and re.search(r'\bна\s+\d+\s*(?:дн|недел|месяц|год)',text,re.I):
            put('term_type','срочный',text)
            return consumed
    if state['scenario']=='motion_attach' and current is None:
        source=state.get('request','')+' '+text
        subject=re.search(r'(?:дело|спор)\s+о(?:б)?\s+([^.!?]+)',source,re.I)
        document=re.search(r'(?:получил[аи]?|имеется|есть)\s+(.+?)(?:\s+и\s+(?:хочу|прошу)|[.!?]|$)',source,re.I)
        if subject:put('case_subject',subject[1].strip(),subject[0])
        if document:put('documents',document[1].strip(),document[0])
    if state['scenario'].startswith('pretense_consumer_') and current=='facts' and re.search(r'обращал|писал',text,re.I) and re.search(r'не ответил|ответа (?:нет|не)|без ответа',text,re.I):
        put('seller_response',text,text)
    if state['scenario']=='contract_employment' and current=='leave_context':
        put(current,text,text)
        return consumed
    if state['scenario']=='contract_employment' and current=='counterparty_signature' and re.fullmatch(r'работник(?: лично)?|сам работник|сама работница',text,re.I):
        worker=state['fields'].get('recipient',{})
        if worker.get('status')=='filled':put(current,worker['value'],text)
        return consumed
    if current=='consumer_status' and re.fullmatch(r'\s*да[.! ]*',text,re.I):
        put(current,'для личных нужд',text)
        return consumed
    if current=='counterparty_signature' and re.fullmatch(r'(?:он|она|вторая сторона|сам наниматель)[.! ]*',text,re.I):
        other=state['fields'].get('recipient',{})
        if other.get('status')=='filled':put(current,other['value'],text)
        return consumed
    from app.services.document_case_facts import absence_reply
    if current in {'sender_details','recipient_details','party_details'} and absence_reply(text):
        # An absent identifier is not a literal requisite.  The template omits
        # unknown detail blocks while retaining the user's original answer for
        # possible later correction.
        put(current,None,text,'unknown')
        return consumed
    if current=='other_participants' and absence_reply(text):
        put(current,None,text,'not_applicable')
        return consumed
    optional_absences={'facts','previous_contact','seller_response','pretrial','additional_claims','other_participants',
        'other_dependants','attachments','residents','late_reasons','term_reasons','early_reason','existing_support','assistance','previous_writ','claims','compensations','probation','additional_terms','teaching_load'}
    if current in optional_absences and NEGATIVE.fullmatch(text.strip()):
        # Retain a literal negative where it has legal meaning; omit only an
        # explicitly absent optional section, not a mandatory factual answer.
        if current in {'assistance','existing_support','previous_writ','claims'}:put(current,text,text)
        else:put(current,None,text,'not_applicable')
        return consumed
    if current=='compensations' and re.search(r'(?:всё|все)\s+по\s+закону|как положено по закону',text,re.I):
        put(current,None,text,'not_applicable')
        return consumed
    if current=='contacts':
        contacts=normalize_contacts(text)
        if contacts:put(current,contacts,text)
        elif re.search(r'\b(?:ул\.|улица|город|г\.)',text,re.I) or re.search(r'[А-Яа-яЁё-]+\s*,\s*[А-Яа-яЁё-]+\s+\d',text):put(current,None,text,'not_applicable')
        return consumed
    # The same explicit child/parentage/living utterance can answer several
    # questions in each initial-alimony form; its type never changes.
    if state['scenario'] in {'order_alimony','claim_alimony_share'}:
        bridge=deepcopy(state);bridge['scenario']='claim_alimony_fixed'
        extracted=collect_case_turn(bridge,text,current)
        for key in extracted & set(specs):state['fields'][key]=bridge['fields'][key];consumed.add(key)
        if extracted:state['case_facts']=bridge.get('case_facts',{})
    # Explicit labels are the safest general multi-answer interface. They are
    # not required for a normal answer to the current question.
    aliases={name:[spec.label] for name,spec in specs.items()}
    if 'amount' in specs:
        debt=bool(re.search(r'задолжен|долг|невыплачен|ущерб',specs['amount'].label,re.I))
        aliases['amount']+=['основной долг','задолженность'] if debt else ['сумма','цена','стоимость']
    if 'payment' in specs:aliases['payment']+=['порядок расчётов','порядок расчетов','способ оплаты']
    if 'sender' in specs:aliases['sender']+=['ФИО '+specs['sender'].label]
    if 'recipient' in specs:aliases['recipient']+=['ФИО '+specs['recipient'].label]
    if state['scenario'] in {'contract_services','contract_work'}:
        aliases['recipient']+=['исполнитель','подрядчик']
    if 'sender_address' in specs:aliases['sender_address']+=['адрес '+specs['sender'].label]
    if 'recipient_address' in specs:aliases['recipient_address']+=['адрес '+specs['recipient'].label]
    # "Заказчик — ФИО. Адрес: ..." answers both identity and address.
    # A bare address belongs to the active party only when that party is
    # explicitly named and no second party is named in the same message.
    if current in {'sender','recipient'} and current+'_address' in specs:
        other='recipient' if current=='sender' else 'sender'
        own_label=re.escape(specs[current].label)
        other_label=re.escape(specs[other].label)
        if re.search(r'(?:^|[.;]\s*)'+own_label+r'\s*[:—-]',text,re.I) and not re.search(r'(?:^|[.;]\s*)'+other_label+r'\s*[:—-]',text,re.I):
            aliases[current+'_address']+=['адрес']
    if 'party_details' in specs:aliases['party_details']+=['дополнительные реквизиты сторон']
    patterns=[(name,alias) for name,values in aliases.items() for alias in values if len(alias)>2]
    matches=[]
    if 'party_details' in specs:
        for match in re.finditer(r'(?:^|(?<=\.)\s+)Дополнительные реквизиты сторон\s+(?=неизвестны\b)',text,re.I):
            matches.append((match.start(),match.end(),'party_details'))
    if state['scenario']=='contract_employment':
        # Role labels can name any occupation supplied for this employee;
        # never hard-code school/teacher names into a general contract.
        position=state['fields'].get('position',{}).get('value') or ''
        noun=re.match(r'[А-Яа-яЁё-]+',position)
        if noun and len(noun[0])>=5:
            stem=noun[0].rstrip('ьйая')
            pattern=r'(?:^|[;\n]|(?<=\.)\s+)\s*адрес\s+'+re.escape(stem)+r'[а-яё-]*\s*[:—]\s*'
            for match in re.finditer(pattern,text,re.I):matches.append((match.start(),match.end(),'recipient_address'))
        pattern=r'(?:^|[;\n]|(?<=\.)\s+)\s*(?:руководитель|директор|заведующ[а-яё]*)\b[^:;\n]{0,70}:\s*'
        for match in re.finditer(pattern,text,re.I):matches.append((match.start(),match.end(),'sender_details'))
    for name,alias in patterns:
        pattern=r'(?:^|[;,\n]|(?<=\.)\s+)\s*'+re.escape(alias)+r'\s*[:—–-]\s*'
        for match in re.finditer(pattern,text,re.I):matches.append((match.start(),match.end(),name))
    matches.sort()
    for i,(start,end,name) in enumerate(matches):
        stop=matches[i+1][0] if i+1<len(matches) else len(text)
        value=text[end:stop].strip(' ;\n')
        if specs[name].kind in {'money','date'}:
            scalar=re.match(MONEY if specs[name].kind=='money' else DATE,value,re.I)
            if scalar:
                value=scalar[0]
                stop=end+scalar.end()
        if name in {'sender','recipient','signature','counterparty_signature'}:
            from app.services.document_explicit_facts import NAME
            person=re.match(r'('+NAME+r')(?=[.,;\n]|$)',value)
            if person:
                value=person[1]
                stop=end+person.end()
            else:
                from app.services.document_contract_facts import _clauses
                value=(_clauses(value) or [value])[0].rstrip(' .')
        if value and name not in consumed:
            quote=text[start:stop].strip()
            if name=='sender_details' and state['scenario']=='contract_employment':
                # Keep the representative's role as well as their name.
                value=quote
            put(name,value,quote)
    from app.services.document_obligation_facts import collect_obligation_turn
    consumed.update(collect_obligation_turn(state,text,current,put))
    from app.services.document_rental_facts import collect_rental_turn
    consumed.update(collect_rental_turn(state,text,current,put))
    if state['scenario'] in {'claim_labor_salary','pretense_labor_settlement'} and current in {'employment','wages','debt_period','amount'}:
        debt=bool(re.search(r'не (?:выплат|перечисл)|невыплачен|задолжен|долг',text,re.I))
        if debt:
            amounts=re.findall(MONEY,text,re.I)
            period=re.search(r'за\s+('+MONTH+r'(?:\s+\d{4}(?:\s+года)?)?)',text,re.I)
            if len(amounts)==1:put('amount',amounts[0],amounts[0])
            if period:put('debt_period',period[1],period[0])
            if current=='wages' and (period or amounts):put('wages',None,text,'not_applicable')
    return consumed
