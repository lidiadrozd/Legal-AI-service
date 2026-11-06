"""Unambiguous narrative facts and controls, independent of the next question."""
import re
from datetime import datetime, timedelta, timezone

NAME=r'[А-ЯЁ][а-яё-]+(?:\s+[А-ЯЁ][а-яё-]+){2}'


def nominative_name(value):
    """Conservative dative -> nominative for recognisable Russian full names.

    Do not guess unfamiliar first names or change an ambiguous surname.
    Keep the literal input in field evidence.
    """
    parts=value.strip(' .').split()
    first_names={'Ивану':'Иван','Петру':'Петр','Пётру':'Пётр','Андрею':'Андрей','Сергею':'Сергей',
                 'Алексею':'Алексей','Дмитрию':'Дмитрий','Михаилу':'Михаил','Николаю':'Николай','Павлу':'Павел'}
    if len(parts)==3 and parts[1] in first_names and re.search(r'(?:овичу|евичу)$',parts[2]) and re.search(r'(?:ову|еву|ину)$',parts[0]):
        return ' '.join([parts[0][:-1],first_names[parts[1]],parts[2][:-1]])
    return value


def document_today(state):
    # Dates supplied by the client take precedence over the local service day.
    return state.get('turn_date') or datetime.now(timezone(timedelta(hours=5))).date().isoformat()


def safe_payment_value(value):
    if re.search(r'срок действия|\b(?:cvv|cvc|пин)\b',value,re.I):
        return 'Банковским переводом; реквизиты будут сообщены отдельно.'
    return value


def collect_explicit_facts(state,text,current=None):
    from app.services.document_scenarios import SCENARIOS
    from app.services.document_case_facts import set_field, DATE, MONEY
    from app.services.document_dialogue import conversational_value
    specs={f.key:f for f in SCENARIOS[state['scenario']].fields};consumed=set()
    from app.services.document_loan_facts import collect_loan_facts
    consumed.update(collect_loan_facts(state, text, current))
    def put(key,value,evidence):
        if key not in specs or not value or conversational_value(value):return
        if key in consumed:return
        if key!=current and state['fields'].get(key,{}).get('status')=='filled':return
        if set_field(state,key,value,evidence):consumed.add(key)
    author=re.search(r'\b(?:[Яя]\s*[—–,:-]?\s+|[Мм]еня зовут\s+)('+NAME+r')',text)
    if author and author[1] not in (state['fields'].get('sender',{}).get('value') or ''):put('sender',author[1],author[0])
    if state['scenario'].startswith('motion_'):
        from app.services.document_source_quotes import source_sentences
        own_role=re.search(r'\b(?:Я\s*[—–,:-]?\s+)('+NAME+r')\s*,\s*(истец|ответчик)\b',text)
        if own_role:
            # The role is part of the court-document identity, not a separate
            # guessed fact. The generic name collector above may have run first.
            set_field(state,'sender',own_role[1]+', '+own_role[2],own_role[0]);consumed.add('sender')
            other='Истец' if own_role[2]=='ответчик' else 'Ответчик'
            for sentence in source_sentences(text):
                party=re.match(other+r'\s*[—–:-]\s*(.+)',sentence,re.I)
                if party:put('recipient',party[1].rstrip(' .')+', '+other.lower(),sentence)
        number=re.search(r'дел[аоу]?\s*№\s*([\w/-]+)',text,re.I)
        if number:put('case_number',number[1],number[0])
        for sentence in source_sentences(text):
            court=re.match(r'Дело рассматривает\s+(.+\bсуд\b.*)',sentence,re.I)
            if court:put('court',court[1].rstrip(' .'),sentence)
    if current in specs and specs[current].kind=='date' and text.strip(' .!?').casefold()=='сегодня':
        put(current,document_today(state),text)
    contact=re.search(r'\bКонтакт(?:ы)?\s*:\s*([^\s;,]+@[^\s;,]+)',text,re.I)
    if contact:put('contacts',contact[1].rstrip('.'),contact[0])
    # A detailed opening message often gives the document date together with
    # the case facts. Capture the explicitly labelled date immediately; do not
    # confuse it with dates of the contract, payments, or events.
    if 'date' in specs and state['fields'].get('date',{}).get('status') != 'filled':
        labelled=re.search(r'(?:дата\s+(?:претензии|жалобы|документа|составления)|дата)\s*[—:-]\s*('+DATE+r')',text,re.I)
        if labelled:put('date',labelled[1],labelled[0])
    agreement=re.search(r'договор(?:у|а)?\s+(?:оказания\s+услуг|подряда|найма|займа)\s*№\s*[\w/-]+(?:\s+от\s+'+DATE+r')?',text,re.I)
    if agreement:put('agreement',re.sub(r'^договор[ау]\b','Договор',agreement[0],flags=re.I),agreement[0])
    response=re.search(r'Срок\s+(?:исполнения\s+требования|ответа)\s*[—–:-]?\s*(до\s+'+DATE+r')',text,re.I)
    if response:put('response_term',response[1],response[0])
    if state['scenario']=='contract_housing':
        duration=re.search(r'(?:сдать|снять|нанять)\s+квартиру\s+на\s+(\d+\s+(?:месяц(?:а|ев)?|год(?:а)?|лет))\b',text,re.I)
        if duration:put('term',duration[1],duration[0])
    if state['scenario'] not in {'pretense_debt_loan','claim_debt_loan'}:return consumed
    for clause in re.split(r'(?<=[.!?])\s+(?=[А-ЯЁ])',text):
        clause=re.sub(r'^Я,\s*'+NAME+r',\s*','',clause)
        transfer=re.search(r'(?:'+DATE+r')\s+(?:я\s+)?передал[аи]?\s+('+NAME+r')\s+('+MONEY+r')\s+(банковским переводом|наличными|на карту)',clause,re.I)
        if not transfer:
            transfer=re.search(r'\b(?:дала|дал|передала|передал)\s+('+NAME+r')\s+('+MONEY+r')\s+(банковским переводом|наличными|на карту)(?:\s+'+DATE+r')?',clause)
        if transfer:
            put('recipient',transfer[1],transfer[0])
            put('transfer',transfer[0],transfer[0])
            if re.search(r'ничего не возвращено|не возвращал|платежей не было',text,re.I):put('amount',transfer[2],transfer[0])
        agreement=re.search(r'(?:письменный\s+)?договор(?:у|а)?\s+займа\s*№\s*[\w/-]+',clause,re.I)
        if agreement:put('agreement',re.sub(r'^договор[ау]\b','договор',agreement[0],flags=re.I),agreement[0])
        due=re.search(r'(?:вернуть|возврат\w*).{0,65}?(?:не позднее|до)\s+('+DATE+r')',clause,re.I)
        if due:put('due_date',due[1],due[0])
        if re.fullmatch(r'Ничего не возвращено[. ]*',clause,re.I):
            put('payments','Платежи в счёт возврата займа не поступали.',clause)
            put('facts','Заемные денежные средства не возвращены.',clause)
    if re.search(r'включи.{0,45}основной долг и неустойку|вернуть долг с неустойкой',text,re.I):
        put('requests','Прошу вернуть основной долг и уплатить договорную неустойку.',text)
    interest_free=re.search(r'\bЗа[её]м беспроцентный\b',text,re.I)
    agreement=state['fields'].get('agreement',{})
    if interest_free and agreement.get('status')=='filled' and not re.search(r'беспроцент',agreement['value'],re.I):
        value=agreement['value'].rstrip('. ')+'. '+interest_free[0]+'.'
        if set_field(state,'agreement',value,text):consumed.add('agreement')
    return consumed


def reuse_personal_signer(state):
    from app.services.document_scenarios import SCENARIOS
    from app.services.document_dialogue import conversational_value
    fields=state['fields'];sender=fields.get('sender',{})
    if state['scenario'].startswith('contract_') and state['scenario'] != 'contract_employment':
        context=' '.join([state.get('request',''),*state.get('user_turns',[])])
        available={f.key for f in SCENARIOS[state['scenario']].fields}
        for party, signer in [('sender','signature'),('recipient','counterparty_signature')]:
            person=fields.get(party,{})
            existing=fields.get(signer,{})
            if signer not in available or person.get('status')!='filled' or not re.fullmatch(NAME,person.get('value','')):continue
            # An organisation or an explicitly appointed representative still
            # needs its own signatory and authority; never replace that person.
            representation_context=re.sub(r'без\s+представител\w*|представител\w*\s+нет|(?:оба\s+)?действуем\s+лично', '', context, flags=re.I)
            if re.search(r'представител|доверенност|за\s+(?:меня|него|неё|нее)|от имени',representation_context,re.I):
                if existing.get('origin')=='contract_personal_signature':fields.pop(signer,None)
                continue
            if existing.get('status')=='filled' and existing.get('origin')!='contract_personal_signature':continue
            fields[signer]={'status':'filled','value':person['value'],'evidence':person.get('evidence') or person['value'],
                            'origin':'contract_personal_signature','inputs':[party]}
        return
    if not state['scenario'].startswith(('pretense_','claim_','complaint_','motion_','labor_','bailiff_')):return
    if 'signature' not in {f.key for f in SCENARIOS[state['scenario']].fields}:return
    person_name=re.sub(r',\s*(?:истец|ответчик)\s*$','',sender.get('value') or '',flags=re.I)
    if sender.get('status')!='filled' or not re.fullmatch(NAME,person_name):return
    context=' '.join([state.get('request',''),*state.get('user_turns',[])])
    if re.search(r'представител|доверенност|от имени|подпишет',context,re.I):return
    signature=fields.get('signature',{})
    if signature.get('status')=='filled' and signature.get('origin')!='personal_author_signature' and not conversational_value(signature.get('value','')):return
    fields['signature']={'status':'filled','value':person_name,'evidence':sender.get('evidence') or sender['value'],
                         'origin':'personal_author_signature','inputs':['sender']}


def repair_saved_dialogue(state):
    """One-time recovery from user evidence; never use assistant examples."""
    if state.get('fact_repair_version',0)>=1:return
    from app.services.document_addresses import collect_role_addresses
    from app.services.document_dialogue import conversational_value
    from app.services.document_case_facts import set_field
    fields=state['fields'];request=state.get('request','')
    from app.services.document_export_contract import UNCERTAIN
    attachments=fields.get('attachments',{})
    if UNCERTAIN.search(attachments.get('value') or ''):
        attachments.update(status='needs_clarification',value=None,error=None)
    # Payment credentials previously requested by an unsafe clarification are
    # not necessary document content. Preserve the method, not expiry/CVV.
    for key in ('payment','payment_details'):
        item=fields.get(key,{})
        if re.search(r'срок действия|\b(?:cvv|cvc|пин)\b',item.get('value') or '',re.I):
            item.update(value='Банковским переводом; реквизиты будут сообщены отдельно.',status='filled',origin='payment_method_only')
    for key in ('sender','recipient','signature','response_term'):
        item=fields.get(key,{})
        if item.get('value') and conversational_value(item['value']):
            item.update(status='needs_clarification',value=None,error=None)
    if state['scenario'] in {'pretense_debt_loan','claim_debt_loan'}:
        if re.search(r'договор\s+займа\s*№',request,re.I):
            item=fields.get('agreement',{})
            if item.get('value') and not re.search(r'договор|расписк',item['value'],re.I):item.update(status='needs_clarification',value=None)
        item=fields.get('transfer',{})
        if item.get('value') and re.fullmatch(r'на карту|банковским переводом',item['value'],re.I):item.update(status='needs_clarification',value=None)
        item=fields.get('facts',{})
        if item.get('value') and re.search(r'на личные нужды|наверное',item['value'],re.I):item.update(status='needs_clarification',value=None)
        item=fields.get('payments',{})
        if item.get('value') and re.fullmatch(r'на карту|банковским переводом',item['value'],re.I):item.update(status='needs_clarification',value=None)
        collect_explicit_facts(state,request)
        from app.services.document_formula_intake import synchronize_formula_plan
        if not state.get('calculation_plan'):synchronize_formula_plan(state,request)
    for text in state.get('user_turns',[]):collect_role_addresses(state,text)
    from app.services.document_consumer_facts import prepare_consumer_facts
    prepare_consumer_facts(state)
    reuse_personal_signer(state)
    state['fact_repair_version']=1
