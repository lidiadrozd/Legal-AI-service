"""Conversational intent and field guidance, independent of the document renderer."""
import re


def asks_for_help(message):
    text = message.casefold().replace("ё", "е")
    # A short request for an example must never be recorded as a factual
    # answer.  In particular, users often write "пример паспортных данных"
    # while the form asks for party details; treating it as the answer skipped
    # the field and moved the interview to an unrelated next question.
    if re.fullmatch(r'\s*(?:например|конкретно какие|что указать|(?:приведи\s+)?пример(?:\s+(?:паспортн\w*\s+(?:данн\w*|реквизит\w*)|данн\w*))?)[.!? ]*',text):return True
    return bool("?" in text
        # A common clarification after the assistant has mixed two parties is
        # often typed without a question mark: "обо мне или о компании?".
        # Treat it as control input, never as a factual requisite.
        or re.search(r"\b(?:обо?\s+мне|о\s+компан\w*|о\s+организац\w*|обо?\s+ответчик\w*)\s+или\s+(?:обо?\s+мне|о\s+компан\w*|о\s+организац\w*|обо?\s+ответчик\w*)\b", text)
        or re.fullmatch(r"\s*(?:истец|ответчик|идентификатор\w*|подсудность)\s*", text) or re.search(
        r"\b(?:поясни|объясни|обьясни|подскажи|расскажи|посоветуй|помоги|разберись|посчитай|рассчитай)\b"
        r"|не (?:понял|поняла|понимаю)|\b(?:какие|какой|какого|какая|кто|зачем|почему|что такое)\b"
        r"|ты (?:должен|должна)|уже отвечал|одно и то же|заладил|не знаю.{0,25}например"
        r"|можно ли|надо ли|а можно|а нельзя|не разбираюсь|перепиши|исправь документ|проверь документ"
        # Requests to determine the law are help turns too.  They used to be
        # caught only by the conversational wrapper, while the persistent
        # controller still tried to save them as facts before it reached the
        # consultation path.
        r"|\bсам\w*\s+(?:посмотри|скажи|определи)\b|\bпосмотри.{0,30}\bзакон\b", text))


def leaves_blank(message):
    if asks_for_help(message):
        return False
    # A hesitant introduction must not erase the facts after it: "не знаю.
    # Работал ..." is an answer containing facts, not a request to leave blank.
    parts = re.split(r"[.!;]\s+|\bно\b|\bоднако\b", message, flags=re.I)
    pattern = r"\bне знаю\b|\bне помню\b|\bне\s*извест\w*|не определил\w*|не\s*определ[её]н\w*|не выбрал\w*|ничего не выбирал\w*|впишу позже|остав\w* (?:пуст|пропуск)|сомневаюсь"
    meaningful = [p.strip() for p in parts if p.strip()]
    return bool(meaningful and all(re.search(pattern, p, re.I) for p in meaningful))


def conversational_value(value):
    """A command/question must never become a document fact, including old sessions."""
    return asks_for_help(value) or leaves_blank(value) or is_progress_message(value)


def is_progress_message(message):
    text = message.strip().casefold().replace("ё", "е").rstrip(".!? ")
    return bool(re.fullmatch(r"(?:да|ага|ок|окей|хорошо|понятно|спасибо|продолжай|продолжим|продолжить|повтори|дальше|что дальше|а что дальше)(?:,?\s*(?:дальше|продолжай|спасибо))?", text)
                or re.search(r"(?:где|когда).{0,20}(?:моя |мой )?(?:жалоба|претензия|иск|документ)|а что дальше", text))


def is_recall_request(message):
    return bool(re.search(r"уже\s+(?:отвечал|писал|говорил|сообщал|сказал)|(?:я же|я ведь).{0,20}(?:писал|сказал|говорил)|посмотри\s+выше|забыл.{0,15}контекст|ты забыл|ты забыла", message, re.I))


def document_kind(state):
    # The initial request establishes the kind; short follow-ups cannot erase it.
    text = " ".join([state.get("request", ""), state.get("title_hint", ""), state.get("document_type_hint", "")]).lower()
    if not state.get('scenario'):
        text+=' '+' '.join(state.get('user_turns',[])).lower()
    from app.services.document_catalog import catalog_kind
    precise_kind=catalog_kind(text)
    if precise_kind:return precise_kind
    kinds = {'договор': 'contract', 'контракт': 'contract', 'иск': 'claim', 'исковое': 'claim',
             'претензия': 'pretense', 'претензию': 'pretense', 'жалоба': 'complaint', 'жалобу': 'complaint',
             'ходатайство': 'procedural', 'доверенность': 'authority', 'расписка': 'receipt', 'расписку': 'receipt', 'акт': 'act'}
    explicit = re.search(r'\b(?:нужен|нужна|нужно|составь|составить|подготовь|подготовить|оформи|оформить|напиши|написать|заключить)\s+(?:(?:мне|проект|новый|новую|такой|такую)\s+){0,3}(договор|контракт|исковое|иск|претензи[яю]|жалоб[ау]|ходатайство|доверенность|расписк[ау]|акт)\b', text)
    if re.search(r'апелляционн\w* жалоб', text): return 'appeal'
    if explicit: return kinds[explicit[1]]
    if state.get('scenario'):
        for prefix, family in (('pretense_', 'pretense'), ('claim_', 'claim'), ('contract_', 'contract'),
                ('complaint_', 'complaint'), ('motion_', 'procedural'), ('appeal_', 'appeal'), ('act_', 'act'),
                ('order_', 'court_order'), ('labor_', 'employment_statement'), ('bailiff_', 'enforcement')):
            if state['scenario'].startswith(prefix): return family
    if re.search(r"трудов\w* инспекц|инспекц\w* (?:по )?труд|роструд|роспотребнадзор", text): return "complaint"
    if "ходатайств" in text: return "procedural"
    if re.search(r"\bиск\b|\bисков\w*", text): return "claim"
    if "претенз" in text: return "pretense"
    if "жалоб" in text and not re.search(r"апелляц|судебн", text):
        return state.get("document_kind", "complaint")
    if re.search(r'доверенност', text): return 'authority'
    if re.search(r'\bрасписк\w*', text) and not re.search(r'верну|долг|взыск', text): return 'receipt'
    if re.search(r'\bдоговор\w*|\bконтракт\w*', text): return 'contract'
    if re.search(r'\bакт\w*', text): return 'act'
    return state.get("document_kind", "")


def infer_scenario(state, message):
    kind = document_kind(state)
    text = " ".join([state.get("request", ""), state.get("context", ""), *state.get("user_turns", []), message]).lower()
    from app.services.document_catalog import infer_catalog_scenario
    exact=infer_catalog_scenario(kind,text)
    if exact:return exact
    if 'алимент' in text:return None
    if kind == 'contract':
        if re.search(r'купл[ия].{0,4}продаж', text) and re.search(r'нежил\w* помещен', text): return 'contract_sale_nonresidential'
        if re.search(r'квартир|жиль|жил(?:ое|ого) помещен|жил(?:ой|ого) дом', text) and re.search(r'найм|на[её]м|аренд|сда(?:ть|вать|ю)|сня(?:ть|тия)|снимать', text): return 'contract_housing'
        if re.search(r'подряд|ремонт|выполнени\w* работ', text): return 'contract_work'
        if re.search(r'услуг', text): return 'contract_services'
        if re.search(r'за[её]м|займ|в долг|одолж', text): return 'contract_loan'
        return None
    if kind == 'authority': return 'power_of_attorney'
    if kind == 'receipt': return 'act_loan_receipt' if re.search(r'за[её]м|займ|в долг|одолж', text) else None
    if kind == 'act':
        if re.search(r'услуг', text): return 'act_services'
        if re.search(r'работ|подряд', text): return 'act_work'
        return None
    if kind == 'appeal':
        return ('appeal_arbitration' if re.search(r'арбитраж', text) else
                ('appeal_civil' if re.search(r'гражданск|районн\w* суд|миров\w* судь|суд\w* общей юрисдикц', text) else None))
    if kind == "complaint" and re.search(r"трудов\w* инспекц|инспекц\w* (?:по )?труд|роструд", text):
        return "complaint_labor_agency"
    if kind == "procedural" and re.search(r"отлож|перен[её]с|перенос", text):
        return "motion_postpone"
    if kind == "complaint" and "роспотребнадзор" in text:
        return "complaint_consumer_agency"
    if kind not in {"claim", "pretense"} and re.search(r"купл[ия].{0,4}продаж", text) and re.search(r"нежил\w* помещен", text):
        return "contract_sale_nonresidential"
    if kind not in {"claim", "pretense"}: return None
    if re.search(r"защит\w* прав потреб|некачествен\w* товар|телефон.{0,35}(?:взорвал|слома)|товар.{0,30}недостат|ист[её]кш\w* срок\w* годност|просроченн\w* (?:товар|продукт)", text):
        return "claim_consumer" if kind == "claim" else "pretense_consumer_defective_goods"
    if "залив" in text or "затоп" in text:
        return ("claim" if kind == "claim" else "pretense") + "_damage_flood"
    basis = next((suffix for pattern, suffix in (
        (r"расписк|займ|за[её]м|дал\w* в долг|одолж", "loan"),
        (r"аренд", "rent"), (r"оказан\w* услуг|договор\w* услуг", "services"),
        (r"поставк|поставлен\w* товар", "supply")) if re.search(pattern, text)), None)
    return f"{kind}_debt_{basis}" if basis else None


def scenario_candidates(state):
    """An explicit document family cannot be replaced by a similar transaction."""
    from app.services.document_scenarios import SCENARIOS
    kind = document_kind(state)
    prefixes = {"claim": ("claim_",), "pretense": ("pretense_",),
                "complaint": ("complaint_",), "procedural": ("motion_",),
                'contract': ('contract_',), 'act': ('act_',), 'authority': ('power_of_attorney',),
                'receipt': ('act_loan_receipt',), 'appeal': ('appeal_',),
                'court_order': ('order_',), 'employment_statement': ('labor_',), 'enforcement': ('bailiff_',)}
    return [key for key in SCENARIOS if kind not in prefixes or key.startswith(prefixes[kind])]


def classification_guidance(state):
    kind = document_kind(state)
    if kind == 'contract':
        return 'Готовим договор. Что именно стороны хотят согласовать: трудовые отношения, наём жилья, услуги, выполнение работ, заём или другую сделку?'
    if kind == 'act': return 'Готовим акт. Он подтверждает выполненные работы, оказанные услуги или другое действие?'
    if kind == 'receipt': return 'Готовим расписку. На каком основании получены деньги: заём, оплата покупки или другое основание?'
    if kind in {"claim", "pretense"}:
        name = "претензия" if kind == "pretense" else "иск"
        return (f"Вид документа уже понятен — {name}. Осталось выяснить, из-за чего возникло требование. "
                "Например: передали деньги в долг, не оплатили работу, не вернули оплату за товар или повредили имущество. "
                "Что произошло в вашей ситуации?")
    return "Опишите, какого результата хотите добиться: обратиться к другой стороне, в суд или в ведомство? Помогу выбрать документ по вашей ситуации."


def field_guidance(state, key, scenario):
    if scenario.key == 'claim_damage_flood':
        explanations = {
            'property_address': 'Нужен адрес квартиры, пострадавшей от залива. Он может отличаться от вашего адреса для корреспонденции. Ссылку на уже сообщённый адрес я сначала предложу подтвердить.',
            'source_address': 'Нужен адрес места, откуда поступила вода. Например, номер квартиры сверху в уже указанном доме. Если точный источник не установлен, его нельзя угадывать.',
            'property_right': 'Нужно объяснить, почему именно вы требуете возмещения за эту квартиру или имущество: например, вы собственник или наниматель. Подтверждением может быть выписка ЕГРН, договор или другой имеющийся документ. Неизвестные реквизиты можно дополнить позже.',
            'source_relation': 'Нужно указать известную связь ответчика с источником воды: владеет ли он квартирой, проживает в ней или обслуживает оборудование. Сам факт проживания сверху ещё не устанавливает причину залива и ответственность.',
            'restoration': 'Здесь выбираем состояние ремонта: ещё не выполнен, выполнен полностью или частично. От ответа зависит, какие расходы будут описаны в документе.',
            'expertise': 'Речь о просьбе к суду назначить экспертизу для выяснения спорных обстоятельств. Уже имеющийся отчёт оценщика и судебная экспертиза — разные сведения. Такую просьбу не добавляем автоматически.',
            'security': 'Это отдельная просьба о временной мере для обеспечения будущего исполнения решения. Нужны конкретная мера и её обоснование. Если такой просьбы нет, раздел не включаем.',
            'sender_details': 'Нужны известные дополнительные реквизиты именно истца: дата и место рождения, идентификатор и контакты. ФИО и адрес уже сохраняются отдельно.',
            'recipient_details': 'Нужны известные дополнительные реквизиты именно ответчика: дата и место рождения, место работы и идентификатор. Неизвестные сведения не нужно придумывать.',
            'copy_notice': 'Сейчас уточняем подтверждение отправки именно искового заявления и приложений другим участникам. Подтверждение отправки досудебной претензии относится к другому этапу.',
            'copy_status': 'Сейчас речь об отправке копий именно подготовленного иска другим участникам, а не о ранее направленной претензии. Если отправки пока не было, это будет отмечено среди действий перед подачей.',
        }
        if key in explanations:
            spec = next(f for f in scenario.fields if f.key == key)
            return explanations[key] + '\n\n' + spec.question
    facts = state.get("fields", {})
    sender = facts.get("sender", {}).get("value") or "человек или организация, от имени которых подаётся документ"
    guides = {
        "agreement": "Речь об основании долга — договоре займа или расписке, по которым передавались деньги. Не нужно переписывать документ целиком. Сообщите известную дату и название; если год или номер неизвестны, их можно оставить для заполнения. Какие сведения о расписке или договоре вам известны?",
        "principal_details": "Да, речь о паспортных реквизитах доверителя — человека, который выдаёт доверенность. Обычно указывают серию и номер паспорта, кем и когда он выдан; при необходимости — дату рождения. ФИО и адрес, которые вы уже сообщили, повторять не нужно. Неизвестные реквизиты можно оставить для заполнения. Какие паспортные реквизиты доверителя вам известны?",
        "agent_details": "Речь о паспортных реквизитах представителя — человека, которому выдаётся доверенность, например бабушки. Это серия и номер паспорта, кем и когда он выдан. ФИО и адрес уже сохранены, повторять их не нужно. Какие паспортные реквизиты представителя вам известны?",
        "powers": "Полномочия — конкретные действия, которые поручаете представителю: например, получать определённые документы или подавать заявления от вашего имени. Для документа нужно уточнить, что именно представитель будет делать от вашего имени. Какие действия вы хотите поручить?",
        "validity": "Это срок, на который выдаётся доверенность: например, 6 месяцев или 2 года. Пример не является вашим выбором. На какой срок хотите выдать доверенность?",
        "sender": f"Истец — тот, кто обращается в суд за защитой своего права. Здесь нужны его ФИО полностью. Если подаёте иск за себя, укажите свои ФИО.",
        "sender_address": f"Истец — тот, кто подаёт иск; в этом документе это {sender}. Нужен полный почтовый адрес именно этой стороны, а не суда и не продавца. Укажите населённый пункт, улицу, дом и квартиру при наличии. Какой адрес нужно указать?",
        "recipient": "Ответчик — тот, к кому предъявляете иск. В споре о покупке это может быть продавец: его юридическое наименование часто указано в чеке. Какое наименование указано у вас?",
        "recipient_address": "Нужен адрес другой стороны: для организации его можно посмотреть в реквизитах продавца или сведениях о юридическом лице. Если пока неизвестен, оставим обозначенное место. Какой адрес вам известен?",
        "party_details": "Речь о дополнительных реквизитах сторон, а не о новых участниках. Например, для гражданина — дата и место рождения, известный ИНН или СНИЛС; для организации — ИНН и ОГРН. Не нужно придумывать неизвестные сведения. Какие из этих данных у вас есть?",
        "sender_details": "Здесь указываются дополнительные сведения об истце. Пример формата: «паспорт гражданина РФ: серия 0000 № 000000, выдан ОМВД России по [району] 01.01.2020, код подразделения 000-000». Это только пример формата — чужие или вымышленные данные в документ не подставляем. Если реквизиты неизвестны, можно ответить «не знаю».",
        "recipient_details": "Здесь указываются известные дополнительные сведения об ответчике. Для гражданина это могут быть дата и место рождения, ИНН, СНИЛС или паспортные данные; для организации — ИНН и ОГРН. Неизвестные данные не нужно угадывать.",
        "court": "Суд пока можно не указывать: сначала нужно определить вид спора, требования и территориальную подсудность. Название суда не следует угадывать. Если выбор ещё не сделан, оставим поле для уточнения. В каком населённом пункте вы живёте?",
        "procedure": "Для выбора порядка важно, связана ли ситуация с личными нуждами человека или с бизнесом. Покупка телефона для себя — пример личных нужд. Какова цель в вашей ситуации?",
        "purchase": "Опишите покупку обычными словами: что купили, у кого, когда и за какую цену. Для документа я затем изложу это официальным языком. Что известно о покупке?",
        "seller_response": "Я спрашиваю, обращались ли вы к продавцу после обнаружения проблемы: приходили в магазин, звонили, писали сообщение или заявление. Это нужно, чтобы описать попытки урегулирования и ответ продавца. Обращались ли вы к нему?",
        "pretrial": "Претензия — письменное требование к другой стороне до суда. Здесь нужно указать, направляли ли её, и что произошло после этого. Если пока только готовите иск, так и запишем, без выдуманного обращения. Направляли претензию?",
        "copy_notice": "Имеются в виду копии этого иска и приложений для остальных участников дела, а не другой документ. Здесь фиксируют факт отправки и подтверждение. Если иск только готовится, можно указать, что копии ещё не направлялись. Уже отправляли копии?",
        "attachments": "Приложения — документы, подтверждающие описанные обстоятельства: например, чек, договор, фотографии повреждений или переписка. Включим только то, что действительно есть. Какие документы есть у вас?",
        "fee": "Госпошлина — платёж за обращение в суд, а чек о покупке подтверждает оплату товара. Это разные документы. Сначала проверю применимую льготу и условия, а чек о покупке сохраню как доказательство.",
        "legal_basis": "Подбор правовых норм — моя задача: вам не нужно знать номера статей. Я сопоставлю требования с предоставленными источниками и обозначу вопросы, для которых данных пока не хватает.",
        "jurisdiction": "Это основание выбора суда, а не отдельное доказательство вашей правоты. Его нужно определить по виду спора, сторонам и адресам; вам не требуется самостоятельно формулировать юридическое обоснование.",
        "property_right": "Здесь нужны не статьи закона и не формулировка нарушенного права, а факты: вы собственник, наниматель или иной законный владелец имущества и какой документ это подтверждает. Не нужно самостоятельно формулировать правовую оценку: её подберу я. На каком фактическом основании имущество находится у вас?",
        "responsibility": "Здесь нужны известные факты о связи другой стороны с вредом: что она обслуживает, сделала или не сделала и чем это подтверждается. Не нужно самостоятельно решать, виновна ли она по закону. Какие факты и документы у вас есть?",
        "calculation": "Расчёт — это понятная разбивка подтверждённых сумм, а не ссылка на оценщика. Назовите каждую позицию: например, ущерб, расходы на оценку, уже понесённые расходы. Я сложу указанные суммы и покажу формулу. Для процентов или неустойки дополнительно понадобятся основание, период просрочки, ставка и платежи. Компенсацию морального вреда нельзя назначить автоматически: заявляемую сумму выбираете вы, окончательный размер определяет суд. Какие суммы и за что у вас уже подтверждены?",
        "requests": "Требования — конкретный результат, который просите у суда: например, взыскать стоимость товара или указанную вами компенсацию морального вреда. Денежные требования нужно разделить. Просьбу об извинениях нельзя автоматически превращать в обязательное судебное требование. Какое денежное требование хотите заявить?",
        "payment_details": "Нужен способ получения денег. Для банковского перевода могут потребоваться реквизиты счёта и получателя; номер карты сам по себе не заменяет полный набор реквизитов. Если пока не хотите их указывать, оставим поле для заполнения.",
        "facts": "Расскажите, что именно произошло и в какой последовательности. Я сохраню факты, уберу разговорные выражения и не добавлю события, которых вы не сообщали. Что произошло?",
    }
    if not scenario.key.startswith("claim_"):
        labels = {f.key: f.label.lower() for f in scenario.fields}
        guides["sender"] = f"В этом документе первая сторона — {labels.get('sender', 'заявитель')}. Укажите её ФИО полностью или наименование организации. От чьего имени готовим документ?"
        guides["sender_address"] = f"Здесь нужен адрес первой стороны: {labels.get('sender', 'заявителя')}. Не адрес суда или другой стороны. Укажите населённый пункт, улицу, дом и квартиру при наличии. Какой адрес нужно указать?"
        guides["recipient"] = f"Вторая сторона в этом документе — {labels.get('recipient', 'адресат')}. Укажите её ФИО или точное наименование организации. Какие сведения о ней известны?"
    if scenario.key == "power_of_attorney":
        guides["sender"] = "Доверитель — человек, который выдаёт доверенность и поручает действия от своего имени. Представитель — тот, кому эти действия поручены. Если вы выдаёте доверенность бабушке, доверитель — вы, представитель — бабушка. Укажите ФИО доверителя полностью."
        guides["recipient"] = "Представитель — человек, которому выдаётся доверенность. Если это бабушка, нужны её ФИО. Укажите ФИО представителя полностью."
        guides["sender_address"] = f"Нужен адрес доверителя: {sender}. Это адрес человека, который выдаёт доверенность. Можно написать обычным способом: Екатеринбург, Блюхера 45, 38. Какой адрес доверителя нужно указать?"
        guides["recipient_address"] = "Нужен адрес представителя — человека, которому выдаётся доверенность. Если это бабушка, укажите её адрес. Если он неизвестен, оставим поле для заполнения. Какой адрес представителя вам известен?"
    if key in guides: return guides[key]
    spec = next((f for f in scenario.fields if f.key == key), None)
    return (f"Это сведения для раздела «{spec.label}». Можно ответить своими словами; я помогу сформулировать их для документа. "
            "Если данных нет, поле можно оставить для заполнения. Что об этом известно?") if spec else classification_guidance(state)


def normalize_address(raw):
    raw=re.sub(r'^\s*(?:место (?:работы|жительства)|почтовый адрес|адрес(?: работодателя| истца| ответчика| заявителя)?)\s*[:—-]\s*','',raw,flags=re.I)
    value = re.sub(r"\s+", " ", raw.strip()).rstrip(".")
    from app.services.document_addresses import RELATIVE
    if RELATIVE.search(value):
        return value
    # Accept ordinary chat shorthand without punctuation, preserving both
    # numeric components. Do not confuse a street/house with a locality.
    compact = re.fullmatch(r'(?P<city>[А-Яа-яЁё-]+)\s+(?P<street>[А-Яа-яЁё-]+)\s+(?P<house>\d+[А-Яа-яЁё/-]*)(?:\s+(?P<flat>\d+[А-Яа-яЁё/-]*))?', value)
    if compact and not re.match(r'^(?:ул|улица|дом|квартира|проспект|пос[её]лок|деревня)\b', value, re.I):
        value = compact['city'] + ', ' + compact['street'] + ' ' + compact['house'] + (', ' + compact['flat'] if compact['flat'] else '')
    # The locality can follow the street; an address prefix is descriptive
    # text, not part of the street's name. Preserve only supplied components.
    reverse = re.search(r"(?:^|\sна\s|\sпо адресу\s)(?P<street>(?:ул\.?\s*)?[А-Яа-яЁё-]+\s+\d+[А-Яа-яЁё/-]*(?:,\s*(?:кв\.?\s*)?\d+)?),\s*(?:г\.?\s*)?(?P<city>[А-Яа-яЁё-]+)$", value, re.I)
    if reverse:
        value = reverse["city"] + ", " + reverse["street"]
    # A component with house digits is never interpreted as a city.
    short = re.fullmatch(
        r"(?:(?:г\.?\s*)?(?P<city>[А-Яа-яЁё-]+(?:\s+[А-Яа-яЁё-]+)*),\s*)?"
        r"(?:ул\.?\s*)?(?P<street>[А-Яа-яЁё-]+(?:\s+[А-Яа-яЁё-]+)*)\s+"
        r"(?P<house>\d+[А-Яа-яЁёA-Za-z/-]*)(?:,\s*(?:кв\.?\s*)?(?P<flat>\d+[А-Яа-яЁё/-]*))?", value, re.I)
    if short:
        parts = (["г. " + short["city"]] if short["city"] else [])
        parts.extend(["ул. " + short["street"], "д. " + short["house"]])
        if short["flat"]: parts.append("кв. " + short["flat"])
        value = ", ".join(parts)
    value = re.sub(r"\bкв(?:артира)?\.?\s*(\d+[\w/-]*)", r"кв. \1", value, flags=re.I)
    value = re.sub(r"\b(?:дом|д)\.?\s*(\d+[\w/-]*)", r"д. \1", value, flags=re.I)
    value = re.sub(r"\b(?:улица|ул)\.?\s*", "ул. ", value, flags=re.I)
    value = re.sub(r"(?<!\w)(?:г|город)\.?\s+", "г. ", value, flags=re.I)
    value = re.sub(r"(?<!\w)([а-яё][а-яё-]*)", lambda m: m[1].capitalize() if m[1] not in {"г", "ул", "д", "кв", "корп", "обл", "р", "н", "с", "п", "пер", "проспект", "область", "район"} else m[1], value)
    value = re.sub(r"(?<![\d.])\s+(\d+)(?=,?\s*кв\.)", r", д. \1", value)
    return re.sub(r",\s*,", ",", value)


def has_locality(value):
    if re.search(r"\b(?:г\.|город|село|с\.|пос[её]лок|п\.|деревня|д\.|станица)\s+[А-Яа-яЁё-]", value, re.I):
        return True
    # 'Екатеринбург, ул. ...' also explicitly names a locality.
    return bool(re.match(r"^[А-Яа-яЁё-]+,\s*(?:ул\.|улица|проспект|пер\.)", value, re.I))


def question_text(state, spec):
    if spec.key in {'party_details','sender_details','recipient_details'}:
        party='sender' if spec.key=='sender_details' else 'recipient'
        value=state.get('fields',{}).get(party,{}).get('value') or ''
        if re.search(r'\b(?:ООО|АО|ПАО|ЗАО|ОАО)\b',value,re.I):
            return f'Какие ИНН и ОГРН организации «{value}» вам известны? Неизвестные реквизиты можно дополнить позднее.'
    from app.services.document_catalog import is_catalog_form
    if is_catalog_form(state.get('scenario')) and state.get('scenario')!='power_of_attorney':
        return spec.question
    court_case = (state.get("scenario") or "").startswith("claim_")
    if state.get('scenario', '') in {'contract_housing', 'contract_services', 'contract_work', 'contract_loan'}:
        return spec.question
    if state.get('scenario') == 'claim_damage_flood' and spec.key not in {'sender', 'recipient', 'signature', 'court', 'sender_address', 'recipient_address'}:
        return spec.question
    if state.get("scenario") == "power_of_attorney":
        return {
            "sender": "Укажите ФИО доверителя — человека, который выдаёт доверенность. Если выдаёте её от своего имени, нужны ваши ФИО.",
            "sender_address": "Укажите полный адрес доверителя — человека, который выдаёт доверенность.",
            "recipient": "Укажите ФИО представителя — человека, которому поручаете действия. Если это бабушка, нужны ФИО бабушки.",
            "recipient_address": "Укажите полный адрес представителя — человека, которому выдаёте доверенность.",
            "principal_details": "Какие паспортные реквизиты доверителя вам известны? Неизвестные можно вписать позже.",
            "agent_details": "Какие паспортные реквизиты представителя вам известны? Неизвестные можно вписать позже.",
            "signature": "Укажите ФИО доверителя, который подпишет доверенность.",
        }.get(spec.key, spec.question)
    if state.get("scenario", "").startswith("complaint_") and spec.key in {"recipient", "recipient_address"}:
        return ("В какое ведомство и его территориальное подразделение направляем жалобу? Неизвестное подразделение можно оставить для уточнения."
                if spec.key == "recipient" else "Какой почтовый адрес ведомства вам известен? Если неизвестен, оставим поле для заполнения.")
    if spec.key in {"sender", "recipient", "signature", "counterparty_signature"}:
        from app.services.document_scenarios import SCENARIOS
        party = "sender" if spec.key in {"sender", "signature"} else "recipient"
        label = next(f.label for f in SCENARIOS[state["scenario"]].fields if f.key == party)
        genitive = {"Истец": "истца", "Ответчик": "ответчика", "Заявитель": "заявителя", "Адресат": "адресата",
                    "Заказчик": "заказчика", "Исполнитель": "исполнителя", "Подрядчик": "подрядчика",
                    "Наймодатель": "наймодателя", "Наниматель": "нанимателя", "Займодавец": "займодавца",
                    "Заёмщик": "заёмщика", "Продавец": "продавца", "Покупатель": "покупателя"}.get(label, label.lower())
        if spec.key in {"signature", "counterparty_signature"}:
            return f"Укажите ФИО человека, который подпишет документ от имени {genitive}."
        return f"Укажите полное ФИО {genitive} либо наименование, если это организация."
    if state.get("scenario") == "contract_sale_nonresidential":
        return {"sender": "Кто продавец: укажите полное ФИО или название организации.",
                "recipient": "Кто покупатель: укажите полное ФИО или название организации.",
                "amount": "Какова согласованная цена помещения в рублях?"}.get(spec.key, spec.question)
    questions = {
        "sender": "Кто подаёт иск: укажите ФИО полностью или название организации." if court_case else spec.question,
        "sender_address": "Укажите адрес того, от чьего имени готовим документ: населённый пункт, улицу, дом и квартиру при наличии.",
        "recipient": "К кому предъявляем требования: укажите ФИО человека или юридическое наименование организации.",
        "recipient_address": "Какой адрес другой стороны вам известен? Если пока не знаете, можно оставить поле для заполнения.",
        "party_details": "Какие дополнительные данные сторон вам известны — например, дата рождения или ИНН гражданина, ИНН и ОГРН организации?",
        "court": "Вы уже выбрали суд для обращения или пока оставить его название для уточнения?",
        "purchase": "Расскажите о покупке: что приобрели, у кого, когда и за сколько.",
        "seller_response": "Обращались ли вы к продавцу после обнаружения проблемы?",
        "pretrial": "Направляли ли вы другой стороне письменную претензию до подготовки иска?",
        "copy_notice": "Копии этого документа и приложений уже отправлены другим участникам или отправка ещё предстоит?",
        "calculation": "Из каких отдельных сумм складываются ваши денежные требования? Помогу посчитать после уточнения составляющих.",
    }
    return questions.get(spec.key, spec.question)
