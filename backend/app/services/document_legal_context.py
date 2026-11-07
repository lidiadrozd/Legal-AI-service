"""Small, explicitly sourced guidance for document preparation; not model memory."""
CONSUMER_SOURCES = [
    {"title": "Закон РФ № 2300-1, статья 15", "url": "https://base.garant.ru/10106035/36bfb7176e3e8bfebe718035887e4efc/",
     "summary": "Авторское изложение: размер компенсации морального вреда определяет суд; это не фиксированный процент стоимости товара. Не обещать заранее присуждение суммы."},
    {"title": "НК РФ, статья 333.36, пункты 2 и 3", "url": "https://www.consultant.ru/document/cons_doc_LAW_28165/61fdaaad02ecf7772dc9e0331d21c7ddc3323d4f/",
     "summary": "Авторское изложение: для истцов по искам о нарушении прав потребителей предусмотрена льгота по госпошлине; для имущественных требований действует предел цены иска 1 000 000 рублей и правило расчёта при его превышении. Чек о покупке не подтверждает уплату госпошлины."},
    {"title": "ГПК РФ, статья 131", "url": "https://www.consultant.ru/document/cons_doc_LAW_39570/69470b15e4eb033f5bfa691094e1d083f32238e9/",
     "summary": "Авторское изложение: в иске указывают сведения об истце и ответчике; состав зависит от вида стороны. Для граждан предусмотрены, в частности, дата/место рождения и идентификатор, для организаций — реквизиты. Не придумывать неизвестные данные."},
    {"title": "Закон РФ № 2300-1, статья 18", "url": "https://www.consultant.ru/document/cons_doc_LAW_305/76ae101b731ecc22467fd9f1f14cb9e2b8799026/",
     "summary": "Авторское изложение: требования при недостатках товара включают возврат уплаченной суммы. Для технически сложных товаров действуют специальные условия и сроки; нельзя обещать безусловный возврат без данных о товаре и недостатке."},
    {"title": "Закон РФ № 2300-1, статья 17", "url": "https://www.consultant.ru/document/cons_doc_LAW_305/e38dd0dc96d081c4325d34a3d2a1cd3d037e7fec/",
     "summary": "Авторское изложение: потребитель может выбирать территориальную подсудность из предусмотренных законом вариантов, в том числе по своему месту жительства или пребывания. Конкретный суд нужно проверить отдельно; название не угадывать."},
]


def legal_guidance(state):
    from app.services.document_form_rules import uses_form_composer,legal_profile
    if uses_form_composer(state):
        text,urls=legal_profile(state['scenario'])
        return [{'title':'Правовая основа выбранной формы','url':urls[0],'summary':text}]
    return CONSUMER_SOURCES if "consumer" in (state.get("scenario") or "") else []


def prepare_managed_fields(state):
    """Legal research is an assistant responsibility, not a mandatory user answer."""
    from app.services.document_case_composition import uses_case_composer, prepare_case_rules
    if uses_case_composer(state):
        prepare_case_rules(state)
        return
    from app.services.document_form_rules import uses_form_composer,prepare_form_rules
    if uses_form_composer(state):
        prepare_form_rules(state)
        return
    from app.services.document_scenarios import SCENARIOS
    keys = {f.key for f in SCENARIOS[state["scenario"]].fields}
    for key in {"legal_basis", "fee", "jurisdiction"} & keys:
        existing = state["fields"].get(key, {})
        if existing.get("status") == "filled" and existing.get("origin") == "user_verified":
            continue
        # A deferred field is not falsely represented as the user's 'don't know'.
        state["fields"][key] = {"status": "review_required", "value": None, "original": existing.get("original"),
                                "error": None, "origin": "assistant_review"}
    if state['scenario'] == 'claim_damage_flood':
        # General statutory rules, not a finding that the named neighbour is
        # liable. The cause, defendant's relationship and evidence stay separate.
        state['fields']['legal_basis'] = {'status': 'filled', 'origin': 'verified_rule', 'error': None,
            'value': 'В соответствии со статьёй 15 ГК РФ лицо, право которого нарушено, вправе требовать полного возмещения убытков, если законом или договором не предусмотрено иное. Реальный ущерб включает расходы на восстановление нарушенного права, утрату или повреждение имущества. Согласно статье 1064 ГК РФ вред, причинённый имуществу гражданина, по общему правилу возмещается в полном объёме лицом, причинившим вред. Обстоятельства причинения вреда и основания предъявления требований к ответчику подтверждаются указанными в настоящем заявлении доказательствами.',
            'sources': [
                {'title': 'ГК РФ, статья 15', 'url': 'https://www.consultant.ru/document/cons_doc_LAW_5142/4734407fbf4d5eec5306840f8b75b994e5d57090/'},
                {'title': 'ГК РФ, статья 1064', 'url': 'https://www.consultant.ru/document/cons_doc_LAW_9027/c511835e25e63740cf185038b1ad056526f814e9/'}],
            'checked_at': '2026-10-25'}
    if state["scenario"] == "claim_consumer":
        amount = state["fields"].get("amount", {})
        procedure = (state["fields"].get("procedure", {}).get("value") or "").lower()
        personal = "личн" in procedure or "потреб" in procedure
        if personal:
            legal_basis = "Защита прав потребителя осуществляется судом в соответствии со статьёй 17 Закона РФ от 07.02.1992 № 2300-1 «О защите прав потребителей»."
            narrative = " ".join(str(state["fields"].get(k, {}).get("value") or "") for k in ("purchase", "facts", "violation"))
            sources = [CONSUMER_SOURCES[4]]
            if any(word in narrative.lower() for word in ("товар", "телефон", "недостат")):
                legal_basis += " Требования в связи с недостатками товара подлежат оценке с учётом статьи 18 указанного Закона, категории товара, сроков предъявления требований и характера недостатка."
                sources.append(CONSUMER_SOURCES[3])
            demand = " ".join(str(state["fields"].get(k, {}).get("value") or "") for k in ("requests", "calculation"))
            if "морал" in demand.lower():
                legal_basis += " Размер компенсации морального вреда определяется судом в соответствии со статьёй 15 указанного Закона."
                sources.append(CONSUMER_SOURCES[0])
            state["fields"]["legal_basis"] = {"status": "filled", "value": legal_basis,
                "original": None, "origin": "verified_rule", "sources": sources, "error": None}
        if personal and amount.get("status") == "filled":
            from decimal import Decimal
            if Decimal(amount["value"]) <= 1000000:
                state["fields"]["fee"] = {"status": "filled", "value": "Истец освобождён от уплаты государственной пошлины на основании подпункта 4 пункта 2 и пункта 3 статьи 333.36 НК РФ.",
                    "original": None, "origin": "verified_rule", "sources": [CONSUMER_SOURCES[1]], "error": None}
