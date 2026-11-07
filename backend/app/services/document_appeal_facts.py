"""Literal multi-field appeal facts, including the appellant's actual role."""
import re
from app.services.document_source_quotes import source_sentences


def collect_appeal_facts(state,text,current=None):
    if state.get('scenario') not in {'appeal_civil','appeal_arbitration'}:return set()
    from app.services.document_explicit_facts import NAME
    from app.services.document_case_facts import set_field,DATE,MONTH
    from app.services.document_workflow import normalize_field
    from app.services.document_scenarios import SCENARIOS
    specs={f.key:f for f in SCENARIOS[state['scenario']].fields}
    fields=state['fields'];consumed=set();sentences=source_sentences(text)

    def put(key,value,evidence,*,extend=False,replace=False):
        if not value or key not in specs:return
        old=fields.get(key,{})
        if old.get('status')=='filled':
            if value.rstrip('. ') in (old.get('value') or ''):return
            if extend:
                parts=source_sentences(old['value'])+source_sentences(value)
                value=' '.join(p.rstrip('. ') + '.' for p in dict.fromkeys(parts))
            elif not replace:return
        if set_field(state,key,value,evidence):
            fields[key].update(origin='appeal_literal_facts',source_field=current)
            consumed.add(key)

    author=re.search(r'\b(?:[Яя]\s*[—–,:-]?\s+|[Мм]еня зовут\s+)('+NAME+r')(?:\s*,\s*(истец|ответчик))?',text)
    if author:
        old=fields.get('sender',{}).get('value') or ''
        role=author[2]
        value=author[1]+(', '+role if role else '')
        put('sender',value,author[0],replace=old==author[1])
        if not old or author[1] in old:
            state['appellant_identity']={'name':author[1],'role':role,'evidence':author[0]}
    identity=state.get('appellant_identity',{})
    role=identity.get('role')
    other_role={'истец':'ответчик','ответчик':'истец'}.get(role)
    if other_role:
        other=re.search(r'\b'+other_role+r'\s*[—–:-]\s*('+NAME+r')',text,re.I)
        if other:put('recipient',other[1]+', '+other_role,other[0])
    for sentence in sentences:
        own=re.match(r'Мой\s+(?:почтовый\s+)?адрес\s*:\s*(.+)',sentence,re.I)
        if own:put('sender_address',own[1].strip(' .'),sentence)
        for party,party_role in [('sender',role),('recipient',other_role)]:
            if party_role:
                label={'истец':'истца','ответчик':'ответчика'}[party_role]
                match=re.match(r'Адрес\s+'+label+r'\s*:\s*(.+)',sentence,re.I)
                if match:put(party+'_address',match[1].strip(' .'),sentence)
        process=re.search(r'гражданск\w*\s+дел\w*',sentence,re.I)
        if process:put('procedure',process[0],sentence)
        number=re.search(r'дел[аоу]?\s*№\s*([\w/-]+)',sentence,re.I)
        if number:put('case_number',number[1],sentence)
        route=re.search(r'жалоб\w*\s+(?:(?:готовим|пода[её]м|направляем)\s+)?в\s+(.+?\bсуд)\s+через\s+(.+?\bсуд[^.!?]*)[.]?$',sentence,re.I)
        if route:
            put('court',route[1],sentence)
            put('first_court',route[2].strip(' .'),sentence)
        decision=re.match(r'(.+?\bсуд[^.!?]*?)\s+('+DATE+r')\s+вынес\w*\s+решени\w*',sentence,re.I)
        if decision:
            put('first_court',decision[1],sentence)
            put('challenged_act',sentence,sentence)
            parsed,error=normalize_field(specs['act_date'],decision[2])
            if not error:state['appeal_decision_date']={'value':parsed,'evidence':decision[0]}

    def related_date(raw):
        parsed,error=normalize_field(specs['act_date'],raw)
        if not error:return parsed,None
        reference=state.get('appeal_decision_date',{})
        if reference:
            # Only the same month as the explicitly dated judgment. A
            # December/January transition or ambiguous year stays a question.
            candidate=raw+' '+reference['value'][:4]
            parsed,error=normalize_field(specs['act_date'],candidate)
            if not error and parsed[:7]==reference['value'][:7] and parsed>=reference['value']:
                return parsed,reference
        return raw,None

    grounds=[];requests=[]
    for sentence in sentences:
        final=re.search(r'(?:решени\w*\s+)?в\s+окончательной\s+форме\s+изготовлен\w*\s+(\d{1,2}\s+'+MONTH+r'(?:\s+\d{4}(?:\s+года)?)?|\d{1,2}[./]\d{1,2}[./]\d{2,4})',sentence,re.I)
        if final:
            value,reference=related_date(final[1])
            put('act_date',value,sentence)
            if 'act_date' in consumed and reference:fields['act_date']['derived_year_from']=reference
        received=re.search(r'копию\s+(?:решения\s+)?(?:я\s+)?получил[аи]?\s+(\d{1,2}\s+'+MONTH+r'(?:\s+\d{4}(?:\s+года)?)?|\d{1,2}[./]\d{1,2}[./]\d{2,4})',sentence,re.I)
        if received:
            received_text=received[0]
            if final and not re.search(r'копию\s+решения',received_text,re.I):
                # The preceding clause explicitly names the decision. Keep
                # this referent so the prose editor cannot guess "жалобы".
                received_text=re.sub(r'^копию\b','Копию решения',received_text,flags=re.I)
            put('appeal_term',received_text,sentence)
        if re.match(r'Прошу\b',sentence,re.I) or re.search(r'(?:другие|остальные)\s+части\s+решения\s+не\s+обжалую',sentence,re.I):
            requests.append(sentence)
        elif re.search(r'первоначально.{0,35}(?:занимал|за[её]м)|вернул\w*.{0,45}(?:руб|перевод)|назначени\w*\s+платежа|подтверждени\w*\s+перевода.{0,70}(?:суд|представ)|плат[её]ж\s+не\s+оцен[её]н|оставшимся\s+долгом.{0,50}соглас',sentence,re.I):
            grounds.append(sentence)
        if re.match(r'(?:Контакт(?:ы)?|Телефон|Электронная почта)\s*:',sentence,re.I):
            # Appeals keep contacts in party_details; never turn the case
            # number or monetary figures into a guessed telephone number.
            put('party_details',sentence,sentence,extend=True)
        docdate=re.search(r'Дата\s+(?:жалобы|документа)\s*[—–:-]\s*('+DATE+r')',sentence,re.I)
        if docdate:put('date',docdate[1],sentence)
        if re.search(r'подписываю\s+сам[а]?\b|подпишу\s+(?:сам[а]?|лично)',sentence,re.I) and identity.get('name'):
            put('signature',identity['name'],identity['evidence']+'\n'+sentence)
        if re.search(r'копи\w*\s+жалобы.{0,75}(?:не\s+направ|не\s+отправ|направил|отправил)',sentence,re.I):
            put('copy_notice',sentence,sentence)
        if re.match(r'(?:Есть|Приложу|Прилагаю|Приложения\s*:)\s+',sentence,re.I) and re.search(r'копи\w*\s+решения|подтверждени\w*\s+перевода',sentence,re.I):
            items=re.sub(r'^(?:Есть|Приложу|Прилагаю|Приложения\s*:)\s+','',sentence,flags=re.I).strip(' .')
            put('attachments','\n'.join(item[:1].upper()+item[1:] for item in re.split(r'\s+и\s+|;\s*',items)),sentence)
    if grounds:
        old=fields.get('grounds',{}).get('value') or ''
        # The short opening complaint is a summary, not a completed account.
        replace=bool(old and old in state.get('request','') and len(old)<180)
        put('grounds',' '.join(grounds),' '.join(grounds),extend=not replace,replace=replace)
    if requests:put('requests',' '.join(requests),' '.join(requests),extend=True)
    return consumed
