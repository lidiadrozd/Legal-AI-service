"""Versioned case-to-document compiler. The model never writes the DOCX body.

Facts retain user evidence; legal rules and paragraph layout are trusted assets.
An unrecognised assertion becomes a visible review item, never invented prose.
"""
from copy import deepcopy
from decimal import Decimal
import re

from app.services.document_case_facts import CASES, fact, raw_field, refresh_case, normalize_contacts

COMPOSITION_VERSION=2
SK='https://www.consultant.ru/document/cons_doc_LAW_8982/'
GPK='https://www.consultant.ru/document/cons_doc_LAW_39570/'
TK='https://www.consultant.ru/document/cons_doc_LAW_34683/'
NK='https://www.consultant.ru/document/cons_doc_LAW_28165/61fdaaad02ecf7772dc9e0331d21c7ddc3323d4f/'


def uses_case_composer(state):
    return state.get('scenario') in CASES and state.get('text_package',{}).get('composition')=='legal_document'


def prepare_case_rules(state):
    if state['scenario']=='claim_alimony_fixed':
        rules={
            'legal_basis': ('Статья 80 СК РФ возлагает на родителей обязанность содержать несовершеннолетних детей. '
                'Статья 83 СК РФ допускает взыскание алиментов в твёрдой денежной сумме при предусмотренных ею обстоятельствах, '
                'в том числе при нерегулярном доходе родителя. Размер определяется судом с учётом прежнего уровня обеспечения ребёнка, '
                'материального и семейного положения сторон и иных заслуживающих внимания обстоятельств. '
                'По статье 107 СК РФ алименты по общему правилу присуждаются с момента обращения в суд. '
                'Индексация производится по правилам статьи 117 СК РФ. Иск предъявляется с соблюдением статей 131 и 132 ГПК РФ.',
                [SK,GPK]),
            'fee':('Истец освобождён от уплаты государственной пошлины на основании подпункта 2 пункта 1 статьи 333.36 НК РФ.',[NK])}
    else:
        rules={'legal_basis':('Статья 140 ТК РФ предусматривает выплату причитающихся работнику сумм при увольнении в установленные ею сроки. '
            'В соответствии со статьёй 356 ТК РФ федеральная инспекция труда осуществляет надзор за соблюдением трудового законодательства, '
            'рассматривает обращения о нарушениях трудовых прав и принимает меры в пределах своей компетенции.',[TK])}
    for key,(text,urls) in rules.items():
        state.setdefault('fields',{})[key]={'status':'filled','value':text,'origin':'verified_rule',
            'sources':urls,'checked_at':'2026-10-26','error':None}
    if state['scenario']=='claim_alimony_fixed':
        amount=state.get('fields',{}).get('monthly_amount',{})
        state['fields']['claim_price']={'status':'filled','value':_money(Decimal(amount['value'])*12)+' ('+_money(amount['value'])+' × 12 месяцев; пункт 3 части 1 статьи 91 ГПК РФ)','origin':'arithmetic','inputs':['monthly_amount'],'error':None} if amount.get('status')=='filled' else {'status':'review_required','value':None,'origin':'arithmetic'}
        # The statutory indexation request is already a fixed part of the
        # operative request.  The regional living-wage ratio is not a fact
        # that can be guessed, so never render it as a fake completed field.
        state['fields']['indexation']={'status':'not_applicable','value':None,'origin':'statutory_request'}
        for key in ('payment','pretrial','requests'):
            state['fields'].setdefault(key,{'status':'not_applicable','value':None,'origin':'composition_metadata'})


def _money(value):
    return format(Decimal(value),',.2f').replace(',',' ').rstrip('0').rstrip('.')+' рублей'


def _sentence(text):
    text=text.strip(' .\n')
    return text[:1].upper()+text[1:]+'.' if text else ''


def _document_list(text):
    text=re.sub(r'^(?:есть|имеются|приложу|прилагаю)\s+','',text.strip(),flags=re.I)
    text=re.sub(r'\bпритензи', 'претензи', text, flags=re.I)
    # A frequent shorthand in the interview is "договор и работах".  It
    # cannot be printed verbatim as an application item, but it also does not
    # entitle the service to invent an "акт".  Keep the user's meaning at the
    # safe document-category level instead.
    text=re.sub(r'\bдоговор\s+и\s+работах\b',
                'договор и документы о выполненных работах',text,flags=re.I)
    document_head=(r'банковск|расч[её]тн|приказ|свидетельств|справк|копи|расписк|претензи|'
                   r'исков\w* заявлен|уведомлен|квитанц|опи[сьс]|почтов\w* отправлен|'
                   r'плат[её]жн\w* поручен|договор|акт|чек|переписк')
    # Allow ordinary user wording such as "расписку и претензию" as two
    # applications.  The look-ahead has to accept inflected document words;
    # a strict word boundary immediately after the stem made "претензию"
    # remain glued to the preceding item.
    parts=re.split(r'\n|;|,(?!\s*\d)|\s+и\s+(?=(?:'+document_head+r'))',text,flags=re.I)
    return '\n'.join(f'{n}. '+_sentence(re.sub(r'^\d+[.)]\s*','',part)) for n,part in enumerate(filter(None,(p.strip() for p in parts)),1))


def _compose(state):
    working=deepcopy(state)
    refresh_case(working)
    prepare_case_rules(working)
    fields=deepcopy(working.get('fields',{}));notes=[]
    def value(k):
        item=fields.get(k,{})
        return str(item.get('value') or '') if item.get('status')=='filled' else ''
    def emit(key,text):
        fields[key]={**fields.get(key,{}),'status':'filled' if text else 'not_applicable','value':text or None,
            'origin':'case_composition','composition_version':COMPOSITION_VERSION}
    def review(key):
        notes.append(key)
        emit(key,'['+labels.get(key,key).lower()+' — требуется уточнение]')
    def retain_formal(key,prefix=''):
        from app.services.document_export_contract import formal_text
        source=raw_field(working,key)
        if not source:return emit(key,'')
        from app.services.document_drafting import editorial_digest
        cached=state.get('draft_cache',{}).get(key,{})
        if cached.get('digest')==editorial_digest(state['scenario'],key,source):
            emit(key,cached['text'])
            fields[key]['origin']='case_retained_source'
            return
        if key in state.get('form_review_fields',[]):
            review(key)
            fields[key]['origin']='case_retained_source'
            return
        # A complete neutral first-person assertion can pass unchanged. A
        # fragment is not made grammatical merely by capitalising its words.
        if formal_text(source) and re.search(r'\b(?:я|мне|реб[её]нок|ответчик|работодатель)\b',source,re.I):
            emit(key,_sentence(prefix+source))
        else:review(key)
        fields[key]['origin']='case_retained_source'
    from app.services.document_scenarios import SCENARIOS
    labels={f.key:f.label for f in SCENARIOS[state['scenario']].fields}
    from app.services.document_export_contract import clean_requisite
    for key in ('sender','recipient','employer','signature','court'):
        if value(key):
            cleaned=clean_requisite(key,value(key))
            if cleaned is None:review(key)
            else:fields[key]['value']=cleaned
    contacts=normalize_contacts(raw_field(working,'contacts'))
    emit('contacts',contacts)
    if value('attachments'):emit('attachments',_document_list(raw_field(working,'attachments')))
    if state['scenario']=='complaint_labor_agency':
        position=fact(working,'position');start=fact(working,'employment_start');end=fact(working,'employment_end')
        contract=fact(working,'employment_contract');employer=value('employer') or '[наименование работодателя]'
        if position or start or contract:
            employment=f'Между мной и работодателем {employer} возникли трудовые отношения.'
            if position:employment+=' В указанный период я работал'+('а' if re.search(r'\bработала\b',raw_field(working,'employment'),re.I) else '')+' '+position+'.'
            if start:employment+=' Период работы: с '+start+(' по '+end if end else '')+'.'
            if contract:employment+=' Трудовой договор № '+contract+'.'
            emit('employment',employment)
        else:retain_formal('employment')
        if fact(working,'dismissal_basis')=='own_will':
            emit('dismissal','Трудовой договор прекращён по моей инициативе (по собственному желанию)'+(' '+end if end else '')+'.')
        elif raw_field(working,'dismissal'):retain_formal('dismissal')
        period=value('debt_period')
        if period:
            from app.services.document_case_facts import MONTH
            match=re.search(MONTH+r'(?:\s+\d{4}(?:\s+года)?)?',period,re.I)
            period=match[0] if match else re.sub(r'^(?:зарплата|заработная плата)?\s*(?:за\s+)?','',period,flags=re.I).strip(' .')
        amount=value('amount')
        if period or amount:
            emit('debt_period','Работодатель не выплатил мне заработную плату'+(' за '+period if period else ' за [период невыплаты]')+
                (' в размере '+_money(amount) if amount else ' в размере [сумма задолженности]')+'.')
        if fact(working,'evidence_inventory'):
            inventory=re.sub(r'^(?:есть|имеются)\s+','',fact(working,'evidence_inventory').strip(' .'),flags=re.I)
            from app.services.document_export_contract import formal_text
            if formal_text(inventory):emit('evidence','В моём распоряжении имеются следующие документы: '+inventory[:1].lower()+inventory[1:]+'.')
            else:review('evidence')
        if fact(working,'contact_no_reply'):
            emit('previous_contact','По вопросу невыплаты заработной платы я обращался к работодателю. Ответ на обращение не получен.'
                if re.search(r'обращался',raw_field(working,'previous_contact'),re.I) else
                'Обращение к работодателю по вопросу невыплаты заработной платы осталось без ответа.')
        elif value('previous_contact'):retain_formal('previous_contact')
        emit('requests','1. Проверить изложенные обстоятельства невыплаты заработной платы работодателем '+employer+'.\n'
            '2. При подтверждении нарушения принять предусмотренные законом меры в пределах полномочий инспекции для восстановления моих трудовых прав.')
        request_source=raw_field(working,'requests')
        if re.search(r'ответственност',request_source,re.I):
            fields['requests']['value']+='\n3. При наличии законных оснований рассмотреть вопрос о привлечении виновных лиц к установленной законом ответственности.'
        elif request_source and not re.search(r'провер|выплат|зарплат|\bзп\b|инспекц|^нет[.! ]*$',request_source,re.I):
            notes.append('requests');fields['requests']['value']+='\n[Дополнительные просьбы заявителя — требуется уточнение].'
        method=raw_field(working,'payment')
        if re.search(r'личн\w* кабинет',method,re.I):reply='через личный кабинет сервиса, посредством которого подано обращение'
        elif re.search(r'электрон|e-?mail',method,re.I):
            emails=re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-zА-Яа-я]{2,}',contacts)
            reply='по электронной почте на адрес '+(emails[0] if emails else '[электронная почта для ответа]')
        else:reply='по почтовому адресу '+(fact(working,'reply_address') or value('sender_address') or '[адрес для ответа]')
        emit('payment','О результатах рассмотрения жалобы прошу сообщить '+reply+'.')
        if value('facts'):retain_formal('facts')
    else:
        child_name=fact(working,'child_name');birth=fact(working,'child_birth')
        if child_name and birth:emit('children','Требование о взыскании алиментов заявляется на содержание несовершеннолетнего ребёнка. Сведения о ребёнке: '+child_name+'; дата рождения: '+birth.strip(' .')+'.')
        else:review('children')
        if fact(working,'parentage_certificate'):
            emit('parentage','Ответчик является отцом ребёнка, что подтверждается свидетельством о рождении.'+
                (' Отцовство не оспаривается.' if fact(working,'parentage_undisputed') else ''))
        elif value('parentage'):retain_formal('parentage')
        living=fact(working,'child_living')
        if living:
            living=re.sub(r'\bсо мной\b','со мной',living,flags=re.I)
            emit('living',_sentence('Ребёнок проживает '+living))
        elif value('living'):retain_formal('living')
        if fact(working,'existing_support_absent'):
            emit('existing_support','Алименты на содержание ребёнка ранее в судебном порядке не устанавливались. Нотариально удостоверенное соглашение об уплате алиментов не заключалось.')
        elif value('existing_support'):retain_formal('existing_support')
        if fact(working,'other_children_absent'):
            emit('other_dependants','По имеющимся у меня сведениям, других детей у ответчика нет.')
        elif value('other_dependants'):retain_formal('other_dependants')
        if fact(working,'assistance_absent'):emit('assistance','Ответчик не оказывает материальной помощи на содержание ребёнка.')
        elif value('assistance'):retain_formal('assistance')
        grounds=[]
        if fact(working,'irregular_income'):grounds.append('Доход ответчика носит нерегулярный характер.')
        if fact(working,'one_off_jobs'):grounds.append('Ответчик получает доход от выполнения разовых заказов.')
        if grounds:
            grounds.append('С учётом указанных обстоятельств прошу определить алименты в твёрдой денежной сумме, обеспечивающей регулярное содержание ребёнка.')
            emit('fixed_grounds',' '.join(grounds))
        elif value('fixed_grounds'):retain_formal('fixed_grounds')
        amount=value('monthly_amount');budget=fact(working,'child_budget')
        if budget:
            description='Общие ежемесячные расходы на содержание ребёнка составляют '+_money(budget)+'.'
            if fact(working,'half_child_budget'):
                half=Decimal(budget)/2
                description+=' На ответчика прошу возложить половину указанных расходов: '+_money(budget)+' / 2 = '+_money(half)+'.'
                if amount and Decimal(amount)!=half:raise ValueError('Ежемесячная сумма не совпадает с половиной указанных расходов на ребёнка.')
            emit('maintenance_calculation',description)
        elif value('maintenance_calculation'):retain_formal('maintenance_calculation')
        if not fact(working,'start_at_application'):
            # Past periods need distinct evidence of prior measures/evasion;
            # never quietly substitute an ordinary initial claim for arrears.
            if value('start'):review('start')
        start='со дня обращения в суд' if fact(working,'start_at_application') else '[дата начала взыскания — требуется уточнение]'
        emit('requests','1. Взыскать с ответчика в пользу истца алименты на содержание несовершеннолетнего ребёнка (ФИО: '+(child_name or '[ФИО ребёнка]')+
            '; дата рождения: '+(birth.strip(' .') if birth else '[дата рождения ребёнка]')+') в твёрдой денежной сумме '+(_money(amount) if amount else '[ежемесячная сумма]')+
            ' ежемесячно, начиная '+start+' и до достижения ребёнком совершеннолетия.\n'
            '2. Производить индексацию алиментов пропорционально росту величины прожиточного минимума для детей по месту жительства получателя алиментов, '
            'а при отсутствии такой величины в соответствующем субъекте Российской Федерации — для детей в целом по Российской Федерации, в порядке статьи 117 СК РФ.')
        # A vague card preference is not a bank account or a separate claim.
        emit('payment','');emit('pretrial','');emit('calculation','')
        if amount:emit('claim_price',_money(Decimal(amount)*12)+' ('+_money(amount)+' × 12 месяцев; пункт 3 части 1 статьи 91 ГПК РФ)')
        for key in ('sender_details','party_details'):
            source=raw_field(working,key)
            details=[]
            birth_match=re.search(r'(?:дата рождения\s*[:—-]?\s*)?(\d{1,2}[./]\d{1,2}[./]\d{4})',source,re.I)
            if birth_match:details.append('Дата рождения: '+birth_match[1])
            inn=re.search(r'ИНН\s*[:—-]?\s*(\d{10,12})(?!\d)',source,re.I)
            if inn:details.append('ИНН: '+inn[1])
            place=re.search(r'место рождения\s*[:—-]\s*([^;\n.]+)',source,re.I)
            if place:details.append('Место рождения: '+place[1].strip())
            job=re.search(r'место работы\s*[:—-]\s*([^;\n.]+)',source,re.I)
            if job:details.append('Место работы: '+job[1].strip())
            if details:emit(key,'\n'.join(details))
            elif source:review(key)
        # The court may request unknown respondent identifiers; no false ID.
        if fields.get('party_details',{}).get('status')=='unknown':
            emit('party_details','Дата и место рождения, место работы и идентификатор ответчика мне неизвестны. Прошу суд запросить необходимые сведения в предусмотренном законом порядке.')
    # Persist notes on the derived view, not in the user's immutable answers.
    return fields,notes


def case_presentation_fields(state):
    from app.services.document_narrator_grammar import align_narrator_gender
    return align_narrator_gender(_compose(state)[0],state)


def case_narrative_keys(state):
    fields,_=_compose(state)
    return [key for key,item in fields.items() if item.get('origin')=='case_retained_source'
            and state.get('fields',{}).get(key,{}).get('status')=='filled']


def prepare_case_document(state):
    result=deepcopy(state)
    fields,notes=_compose(result)
    from app.services.document_drafting import facts_digest
    from app.services.document_export_contract import EDITOR_VERSION
    result['draft_fields']={k:v['value'] for k,v in fields.items() if v.get('origin') in {'case_composition','case_retained_source'} and v.get('value')}
    result['composition_review_fields']=notes
    result['composition_version']=COMPOSITION_VERSION
    result['draft_version']=EDITOR_VERSION;result['draft_digest']=facts_digest(result['fields'])
    return result
