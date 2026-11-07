"""Source-bound case records, shared by intake and the document composer.

No editor output is a source. Unknown, absent and ambiguous are different states.
One utterance may answer several questions; its quoted evidence is retained.
"""
from copy import deepcopy
import re

CASES={'complaint_labor_agency','claim_alimony_fixed','claim_debt_loan'}
# These are answers about the *absence* of a fact, not document text.  Keep
# the vocabulary in one place so "никто" does not become a fictional third
# party and "никаких" does not become an address or passport requisite.
NEGATIVE=re.compile(
    r'^(?:нет(?:\s+(?:ничего|данных|сведений))?|никак(?:их|ого|ой|ие)?|никто|никого|ничего|'
    r'отсутств(?:ует|уют|овал|овали)?|не было|третьих лиц нет)[.! ]*$',
    re.I,
)
MONTH=r'(?:январ[ья]|феврал[ья]|март[а]?|апрел[ья]|ма[йя]|июн[ья]|июл[ья]|август[а]?|сентябр[ья]|октябр[ья]|ноябр[ья]|декабр[ья])'
DATE=r'(?:\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{1,2}\s+'+MONTH+r'\s+\d{4}(?:\s*года)?)'
MONEY=r'\d+(?:[ \u00a0]\d{3})*(?:[.,]\d{1,2})?\s*(?:тыс\.?|тысяч(?:а|и)?|млн\.?)?\s*(?:руб(?:лей|ля|ль|\.)?|₽)'


def absence_reply(text: str) -> bool:
    """Whether a short answer means that the requested fact is absent."""
    return bool(NEGATIVE.fullmatch((text or '').strip()))


def raw_field(state,key):
    item=state.get('fields',{}).get(key,{})
    if item.get('status')!='filled':return ''
    return item.get('original') or item.get('evidence') or item.get('value') or ''


def remember(state,key,value,evidence,*,field=None):
    # Every derivation names its literal evidence and contextual question.
    state.setdefault('case_facts',{})[key]={'value':value,'evidence':evidence,
        'field':field,'source':'user','turn':max(0,len(state.get('user_turns',[]))-1)}


def fact(state,key,default=''):
    return state.get('case_facts',{}).get(key,{}).get('value',default)


def normalize_contacts(raw):
    phones=re.findall(r'(?<!\w)\+?\d[\d ()-]{8,}\d(?!\w)',raw)
    phones=[p.strip() for p in phones if 10<=len(re.sub(r'\D','',p))<=15]
    emails=re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-zА-Яа-я]{2,}',raw)
    lines=[]
    for label,values in [('Телефон',phones),('Электронная почта',emails)]:
        for value in dict.fromkeys(values):lines.append(label+': '+value)
    return '\n'.join(lines)


def set_field(state,key,value,evidence,status='filled'):
    from app.services.document_scenarios import SCENARIOS
    from app.services.document_workflow import normalize_field
    specs={f.key:f for f in SCENARIOS[state['scenario']].fields}
    if key not in specs:return False
    if status=='filled':value,error=normalize_field(specs[key],value)
    else:value,error=None,None
    state.setdefault('fields',{})[key]={'status':'incomplete' if error else status,'value':value,
        'original':evidence,'evidence':evidence,'error':error,'origin':'source_bound_extraction'}
    state['revision']=state.get('revision',0)+1
    return True


def collect_case_turn(state,text,key):
    """Capture multiple explicit facts before choosing the next question.

    Return consumed field IDs; other facts remain in the ledger for rendering.
    These rules parse dates, amounts and explicit labels, never infer intent
    from a nearest template or interpret a person's income as child expenses.
    """
    if state.get('scenario') not in CASES:return set()
    scenario=state['scenario'];consumed=set();t=text.strip()
    def put(k,value,quote=None,status='filled'):
        if set_field(state,k,value,quote or value,status):
            consumed.add(k)
            state['fields'][k]['source_field']=key
    if key=='signature' and re.fullmatch(r'(?:я|сам|сама|лично|подпишу (?:сам|сама|лично)|я лично|мо[йёя])[.! ]*',t,re.I):
        sender=state.get('fields',{}).get('sender',{})
        if sender.get('status')=='filled':put(key,sender['value'],t)
        return consumed
    if key in {'court','recipient_address','employer_address'} and NEGATIVE.fullmatch(t):
        put(key,None,t,'unknown');return consumed
    if key in {'facts','other_participants','pretrial','previous_contact','existing_support','other_dependants','assistance'} and NEGATIVE.fullmatch(t):
        remember(state,key+'_absent',True,t,field=key)
        put(key,None,t,'not_applicable');return consumed
    if key=='contacts':
        contacts=normalize_contacts(t)
        address=re.search(r'\bадрес\s*[:—-]\s*(.+)',t,re.I)
        if address:
            from app.services.document_dialogue import normalize_address
            normalized=normalize_address(address[1].strip(' .'))
            if normalized!=state.get('fields',{}).get('sender_address',{}).get('value'):
                remember(state,'reply_address',normalized,address[0],field=key)
        if contacts:put('contacts',contacts,t)
        elif re.search(r'\b(?:ул\.|улица|город|г\.)',t,re.I) or re.search(r'[А-Яа-яЁё-]+\s*,\s*[А-Яа-яЁё-]+\s+\d',t) or NEGATIVE.fullmatch(t):
            # A supplied postal address isn't a phone number or an email.
            put('contacts',None,t,'not_applicable')
        return consumed
    if scenario=='claim_debt_loan':
        fields=state.setdefault('fields',{})

        def fill_if_missing(field_name,value,evidence,status='filled'):
            stored=fields.get(field_name,{})
            if stored.get('status') in {'filled','unknown','not_applicable'}:
                return
            put(field_name,value,evidence,status)

        # The opening description often already contains the receipt, transfer,
        # maturity date and demand.  Save those literal facts before asking the
        # same questions again; the case composer turns them into one coherent
        # chronology at export time.
        if key is None:
            if re.search(r'\bрасписк\w*\b|договор\w*\s+займ',t,re.I):
                fill_if_missing('agreement',t,t)
            if re.search(r'\b(?:дал[аи]?|передал[аи]?|перев[её]л[аи]?|предоставил[аи]?)\b.{0,100}\b(?:деньг|за[её]м)',t,re.I):
                fill_if_missing('transfer',t,t)
            if re.search(r'\b(?:вернут|возврат|срок)\w*.{0,80}\b(?:до|не позднее)\s+'+DATE,t,re.I):
                fill_if_missing('due_date',t,t)
            amounts=re.findall(MONEY,t,re.I)
            if len(amounts)==1:
                fill_if_missing('amount',amounts[0],amounts[0])
            if re.search(r'\b(?:деньги|долг).{0,50}\bне вернул|\bне возвращ(?:ены|ен|ала|ал)',t,re.I):
                fill_if_missing('payments',None,t,'not_applicable')
            if re.search(r'\bпретензи\w*|\bобращал(?:ась|ся)?\b.{0,80}\bответ',t,re.I):
                fill_if_missing('pretrial',t,t)
            return consumed

        if key in {'sender_details','party_details','recipient_details'} and absence_reply(t):
            put(key,None,t,'unknown')
            return consumed
        if key=='other_participants' and absence_reply(t):
            put(key,None,t,'not_applicable')
            return consumed
        if key=='payments' and (
            absence_reply(t)
            or re.search(r'\b(?:все|всё)\s+возвращ\w*|\bне\s+вернул\w*\b|\bплатеж\w*\s+не\s+было',t,re.I)
        ):
            put(key,None,t,'not_applicable')
            return consumed
        if key=='agreement' and not re.search(r'\bрасписк\w*\b|договор\w*\s+займ|за[её]м',t,re.I) and re.search(r'\b(?:нужн\w*\s+деньг|не знаю.{0,20}(?:зачем|для чего))',t,re.I):
            # The borrower\'s purpose is not an essential term of an ordinary
            # loan, but the loan's written basis is.  Do not turn an answer
            # about purpose into either a fabricated agreement or an omitted
            # mandatory field in the document.
            put(key,None,t,'incomplete')
            state['fields'][key]['error']=(
                'Укажите известные сведения о расписке или договоре займа: '
                'дату, номер (если есть) и письменное подтверждение передачи денег.'
            )
            return consumed
        if key=='order_history':
            if re.search(r'\bпретензи\w*|\bобращал(?:ась|ся)?\b|\bответа?\s+не\s+(?:получ|было)',t,re.I):
                fill_if_missing('pretrial',t,t)
                put(key,None,t,'not_applicable')
                return consumed
            if absence_reply(t) or re.search(r'\b(?:приказ\w*.{0,25}не\s+(?:подавал|выдавал)|не\s+обращал)',t,re.I):
                put(key,None,t,'not_applicable')
                return consumed
    if scenario=='complaint_labor_agency':
        employer=re.search(r'(?:работодатель\s*[:—-]\s*)?((?:ООО|АО|ПАО|ИП)\s*[«"].+?[»"])',t,re.I)
        if employer and (key in {'employment','employer'} or re.search(r'работодател|работал|работаю',t,re.I)):
            put('employer',employer[1])
        position=re.search(r'работал[аи]?\s+(.+?)(?=\s+с\s+\d|[.;]|$)',t,re.I)
        if position and key=='employment':remember(state,'position',position[1].strip(),position[0],field=key)
        interval=re.search(r'с\s+(\d{1,2}\s+'+MONTH+r'(?:\s+\d{4})?)\s+по\s+(\d{1,2}\s+'+MONTH+r'\s+\d{4})(?:\s+года)?',t,re.I)
        if interval and key in {'employment','dismissal'}:
            remember(state,'employment_start',interval[1],interval[0],field=key)
            remember(state,'employment_end',interval[2],interval[0],field=key)
        contract=re.search(r'трудов[оы][йм]\s+договор\w*\s*№\s*([\w/-]+)',t,re.I)
        if contract:remember(state,'employment_contract',contract[1],contract[0],field=key)
        if key=='employment' and (position or contract):put('employment',t,t)
        if re.search(r'по собственному желанию',t,re.I):
            remember(state,'dismissal_basis','own_will',t,field=key);put('dismissal',t,t)
        # A debt stated in response to the pay question also answers amount
        # and period. It does not establish the contractual monthly salary.
        debt_context=re.search(r'не (?:выплат|перечисл)|невыплачен|долг|задолжен|начислен',t,re.I)
        if key in {'amount','debt_period','wages','violation'} or debt_context:
            periods=re.search(r'за\s+('+MONTH+r'(?:\s+\d{4}(?:\s+года)?)?)',t,re.I)
            money=re.findall(MONEY,t,re.I)
            if periods:
                remember(state,'debt_period',periods[1],periods[0],field=key);put('debt_period',periods[1],periods[0])
            if len(money)==1:put('amount',money[0])
            if periods or money:
                put('violation','Невыплата заработной платы',t)
                if key=='wages':put('wages',None,t,'not_applicable')
        if key=='evidence':
            remember(state,'evidence_inventory',t,t,field=key)
            put('evidence',t,t)
            # Possession is not submission. Only an explicit attachment list
            # or a later confirmation fills attachments.
        if key=='previous_contact':
            if re.search(r'ответа не (?:было|получ)|не ответил',t,re.I):
                remember(state,'contact_no_reply',True,t,field=key);put(key,t,t)
        if key=='requests' and re.search(r'выплат|зарплат|\bзп\b|провер|инспекц',t,re.I):
            remember(state,'request_wage_check',True,t,field=key);put(key,t,t)
        if key=='payment':
            if re.fullmatch(r'да|ага|ок',t,re.I):
                put(key,t,t);state['fields'][key].update(status='incomplete',error='Речь о получении ответа инспекции. Куда направить ответ: почтой, на электронную почту или через личный кабинет?')
            elif re.search(r'подать жалоб|отправить жалоб',t,re.I):
                put(key,t,t);state['fields'][key].update(status='incomplete',error='Это способ подачи жалобы. А ответ инспекции вы хотите получить почтой, по электронной почте или в личном кабинете?')
            else:put(key,t,t)
    else:
        if key=='party_details':
            birth=re.search(DATE,t,re.I)
            if birth:remember(state,'respondent_birth',birth[0],birth[0],field=key)
            job=re.search(r'место работы\s*[:—-]\s*([^.;]+)',t,re.I)
            if job:remember(state,'respondent_work',job[1],job[0],field=key)
            put(key,t,t)
        child=re.search(r'([А-ЯЁ][а-яё-]+\s+[А-ЯЁ][а-яё-]+\s+[А-ЯЁ][а-яё-]+)\s*,?\s*('+DATE+r')',t)
        if child and key=='children':
            remember(state,'child_name',child[1],child[0],field=key)
            remember(state,'child_birth',child[2],child[0],field=key)
            put('children',child[0],child[0])
        if key in {'children','parentage','living','existing_support'}:
            parentage=re.search(r'(?:отцовство|ответчик.{0,15}(?:отец|отцом)).*?(?:свидетельств[^.!]*)(?:[.!]|$)',t,re.I)
            if parentage:
                remember(state,'parentage_certificate',True,parentage[0],field=key)
                put('parentage',parentage[0])
            if re.search(r'не оспарива',t,re.I):remember(state,'parentage_undisputed',True,t,field=key)
            living=re.search(r'реб[её]нок\s+(?:жив[её]т|проживает)\s+([^.!]+)',t,re.I)
            if living:
                remember(state,'child_living',living[1],living[0],field=key);put('living',living[0])
            court_absent=re.search(r'(?:ранее )?алименты не устанавливались|судебного (?:акта|решения|приказа) нет',t,re.I)
            agreement_absent=re.search(r'(?:нотариального )?соглашения нет|соглашение не заключалось',t,re.I)
            if court_absent:remember(state,'support_order_absent',True,court_absent[0],field=key)
            if agreement_absent:remember(state,'support_agreement_absent',True,agreement_absent[0],field=key)
            if fact(state,'support_order_absent') and fact(state,'support_agreement_absent'):
                remember(state,'existing_support_absent',True,t,field=key);put('existing_support',t)
            elif key=='existing_support' and (court_absent or agreement_absent):
                put(key,t,t);state['fields'][key].update(status='incomplete',error='Уточните отдельно: есть ли судебный акт и есть ли нотариальное соглашение об алиментах?')
        if key=='other_dependants' and re.search(r'других детей нет',t,re.I):
            remember(state,'other_children_absent',True,t,field=key);put(key,t,t)
        if key=='assistance':
            if re.search(r'мои|наши|общие',t,re.I) and fact(state,'ambiguous_support_amount'):
                from app.services.document_workflow import normalize_money
                remember(state,'child_budget',normalize_money(fact(state,'ambiguous_support_amount')),t,field=key)
                put(key,None,t,'unknown')
            elif re.search(r'(?:уходит|расход|трач|содержан).{0,50}\d',t,re.I) and not re.search(r'(?:отец|ответчик).{0,20}(?:платит|да[её]т|перечисляет|тратит)',t,re.I):
                money=re.findall(MONEY,t,re.I)
                if not money:money=re.findall(r'\d+\s*тыс\.?',t,re.I)
                if len(money)==1:remember(state,'ambiguous_support_amount',money[0],t,field=key)
                put(key,t,t);state['fields'][key].update(status='incomplete',error='Уточните, эта сумма — ваши общие расходы на ребёнка или помощь, которую перечисляет отец?')
            elif re.search(r'мои|наши|общие|расходы на реб[её]нка',t,re.I) and fact(state,'ambiguous_support_amount'):
                from app.services.document_workflow import normalize_money
                remember(state,'child_budget',normalize_money(fact(state,'ambiguous_support_amount')),t,field=key)
                put(key,None,t,'unknown')
            else:put(key,t,t)
        if key=='fixed_grounds':
            if re.search(r'нерегулярн|непостоянн|нестабильн',t,re.I):remember(state,'irregular_income',True,t,field=key)
            if re.search(r'разов\w* заказ',t,re.I):remember(state,'one_off_jobs',True,t,field=key)
            put(key,t,t)
        if key=='maintenance_calculation':
            if re.fullmatch(r'пополам|половин[ауы]|50\s*%',t,re.I):
                if fact(state,'child_budget'):
                    remember(state,'half_child_budget',True,t,field=key);put(key,t,t)
                else:
                    put(key,t,t);state['fields'][key].update(status='incomplete',error='Половину какой суммы вы имеете в виду: общих расходов на ребёнка или другого показателя? Укажите общую сумму расходов.')
            else:
                money=re.findall(MONEY,t,re.I)
                if len(money)==1 and re.search(r'расход|бюджет|трач',t,re.I):
                    from app.services.document_workflow import normalize_money
                    remember(state,'child_budget',normalize_money(money[0]),t,field=key)
                remember(state,'budget_description',t,t,field=key);put(key,t,t)
        if key=='start' and re.search(r'настоящего времени|сейчас|со дня (?:подачи|обращения)|с момента обращения',t,re.I):
            remember(state,'start_at_application',True,t,field=key);put(key,t,t)
        if key=='payment':
            remember(state,'payment_preference',t,t,field=key);put(key,t,t)
    if key=='attachments':remember(state,'attachment_list',t,t,field=key);put(key,t,t)
    return consumed


def refresh_case(state):
    """Re-read original answers when exporting old chats, never cached prose."""
    if state.get('scenario') not in CASES:return
    originals=deepcopy(state.get('fields',{}))
    revision=state.get('revision',0)
    for key,item in originals.items():
        # A parsed secondary field is not another user answer. Replaying it
        # used to restore an old amount after a later explicit correction.
        if item.get('source_field',key)!=key:continue
        if item.get('status')=='filled' and item.get('origin') not in {'verified_rule','arithmetic','case_composition'}:
            text=item.get('original') or item.get('evidence') or item.get('value') or ''
            collect_case_turn(state,text,key)
    state['fields']=originals
    state['revision']=revision


def invalidate_case_facts(state,key):
    if state.get('scenario') not in CASES:return
    state['case_facts']={name:item for name,item in state.get('case_facts',{}).items() if item.get('field')!=key}


def automatic_case_fields(state):
    if state.get('scenario') not in CASES:return
    fields=state.setdefault('fields',{})
    if state['scenario']=='complaint_labor_agency':
        keys={'wages','facts','violation'}
    elif state['scenario']=='claim_alimony_fixed':
        keys={'calculation','other_participants'}
    else:
        keys=set()
    # These duplicate other factual questions in the old questionnaire. They
    # remain archived, but are no longer mandatory independent questions.
    for key in keys:
        if key not in fields:fields[key]={'status':'not_applicable','value':None,'origin':'composition_metadata'}
