"""Source-bound parties, limited powers and explicit omissions in an authority."""
import re
from app.services.document_source_quotes import source_sentences

KIN=r'(?:сестр\w*|брат\w*|мам\w*|матер\w*|отц\w*|пап\w*|бабушк\w*|дедушк\w*|супруг\w*|муж\w*|жен\w*|дочер\w*|сын\w*|представител\w*)'


def is_authority_request(text):
    # An actual delegation of actions, not merely "доверяю сестре" or a
    # complaint about what a relative has done.
    match=re.search(r'\b(?:доверить|поручить|уполномочить|доверяю|уполномочиваю)\b.{0,90}\b'+KIN+r'\b.{0,50}\b(?:получ\w*|подпис\w*|представ\w*|пода\w*)',text,re.I)
    return bool(match and not re.search(r'не\s*(?:хочу\s*)?$',text[:match.start()],re.I))


def nominative_agent(value):
    """Only unambiguous Russian dative endings; retain unfamiliar names."""
    parts=value.split()
    if len(parts)!=3:return value
    patronymic=next((i for i,p in enumerate(parts) if re.search(r'(?:овне|евне|ичне)$',p)),None)
    if patronymic is None:return value
    first=0 if patronymic==1 else 1
    last=2 if patronymic==1 else 0
    if not re.search(r'(?:овой|евой|иной|ской|цкой)$',parts[last]):return value
    names={'Ирине':'Ирина','Анне':'Анна','Елене':'Елена','Ольге':'Ольга','Марии':'Мария','Наталье':'Наталья',
           'Татьяне':'Татьяна','Дарье':'Дарья','Юлии':'Юлия','Софье':'Софья','Екатерине':'Екатерина',
           'Светлане':'Светлана','Валентине':'Валентина','Оле':'Оля'}
    name=names.get(parts[first])
    if not name:return value
    parts[first]=name
    parts[patronymic]=parts[patronymic][:-1]+'а'
    surname=parts[last]
    parts[last]=surname[:-2]+('ая' if surname.endswith(('ской','цкой')) else 'а')
    return ' '.join(parts)


def collect_authority_facts(state,text,current=None):
    if state.get('scenario')!='power_of_attorney':return set()
    from app.services.document_explicit_facts import NAME
    from app.services.document_case_facts import set_field,DATE
    from app.services.document_dialogue import conversational_value
    fields=state['fields'];consumed=set();sentences=source_sentences(text)

    def put(key,value,evidence,*,replace=False,status='filled'):
        old=fields.get(key,{})
        if old.get('origin')=='authority_literal_facts' and old.get('original')==evidence and old.get('status')==status:return
        if old.get('status')==status and old.get('value')==value:return
        if old.get('status')=='filled' and not replace and not conversational_value(old.get('value') or ''):return
        if set_field(state,key,value,evidence,status):
            fields[key].update(origin='authority_literal_facts',source_field=current)
            consumed.add(key)

    author=re.search(r'\b(?:Я\s*[—–,:-]?\s+|Меня зовут\s+)('+NAME+r')',text)
    if author:
        old=fields.get('sender',{}).get('value') or ''
        put('sender',author[1],author[0],replace=old==author[0] or not old)
    powers=[]
    for sentence in sentences:
        agent=re.match(r'(?:Доверяю|Уполномочиваю|Поручаю)\s+(?:(?:своей|моей|своему|моему)\s+)?(?:('+KIN+r')\s*[,—:-]?\s*)?('+NAME+r')\s*,?\s+(получить\b.+)',sentence)
        if agent:
            normalized=nominative_agent(agent[2])
            put('recipient',normalized,sentence,replace=fields.get('recipient',{}).get('value')==agent[2])
            state['authority_agent']={'name':normalized,'literal_name':agent[2],'relation':agent[1],'evidence':sentence}
            powers.append(agent[3][:1].upper()+agent[3][1:])
        elif re.match(r'(?:Разрешаю|Уполномочиваю|Поручаю)\s+(?:подать|получить|подписать|представлять)',sentence,re.I):
            powers.append(sentence)
        elif re.search(r'\b(?:не\s+(?:должн\w*|вправе|разрешаю|уполномоч\w*)|запрещ\w*)\b',sentence,re.I) and re.search(r'получ\w*\s+деньг|заключ\w*\s+соглашени|подпис\w*\s+(?:другие|иные)\s+документ',sentence,re.I):
            powers.append(sentence)
        for label,key in [(r'Мой\s+(?:почтовый\s+)?адрес|Адрес\s+доверителя','sender_address'),(r'Адрес\s+'+KIN,'recipient_address')]:
            address=re.match(r'(?:'+label+r')\s*:\s*(.+)',sentence,re.I)
            if address:put(key,address[1].strip(' .'),sentence)
        target=re.match(r'Адрес\s+(?:работодателя|организации)\s*:\s*(.+)',sentence,re.I)
        if target:
            # Destination belongs to the powers, never to the representative.
            state['authority_target_address']={'value':target[1].strip(' .'),'evidence':sentence}
        substitution=re.search(r'\b(?:без\s+права\s+передоверия|с\s+правом\s+передоверия)\b',sentence,re.I)
        if substitution:put('substitution',substitution[0],sentence)
        term=re.search(r'(?:сроком\s+|срок\s+действия\s*[—:-]?\s*)(до\s+'+DATE+r'(?:\s+включительно)?|\d+\s+(?:год|года|лет|месяц\w*|дн\w*))',sentence,re.I)
        if term:put('validity',term[1],sentence)
        place=re.search(r'Место\s+(?:составления|совершения)\s*[—–:-]\s*([^,;.]+)',sentence,re.I)
        if place:put('place',place[1],sentence)
        date=re.search(r'\bдата(?:\s+(?:составления|доверенности))?\s*[—–:-]\s*('+DATE+r')',sentence,re.I)
        if date:put('date',date[1],sentence)
        if re.search(r'паспортн\w*\s+данн\w*',sentence,re.I) and re.search(r'внес[её]м\s+вручную|впиш\w*\s+(?:позже|вручную)|остав\w*.{0,30}пол',sentence,re.I):
            targets=['principal_details','agent_details'] if re.search(r'обеих|обоих|обоим|обеим',sentence,re.I) else []
            if re.search(r'мои|доверителя',sentence,re.I):targets.append('principal_details')
            if re.search(r'сестры|брата|представителя',sentence,re.I):targets.append('agent_details')
            for key in set(targets):put(key,None,sentence,replace=True,status='unknown')
        if re.search(r'подписываю\s+(?:доверенность\s+)?(?:лично|сам[а]?)',sentence,re.I):
            sender=fields.get('sender',{})
            if sender.get('status')=='filled':put('signature',sender['value'],(sender.get('evidence') or sender['value'])+'\n'+sentence)
    if powers:
        old=fields.get('powers',{})
        # A previous extractor sometimes copied the remainder of the entire
        # message. Rebuild that exact source-bound overcapture, not later edits.
        replace=bool(old.get('value') and old['value'] in text)
        parts=list(dict.fromkeys(powers))
        target=state.get('authority_target_address')
        if target:parts.append('Адрес работодателя: '+target['value']+'.')
        put('powers',' '.join(parts),'\n'.join(parts),replace=replace or old.get('origin')=='authority_literal_facts')
        # The purpose is known. Whether certification is needed is a review
        # task, not another request to describe these same actions.
        if not fields.get('form_check',{}).get('value'):
            put('form_check',None,'\n'.join(parts),status='review_required')
    return consumed


def authority_powers_candidate(source):
    """Edit explicit limited actions without introducing catch-all powers."""
    clauses=[]
    for sentence in source_sentences(source):
        sentence=sentence.strip().rstrip('.')
        if re.match(r'^(?:Получить|Подать|Подписать|Расписаться)\b',sentence):
            clauses.append(sentence+'.')
        elif re.match(r'^Разрешаю\s+(?:подать|получить|подписать)',sentence):
            clauses.append(sentence+'.')
        elif re.fullmatch(r'.+\s+(?:она|он)\s+не\s+должн[ао]?|.+\s+(?:она|он)\s+не\s+должен',sentence):
            forbidden=re.sub(r'\s+(?:она|он)\s+не\s+(?:должн[ао]?|должен)$','',sentence)
            clauses.append('Представитель не уполномочен '+forbidden[:1].lower()+forbidden[1:]+'.')
        elif re.match(r'^Адрес работодателя:',sentence):clauses.append(sentence+'.')
        else:return None
    return '\n'.join(clauses) if clauses else None


def recipient_accusative(state):
    """Known feminine name in the template's 'уполномочиваю представителя'."""
    identity=state.get('authority_agent',{})
    value=state.get('fields',{}).get('recipient',{}).get('value') or ''
    if identity.get('name')!=value or nominative_agent(identity.get('literal_name',''))==identity.get('literal_name'):return value
    parts=value.split()
    patronymic=next((i for i,p in enumerate(parts) if re.search(r'(?:овна|евна|ична)$',p)),None)
    if patronymic is None:return value
    first=0 if patronymic==1 else 1
    last=2 if patronymic==1 else 0
    if not parts[first].endswith(('а','я')):return value
    parts[first]=parts[first][:-1]+('ю' if parts[first].endswith('я') else 'у')
    parts[patronymic]=parts[patronymic][:-1]+'у'
    parts[last]=parts[last][:-2]+'ую' if parts[last].endswith('ая') else parts[last][:-1]+'у'
    return ' '.join(parts)
