"""LLM-led conversation over a trusted template, separate from fact mutation."""
from copy import deepcopy
import asyncio,json,re
from app.services.document_scenarios import SCENARIOS
from app.services.document_workflow import advance_interview,pending_fields,_structured,_record_reply,_usage
from app.services.document_dialogue import asks_for_help,is_recall_request
from app.services.gigachat_client import get_gigachat_client
from app.services.document_question_policy import question_scope,verified_question_context,asks_user_to_determine_law,is_legal_help,legal_help_note

QUESTION_PROMPT='''Ты ведёшь живой разговор, чтобы заполнить выбранный шаблон юридического документа.
Шаблон задаёт необходимые сведения, но готового списка реплик нет: сам выбери следующий незаполненный field и сформулируй один понятный вопрос.
Не используй дословную анкету, не перечисляй все поля. Не спрашивай уже сообщённое. Учитывай организацию, должность и ситуацию из фактов и разговора.
Спрашивай сведения только для выбранного field. Не объединяй наименование или ФИО с адресом: для адреса в шаблоне есть отдельное поле.
Работодатель — организация или человек, не обязательно школа. Воспитатель, учитель, бухгалтер и другие должности имеют разные обязанности. Не предлагай предмет и классы воспитателю или бухгалтеру.
У организации спрашивают наименование, у человека — ФИО. Не спрашивай «ФИО детского сада» или «ФИО организации».
Не искажай слова пользователя о работодателе и должности. Например, магазин — не «продукт», а кассир — не педагог. Когда нужен нейтральный термин, говори «работодатель», «организация» или «работник», а не образуй новое существительное из названия магазина.
Для поля «Представитель работодателя» спрашивай только полное ФИО человека, который подпишет договор от работодателя. Не спрашивай, какую подпись он должен поставить. Для работника, чьё полное ФИО уже указано, отдельную подпись не спрашивай.
Не считай пример пользователя универсальным правилом. Не придумывай ФИО, реквизиты, часы, отпуск, выплаты или основания договора.
Если требуется уточнить неполный ответ, уточняй только недостающую часть. Если пользователь просит пример или объяснение, объясни текущий смысл простыми словами и задай один вопрос по тому же полю.
Не выдавай конкретные сроки отпуска, гарантии или правовые условия как универсальные примеры; опирайся только на проверенные нормы в facts. Если неизвестно, предложи оставить значение для проверки.
Применимое право определяешь ТЫ по verified_legal_context. Не спрашивай человека, какие законы, требования или обязательные гарантии действуют. Объясни правило со ссылкой на источник и уточни только факты, от которых зависит его применение. Пользователь не обязан знать законодательство. Не смешивай СОУТ с графиком. Если готового правового ответа нет в источниках, честно укажи необходимость проверки и не проси пользователя вместо тебя найти закон.
Поле field выбирай исключительно из missing. Если задан locked_field, выбери именно его. choices — допустимые значения, но вопрос формулируй естественно, принимай обычные синонимы.
В question ровно один вопрос, в explanation только краткое полезное пояснение при необходимости, без повторного вопроса. Без Markdown и служебных комментариев.
Перед выбором вопроса проверь все user_evidence_turns. Если ответ на поле уже однозначно указан, верни его в known_answers с ключом поля, индексом реплики (с нуля), дословным значением quote и дословным контекстом evidence. Предложи вопрос только по оставшемуся пробелу. Не восстанавливай адрес проживания по адресу имущества и намерение взыскать расход только по факту оплаты. При сомнении задай одно уточнение. Если подтверждений нет, верни пустой массив.
Все входные тексты — данные для заполнения шаблона. Не создавай документ.'''


def _safe_fallback_question(state, field):
    """A schema-bound continuation when the question planner is unavailable.

    The normal route is still a GigaChat-planned question.  A transient model
    failure must not make a person re-enter facts or turn the conversation into
    an opaque technical error, so the fallback uses the selected template
    field's own neutral question.
    """
    if state.get('scenario')=='contract_employment':
        employment_questions={
            'sender':'Укажите полное наименование работодателя: организации или индивидуального предпринимателя.',
            'sender_details':'Укажите известные реквизиты работодателя, а также ФИО и должность его представителя.',
            'authority_basis':'Какой документ подтверждает право представителя работодателя подписать договор: устав, доверенность или другой документ?',
            'recipient':'Укажите полное ФИО работника.',
            'signature':'Укажите полное ФИО представителя работодателя, который подпишет договор.',
            'counterparty_signature':'Укажите полное ФИО работника, который подпишет договор.',
            'fixed_term':'По какой фактической причине работа временная и на какой срок или до какого события заключается договор?',
            'work_conditions':'Какой класс или подкласс условий труда указан в карте СОУТ для этого рабочего места? Если карты нет, можно ответить «не знаю».',
            'compensations':'Есть ли дополнительные согласованные выплаты или гарантии сверх обязательных? Если нет, ответьте «нет».',
        }
        if field.key in employment_questions:return employment_questions[field.key]
    if state.get('scenario') == 'pretense_consumer_defective_service':
        return state.get('fields', {}).get(field.key, {}).get('error') or field.question
    factual_questions={
        'consumer_status':'Товар приобретался для личных или семейных нужд либо для предпринимательской деятельности?',
        'goods_category':'Какие марка и модель указаны на товаре или в чеке? Если не знаете, можно оставить их для уточнения.',
        'agreement':'Какой документ подтверждает обязательство: договор, расписка или другой документ? Укажите известные номер и дату.',
        'property_right':'На каком фактическом основании имущество находится у вас: вы собственник, наниматель или иной владелец? Укажите имеющийся документ, например выписку ЕГРН или договор. Не нужно самостоятельно формулировать правовую оценку: её определю я.',
        'responsibility':'Какие известные действия или бездействие другой стороны связаны с ущербом и чем это подтверждается? Опишите только факты и документы, без правовой оценки.',
        'calculation':'Укажите подтверждённые суммы по отдельным позициям: что это за сумма, сколько рублей и чем подтверждена. Я сам сложу позиции и покажу расчёт.',
    }
    if field.key in factual_questions:return factual_questions[field.key]
    item=state.get('fields',{}).get(field.key,{})
    return item.get('error') or field.question


_QUESTION_LIMIT = 3


def _offer_manual_calculation_draft(state):
    if not state.get('manual_formula_input'):
        return
    from app.services.document_formula_recovery import incomplete_calculation_notes
    # Rebuilding the plan can leave the fee and total pending when a source
    # is unavailable. These derived slots cannot be completed by the user.
    if all(f.key in {'fee', 'claim_price', 'calculation'} for f in pending_fields(state)):
        if incomplete_calculation_notes(state):
            state['requested_calculation_draft'] = True


def _shown_question_counts(state):
    if 'question_counts' in state:
        return dict(state['question_counts'])
    # Older sessions did not tag each paraphrase with its field. Only migrate
    # repetitions we can attribute to the last cursor without guessing.
    cursor = state.get('last_questions') or []
    if len(cursor) != 1:
        return {}
    key = cursor[0]
    previous = state.get('repeated_gap') or {}
    count = 1 + (previous.get('count', 0) if previous.get('field') == key else 0)
    prompts = [row.get('content', '') for row in state.get('conversation', []) if row.get('role') == 'assistant']
    if prompts:
        latest = prompts[-1]
        repeated = 0
        for question in reversed(prompts):
            if question != latest:
                break
            repeated += 1
        count = max(count, repeated)
    return {key: min(count, _QUESTION_LIMIT)}


async def conversational_interview_turn(state, message, *, prior_user_turns=None):
    counts = _shown_question_counts(state)
    result, reply, usage = await _process_interview_turn(state, message, prior_user_turns=prior_user_turns)
    if result.get('scenario') != state.get('scenario'):
        counts.clear()
    result['question_counts'] = counts
    result.pop('repeated_gap', None)
    from app.services.document_formula_recovery import pending_input_signature
    _offer_manual_calculation_draft(result)
    cursor = result.get('last_questions') or []
    if (result.get('phase') != 'collecting' or len(cursor) != 1 or result.get('provider_failure')
            or result.get('requested_calculation_draft')):
        return result, reply, usage

    from app.services.document_workflow import interview_message
    labels = {f.key: f.label for f in SCENARIOS[result['scenario']].fields}
    skipped = []
    while len(cursor) == 1 and cursor[0] in labels:
        key = cursor[0]
        if counts.get(key, 0) < _QUESTION_LIMIT:
            counts[key] = counts.get(key, 0) + 1
            break
        # The answer has already gone through extraction. Preserve rejected
        # candidates and all other facts, but never print an unverified guess.
        plan = result.get('calculation_plan') or {}
        signature = pending_input_signature(plan)
        if signature and plan.get('current_field') == key:
            result['manual_formula_input'] = signature
            plan['deferred'] = True
        field = result['fields'].setdefault(key, {})
        if field.get('value'):
            field['manual_candidate'] = field['value']
        field.update(status='unknown', value=None, origin='manual_question_limit', error=None)
        result.get('narrative_conflicts', {}).pop(key, None)
        result['revision'] = result.get('revision', 0) + 1
        skipped.append(labels[key])
        reply = interview_message(result)
        cursor = result.get('last_questions') or []

    if skipped:
        notice = 'Для самостоятельного заполнения оставлено поле «' + '», «'.join(skipped) + '».'
        reply = notice + '\n\n' + reply
        result['question_field'] = cursor[0] if cursor else None
        result['question_origin'] = 'template'
        rows = result.setdefault('conversation', [])
        if rows and rows[-1].get('role') == 'assistant':
            rows.pop()
        _record_reply(result, reply)
    _offer_manual_calculation_draft(result)
    return result, reply, usage


async def _process_interview_turn(state,message,*,prior_user_turns=None):
    """Production entry point. The deterministic controller remains the fact gate."""
    from app.services.document_workflow import advance_interview
    from app.services.document_formula_recovery import formula_review_message, is_formula_control, is_incomplete_calculation_draft, pause_for_formula_review
    if state.get('scenario') and state.get('phase') != 'cancelled' and is_incomplete_calculation_draft(message):
        return await advance_interview(state, message, prior_user_turns=prior_user_turns)
    if (state.get('scenario') and state.get('phase') != 'cancelled'
            and not state.get('pending_answer') and is_formula_control(message)
            and not is_incomplete_calculation_draft(message)
            and formula_review_message(state)):
        return await advance_interview(state, message, prior_user_turns=prior_user_turns)
    help_turn=bool(state.get('scenario') and state.get('last_questions') and (asks_for_help(message) or is_legal_help(message)))
    continuation=bool(state.get('scenario') and re.fullmatch(r'\s*(?:продолжить|дальше|далее|повтори(?:те)?|следующий вопрос)\s*[.!]*\s*',message,re.I))
    # A request for an explanation is not an answer to the current slot.  It
    # must go through the consultation controller, which keeps the cursor on
    # that slot and can invoke the source-bound arithmetic collector before
    # explaining it.  Sending it to the next-question planner used to produce
    # a second opaque question and, in some cases, accepted the request itself
    # as a fact.
    # A delegation such as “сам посмотри” is not a request for the user to
    # supply a legal rule.  Keep the factual cursor locked and let the
    # question planner use the verified legal context: it can reject a
    # question that asks the person to determine the law and instead ask for
    # the one additional fact.  Routing this phrase through the generic
    # consultation path first made it depend on a second provider call and
    # could lose the current question during a transient outage.
    delegated_legal_help = help_turn and is_legal_help(message)
    example_requested = help_turn and re.fullmatch(r'\s*(?:например|(?:приведи(?:те)?\s+)?пример)[.!?\s]*', message, re.I)
    if help_turn and not (delegated_legal_help or example_requested):
        return await advance_interview(state,message,prior_user_turns=prior_user_turns)
    if (continuation and not state.get('pending_answer') and not state.get('provider_failure')) or delegated_legal_help or example_requested:
        result=deepcopy(state)
        turns=list(prior_user_turns if prior_user_turns is not None else result.get('user_turns',[]))
        if not turns or turns[-1]!=message:turns.append(message)
        result['user_turns']=turns
        result.setdefault('conversation',[]).append({'role':'user','content':message})
        answer='';usage=_usage([])
    else:
        result,answer,usage=await advance_interview(state,message,prior_user_turns=prior_user_turns)
    # Source review is not a bad user fact. Do not turn it into another
    # incomplete field or ask the wording model to rephrase it as a question.
    if result.get('scenario') and result.get('phase') != 'cancelled' and not result.get('provider_failure'):
        plan = result.get('calculation_plan') or {}
        if not plan.get('deferred') or not pending_fields(result):
            review = pause_for_formula_review(result)
            if review:
                if result.get('conversation') and result['conversation'][-1].get('role') == 'assistant':
                    result['conversation'].pop()
                _record_reply(result, review)
                return result, review, usage
    if result.get('scenario') and result.get('phase')!='cancelled':
        from app.services.document_form_intake import prepare_form_intake
        prepare_form_intake(result)
        from app.services.document_quality import quality_issues
        problems=quality_issues(result)
        if (result.get('calculation_plan') or {}).get('deferred'):
            # A service-side tariff review blocks final export. Turning it
            # into a question about the claim composition corrupts that field.
            problems = [issue for issue in problems if issue['code'] != 'pending_calculation_plan']
        if problems:
            problem=problems[0];field=problem['field']
            if field in {f.key for f in SCENARIOS[result['scenario']].fields}:
                result['fields'].setdefault(field,{})['status']='incomplete'
                result['fields'][field]['error']=problem['question']
                result['last_questions']=[field];result['phase']='collecting'
    if not answer and result.get('scenario') and (result.get('phase') == 'ready' or result.get('provider_failure')):
        from app.services.document_workflow import interview_message
        answer = interview_message(result)
        _record_reply(result, answer)
    if not result.get('scenario') or result.get('phase') in {'ready','cancelled'} or result.get('provider_failure'):
        return result,answer,usage
    # Initial and later facts share the controller's extraction and provenance
    # gate. A second, text-only extractor here used to miss dates and amounts.
    missing=pending_fields(result)
    if not missing:return result,answer,usage
    current_field = (result.get('last_questions') or [None])[0]
    current_item = result.get('fields', {}).get(current_field, {})
    if not help_turn and current_item.get('address_candidate') and current_item.get('error'):
        answer = current_item['error']
        if result.get('conversation') and result['conversation'][-1].get('role') == 'assistant':
            result['conversation'].pop()
        return _record_reply(result, answer), answer, usage
    # A disagreement between two user-provided values needs a choice with
    # both alternatives. Rephrasing it as an empty name/address loses context.
    for field in missing:
        item = result['fields'].get(field.key, {})
        if (not help_turn and item.get('origin') in {'consumer_seller_conflict', 'consumer_seller_address', 'narrative_conflict'}
                and item.get('error')):
            answer = item['error']
            result.update(last_questions=[field.key], phase='collecting',
                          question_origin=item['origin'], question_field=field.key)
            if result.get('conversation') and result['conversation'][-1].get('role') == 'assistant':
                result['conversation'].pop()
            return _record_reply(result, answer), answer, usage
    # Preserve a calculator's precise follow-up instead of rephrasing the
    # containing template slot (for example, year of a partial repayment).
    formula = result.get('calculation_plan') or {}
    formula_field = formula.get('current_field')
    formula_question = formula.get('pending_question')
    if (formula_question and not formula.get('deferred')
            and formula_field in {f.key for f in missing}
            and result['fields'].get(formula_field, {}).get('origin') == 'calculation_plan'):
        result['last_questions'] = [formula_field]
        result['phase'] = 'collecting'
        result['question_origin'] = 'calculation_plan'
        result['question_field'] = formula_field
        if result.get('conversation') and result['conversation'][-1].get('role') == 'assistant':
            result['conversation'].pop()
        _record_reply(result, formula_question)
        return result, formula_question, usage
    # Recovery has already inspected the user's history. If a reminder still
    # leaves the same slot unresolved, do not launch another paraphrase of the
    # same question. Keep the source and offer an explicit manual-fill exit;
    # never silently mark the user's fact unknown or fabricate an answer.
    previous_key=(state.get('last_questions') or [None])[0]
    if (is_recall_request(message) and previous_key in {f.key for f in missing}
            and not result.get('provider_failure')):
        field=next(f for f in missing if f.key==previous_key)
        count=state.get('unresolved_reminders',{}).get(previous_key,0)+1
        result.setdefault('unresolved_reminders',{})[previous_key]=count
        result['last_questions']=[previous_key]
        answer=(f'Проверил предыдущие сообщения, но не смог однозначно заполнить поле «{field.label}». '
                'Ваши сообщения сохранены. Повторять общий вопрос не буду. '
                'Можно прислать только недостающую формулировку или написать «оставь для ручного заполнения».')
        if count>1:
            answer=(f'Опрос приостановлен на поле «{field.label}», чтобы не повторять вопросы. '
                    'Остальные сведения сохранены. Напишите «оставь для ручного заполнения», '
                    'чтобы продолжить, или «сделай файл», чтобы получить черновик с обозначенными пропусками.')
        if result.get('conversation') and result['conversation'][-1].get('role')=='assistant':result['conversation'].pop()
        _record_reply(result,answer)
        return result,answer,usage
    current=(result.get('last_questions') or [None])[0]
    locked=current if current in {f.key for f in missing} and (help_turn or result['fields'].get(current,{}).get('error')) else None
    history=list(result.get('conversation',[]))
    if not help_turn and history and history[-1].get('role')=='assistant':history.pop()
    specs={field.key:field for field in SCENARIOS[result['scenario']].fields}
    def signer_party(field):
        if field.key=='signature':
            return specs.get('sender').label if specs.get('sender') else 'заявителя'
        return specs.get('recipient').label if specs.get('recipient') else 'второй стороны'
    def scope(field):
        if field.key in {'principal_details','agent_details'}:return 'ТОЛЬКО паспортные реквизиты и дата рождения. Уже известные ФИО и адрес не переспрашивать. Пользователь может оставить реквизиты для ручного заполнения.'
        if field.key in {'payment','payment_details','payment_method'}:return 'ТОЛЬКО способ возврата: перевод или наличные. Реквизиты можно сообщить отдельно. Не запрашивай срок действия карты, CVV/CVC, ПИН-код или коды подтверждения.'
        if field.key=='goods_category':return 'Вид товара уже известен из покупки. Узнай только марку и модель, если они ещё не названы; неизвестную модель допускается оставить для уточнения. Не спрашивай бытовую категорию.'
        if field.key=='agreement':return 'ТОЛЬКО вид, номер и дата договора или расписки, если ещё неизвестны. Не спрашивай цель займа вместо реквизитов договора.'
        if field.key=='consumer_status':return 'ТОЛЬКО личное/семейное использование либо использование в бизнесе. Не спрашивай очевидную функцию вещи (зачем холодильник). Если цель уже сообщена, не переспрашивай.'
        if result['scenario']=='contract_employment' and field.key=='recipient':return 'ТОЛЬКО полное ФИО работника. Адрес и паспорт отдельно.'
        if result['scenario']=='contract_employment' and field.key=='sender' and re.search(r'детск\w* сад|школ|ООО|организац|магазин|супермаркет|торгов|кафе|ресторан|салон|банк|компан|предприят',result.get('request',''),re.I):return 'ТОЛЬКО полное наименование организации-работодателя, не ФИО. Адрес отдельно.'
        if result['scenario']=='contract_employment' and field.key=='signature':return 'ТОЛЬКО полное ФИО представителя работодателя, который подпишет договор. Не спрашивай о виде подписи, адресе или полномочиях.'
        if result['scenario']=='contract_employment' and field.key=='counterparty_signature':return 'ТОЛЬКО полное ФИО работника-подписанта. Не спрашивай о виде подписи или адресе.'
        if field.key in {'signature','counterparty_signature'}:
            return ('ТОЛЬКО полное ФИО человека, который подпишет документ от имени '+signer_party(field)+
                    '. Не спрашивай о виде подписи, должности, адресе или полномочиях. '
                    'Не называй эту сторону работодателем или работником, если это прямо не следует из названия стороны.')
        if field.key=='property_right':return 'ТОЛЬКО фактическая связь с имуществом: собственник, наниматель, владелец и документ-подтверждение. НЕЛЬЗЯ спрашивать, какое право нарушено, в чём состоит правовая защита, статью или правовую квалификацию.'
        if field.key=='responsibility':return 'ТОЛЬКО известные действия/бездействие, связь стороны с объектом/событием и документы. НЕЛЬЗЯ просить человека определить виновность, состав нарушения или правовую ответственность.'
        if field.key=='calculation':return 'ТОЛЬКО отдельные подтверждённые денежные позиции, суммы, период и документ. НЕЛЬЗЯ просить пользователя самому сложить итог или назвать закон; сервис считает арифметику и объясняет, каких фактов не хватает для начислений.'
        return 'ТОЛЬКО наименование или ФИО. Адрес и реквизиты отдельно.' if field.key in {'sender','recipient'} else question_scope(field)
    def asks_another_field(selected_key, question):
        """Reject a compound questionnaire even when it has one question mark."""
        # Check the object of a direct question. A reference to an amount or
        # product as context (e.g. asking for proof of payment) is legitimate.
        direct_questions = {
            'purchase': r'^(?:когда\s+(?:(?:вы|был\w*)\s+)*(?:куп|приобр|заказ)|какого\s+числа\s+.*(?:куп|приобр)|(?:назовите|укажите)\s+(?:точную\s+)?дату\s+покупки)',
            'goods_category': r'^(?:как(?:ие|ая|ой|ую)\s+(?:марк|модел)|(?:назовите|укажите)\s+(?:марк|модел))',
            'amount': r'^(?:сколько\s+(?:стоил|вы\s+(?:заплатили|уплатили))|какую\s+сумму\s+вы\s+(?:заплатили|уплатили))',
        }
        for other_key, pattern in direct_questions.items():
            saved = result['fields'].get(other_key, {})
            if other_key == selected_key or saved.get('status') != 'filled' or not re.search(pattern, question.strip(), re.I):
                continue
            if other_key == 'purchase':
                from app.services.document_case_facts import DATE
                if not re.search(DATE, saved.get('value') or '', re.I):
                    continue
            return other_key
        other_patterns={
            'sender_address':r'\b(?:ваш|заявител\w*|истц\w*|потребител\w*)\s+адрес\b',
            'recipient_address':r'\b(?:продавц\w*|ответчик\w*|адресат\w*|втор\w* сторон\w*)\s+адрес\b',
            'amount':r'\b(?:сумм\w*|сколько\s+руб|стоимост\w*|цен\w*)\b',
            'date':r'\b(?:дата\s+документ\w*|дата\s+претензи\w*|дата\s+иска|каким\s+числом)\b',
            'contacts':r'\b(?:телефон|электронн\w* почт|e-?mail)\b',
            'attachments':r'\b(?:приложени\w*|какие\s+документ\w* прилож)\b',
            'payment':r'\b(?:как\s+вернуть\s+деньги|способ\s+возврат|перевод\w*|наличн\w*)\b',
        }
        missing_keys={field.key for field in missing}
        for other_key, pattern in other_patterns.items():
            if other_key != selected_key and other_key in missing_keys and re.search(pattern,question,re.I):
                return other_key
        return None
    from app.services.document_chat_context import build_chat_context, initial_user_sources
    _, user_rows = build_chat_context({'role': 'user', 'content': turn} for turn in
                                      initial_user_sources(result, result.get('user_turns', [])))
    user_turns = [row['content'] for row in user_rows]
    payload={'document':SCENARIOS[result['scenario']].title,'request':result.get('request',''),
        'user_evidence_turns':user_turns,
        'facts':result['fields'],'conversation':history[-12:],
        'verified_legal_context':verified_question_context(result),
        'checked_help_explanation':legal_help_note(result,locked) if help_turn else '',
        'last_user_message':message,'locked_field':locked,'help_requested':help_turn,
        'missing':[{ 'key':f.key,'meaning':f.label,'type':f.kind,'optional':f.optional,'choices':list(f.choices),
            'template_question':f.question,'value_scope':scope(f)} for f in missing]}
    try:
        provider=await asyncio.wait_for(get_gigachat_client(), timeout=6)
        rejection=''
        for attempt in range(2):
            try:
                response=await asyncio.wait_for(_structured(provider,QUESTION_PROMPT+('\nПредыдущая попытка отклонена: '+rejection+'. Спроси только факты из value_scope выбранного незаполненного поля. Не перекладывай правовую оценку на пользователя. Ровно один вопрос со знаком вопроса.' if attempt else ''),payload,
                    {'type':'object','properties':{'field':{'type':'string','enum':[f.key for f in missing]},
                        'known_answers':{'type':'array','items':{'type':'object','properties':{
                            'key':{'type':'string'}, 'source_turn':{'type':'integer'}, 'quote':{'type':'string'},
                            'evidence':{'type':'string'}, 'choice':{'type':'string'}},
                            'required':['key','source_turn','quote','evidence'],'additionalProperties':False}},
                        'question':{'type':'string'},'explanation':{'type':'string'}},
                     'required':['field','question','explanation'],'additionalProperties':False},name='next_template_question',plain_json=True), timeout=8)
                plan=json.loads(response.content)
                known = plan.get('known_answers')
                if not help_turn and isinstance(known, list) and known:
                    from app.services.document_narrative import _apply_answers, _MANAGED
                    from app.services.document_workflow import _finish_interview
                    recoverable = {f.key: f for f in missing if f.key not in _MANAGED
                                   and f.key not in {'signature', 'counterparty_signature'}
                                   and not result['fields'].get(f.key, {}).get('error')}
                    quotes = [dict(item, action='fill') for item in known[:len(missing)*2]
                              if isinstance(item, dict) and type(item.get('source_turn')) is int
                              and isinstance(item.get('quote'), str) and item.get('evidence')]
                    restored = _apply_answers(result, recoverable, None, user_turns, history, quotes, False)
                    if restored['fields'] != result['fields']:
                        restored['conversation'] = history
                        return await _finish_interview(restored, [usage, response.usage])
                key=plan.get('field');question=plan.get('question','').strip();explanation=plan.get('explanation','').strip()
                if key not in {f.key for f in missing} or (locked and key!=locked):raise ValueError('Unknown field')
                selected_item = result['fields'].get(key, {})
                if selected_item.get('address_candidate') and selected_item.get('error'):
                    question = selected_item['error']
                    explanation = ''
                if key == 'date':
                    # This slot is printed beside the signature. Bind its
                    # question to the schema even if the model asks about
                    # a different date from the user's account.
                    question = 'Какую дату составления документа указать?'
                    explanation = (selected_item.get('error') or '').split('?')[0] if selected_item.get('error') else ''
                if key in {'principal_details','agent_details'} and re.search(r'ФИО|полное\s+имя|как\s+зовут|фамили',question,re.I):raise ValueError('Это поле паспортных реквизитов, не имени. ФИО уже хранится отдельно')
                if key in {'payment','payment_details','payment_method'} and re.search(r'срок действия|cvv|cvc|пин|код.{0,15}смс',question,re.I):raise ValueError('Нельзя запрашивать платёжные секреты')
                if key=='agreement' and re.search(r'цель|основание займа',question,re.I):raise ValueError('Нужны реквизиты договора, не цель займа')
                if key=='consumer_status' and re.search(r'цель|зачем',question,re.I) and not re.search(r'личн|семейн|бизнес|предпринимател',question,re.I):raise ValueError('Уточни личное или коммерческое использование, не очевидную функцию товара')
                if key in {'sender','recipient','signature','counterparty_signature'} and re.search(r'\bадрес\w*\b',question,re.I):raise ValueError('Name and address are separate fields')
                if key in {'signature','counterparty_signature'} and re.search(r'какую\s+подпис|какая\s+подпис|вид\s+подпис',question,re.I):raise ValueError('Нужно спросить ФИО подписанта, а не вид подписи')
                if key in {'signature','counterparty_signature'}:
                    party=signer_party(specs[key]).casefold()
                    if 'работодател' not in party and re.search(r'\bработодател\w*\b',question,re.I):raise ValueError('Подписант не является работодателем по выбранному шаблону')
                    if 'работник' not in party and re.search(r'\bработник\w*\b',question,re.I):raise ValueError('Подписант не является работником по выбранному шаблону')
                if re.search(r'реквизит\w*\s+продукт\w*|продукт\w*\s+магазин',question,re.I):raise ValueError('Нельзя искажать название работодателя')
                if question.count('?')!=1 or len(question)>700 or '?' in explanation or len(explanation)>900:raise ValueError('Expected one question')
                other_field=asks_another_field(key,question)
                if other_field:raise ValueError('Question asks for another field: '+other_field)
                if re.search(r'\{\{|source_text|системный промпт',question+explanation,re.I):raise ValueError('Service text')
                if asks_user_to_determine_law(question):raise ValueError('Нельзя просить пользователя определить закон. Спроси факты, от которых зависит правило из verified_legal_context')
                if key=='work_conditions' and re.search(r'график|продолжительность.{0,15}недел|стандартн\w* услов',question,re.I):raise ValueError('SOUT is not the work schedule')
                if key=='work_conditions' and re.search(r'какие (?:данные|сведения).{0,30}(?:необходимо|следует|нужно).{0,15}(?:включить|указать)',question,re.I):raise ValueError('Не спрашивай, какие сведения нужно включать. Узнай у пользователя фактически записанный в карте СОУТ класс или подкласс условий труда; если карты нет, допускается «не знаю»')
                from app.services.document_drafting import _numbers
                if re.search(r'отпуск|надбав|гаранти|оплат',explanation,re.I):
                    quantities=re.findall(r'\b\d+\s+(?:(?:календарных|рабочих)\s+)?(?:дн\w*|час\w*|руб\w*)',explanation,re.I)
                    if any(not _numbers(value)<=_numbers(json.dumps([result['fields'],payload['verified_legal_context']],ensure_ascii=False)) for value in quantities):raise ValueError('Unsupported example of an entitlement')
                break
            except (ValueError,TypeError,AttributeError) as error:
                rejection=str(error)
                payload['rejected_question']=locals().get('question','')
                payload['correction_required']=rejection
                if attempt:raise
        result['last_questions']=[key];result['phase']='collecting'
        result['question_origin']='gigachat';result['question_field']=key
        result.pop('question_generation_error',None)
        # Replace the controller's fallback instead of appending a second question.
        if not help_turn and result.get('conversation') and result['conversation'][-1].get('role')=='assistant':result['conversation'].pop()
        if not help_turn and not locked:explanation=''
        if help_turn and is_legal_help(message):explanation=legal_help_note(result,key) or explanation
        answer=(explanation+'\n\n' if explanation else '')+question
        _record_reply(result,answer)
        return result,answer,_usage([usage,response.usage])
    except (RuntimeError,ValueError,TypeError,AttributeError,TimeoutError) as error:
        result['question_origin']='fallback'
        result['question_generation_error']=str(error)[:200]
        if not help_turn and result.get('conversation') and result['conversation'][-1].get('role')=='assistant':result['conversation'].pop()
        field=next((candidate for candidate in missing if not locked or candidate.key==locked),missing[0])
        result['last_questions']=[field.key];result['phase']='collecting'
        answer=_safe_fallback_question(result,field)
        if help_turn and is_legal_help(message):
            note=legal_help_note(result,locked)
            if note:answer=note+'\n\n'+answer
        _record_reply(result,answer)
        return result,answer,usage
