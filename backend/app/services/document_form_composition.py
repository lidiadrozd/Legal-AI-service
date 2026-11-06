"""Official slot editing for complete forms, with source and meaning checks.

The model edits source-bound slots, not the document structure or legal rules.
Rejected/unavailable prose becomes a named draft gap; it never blocks download
or returns to consultation. Original answers remain available for correction.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import json,re

from app.services.document_form_rules import uses_form_composer,prepare_form_rules
from app.services.document_export_contract import EDITOR_VERSION,formal_text,adds_request,clean_requisite
from app.services.llm_cost import TokenUsage
from app.services.document_editorial_grammar import requires_prose_edit
from app.services.document_narrator_grammar import align_narrator_gender, narrator_gender

REQUISITES={'sender','recipient','employer','seller','signature','counterparty_signature','court','case_number',
    'sender_details','recipient_details','party_details','borrower_details','lender_details','principal_details','agent_details','place','authority_basis'}
MANAGED={'legal_basis','fee','jurisdiction'}


def _package(state):return state.get('text_package') or {}


def requisite_keys(state):
    """Return static and template-declared requisites.

    A form asset may add its own requisite slot (for example, the first
    instance court, a cadastral number, or a legal entity's bank details).
    Such values are identifiers, not free prose for the editorial model.
    """
    package=_package(state)
    dynamic={key for key,mode in package.get('field_formats',{}).items() if mode=='requisite'}
    return REQUISITES|dynamic


def form_narrative_keys(state):
    from app.services.document_scenarios import SCENARIOS,field_is_active
    package=_package(state)
    requisites=requisite_keys(state)
    used=set(re.findall(r'\{\{([a-z_]+)\}\}','\n'.join(b['text'] for b in package['blocks'])))
    return [f.key for f in SCENARIOS[state['scenario']].fields if f.key in used and f.kind=='text'
        and f.key not in requisites|MANAGED and field_is_active(f,state['fields'])
        and state['fields'].get(f.key,{}).get('status')=='filled'
        # Component arithmetic is deterministic and already has document
        # style.  Do not let a prose editor paraphrase or drop part of it.
        and state['fields'][f.key].get('origin') not in {
            'source_bound_arithmetic', 'calculation_plan', 'calculation_plan_composition',
        }
        and state['fields'][f.key].get('value')]


def source_text(state,key):
    item=state['fields'][key]
    # Field value is an already source-bound extraction. A long evidence quote
    # may also contain other answers and must not be reprinted in this slot.
    return item.get('value') or ''



def strip_purpose_echo(text,purpose,source):
    # A field label is editor metadata, not an extra factual sentence. Some
    # providers append it verbatim despite receiving only a source fragment.
    if purpose.casefold() in source.casefold():return text
    return re.sub(r'(?:(?<=\.)\s+|^)'+re.escape(purpose)+r'[.! ]*$', '',text,flags=re.I).strip()


def local_candidate(key,source,mode,scenario):
    from app.services.document_drafting import canonical_editorial,validate_edit
    from app.services.document_editorial_grammar import repair_editorial_surface,formal_source_candidate
    from app.services.document_field_safety import field_value_problem
    # Do not convert a copied label or an appraisal in the wrong slot into a
    # plausible-looking phrase. The interview should have caught it, but this
    # second gate also protects migrated/legacy chats and direct exports.
    # A typed compact value is valid in a phrase slot even though the generic
    # label-echo heuristic cannot distinguish a number from a copied label.
    # Keep the heuristic for prose/sentence slots, where it protects against
    # a user pasting a prompt label into the document.
    safe_scalar = bool(
        (key == 'share' and re.fullmatch(r'[0-9]+ */ *[0-9]+', source.strip()))
        or (key in {'hearing_date', 'force_date', 'payment_date'} and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', source.strip()))
    )
    if field_value_problem(key, source) and not (safe_scalar or (mode=='phrase' and re.fullmatch(r'\d+(?:[.,]\d+)?(?:\s*(?:кв\.?\s*м|м²|м2|процент(?:а|ов)?|%)?)?',source.strip(),re.I))):
        return None
    if key=='contacts':
        from app.services.document_case_facts import normalize_contacts
        return normalize_contacts(source) or None
    # Date and property slots below are embedded in fixed contractual wording.
    # They are data, not prose: wrapping "до 20.10.2026" in another sentence
    # would make the result duplicate the template's predicate and is not
    # necessary for a formal document.
    if key in {'due_date', 'response_term'} and re.fullmatch(r'(?:до|с)\s+\d{1,2}[.]\d{1,2}[.]\d{4}', source.strip(), re.I):
        return source.strip()
    if key == 'property' and re.search(r'(?:г\.|город\s+)?[А-Яа-яЁё-]+(?:,|\s+ул\.)', source):
        # A full chronology can also contain an address.  It cannot be used
        # unchanged in the compact property phrase embedded in the template:
        # the estimate and pre-trial facts would be glued to that paragraph.
        # The presentation composer below extracts the object for legacy
        # states; new intake splits it before it reaches this path.
        if scenario == 'claim_damage_property':
            from app.services.document_form_intake import is_dense_damage_narrative
            if is_dense_damage_narrative(source):
                return None
        return source.strip().rstrip('.')
    if key == 'procedure' and re.fullmatch(r'(?:личн\w* нужд\w* граждан|предпринимательск\w* деятельност\w*)', source.strip(), re.I):
        return source.strip().rstrip('.')
    if key == 'goods' and re.search(r'накладн|акт|товарн', source, re.I):
        return source.strip().rstrip('.')
    if key == 'share' and re.fullmatch(r'[0-9]+ */ *[0-9]+', source.strip()):
        return source.strip()
    if key in {'hearing_date', 'force_date', 'payment_date'} and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', source.strip()):
        return source.strip()
    if key == 'payment_method' and re.search(r'банковск|безналичн', source, re.I):
        return source.strip().rstrip('.')
    # This slot is already placed inside a fixed template sentence such as
    # "Реквизиты для возврата: {{payment_details}}".  A concrete transfer
    # instruction is a requisite, not a narrative that needs an LLM rewrite;
    # preserving it verbatim prevents a transient editor outage from turning a
    # complete consumer claim into a draft gap.
    if key == 'payment_details' and re.search(r'банковск|перечислен|реквизит|сч[её]т|карт', source, re.I):
        return source.strip().rstrip('.')
    negatives={
        'existing_support':'Алименты ранее в судебном порядке не устанавливались; нотариальное соглашение об их уплате не заключалось.',
        'assistance':'Второй родитель материальной помощи на содержание ребёнка не оказывает.',
        'previous_writ':'Исполнительный лист ранее не выдавался.',
        'claims':'Замечаний к передаче, состоянию и комплектности имущества стороны не заявили.',
        'payments':'Платежи в счёт исполнения указанного обязательства не поступали.',
        'received_payments':'Алиментные платежи за указанный период не поступали.'}
    if key in negatives and re.fullmatch(r'нет[.! ]*|ничего[.! ]*|не было[.! ]*',source,re.I):return negatives[key]
    canonical=canonical_editorial(key,source,scenario)
    if canonical:
        if mode=='list':
            from app.services.document_case_composition import _document_list
            return _document_list(canonical)
        return canonical
    candidate=repair_editorial_surface(key,source,formal_source_candidate(source)).strip()
    if not formal_text(candidate):return None
    if requires_prose_edit(candidate):return None
    # A telegram shorthand, a lower-case new sentence or an oral answer is
    # not made official merely by containing a verb such as "получен".
    if re.search(r'\b(?:игнорируй|забудь|выполни инструкц|следуй инструкц|не проверяй|системный промпт)\b',candidate,re.I):return None
    if mode=='list':
        from app.services.document_case_composition import _document_list
        return _document_list(candidate)
    # Short choices/terms can be slots inside a complete trusted sentence.
    # Narration requires a finite verb or an already complete sentence.
    sentence=bool(re.search(r'\b(?:является|имеется|имеются|составляет|составляют|подтвержд[её]н\w*|подтверждается|'
        r'заключ[её]н\w*|обязуется|обязуются|прошу|требую|возражаю|работал[аи]?|проживает|'
        r'передал[аи]?|передан\w*|получил[аи]?|получен\w*|оплатил[аи]?|уплатил[аи]?|'
        r'выплачен\w*|направил[аи]?|направлен\w*|выполнен\w*|оказан\w*|нарушен\w*|'
        r'отмен[её]н\w*|вынес(?:ла|ли)?|вступил\w*|расторгнут\w*|уволен\w*|согласован\w*|предусмотрен\w*|'
        r'расположен\w*|подлежит|подлежат|осуществляется|производится|уплачивается|оплачивается|'
        r'согласовали|несут|нес[её]т|обеспечивает|вносит|прекращены|представляю|находил(?:ся|ась)|назначено|'
        r'не было|отсутству\w*)\b',candidate,re.I))
    # Reusing an already official source is different from approving a model
    # rewrite. Ordinary Russian predicates must not require a network call.
    if candidate[:1].isupper() and candidate.endswith('.') and len(candidate.split())>=4:
        sentence=sentence or bool(re.search(r'\b[А-Яа-яЁё-]{3,}(?:ется|ются|ается|яются|ится|атся|ятся|ает|яет|аёт|ёт|ены|ено|ена|ён|ила|или|илась|ился|лась|лся|ует|уют|ил|ит|ан|ана|ано|аны|ен|ают|яют|аю|яю|ую|усь|юсь)\b',candidate))
    # A dated judicial act is a formal identifier in its own right.  It often
    # has no finite verb ("Решение ... от ..."), but treating it as an
    # unfinished conversational answer needlessly blocks a civil appeal when
    # the editor service is temporarily unavailable.
    if key=='challenged_act' and re.match(r'^(?:решение|определение|постановление)\b',candidate,re.I) and re.search(r'\bот\s+\d{1,2}[.]\d{1,2}[.]\d{4}\b',candidate,re.I):
        sentence=True
    if key=='requests' and re.match(r'^(?:Прошу|Взыскать|Возвратить|Вернуть|Отменить|Восстановить|Приобщить|Выдать|Отложить|Расторгнуть|Отказать)\b',candidate,re.I):sentence=True
    if key=='powers' and re.match(r'^(?:Представлять|Получать|Подавать|Подписывать|Совершать)\b',candidate,re.I):sentence=True
    if key in {'evidence','defect_evidence','payment_evidence','expense_proof'} and re.match(r'^(?:акт|отч[её]т|договор|справка|приказ|фото|чек|кассовый|банковск)',candidate,re.I):
        return ('Доказательства: '+candidate[:1].lower()+candidate[1:]).rstrip('.')+'.' if mode=='sentence' else candidate.rstrip('.')
    if mode=='phrase' and len(candidate)<500 and not re.search(r'\b(?:я|мне|у меня|хочу|надо|нужно|пусть)\b',candidate,re.I):
        return candidate.rstrip(' .')
    if sentence and validate_edit(candidate,source) and not adds_request(key,candidate,source):
        return candidate[:1].upper()+candidate[1:].rstrip(' .')+'.'
    return None


def _validate_slot(key,text,source,mode):
    if re.search(r'мужском\s+роде|женском\s+роде|(?:грамматическ\w*|фактическ\w*)\s+(?:род|пол)|согласу\w*\s+в\s+роде|неизрасходован\w*\s+аванс\s+не\s+(?:равен|приравнивается)',text,re.I) and not re.search(r'\bрод\w*|\bпол\w*|неизрасходован',source,re.I):return False
    if key=='acceptance' and re.search(r'(?:с\s+момента|со\s+дня|после)\s+(?:выполнения|завершения|передачи)',text,re.I) and not re.search(r'момент|со\s+дня|после|передач|завершени',source,re.I):return False
    if re.search(r'(?:ранее|первоначально|впоследствии).{0,30}(?:заявл|требован|обращен)',text,re.I) and not re.search(r'ранее|первоначально|впоследствии|обращал|требовал|просил|а потом',source,re.I):return False
    if key in {'return_facts','deposit_terms'} and re.search(r'(?:передач\w*|передан\w*).{0,65}\b(?:нанимателю|арендатору)\b',text,re.I) and not re.search(r'\b(?:нанимателю|арендатору)\b',source,re.I):return False
    if key=='repairs' and re.search(r'неисправност\w*.{0,65}устраняет\s+наймодатель',source,re.I) and re.search(r'Наниматель.{0,100}устранени\w*\s+неисправност',text,re.I):return False
    if re.search(r'\bнеотработан\w*',source,re.I) and not re.search(r'\bнеотработан\w*',text,re.I):return False
    if re.search(r'\b(?:Исполнитель|Подрядчик|Заказчик)\s+обязана\b',text,re.I):return False
    if key=='acceptance' and re.search(r'проверяет\s+результат',source,re.I) and re.search(r'результат\s+при[её]мки',text,re.I):return False
    if key=='powers' and re.search(r'(?:соверш\w*|осуществ\w*)\s+(?:люб\w*|ин\w*|друг\w*)\s+действи[яй]',text,re.I) and not re.search(r'(?:соверш\w*|осуществ\w*)\s+(?:люб\w*|ин\w*|друг\w*)\s+действи[яй]',source,re.I):return False
    if key=='appeal_term' and re.search(r'копи\w*\s+решения',source,re.I) and not re.search(r'копи\w*\s+(?:решения|судебного\s+(?:решения|акта))',text,re.I):return False
    if key=='requests' and re.search(r'не\s+обжалую',source,re.I) and not re.search(r'не\s+(?:обжалу\w*|оспарива\w*)',text,re.I):return False
    # The editor must not invent a narrator ("Женщина указал") or turn a
    # negative answer about future contract terms into a past defect report.
    if re.search(r'\b(?:женщина|мужчина|пользователь|пользовательница)\b',text,re.I) and not re.search(r'\b(?:женщина|мужчина|пользователь|пользовательница)\b',source,re.I):return False
    if key=='scope' and 'обработан' in source.casefold() and not re.search(r'обработ|коррекц',text,re.I):return False
    if key=='changes' and re.search(r'дополнительн\w*\s+час\w*.{0,80}только\s+после',source,re.I) and re.search(r'(?:требуются|необходимы|заказаны)\s+дополнительные\s+часы',text,re.I):return False
    if key in {'quality','liability','materials'}:
        from app.services.document_case_facts import absence_reply
        if absence_reply(source) and re.search(r'выявлен|доказательств|представлен|указал|сообщил',text,re.I):return False
    from app.services.document_drafting import validate_edit
    from app.services.document_field_safety import field_value_problem
    if not text.strip() or requires_prose_edit(text) or not formal_text(text) or not validate_edit(text,source):return False
    if re.match(r'^Относится к (?:условиям|полю|разделу)\b',text,re.I) and not re.match(r'^Относится к\b',source,re.I):return False
    # A photo's existence is not proof of the alleged fault when the user
    # explicitly says the photo cannot establish it. Preserve that limit.
    if re.search(r'по ним не скажешь|по (?:фото|снимкам|документам).{0,20}(?:нельзя|невозможно) (?:определить|установить)',source,re.I):
        if not re.search(r'нельзя|невозможно|не позволяют|не подтвержда|недостаточно|не дают возможности',text,re.I):return False
    if field_value_problem(key, text):return False
    if re.search(r'[{}<>`]',text) or not re.search(r'[А-Яа-яЁёA-Za-z0-9]',text):return False
    if mode=='sentence' and (not re.search(r'[А-Яа-яЁёA-Za-z]',text) or len(text.split())<2):return False
    if mode=='sentence' and re.match(r'^(?:до|с|на)\s+\d',text,re.I):return False
    if adds_request(key,text,source):return False
    if re.search(r'\b(?:если|в случае|при неисполнении)\b',text,re.I) and not re.search(r'\b(?:если|в случае|при неисполнении)\b',source,re.I):return False
    if re.search(r'неправомерн|следует.{0,25}(?:сформулир|изложить)|должно быть сформулировано',text,re.I) and not re.search(r'неправомерн|следует|должно быть сформулировано',source,re.I):return False
    if any(root in source.casefold() and root not in text.casefold() for root in ('договор','переписк','чек')):return False
    if re.search(r'\b(?:представлен[а-яё]*|направлен[а-яё]*)\b',text,re.I) and re.match(r'^(?:у меня )?есть\b',source,re.I):return False
    if re.search(r'\b(?:я )?не знаю\b',source,re.I) and not re.search(r'\b(?:мне неизвестн[а-яё]*|мне не известн[а-яё]*|не располагаю|не знаю)\b',text,re.I):return False
    if not re.search(r'\b(?:я|приобр[её]л[аи]?|купил[аи]?|заказал[аи]?)\b',source,re.I) and re.search(r'\bя\s+(?:приобр[её]л|купил|заказал)[аи]?\b',text,re.I):return False
    if key=='requests' and mode=='sentence' and re.match(r'^(?:требование|возврат|возмещение)\b',text,re.I):return False
    if re.search(r'\b(?:требуется рассмотреть|в претензии|в заявлении|в документе указано)\b',text,re.I) and not re.search(r'\b(?:требуется рассмотреть|в претензии|в заявлении|в документе указано)\b',source,re.I):return False
    if re.search(r'неизвестн|не известн|не располагаю|не знаю',text,re.I) and not re.search(r'неизвестн|не известн|не располагаю|не знаю',source,re.I):return False
    if re.search(r'\b(?:в связи|по причине|вследствие)\b',text,re.I) and not re.search(r'\b(?:в связи|по причине|вследствие|потому|так как|из-за)\b',source,re.I):return False
    if re.search(r'\b(?:должен|обязан|обязуется|вправе|разрешено|запрещено)\b',text,re.I) and not re.search(r'\b(?:должен|обязан|обязуется|вправе|разреш\w*|запрещ\w*|можно|нельзя|пусть|нужно|надо|соглас\w*|будет|будут)\b',source,re.I):
        # The authoring template supplies duties. A free editor cannot add them.
        return False
    return not re.search(r'\b(?:стать[яиею]|ст\.)\s*\d|\b(?:ГК|СК|ТК|ГПК|АПК|НК)\s*РФ',text) or bool(re.search(r'\b(?:стать|ст\.)',source,re.I))


async def prepare_form_document(state,client=None,*,source_keys=None):
    from app.services.document_drafting import facts_digest,editorial_digest
    from app.services.document_scenarios import SCENARIOS
    from app.services.document_workflow import _structured
    result=deepcopy(state)
    from app.services.document_form_intake import prepare_form_intake
    if source_keys is None:
        prepare_form_intake(result)
        prepare_form_rules(result)
    specs={f.key:f for f in SCENARIOS[result['scenario']].fields};package=_package(result)
    formats=package.get('field_formats',{});edits={};missing=[];usage=[]
    author_gender=None if result['scenario'].startswith('contract_') else {'male':'мужской','female':'женский'}.get(narrator_gender(result.get('fields',{}),result))
    cache=result.setdefault('draft_cache',{});pending=[]
    for key in form_narrative_keys(result) if source_keys is None else source_keys:
        source=source_text(result,key);mode=formats.get(key,'sentence')
        cached=cache.get(key,{})
        if cached.get('digest')==editorial_digest(result['scenario'],key,source) and _validate_slot(key,cached.get('text',''),source,mode):
            edits[key]=cached['text'];continue
        # A verb, initial capital or a short phrase cannot certify business
        # style. Every free-text slot goes through the editor and semantic
        # reviewer when available. Only exact deterministic transformations
        # (lists, explicit negative choices, contacts) may bypass the model.
        from app.services.document_drafting import canonical_editorial
        canonical=canonical_editorial(key,source,result['scenario'])
        candidate=local_candidate(key,source,mode,result['scenario']) if client is None or canonical or key=='contacts' else None
        if candidate:
            result.setdefault('draft_review',{}).pop(key,None)
            edits[key]=candidate;continue
        pending.append(key)
    # Batch by document purpose; schema IDs and slot contexts prevent fields
    # from drifting into another template, role, stage or legal subject.
    for start in range(0,len(pending),8):
        keys=pending[start:start+8]
        if client is None:missing.extend(keys);continue
        data={key:{'source_text':source_text(result,key),'purpose':specs[key].label,
            'format':formats.get(key,'sentence'),'template_context':[b['text'] for b in package['blocks'] if '{{'+key+'}}' in b['text']]}
            for key in keys}
        if author_gender:
            for slot in data.values():
                slot['author_grammatical_gender']=author_gender
        if result['scenario'].startswith('contract_'):
            for slot in data.values():
                slot['grammar']='Согласуй грамматический род наименования стороны. Это инструкция редактору: не включай её в текст документа.'
        try:
            from app.services.document_slot_editor import edit_slots
            valid, items = await edit_slots(client, data, _validate_slot, document=SCENARIOS[result['scenario']].title)
            usage.extend(items)
            # A model may damage an already official source. Such a source
            # can be considered unchanged, but still needs semantic review.
            for key in keys:
                if key not in valid:
                    candidate=local_candidate(key,source_text(result,key),formats.get(key,'sentence'),result['scenario'])
                    if candidate and _validate_slot(key,candidate,source_text(result,key),formats.get(key,'sentence')):valid[key]=candidate
            for revision in range(3):
                if not valid:break
                verification=await _structured(client,
                        'Сравни каждый отредактированный фрагмент с его source_text и назначением поля. '
                        'Для каждого поля отдельно проверь meaning_preserved, business_style, fits_context и объясни reason. '
                        'true — все числа, даты, роли, отрицания, время, условия и смысл сохранены; стиль официальный; новых фактов, прав и обязанностей нет. '
                        'Проверяй также готовое предложение после подстановки в template_context: согласование, отсутствие повторов и ясность. '
                        'Назначение поля задаётся purpose и template_context, а НЕ английским идентификатором. '
                        'Цель покупки «хранение продуктов» сохраняй как цель, не отклоняй из-за отсутствия слов о личных нуждах. '
                        'Не требуй новых фактов и не подменяй проверку смысла проверкой юридической достаточности ответа. '
                        'Дословное копирование разговорного ответа не является редакцией. «Лежать», «дивана тоже нет», «уже 28 октября» — бытовой стиль. '
                        'Допустимо раскрыть короткий ответ в пределах назначения поля: цель «лежать» — личное использование для отдыха. '
                        'false — есть добавление, потеря, двусмысленность, неофициальный стиль или инструкция редактору. '
                        'Не оценивай полноту дела: неизвестные факты проверяются отдельно. Верни отдельный результат по каждому полю.',
                        {'slots':{k:{**data[k],'editorial':v} for k,v in valid.items()}},
                        {'type':'object','properties':{k:{'type':'object','properties':{
                            'meaning_preserved':{'type':'boolean'},'business_style':{'type':'boolean'},
                            'fits_context':{'type':'boolean'},'reason':{'type':'string'}},
                            'required':['meaning_preserved','business_style','fits_context','reason'],'additionalProperties':False} for k in valid},'required':list(valid),'additionalProperties':False},
                        name='verify_official_slots',plain_json=True)
                usage.append(verification.usage);supported=json.loads(verification.content)
                rejected={}
                for key,text in valid.items():
                    verdict=supported.get(key)
                    result.setdefault('draft_review',{})[key]=verdict
                    if isinstance(verdict,dict) and all(verdict.get(check) is True for check in ('meaning_preserved','business_style','fits_context')):
                        edits[key]=text;cache[key]={'digest':editorial_digest(result['scenario'],key,source_text(result,key)),'text':text}
                    else:
                        rejected[key]={**data[key], 'previous_editorial':text, 'review_feedback':verdict}
                if not rejected or revision==2:break
                if revision==0:
                    valid,items=await edit_slots(client,rejected,_validate_slot,document=SCENARIOS[result['scenario']].title)
                    usage.extend(items)
                else:
                    valid={}
                    for key in rejected:
                        candidate=local_candidate(key,source_text(result,key),formats.get(key,'sentence'),result['scenario'])
                        if candidate and _validate_slot(key,candidate,source_text(result,key),formats.get(key,'sentence')):valid[key]=candidate
            missing.extend(k for k in keys if k not in edits)
        except (RuntimeError,ValueError,TypeError,AttributeError):missing.extend(k for k in keys if k not in edits)
    result.update(draft_fields=edits,form_review_fields=sorted(set(missing)),draft_version=EDITOR_VERSION,
        draft_digest=facts_digest(result['fields']),draft_error='incomplete_official_slots' if missing else None)
    total=TokenUsage(sum(u.prompt_tokens for u in usage),sum(u.completion_tokens for u in usage),
        sum(u.total_tokens for u in usage),any(u.usage_estimated for u in usage))
    return result,total


DEBT_CLAIM_SCENARIOS={
    'claim_debt_loan','claim_debt_rent','claim_debt_services','claim_debt_supply',
}
DEBT_PRETENSE_SCENARIOS={
    'pretense_debt_loan','pretense_debt_rent','pretense_debt_services','pretense_debt_supply',
}
_ABSENCE_REPLY=re.compile(
    r'^\s*(?:нет(?:\s+(?:ничего|данных|сведений))?|никак(?:их|ого|ой|ие|ое)?|никто|никого|'
    r'ничего|отсутств(?:ует|уют|овал|овали)?|не было|третьих лиц нет|неизвестно)\s*[.! ]*$',re.I,
)
_DATE_RE=r'(?:\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+\d{4}(?:\s+года)?)'


def _is_absence_reply(value):
    return bool(_ABSENCE_REPLY.fullmatch((value or '').strip()))


def _clean_space(value):
    return re.sub(r'\s+',' ',(value or '')).strip(' .\n')


def _debt_tokens(value):
    """Content words used only to suppress an exact duplicated account.

    This deliberately does not try to decide whether two different factual
    accounts are true.  It only spots a legacy opening narrative copied into
    both a structured field and the residual ``facts`` field.
    """
    ignored={'в','во','и','на','по','с','со','от','до','за','для','что','как','это','был','была','были','было','я','он','она'}
    return {word for word in re.findall(r'[а-яё]{3,}|\d{1,4}',(value or '').lower()) if word not in ignored}


def _repeats_structured_debt_facts(candidate, sources):
    tokens=_debt_tokens(candidate)
    if len(tokens)<8:
        return False
    reference=_debt_tokens(' '.join(source for source in sources if source))
    if not reference:
        return False
    # At least four fifths of a copied narrative are already represented by
    # named fields.  A separate short fact is retained even when it shares a
    # few words such as "долг" or "претензия".
    return len(tokens-reference)<=max(2,round(len(tokens)*0.2))


def _set_presentation(fields,key,value,*,status='filled',origin='debt_claim_composition'):
    stored=fields.get(key,{})
    fields[key]={**stored,'status':status,'value':value,'origin':origin,'error':None}


def _compose_attachment_list(state,fields,source):
    from app.services.document_case_composition import _document_list
    from app.services.document_export_contract import formal_text,UNCERTAIN
    from app.services.document_dialogue import conversational_value
    if not source or _is_absence_reply(source) or state['fields'].get('attachments',{}).get('status')!='filled':return
    candidate=_document_list(source)
    if formal_text(candidate) and not conversational_value(source) and not UNCERTAIN.search(source):
        _set_presentation(fields,'attachments',candidate,origin='source_bound_attachment_list')
    else:
        _set_presentation(fields,'attachments',None,status='review_required',origin='attachment_review')


def _loan_receipt_sentence(source):
    if not re.search(r'\bрасписк\w*\b',source or '',re.I):
        return None
    dated=re.search(r'\bрасписк\w*\b.{0,48}?\bот\s+('+_DATE_RE+r')',source,re.I)
    if not dated:
        dated=re.search(r'\b('+_DATE_RE+r')\b.{0,55}?\bрасписк\w*\b',source,re.I)
    return ('Получение денежных средств подтверждается распиской'
            +(' от '+dated[1] if dated else '')+'.')


def _date_near(source, anchor):
    """Return the date that belongs to a particular factual event.

    A single opening narrative can contain the date of the loan, its maturity
    and a later claim.  Selecting the first date in that paragraph silently
    moves the pre-trial claim to the loan date.  We only choose an existing
    date, preferring the one nearest to the specified event word.
    """
    if not source:
        return None
    events=list(re.finditer(anchor,source,re.I))
    dates=list(re.finditer(_DATE_RE,source,re.I))
    if not events or not dates:
        return None
    event=events[0]
    return min(dates,key=lambda match:abs(match.start()-event.start()))[0]


def _loan_agreement_sentence(source):
    receipt=_loan_receipt_sentence(source)
    if receipt:
        return receipt
    match=re.search(r'\bдоговор(?:\s+займа)?(?:\s*№\s*[\w/-]+)?(?:\s+от\s+'+_DATE_RE+r')?',source or '',re.I)
    if match:
        title=_clean_space(match[0])
        if not re.search(r'займ',title,re.I):
            title+=' займа'
        return title[:1].upper()+title[1:].rstrip('.')+'.'
    return None


def _loan_transfer_sentence(source,amount):
    event=r'\b(?:дал[аи]?|передал[аи]?|перев[её]л[аи]?|предоставил[аи]?)\b'
    verb=re.search(event,source or '',re.I)
    # The question itself establishes that this answer concerns the transfer.
    # A user commonly writes "перевела ему их на карту" rather than repeats
    # the word "деньги"; that is still an explicit transfer and must not turn
    # into a bracket placeholder in the final claim.
    if not verb:
        return None
    date=_date_near(source,event)
    date_part=(date+' ' if date else '')
    amount_part=('в размере '+amount+' ' if amount else '')
    method=''
    if re.search(r'наличн',source,re.I):
        method=' наличными денежными средствами'
    elif re.search(r'(?:банковск\w*\s+)?перевод',source,re.I):
        method=' банковским переводом'
    elif re.search(r'\bперев[её]л[аи]?\b.{0,80}\bкарт',source,re.I):
        method=' на банковскую карту'
    predicate='были переданы'
    if re.search(r'\bперев[её]л[аи]?\b',source,re.I):
        predicate='были перечислены'
    return (date_part+'денежные средства '+amount_part+predicate+' ответчику'
            +method+' в качестве займа.').replace('  ',' ')


def _loan_due_phrase(source):
    match=re.search(r'\b(?:до|не\s+позднее)\s+('+_DATE_RE+r')',source or '',re.I)
    return ('до '+match[1]) if match else None


def _loan_pretrial_sentence(source):
    if not re.search(r'\b(?:претензи\w*|обращал(?:ась|ся)?|обращени\w*)\b',source or '',re.I):
        return None
    date=_date_near(source,r'\b(?:претензи\w*|обращал(?:ась|ся)?|обращени\w*)\b')
    if re.search(r'\bпретензи\w*\b',source,re.I):
        text='Письменная претензия была направлена ответчику'
    else:
        text='Ответчику было направлено обращение'
    if date:
        text+=' '+date
    text+='.'
    if re.search(r'\b(?:ответа?\s+(?:не\s+получ\w*|нет|не\s+было)|без\s+ответа)\b',source,re.I):
        text+=' Ответ на обращение не получен.'
    return text


def _services_agreement_reference(source):
    """Keep the service-agreement slot to its stated reference only."""
    source=_clean_space(source)
    match=re.search(
        r'\bдоговор\w*(?:\s+(?P<kind>(?:возмездного\s+)?оказания\s+услуг))?'
        r'(?:\s*№\s*(?P<number>[\w/-]+))?'
        r'(?:\s+от\s+(?P<date>'+_DATE_RE+r'))?',source,re.I)
    if not match or not (match['number'] or match['date']):
        return None
    title='Договор'
    if match['kind']:
        title+=' '+_clean_space(match['kind']).lower()
    if match['number']:
        title+=' № '+match['number']
    if match['date']:
        title+=' от '+match['date']
    return title+'.'


def _service_performance_sentence(source, evidence, recipient):
    """Use neutral wording for a compact service description.

    The question itself establishes that the answer is an already rendered
    service.  Therefore a one-line response such as ``разработка сайта`` can
    safely receive the neutral predicate ``Оказаны услуги`` without guessing
    the author's gender or a new factual detail.
    """
    source=_clean_space(source)
    source=re.sub(r'^(?:исполнение\s+обязательств|оказанные\s+услуги)\s*[:—–-]\s*','',source,flags=re.I)
    if not source:
        return None
    subject=''
    compact=re.fullmatch(r'[^.!?]{2,240}',source)
    if compact and not re.search(r'\b(?:оказан\w*|выполнен\w*|разработан\w*|оказал[аи]?|выполнил[аи]?|разработал[аи]?)\b',source,re.I):
        subject=source.strip(' .')
    if not subject:
        action=re.search(
            r'\b(?:разработал[аи]?|выполнил[аи]?|оказал[аи]?|создал[аи]?|подготовил[аи]?)\s+'
            r'(?P<subject>.+?)(?=\s+по\s+договор\w*|[.;]|$)',source,re.I)
        if action:
            subject=action['subject'].strip(' ,.;')
            if recipient:
                subject=re.sub(r'^для\s+'+re.escape(recipient)+r'\s+','',subject,flags=re.I)
            subject=re.sub(r'^для\s+(?:(?:ООО|АО|ПАО|ИП|НКО|ФГБУ)\s*)?[«\"][^»\"]+[»\"]\s+', '', subject, flags=re.I)
    if not subject:
        return None
    subject=subject.rstrip(' .')
    # This is the ordinary short reply in the services questionnaire.  The
    # nominal predicate is more natural under the template's own heading than
    # a second colon ("Исполнение обязательств: Оказаны услуги: ...").
    if re.match(r'^разработка\b',subject,re.I):
        result='Выполнена '+subject+'.'
    else:
        result='Оказаны услуги: '+subject+'.'
    act=re.search(r'\bакт(?:\s+[^.]{0,80})?\s+подписан(?:\s+'+_DATE_RE+r')?',evidence or '',re.I)
    if act:
        act_text=_clean_space(act[0])
        if act_text and act_text.casefold() not in result.casefold():
            result+=' '+act_text[:1].upper()+act_text[1:].rstrip('.')+'.'
    return result


def _service_violation_sentence(source):
    """Replace a copied price ledger with the stated non-payment fact."""
    source=_clean_space(source)
    source=re.sub(r'^обстоятельства\s+нарушения\s*[:—–-]\s*','',source,flags=re.I)
    if not source:
        return None
    unpaid=bool(re.search(
        r'\bнеоплат\w*\s+оказан\w*\s+услуг|'
        r'\b(?:деньг\w*|оплат\w*|плат[её]ж\w*|остаток)\b.{0,80}\bне\s+(?:поступил\w*|оплачен\w*|перечислен\w*)',source,re.I))
    if not unpaid:
        return None
    result='Оплата оказанных услуг не поступила.'
    if re.search(r'\bответа?\s+(?:нет|не\s+получ\w*)\b|\bответ\s+не\s+получ\w*\b',source,re.I):
        result+=' Ответ на обращение не получен.'
    return result


def _compose_debt_pretense_presentation(state,fields):
    """Keep every debt pretense's factual slots non-repeating at export."""
    scenario=state.get('scenario')
    if scenario not in DEBT_PRETENSE_SCENARIOS:
        return
    raw={key:_clean_space(source_text(state,key)) for key in state.get('fields',{})}
    # Lists retain their item boundaries. Narrative whitespace normalization
    # would merge separate attachments before the numbering pass.
    attachments=source_text(state,'attachments') if 'attachments' in state['fields'] else ''
    _compose_attachment_list(state,fields,attachments)
    if scenario=='pretense_debt_loan':
        from app.services.document_case_composition import _money
        transfer=_loan_transfer_sentence(raw.get('transfer',''),_money(raw['amount']) if raw.get('amount') else '')
        if transfer:_set_presentation(fields,'transfer',transfer.replace('ответчику','заёмщику'))
        if re.search(r'платежи.{0,40}не поступали|ничего не возвращено',raw.get('payments',''),re.I):
            _set_presentation(fields,'payments','не поступали')
    if scenario!='pretense_debt_services':
        return
    agreement=_services_agreement_reference(raw.get('agreement',''))
    if agreement:
        _set_presentation(fields,'agreement',agreement,origin='services_agreement_reference')
    performance_source=raw.get('performance') or raw.get('agreement','')
    performance=_service_performance_sentence(
        performance_source,
        ' '.join(value for value in (raw.get('performance',''),raw.get('agreement','')) if value),
        raw.get('recipient',''),
    )
    if performance:
        _set_presentation(fields,'performance',performance,origin='services_performance_composition')
    due=_loan_due_phrase(raw.get('due_date',''))
    if due:
        _set_presentation(fields,'due_date',due,origin='services_due_date_reference')
    facts=_service_violation_sentence(raw.get('facts',''))
    if facts:
        _set_presentation(fields,'facts',facts,origin='services_violation_composition')


def _confirmed_plan_items(state):
    """Read both the legacy ledger and the new formula plan defensively.

    The plan is intentionally data-driven.  This adapter accepts the stable
    item shape used by the registry without coupling document composition to
    a particular formula implementation.  Only a calculated/confirmed item
    can become an operative monetary demand.
    """
    items=[]
    plan=state.get('calculation_plan',{})
    if isinstance(plan,dict):
        plan_status=plan.get('status')
        if plan_status in {'calculated','confirmed','complete'}:
            items.extend(plan.get('items') or [])
        for rule in plan.get('rules') or []:
            if isinstance(rule,dict) and rule.get('status') in {'calculated','confirmed','complete'}:
                items.extend(rule.get('items') or [])
    ledger=state.get('calculation_ledger',{})
    if not items and isinstance(ledger,dict) and ledger.get('status')=='confirmed':
        items.extend(ledger.get('items') or [])
    stable=[]
    primary_kinds={'principal','damage'}

    def flag(value,default):
        """Accept old JSON booleans without treating the string ``false`` as true."""
        if value is None:return default
        if isinstance(value,str):return value.strip().lower() not in {'0','false','no','нет'}
        return bool(value)

    for item in items:
        if not isinstance(item,dict):
            continue
        value=item.get('value')
        try:
            Decimal(str(value))
        except (InvalidOperation,TypeError,ValueError):
            continue
        # The registry uses ``include_*``; tolerate an earlier experimental
        # spelling in persisted chats.  A state duty is a procedural payment,
        # not a monetary prayer against the opposing party, unless a future
        # dedicated reimbursement rule says otherwise.
        kind=str(item.get('kind') or 'other')
        default_price=kind not in {'state_duty','court_cost','claim_price_reference'}
        default_recovery=kind not in {'state_duty','claim_price_reference'}
        candidate={'kind':kind,'label':str(item.get('label') or 'Дополнительная сумма'),
                   'value':str(value),
                   'include_in_claim_price':flag(item.get('include_in_claim_price',item.get('included_in_claim_price')),default_price),
                   'include_in_recovery_total':flag(item.get('include_in_recovery_total'),default_recovery)}
        # A legacy plan can retain both the ordinary amount as ``principal``
        # and the same repair cost as ``damage``.  It is one primary monetary
        # demand, unlike two equal ancillary costs with different purposes.
        mirrored_primary=any(
            old['kind'] in primary_kinds and candidate['kind'] in primary_kinds
            and Decimal(old['value'])==Decimal(candidate['value'])
            for old in stable
        )
        if not mirrored_primary and not any(old['kind']==candidate['kind'] and Decimal(old['value'])==Decimal(candidate['value']) for old in stable):
            stable.append(candidate)
    return stable


def _money_requests_for_debt_claim(state,fields):
    """Build the monetary prayers once from typed/confirmed calculations.

    Raw user prose such as "взыскать долг, проценты и расходы" is evidence
    of intent, but it is not a calculation.  The principal is always derived
    from the typed amount; a regulated item is added only after the shared
    calculation plan has confirmed its value.
    """
    from app.services.document_case_composition import _money
    scenario=state['scenario'];amount=fields.get('amount',{})
    if amount.get('status')!='filled' or not amount.get('value'):
        return None
    actions={
        'claim_debt_loan':'основную задолженность по договору займа',
        'claim_debt_rent':'задолженность по арендной плате',
        'claim_debt_services':'основную задолженность по оплате оказанных услуг',
        'claim_debt_supply':'задолженность по договору поставки',
    }
    result=['Взыскать с ответчика в пользу истца '+actions[scenario]+' в размере '+_money(amount['value'])+'.']
    for item in _confirmed_plan_items(state):
        if item['kind'] in {'principal','damage','state_duty','claim_price_reference'} or not item.get('include_in_recovery_total',True):
            continue
        money=_money(item['value'])
        if item['kind']=='interest':
            result.append('Взыскать проценты за пользование чужими денежными средствами в размере '+money+'.')
        elif item['kind']=='penalty':
            result.append('Взыскать неустойку в размере '+money+'.')
        elif item['kind'] in {'expenses','valuation'}:
            label='судебные расходы' if item['kind']=='expenses' else 'расходы на оценку'
            result.append('Взыскать '+label+' в размере '+money+'.')
        elif item['kind']=='moral':
            result.append('Взыскать компенсацию морального вреда в размере '+money+'.')
        else:
            result.append('Взыскать '+item['label'].lower().rstrip('.')+' в размере '+money+'.')
    return '\n'.join(result)


def _confirmed_calculation_text(state,fields):
    """Render a plan-led calculation without trusting a conversational slot."""
    from app.services.document_case_composition import _money
    # State duty is a procedural payment, not a sum requested from the
    # opposing party.  It belongs in its own requisites block and must never
    # enter the equation headed "Расчёт денежных требований".  The same rule
    # keeps a claim-price reference out of a recovery calculation.
    items=[item for item in _confirmed_plan_items(state)
           if item['kind'] not in {'state_duty','claim_price_reference'}
           and item.get('include_in_recovery_total',True)]
    if not items:
        return None
    parts=[]
    for item in items:
        parts.append(item['label']+' — '+_money(item['value']))
    total=sum((Decimal(item['value']) for item in items),Decimal('0'))
    if total<=0:
        return None
    expression=' + '.join(_money(item['value']).removesuffix(' рублей') for item in items)
    return 'Расчёт заявленных денежных требований: '+'; '.join(parts)+'. Итого: '+expression+' = '+_money(total)+'.'


def _compose_debt_claim_presentation(state,fields):
    """Give every debt-claim template one source-bound chronology.

    Older sessions often contain an entire opening story in several fields.
    This is a presentation-only composition: original answers remain intact
    in state, while the document receives each proven fact in one suitable
    slot rather than repeating it under "facts", "agreement" and "pretrial".
    """
    if state.get('scenario') not in DEBT_CLAIM_SCENARIOS:
        return
    raw={key:_clean_space(source_text(state,key)) for key in state.get('fields',{})}
    # Repair persisted chats too: a one-word absence is not a requisite and
    # must never be printed below a postal address.
    for key in ('sender_details','recipient_details','party_details'):
        if _is_absence_reply(raw.get(key,'')):
            _set_presentation(fields,key,None,status='unknown',origin='absence_normalization')
    if _is_absence_reply(raw.get('other_participants','')):
        _set_presentation(fields,'other_participants',None,status='not_applicable',origin='absence_normalization')

    if state['scenario']=='claim_debt_loan':
        combined=' '.join(raw.get(key,'') for key in ('agreement','transfer','due_date','pretrial','facts'))
        from app.services.document_case_composition import _money
        amount=fields.get('amount',{}).get('value')
        formatted_amount=_money(amount) if amount else ''
        agreement=_loan_agreement_sentence(raw.get('agreement') or combined)
        if agreement:
            _set_presentation(fields,'agreement',agreement)
        transfer=_loan_transfer_sentence(raw.get('transfer') or combined,formatted_amount)
        if transfer:
            _set_presentation(fields,'transfer',transfer)
        due=_loan_due_phrase(raw.get('due_date') or combined)
        if due:
            _set_presentation(fields,'due_date',due)
        payments=fields.get('payments',{})
        if (payments.get('status')=='not_applicable' or _is_absence_reply(raw.get('payments',''))
                or re.search(r'\bне\s+вернул\w*\b|\bплатеж\w*\s+не\s+было\b|'
                             r'\bпусть\s+вс[её].{0,25}\b(?:верн|возвращ)',raw.get('payments',''),re.I)):
            # The surrounding template already says "Фактически полученные в
            # счёт возврата платежи".  Store a phrase here so the final
            # sentence is grammatical rather than a label followed by another
            # complete sentence.
            _set_presentation(fields,'payments','не поступали')
        pretrial=_loan_pretrial_sentence(raw.get('pretrial') or combined)
        if pretrial:
            _set_presentation(fields,'pretrial',pretrial)

    attachments=source_text(state,'attachments') if 'attachments' in state['fields'] else ''
    _compose_attachment_list(state,fields,attachments)

    # A field may have been completed from the opening description, then a
    # later question received the same narrative again.  Prefer the named
    # chronology and remove only a near-verbatim duplicate from the residual
    # facts slot.  The comparison intentionally uses source evidence, never
    # model-edited copy.
    facts=raw.get('facts','')
    structured=[raw.get(key,'') for key in ('agreement','transfer','performance','property','goods','due_date','payments','pretrial')]
    if facts and _repeats_structured_debt_facts(facts,structured):
        _set_presentation(fields,'facts',None,status='not_applicable',origin='duplicate_structured_fact')
    requests=_money_requests_for_debt_claim(state,fields)
    if requests:
        _set_presentation(fields,'requests',requests,origin='typed_request_composition')
    calculation=_confirmed_calculation_text(state,fields)
    if calculation and 'calculation' in fields:
        _set_presentation(fields,'calculation',calculation,origin='calculation_plan_composition')


def _compose_damage_property_presentation(state, fields):
    """Keep a legacy multi-fact answer out of a short property paragraph.

    The raw interview answer stays untouched for provenance.  This is a
    render-time repair for saved chats created before the intake splitter was
    added; it also protects exports if a remote factual extractor returns the
    full user message for the active property field.
    """
    if state.get('scenario') != 'claim_damage_property':
        return
    source = source_text(state, 'property') if 'property' in state.get('fields', {}) else ''
    if not source:
        return
    from app.services.document_form_intake import damage_property_phrase, is_dense_damage_narrative
    if not is_dense_damage_narrative(source):
        return
    compact = damage_property_phrase(source)
    if compact:
        _set_presentation(fields, 'property', compact, origin='multi_fact_property_presentation')


def form_presentation_fields(state):
    fields=deepcopy(state['fields'])
    from app.services.document_scenarios import SCENARIOS
    labels={f.key:f.label for f in SCENARIOS[state['scenario']].fields}
    # These values exist solely to guide the questionnaire (for example,
    # whether a court order was requested).  They must not become a narrative
    # paragraph or a bracketed placeholder in an older DOCX asset.
    for key in _package(state).get('intake_only_fields',[]):
        if key in fields:
            fields[key]={**fields[key], 'status':'not_applicable', 'value':None,
                         'origin':'intake_only_metadata'}
    for key in form_narrative_keys(state):
        candidate=state.get('draft_fields',{}).get(key)
        if candidate:fields[key]['value']=candidate
        else:
            fields[key].update(value='['+labels[key].lower()+']',origin='unverified_draft_slot')
    for key in requisite_keys(state):
        stored=fields.get(key,{})
        if stored.get('status')!='filled':continue
        value=clean_requisite(key,stored['value'])
        if value is None:stored.update(status='review_required',value=None)
        else:
            if key in {'sender_details','recipient_details','party_details'}:
                pair=re.fullmatch(r'(\d{1,2}[./]\d{1,2}[./]\d{4})\s+([А-ЯЁ][А-Яа-яЁё -]+)[. ]*',value)
                if pair:value='Дата рождения: '+pair[1]+'\nМесто рождения: '+pair[2].strip(' .')
            stored['value']=value
    key=state['scenario']
    if key=='power_of_attorney' and fields.get('recipient',{}).get('status')=='filled':
        from app.services.document_authority_facts import recipient_accusative
        fields['recipient']['value']=recipient_accusative(state)
    # The operative amount comes from the typed source field, never a model's
    # summary.  Some DOCX assets intentionally mark ``amount`` as
    # intake-only because the number is rendered inside the calculation or
    # operative request.  At this point the presentation copy has already
    # hidden those intake-only fields, so reading from it would silently drop
    # a confirmed amount from every affected form.
    amount=state.get('fields',{}).get('amount',{})
    money_actions={
        'claim_debt_loan':'основную задолженность по договору займа',
        'claim_debt_rent':'задолженность по арендной плате',
        'claim_debt_services':'основную задолженность по оплате оказанных услуг',
        'claim_debt_supply':'основную задолженность по договору поставки',
        'claim_rent_deposit':'невозвращённый обеспечительный платёж',
        'claim_damage_flood':'возмещение имущественного ущерба от залива квартиры',
        'claim_damage_property':'возмещение имущественного ущерба',
        'claim_consumer_late_delivery':'возврат предварительной оплаты за товар',
        'claim_consumer_defective_goods':'возврат уплаченной за товар суммы',
        'claim_labor_salary':'невыплаченную заработную плату',
    }
    if key in money_actions and amount.get('status')=='filled':
        from app.services.document_case_composition import _money
        base='Взыскать с ответчика в пользу истца '+money_actions[key]+' в размере '+_money(amount['value'])+'.'
        current=fields.get('requests',{});text=current.get('value') or ''
        # Preserve genuinely additional requests. A generic principal-only
        # request is already represented by the complete operative clause.
        primary=bool(re.search(r'долг|средств|деньг|возмещ|ущерб|зарплат|заработн|обеспечител|депозит|взыск|верну|возврат|оплат|выплат',source_text(state,'requests') if 'requests' in state['fields'] else '',re.I))
        extra=bool(re.search(r'процент|неустойк|морал|расход|штраф|компенсац|иные|дополнител|обязать|запрет|признать|предоставить|устранить|извин',text,re.I))
        if primary and not re.search(r'не (?:взыск|треб|верну)',text,re.I):
            fields['requests']={**current,'status':'filled','value':base+('\n'+text if extra else ''),'origin':'typed_request_composition'}
    if key.startswith('pretense_consumer_') and amount.get('status')=='filled':
        request=state['fields'].get('requests',{}).get('value') or ''
        if re.fullmatch(r'\s*(?:(?:прошу|хочу|требую)\s+)?(?:возврат (?:оплаты|денег|уплаченной суммы)|вернуть (?:деньги|оплату|уплаченную сумму))[.! ]*',request,re.I):
            from app.services.document_presentation import format_money
            fields['requests']={**fields.get('requests',{}),'status':'filled','value':'Прошу вернуть уплаченную сумму в размере '+format_money(amount['value'])+' рублей.','origin':'typed_request_composition'}
    if 'consumer' in key:
        purchase=state.get('fields',{}).get('purchase',{})
        # A missing purchase date does not erase the already supplied item
        # and price from an explicitly requested draft.
        if purchase.get('status')=='incomplete' and (purchase.get('error') or '').startswith('Когда приобретён товар?'):
            candidate=local_candidate('purchase',purchase.get('value') or '', 'sentence',key)
            if candidate:
                fields['purchase']={**purchase,'status':'filled', 'value':candidate+' Дата приобретения: [дата покупки].'}
    if key in {'order_alimony','claim_alimony_share'}:
        share=fields.get('share',{}).get('value') or ''
        fraction=re.search(r'\b(\d+)\s*/\s*(\d+)\b',share)
        child=fields.get('children',{}).get('value') or '[сведения о ребёнке]'
        start=fields.get('start',{}).get('value') or '[начало взыскания]'
        if re.search(r'настоящего времени|сейчас|обращени|подачи',start,re.I):start='со дня обращения в суд'
        if fraction:
            prefix='Выдать судебный приказ, которым взыскать с должника в пользу взыскателя' if key=='order_alimony' else 'Взыскать с ответчика в пользу истца'
            text=prefix+' алименты на содержание несовершеннолетнего ребёнка (сведения: '+child.rstrip(' .')+') в размере '+fraction[1]+'/'+fraction[2]+' заработка и иного дохода обязанного родителя, начиная '+start.rstrip(' .').lower()+', до достижения ребёнком совершеннолетия.'
            fields['requests']={**fields.get('requests',{}),'status':'filled','value':text,'origin':'typed_request_composition'}
    # Do this last: a debt calculation is composed from typed monetary facts
    # and a confirmed plan, so it must not be overwritten by a raw request
    # that happens to mention the same principal debt.
    _compose_debt_claim_presentation(state,fields)
    _compose_debt_pretense_presentation(state,fields)
    _compose_damage_property_presentation(state,fields)
    if key=='contract_work':
        from app.services.document_contract_facts import TERM_KEYS
        replacements={'исполнитель':'Подрядчик','исполнителя':'Подрядчика','исполнителю':'Подрядчику','исполнителем':'Подрядчиком'}
        for field_key in TERM_KEYS:
            item=fields.get(field_key,{})
            if item.get('value'):
                item['value']=re.sub(r'\bисполнител(?:ь|я|ю|ем)\b',lambda m:replacements[m[0].lower()],item['value'],flags=re.I)
    return align_narrator_gender(fields,state)
