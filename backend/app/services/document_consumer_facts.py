"""Literal consumer facts shared by consumer letters and claims.

Keep the user's wording as evidence. Product classification here is ordinary
vocabulary, never a determination of the product's statutory legal category.
"""
import re
from copy import deepcopy
from datetime import date

from app.services.document_source_quotes import source_sentences

_RECEIPT_PRESENT = re.compile(
    r'\b(?:(?:есть|имеется|сохранился)\s+(?:кассов\w*\s+|электронн\w*\s+)?чек|'
    r'(?:кассов\w*\s+|электронн\w*\s+)?чек\s+(?:есть|имеется|сохранился))\b',
    re.I,
)
_RECEIPT_ABSENT = re.compile(
    r'\b(?:чека\s+нет|нет\s+(?:кассов\w*\s+|электронн\w*\s+)?чека|'
    r'(?:кассов\w*\s+|электронн\w*\s+)?чек\s+(?:не\s+сохранился|утерян|потерян))\b',
    re.I,
)

_CONSUMER_GOODS = re.compile(
    r'\b(?:холодильн\w*|телевизор\w*|стиральн\w*\s+машин\w*|посудомоечн\w*\s+машин\w*|'
    r'пылесос\w*|микроволнов\w*\s+печ\w*|ноутбук\w*|телефон\w*|смартфон\w*|'
    r'планшет\w*|монитор\w*|фотоаппарат\w*|компьютер\w*|(?:электрическ\w*\s+)?чайник\w*|товар\w*)\b',
    re.I,
)

_NUMERIC_DATE = re.compile(r'\b(\d{1,2})[./](\d{1,2})[./](\d{2,4})\b')
_PURCHASE_VERB = re.compile(r'\b(?:купил[аи]?|приобр[её]л[аи]?|заказал[аи]?)\b', re.I)
_PURCHASE_SELLER = re.compile(
    r'\b(?:в|у)\s+(?:магазин\w*\s+)?((?:ООО|АО|ПАО|ЗАО|ОАО)\s*[«"][^»"\n]+[»"])', re.I,
)
_QUOTED_NAME = r'(?:«[^»\n]{1,100}»|"[^"\n]{1,100}")'
_RECEIPT_LOCATOR = re.compile(r'\bв\s+(?:(электронн\w*|кассов\w*)\s+)?чеке\b', re.I)
_UNCERTAIN_RECEIPT = re.compile(r'\b(?:если|возможно|кажется|например|вроде|допустим|не\s+(?:помню|уверен\w*))\b', re.I)
_SELLER_ON_RECEIPT = re.compile(
    r'^\s*[,:\-–—]?\s*(?:(?:в\s+качестве\s+продавца|продавцом|продавец)\s*'
    r'(?:(?:указан[ао]?|значится|записан[ао]?)\s*)?|(?:указан|значится)\s+продавец\s*)[:\-–—]?\s*'
    r'((?:ООО|АО|ПАО|ЗАО|ОАО)\s*' + _QUOTED_NAME + r')', re.I)
_BUYER_CLAUSE = re.compile(r',\s*(?:но|однако|а)\s+(?=(?:я\s+)?(?:хочу|прошу|требую)\b)', re.I)
_STORE_REPLY = re.compile(r'\b(?:продавец|магазин|в\s+магазине)\s+(?:предложил|отказал|согласился|ответил|принял)\w*\b', re.I)


def receipt_parties(sentence):
    """Identify a seller only when the receipt explicitly assigns that role."""
    locator = _RECEIPT_LOCATOR.search(sentence)
    if (not locator or '?' in sentence or _UNCERTAIN_RECEIPT.search(sentence)
            or _RECEIPT_ABSENT.search(sentence) or re.search(r'\bне\s*$', sentence[:locator.start()], re.I)):
        return None, None
    after = sentence[locator.end():]
    if not re.search(r'\b(?:продавц\w*|продавец|указан\w*|значится|написан\w*)\b', after, re.I):
        return None, None
    kind = locator[1] or ''
    receipt = ('электронный чек' if kind.lower().startswith('электронн') else
               'кассовый чек' if kind else 'чек')
    match = _SELLER_ON_RECEIPT.match(after)
    if not match or re.match(r'\s*(?:/|[,;]?\s*(?:(?:или|либо)\b|(?:и\s+)?(?:ООО|АО|ПАО|ЗАО|ОАО)\b))',
                             after[match.end():], re.I):
        return receipt, None
    return receipt, match[1]


def consumer_role_quote(key, quote, evidence, source):
    """Check a model's literal snippet against the roles assigned by its source sentence."""
    if key in {'payment', 'payment_method', 'payment_details'}:
        if (re.search(r'\b(?:за)?платил[аи]?\b|\bоплатил[аи]?\b', evidence, re.I)
                and not re.search(r'\b(?:возврат|верн|возвращ)\w*\b|'
                                  r'\b(?:прошу|хочу)\s+(?:перечислить|получить|перевести)\b|'
                                  r'\bна\s+(?:(?:эту|ту)\s+(?:же\s+)?)?карту,?\s+с\s+которой\b', evidence, re.I)):
            return None
    if key not in {'seller', 'recipient', 'goods_category', 'facts', 'seller_response', 'requests'}:
        return quote, evidence
    for sentence in source_sentences(source):
        if quote.casefold() not in sentence.casefold():
            continue
        if key in {'facts', 'seller_response', 'requests'}:
            parts = _BUYER_CLAUSE.split(sentence, maxsplit=1)
            if len(parts) == 2 and _STORE_REPLY.search(parts[0]):
                return (parts[-1] if key == 'requests' else parts[0]), sentence
            continue
        locator = _RECEIPT_LOCATOR.search(sentence)
        if not locator:
            if (key in {'recipient', 'seller'} and re.search(r'\bна\s+(?:коробке|упаковке|этикетке)\b', sentence, re.I)
                    and not re.search(r'\b(?:продавец|продавц\w*|продавал\w*)\b', sentence, re.I)):
                return None
            continue
        _, seller = receipt_parties(sentence)
        if key == 'goods_category':
            if (quote == sentence or re.fullmatch(r'(?:ООО|АО|ПАО|ЗАО|ОАО)\s*' + _QUOTED_NAME, quote, re.I)):
                return None
        elif seller:
            return seller, sentence
        elif (re.search(r'\b(?:продавцом|продавца|продавец)\b', sentence, re.I)
              and ('?' in sentence or _UNCERTAIN_RECEIPT.search(sentence) or _RECEIPT_ABSENT.search(sentence)
                   or re.search(r'\b(?:не|или|либо)\b|/', sentence, re.I)
                   or _SELLER_ON_RECEIPT.match(sentence[locator.end():]))):
            return None
    return quote, evidence
_USE_PURPOSE = re.compile(
    r'\bдля\s+(?:дома|себя|семьи|личн\w*\s+(?:и\s+семейн\w*\s+)?(?:нужд|пользовани\w*|использовани\w*)|'
    r'предпринимательской деятельности|перепродажи|бизнеса)\b', re.I,
)
_MODEL_BOUNDARY = re.compile(
    r'\b\d{1,2}(?:[./]\d{1,2}[./]\d{2,4}|\s+(?:января|февраля|марта|апреля|мая|июня|'
    r'июля|августа|сентября|октября|ноября|декабря))\b|'
    r'\s+(?:в|во|у|от|на|по|за|ценой|стоимостью|приобр[её]л\w*|купил\w*)\s+|[,;!?\n]',
    re.I,
)


def _product_model(product, source: str) -> str | None:
    """Keep model tokens together without treating a following calendar day as a model suffix."""
    tail = source[product.end():].lstrip()
    tail = re.sub(r'^(?:марка|модель|марки|модели)\s*[:—-]?\s+', '', tail, flags=re.I)
    quoted = re.match(r'(«[^»\n]{1,80}»|"[^"\n]{1,80}")', tail)
    if quoted:
        return quoted[0]
    label = _MODEL_BOUNDARY.split(tail, maxsplit=1)[0].strip(' .')
    if re.fullmatch(r'[A-Za-zА-ЯЁ][\w+-]*(?:\s+(?:[A-Za-zА-ЯЁ0-9][\w+-]*)){0,6}', label):
        if any(char.isdigit() for char in label) or len(label.split()) > 1:
            return label
    return None


def _named_product(source):
    return next((m for m in _CONSUMER_GOODS.finditer(source)
                 if not m[0].casefold().startswith('товар')), None)


def _purchase_date_error(source: str) -> str | None:
    """Validate a purchase date without discarding the user's chronology."""
    match = _NUMERIC_DATE.search(source or '')
    if match:
        day, month, raw_year = match.groups()
        year = int(raw_year)
        if len(raw_year) == 2:
            year += 2000
        try:
            parsed = date(year, int(month), int(day))
        except ValueError:
            parsed = None
        if parsed is None or parsed.year < 1900 or parsed.year > date.today().year + 100:
            return ('Дата покупки выглядит невозможной. Сохранил остальные сведения о покупке. '
                    'Проверьте дату и укажите полный год, например: 08.09.2026. '
                    'Пример не является вашими данными.')
        return None
    words = re.search(
        r'\b(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|'
        r'сентября|октября|ноября|декабря)\s+(\d{4})(?:\s*года)?\b', source or '', re.I)
    if words:
        months = {
            'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6,
            'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12,
        }
        try:
            parsed = date(int(words[3]), months[words[2].lower()], int(words[1]))
        except ValueError:
            parsed = None
        if parsed is None or parsed.year < 1900 or parsed.year > date.today().year + 100:
            return ('Дата покупки выглядит невозможной. Сохранил остальные сведения о покупке. '
                    'Проверьте дату и укажите полный год, например: 08.09.2026. '
                    'Пример не является вашими данными.')
        return None
    return ('Когда приобретён товар? Укажите дату покупки; название товара и продавца повторять не нужно. '
            'Если дата неизвестна, так и напишите.')


def _active_purchase_answer(state, text: str) -> bool:
    """Whether a short turn is the literal answer to the purchase question.

    People normally omit the verb in this reply ("8.09.2026 в магазине ...")
    because the question already says what was purchased.  Requiring another
    "купила" made the deterministic collector miss the answer and left a gap
    whenever the provider was unavailable or conservative.
    """
    if (state.get('last_questions') or [None])[0] != 'purchase':
        return False
    if not re.search(r'\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b|\b\d{1,2}\s+[а-яё]+\s+\d{4}\b', text, re.I):
        return False
    return bool(_CONSUMER_GOODS.search(text) or re.search(r'\b(?:магазин|продавц|заказ|приобр|купил)\w*\b', text, re.I))


def _purchase_subject(state) -> str | None:
    """Return only a product explicitly named earlier in this conversation."""
    # ``collect_explicit_facts`` appends the current answer before this
    # collector runs.  Inspect every available source; a date-only answer is
    # skipped naturally, while the earlier drafting request still contributes
    # its explicitly named product.
    sources = [*state.get('user_turns', []), state.get('request', '')]
    for source in reversed(sources):
        match = _CONSUMER_GOODS.search(source or '')
        if match and match[0].casefold() != 'товар':
            value = match[0]
            canonical = (
                ('холодильн', 'холодильник'), ('стиральн', 'стиральная машина'),
                ('посудомоечн', 'посудомоечная машина'), ('микроволнов', 'микроволновая печь'),
                ('телевизор', 'телевизор'), ('пылесос', 'пылесос'), ('ноутбук', 'ноутбук'),
                ('смартфон', 'смартфон'), ('телефон', 'телефон'),
                ('планшет', 'планшет'), ('монитор', 'монитор'), ('фотоаппарат', 'фотоаппарат'),
                ('компьютер', 'компьютер'),
            )
            lowered = value.casefold()
            return next((name for stem, name in canonical if stem in lowered), value)
    return None


def receipt_evidence(text: str) -> str | None:
    """Return the literal sentence in which the user says a receipt exists."""
    for sentence in source_sentences(text or ''):
        sentence = sentence.strip()
        if not _RECEIPT_ABSENT.search(sentence) and receipt_parties(sentence)[0]:
            return sentence
        present = _RECEIPT_PRESENT.search(sentence)
        if not present or _RECEIPT_ABSENT.search(sentence):
            continue
        if '?' not in sentence:
            return sentence
        # A person can answer and ask for guidance in one turn: "Есть чек,
        # а какие реквизиты указать?".  Keep the assertion before the comma,
        # but do not turn an actual question such as "чек есть?" into a fact.
        question = sentence.find('?')
        separator = re.search(r'[,;.]', sentence[present.end():question])
        if present.start() == 0 and separator:
            return sentence[:present.end()]
    return None


def _seller_field(state):
    from app.services.document_scenarios import SCENARIOS
    for spec in SCENARIOS[state['scenario']].fields:
        if spec.key == 'seller' or (spec.key == 'recipient' and re.search(r'продавец|исполнитель', spec.label, re.I)):
            return spec.key
    return None


def _product_at_seller(text):
    """A quoted item followed by a single identified company is two facts."""
    match = _PURCHASE_SELLER.search(text)
    if not match or text[match.end():].strip(' .'):
        return None
    product = text[:match.start()].strip()
    if re.fullmatch(_QUOTED_NAME, product):
        return product, match[1]
    return None


def collect_consumer_facts(state, text, put):
    if 'consumer' not in state.get('scenario', ''):
        return
    from app.services.document_money_tokens import find_money_quotes
    if state['scenario'] == 'pretense_consumer_defective_service':
        _collect_service_facts(text, put)
    receipt = receipt_evidence(text)
    if pair := _product_at_seller(text):
        seller_key = _seller_field(state)
        if seller_key and seller_key in state.get('last_questions', ()):
            put(seller_key, pair[1], text)
            put('goods_category', pair[0], text)
    sentences = source_sentences(text)
    purchase_clause = next((s for s in sentences if '?' not in s and _PURCHASE_VERB.search(s)), None)
    if purchase_clause is None and sentences and _active_purchase_answer(state, sentences[0]):
        source = sentences[0]
        # Keep the supplied wording and add only the product that the person
        # explicitly named earlier.  This is contextual ellipsis resolution,
        # not a guessed make, model, seller or purchase date.
        if not _CONSUMER_GOODS.search(source):
            product = _purchase_subject(state)
            if product:
                source = f'{source.rstrip(". ")}. Приобретённый товар: {product}.'
        put('purchase', source, sentences[0])
    for index, sentence in enumerate(sentences):
        if '?' in sentence:
            continue
        receipt_kind, receipt_seller = receipt_parties(sentence)
        if receipt_seller and (field_key := _seller_field(state)):
            put(field_key, receipt_seller, sentence)
        if sentence == purchase_clause:
            put('purchase', sentence, sentence)
            product = _named_product(sentence)
            if product and (model := _product_model(product, sentence)):
                put('goods_category', f'{product[0].lower()} {model}', sentence)
            seller = _PURCHASE_SELLER.search(sentence)
            if not product:
                # A quoted model may follow either the item or the seller.
                # Exclude company names and titles following a document label.
                after_verb = _PURCHASE_SELLER.sub('', sentence[_PURCHASE_VERB.search(sentence).end():])
                models = [match[0] for match in re.finditer(_QUOTED_NAME, after_verb)
                          if not re.search(r'\b(?:магазин\w*|компани\w*|ООО|ПАО|АО|ИП|договор\w*)\s*$',
                                           after_verb[:match.start()], re.I)]
                if len(models) == 1:
                    put('goods_category', models[0], sentence)
            if seller and sentence != state.get('consumer_disputed_purchase') and (field_key := _seller_field(state)):
                put(field_key, seller[1], sentence)
            purpose = list(_USE_PURPOSE.finditer(sentence))
            if len(purpose) == 1 and not re.search(r'\bне\s*$', sentence[:purpose[0].start()], re.I):
                put('consumer_status', purpose[0][0], sentence)
            amounts = find_money_quotes(sentence)
            if len(amounts) == 1:
                put('amount', amounts[0], sentence)
        if re.search(r'перестал\w*\s+\w+|не\s+(?:работает|охлаждает|включается)|обнаружен\w*\s+(?:дефект|недостат)|'
                     r'\b(?:теч[её]т\s+вода|протекает|протечка|стал[ао]?\s+гаснуть)\b', sentence, re.I):
            put('defect', sentence, sentence)
        if re.search(r'\b(?:не\s+(?:падал\w*|ронял\w*|ремонтировал\w*)|'
                     r'с\s+водой\s+не\s+контактировал\w*|пользовал\w*\s+по\s+инструкции)\b', sentence, re.I):
            use = re.split(r'[,;]\s*(?=[^,;]{0,40}\b(?:сня[лт]\w*\s+на\s+видео|сфотографир\w*))', sentence, maxsplit=1, flags=re.I)
            put('facts', use[0], sentence)
        refund = re.search(r'\b(?:хочу|прошу|требую)\b.{0,100}\b(?:получить|вернуть)\b.{0,45}'
                           r'\b(?:деньги|оплат\w*|уплаченн\w* сумм\w*|рубл\w*)\b', sentence, re.I)
        response_and_request = _BUYER_CLAUSE.split(sentence, maxsplit=1)
        if refund:
            put('requests', response_and_request[-1], sentence)
            if method := re.search(r'\bна\s+(?:карту|сч[её]т)\b[^.!?]*', sentence, re.I):
                put('payment', method[0], sentence)
        if receipt and sentence.strip() == receipt:
            stated_kind = re.search(r'\b(?:электронн\w*|кассов\w*)\s+чек\b', sentence, re.I)
            put('payment_evidence', receipt_kind or (stated_kind[0] if stated_kind else 'чек'), sentence)
        if (re.search(r'\b(?:видео|видеозапис|фото|фотограф)\w*\b', sentence, re.I)
                and not re.search(r'\bне\s+(?:сня[лт]|снима|сфотографир)\w*|\b(?:видео|фото)\s+нет\b', sentence, re.I)
                and re.search(r'неисправ|недостат|дефект|не\s+(?:работает|охлаждает)|перестал|сня[лт]\w*\s+(?:это\s+)?на\s+видео', sentence, re.I)):
            evidence_clause = next((s.strip() for s in re.split('[,;]', sentence)
                                    if re.search(r'\b(?:сня[лт]\w*\s+на\s+видео|сфотографир\w*)', s, re.I)), sentence)
            put('defect_evidence', evidence_clause, sentence)
        if items := re.match(r'\s*(?:к\s+претензии\s+)?(?:приложу|прилагаю)\s+(.+?)[.!]*$', sentence, re.I):
            put('attachments', items[1], sentence)
        if _STORE_REPLY.search(sentence):
            response = response_and_request[0]
            if len(response_and_request) > 1 and re.match(r'\d{1,2}\s+\w+', response):
                put('facts', response, sentence)
            if index and re.search(r'\b(?:прин[её]с\w*|обратил\w*|обращал\w*|отн[её]с\w*)\b.*?\b(?:магазин\w*|продавц\w*)\b',
                                   sentences[index-1], re.I):
                response = sentences[index-1] + ' ' + response
            put('seller_response', response, response)
        if re.search(r'(?:к продавцу|в магазин).{0,15}(?:пока\s+)?не обращал|(?:пока\s+)?не обращал\w*.{0,20}(?:к продавцу|в магазин)|ни к кому не обращал', sentence, re.I):
            put('seller_response', sentence, sentence)
        if re.match(r'\s*(?:Обнаружение неисправности|Дата обнаружения (?:недостатков|неисправности))\s*:',sentence,re.I):
            put('facts', sentence, sentence)


def _collect_service_facts(text, put):
    from app.services.document_money_tokens import find_money_quotes

    sentences = source_sentences(text)
    services = [s for s in sentences if _PURCHASE_SELLER.search(s)
                and re.search(r'\b(?:сдал[аи]?|передал[аи]?|заказал[аи]?)\b', s, re.I)]
    if len(services) == 1:
        service = services[0]
        following = sentences[sentences.index(service) + 1:sentences.index(service) + 2]
        ref = next((s for s in following if re.fullmatch(
            r'(?:номер\s+заказа|заказ\s*№|квитанция\s*№)\s*[:№]?\s*[\w/-]+\.?', s, re.I)), '')
        purchase = service + (' ' + ref if ref else '')
        # The order number can be in a different sentence; both remain in
        # the purchase field and the complete user turn is its provenance.
        put('purchase', purchase, text if ref else service)
        seller = _PURCHASE_SELLER.search(service)
        put('recipient', seller[1], service)
        if description := re.search(r'\bдля\s+([^.!?;]+)', service[seller.end():], re.I):
            if not _USE_PURPOSE.fullmatch(description[0]):
                subject = re.search(r'\b(?:сдал[аи]?|передал[аи]?|заказал[аи]?)\s+(.+?)\s*$', service[:seller.start()], re.I)
                value = (subject[1] + ' ' + description[0]) if subject else description[1]
                put('service_description', value, service)
    for index, sentence in enumerate(sentences):
        if re.search(r'\b(?:заплатил[аи]?|оплатил[аи]?|уплатил[аи]?|платил[аи]?)\b', sentence, re.I):
            amounts = find_money_quotes(sentence)
            if len(amounts) == 1:
                put('amount', amounts[0], sentence)
            proof = re.search(r'\b(?:квитанци[яю]|чек)\s+(?:сохранил\w*|есть|имеется)', sentence, re.I)
            if proof:
                put('payment_evidence', proof[0], sentence)
        if (re.search(r'\b(?:увидел[аи]?|обнаружил[аи]?|заметил[аи]?)\b[^.!?;]{0,65}\b(?:пятн\w*|развод\w*|дыр\w*|повреждени\w*)\b|'
                      r'\b(?:остались|появились|осталось|появилось)\s+(?:\w+\s+){0,2}(?:пятн[ао]|разводы)\b|'
                      r'\b(?:повредил\w*|поврежд[её]н\w*|полинял\w*|усадк\w*|оторвал\w*|оторван\w*|порвал\w*|порван\w*)\b',
                      sentence, re.I) and '?' not in sentence
                and not re.search(r'\bне\s+(?:увидел|обнаружил|заметил)\w*\b', sentence, re.I)):
            put('defect', sentence, sentence)
        if re.search(r'\b(?:сфотографировал[аи]?|снял[аи]?\s+на\s+видео)\b', sentence, re.I):
            put('defect_evidence', sentence, sentence)
        if re.search(r'\b(?:химчистк\w*|исполнитель|администратор)\s+(?:отказал\w*|предложил\w*|ответил\w*)\b', sentence, re.I):
            response = sentence
            following = sentences[index+1:index+2]
            if following and re.match(r'^(?:я\s+)?(?:отказал[а-я]*сь|согласил[а-я]*сь)\b', following[0], re.I):
                response += ' ' + following[0]
            put('seller_response', response, response)
        if comparison := re.search(r'\bпри\s+(?:сдаче|при[её]мке)[^,;.!?]*', sentence, re.I):
            put('facts', comparison[0], sentence)
        if photo := re.search(r'\b(?:видно|зафиксирован\w*)\s+на\s+(фото(?:графи\w*)?[^.!?;]*)', sentence, re.I):
            put('defect_evidence', photo[1], sentence)
        if re.match(r'\s*(?:стоимость|цену)\b.*\bне\s+(?:прошу|требую|заявляю)\b', sentence, re.I):
            # The user can decline the cost of an item while claiming a different extra expense.
            if re.search(r'\b(?:вернуть|взыскать|возместить)\s+только\b', text, re.I):
                put('additional_claims', sentence, sentence)


def supplement_consumer_narrative(state, text):
    """Fill omitted slots from literal statements without changing a resolved answer."""
    from app.services.document_case_facts import set_field
    from app.services.document_explicit_facts import collect_explicit_facts
    from app.services.document_scenarios import SCENARIOS

    if 'consumer' not in state.get('scenario', ''):
        return set()
    available = {spec.key for spec in SCENARIOS[state['scenario']].fields}
    filled = set()

    def put(key, value, evidence):
        if key not in available:
            return
        old = state['fields'].get(key, {})
        if (key in {'purchase', 'service_description', 'defect', 'seller_response', 'defect_evidence'}
                and state['scenario'] == 'pretense_consumer_defective_service'
                and old.get('origin') == 'llm_user_quote' and key not in state.get('narrative_decisions', {})
                and old.get('value') and old['value'].casefold() in value.casefold()
                and old['value'] != value and (key != 'purchase' or not _purchase_date_error(value))
                and (old.get('evidence') or '').casefold() in text.casefold()):
            if set_field(state, key, value, evidence):
                filled.add(key)
            return
        if (old.get('status') in {'filled', 'unknown', 'not_applicable', 'review_required'}
                or key in state.get('narrative_decisions', {})
                or old.get('origin') in {'manual', 'narrative_conflict', 'consumer_seller_conflict', 'consumer_seller_address'}):
            return
        if set_field(state, key, value, evidence):
            filled.add(key)

    # Reuse role-bound identification for an introduction in the same turn.
    if 'sender' in available and not state['fields'].get('sender', {}).get('value'):
        trial = deepcopy(state)
        if 'sender' in collect_explicit_facts(trial, text):
            author = trial['fields']['sender']
            put('sender', author['value'], author['evidence'])
    collect_consumer_facts(state, text, put)
    return filled


def _seller_name_key(name):
    return re.sub(r'[\W_]+', '', name.casefold().replace('ё', 'е'))


def _purchase_seller_name(text):
    """Recognize one explicit seller in a narrative accidentally saved as the addressee."""
    if not _PURCHASE_VERB.search(text):
        return None
    readings = list(_PURCHASE_SELLER.finditer(text))
    if not readings:
        return None
    name = readings[0][1]
    companies = re.findall(r'\b(?:ООО|ПАО|АО|ОАО|ЗАО)\s*' + _QUOTED_NAME, text, re.I)
    if any(_seller_name_key(company) != _seller_name_key(name) for company in companies):
        return None
    # A negated, hypothetical or unresolved purchase cannot identify the addressee.
    if ('?' in text or re.search(r'\b(?:не\s+(?:покупал|купил|заказал|приобр)|возможно|например|либо)\w*', text, re.I)
            or any(re.search(r'\bне\s*$', text[:reading.start()], re.I) for reading in readings)):
        return None
    return name


def resolve_consumer_seller_choice(state, key, message):
    """Bind an ordinal or confirmation to the alternatives in the last question."""
    fields = state.get('fields', {})
    item = fields.get(key, {})
    origin = item.get('origin')
    if origin not in {'consumer_seller_conflict', 'consumer_seller_address'}:
        return False
    from app.services.document_case_facts import set_field
    from app.services.document_dialogue import asks_for_help, is_recall_request, leaves_blank
    text = message.strip(' .!')
    if leaves_blank(text):
        return set_field(state, key, None, message, 'unknown')
    if asks_for_help(text) or is_recall_request(text):
        return False
    if origin == 'consumer_seller_address':
        candidate = item.get('proposed_address')
        if candidate and re.fullmatch(r'(?:да|верно|правильно|подтверждаю|тот же|адрес тот же|да[, ]+верно)', text, re.I):
            return set_field(state, key, candidate, f'{candidate}\n{message}')
        if re.fullmatch(r'нет|другой|адрес другой', text, re.I):
            item.pop('proposed_address', None)
            item['error'] = 'Какой адрес указать для выбранного продавца?'
            return True
        return False
    choices = item.get('seller_choices') or []
    if len(choices) != 2:
        return False
    answer = re.split(r'[,;\n]|\.\s+(?=[А-ЯЁ])', text, maxsplit=1)[0].strip()
    ordinal = re.fullmatch(r'(?:вариант\s+)?(1|2|перв(?:ый|ого|ую)|втор(?:ой|ого|ую))(?:\s+(?:вариант|продавец|продавца|компанию))?', answer, re.I)
    if ordinal:
        selected = choices[0] if ordinal[1].casefold().startswith(('1', 'перв')) else choices[1]
    else:
        reply_name = _seller_name_key(answer)
        matches = [name for name in choices if reply_name in (
            _seller_name_key(name),
            _seller_name_key(re.sub(r'^(?:ООО|АО|ПАО|ЗАО|ОАО|ИП)\s+', '', name, flags=re.I)),
        )]
        selected = matches[0] if len(matches) == 1 else None
        if selected is None:
            # The person may explicitly supply a third, corrected legal name.
            if not re.fullmatch(r'(?:ООО|АО|ПАО|ОАО|ЗАО|ИП)\s+(?:«[^»]+»|"[^"]+"|[\w-]+(?: [\w-]+){0,4})', answer, re.I):
                # File/control requests have their own workflow. An ambiguous
                # acknowledgment by itself cannot select one of two names.
                from app.services.document_workflow import file_request_kind
                return not file_request_kind(message)
            selected = answer
    set_field(state, key, selected, f'{selected}\n{message}')
    confirm_address_after_seller_change(state, key, choices[0], selected)
    if (fields.get(key + '_address') or {}).get('origin') == 'consumer_seller_address':
        from app.services.document_addresses import collect_role_addresses
        collect_role_addresses(state, message)
    return True


def confirm_address_after_seller_change(state, key, previous_name, selected):
    if (not previous_name or not selected or 'consumer' not in state.get('scenario', '')
            or _seller_field(state) != key or _seller_name_key(selected) == _seller_name_key(previous_name)):
        return
    address = state.get('fields', {}).get(key + '_address', {})
    if address.get('status') == 'filled' and address.get('value'):
        previous = address['value']
        address.update(status='incomplete', value=None, proposed_address=previous,
                       origin='consumer_seller_address',
                       error=f'Для {selected} указать прежний адрес «{previous}»? Если адрес другой, напишите его.')


def _reconcile_purchase_seller(state, purchase):
    sentence = purchase.get('value') or ''
    match = _PURCHASE_SELLER.search(sentence)
    if not match or not _PURCHASE_VERB.search(sentence):
        return
    field_key = _seller_field(state)
    if not field_key:
        return
    recipient = state['fields'].get(field_key, {})
    previous = recipient.get('value') or ''
    if recipient.get('status') != 'filled' or not previous:
        return
    if _seller_name_key(previous) == _seller_name_key(match[1]):
        return
    # Keep the purchase date, item and price. The confirmed seller will
    # appear in the addressee slot; a disputed name must not survive in prose.
    purchase['value'] = re.sub(r'\s+', ' ', sentence[:match.start()] + sentence[match.end():]).strip()
    purchase['value'] = re.sub(r'\s+([.,;])', r'\1', purchase['value'])
    if sentence == state.get('consumer_disputed_purchase'):
        return
    state['consumer_disputed_purchase'] = sentence
    recipient.update(
        status='incomplete', value=None, origin='consumer_seller_conflict', seller_choices=[previous, match[1]],
        error=f'Какого продавца указать в документе — 1) {previous} или 2) {match[1]}?',
    )


def _paid_price_reference(key, clause, token):
    """A price and a separate expense can have the same numeric value."""
    before, after = clause[:token.start()], clause[token.end():]
    if re.search(r'\b(?:частичн\w*|часть|неустойк\w*|убыт\w*|расход\w*|доставк\w*|'
                 r'аванс\w*|задат\w*|предлаг\w*|предлож\w*|компенсац\w*|скидк\w*)\b', clause, re.I):
        return False
    if key == 'requests':
        # A numerical request follows the purchase price only when it actually
        # asks for that refund. Keep reductions, caps and independent claims.
        refund = re.search(r'\b(?:вернуть|возвратить|верните|возврат(?:ить)?|получить)\s+'
                           r'(?:(?:только|мне|уплаченн\w*|полную|сумму|стоимость|'
                           r'оплату|денег|денежных|средств|за|товар|услугу|в|размере)\s+)*$', before, re.I)
        return bool(refund and not re.search(r'\bне\s+(?:(?:прошу|хочу|требую)\s+)?$', before[:refund.start()], re.I)
                    and re.match(r'^\s*(?:(?:за\s+(?:услуг\w*|товар\w*|работ\w*|заказ\w*)|'
                                 r'на\s+(?:карту|сч[её]т)\b.*)\s*)*[.!?]*$', after, re.I))
    return bool((_PURCHASE_VERB.search(before) and re.search(r'\b(?:за|стоимостью|ценой|по цене)\s*$', before, re.I))
                or re.search(r'\b(?:за\s+(?:услугу|товар|работу)\s+)?(?:у|о|за)?платил[аи]?\s+'
                             r'(?:(?:картой|наличными)\s+)?$', before, re.I)
                or re.search(r'\b(?:цена|стоимость|оплата)\s+(?:услуги|товара|работы|заказа)\s*'
                             r'(?:(?:состав\w*)\s+|[-—:]\s*)?$', before, re.I))


def reprice_consumer_text(key, text, old_amount, new_amount):
    from app.services.document_money_tokens import MONEY_PATTERN, money_token_starts_here
    from app.services.document_presentation import format_money
    from app.services.document_workflow import normalize_money

    # Split on clause boundaries, while preserving decimals and every separator.
    parts = re.split(r'([.!?;]\s+|,\s+|\s+и\s+(?=(?:возместить|взыскать|вернуть|получить)\b)|\n+)', text, flags=re.I)
    for index in range(0, len(parts), 2):
        clause = parts[index]
        for token in reversed(list(re.finditer(MONEY_PATTERN, clause, re.I))):
            if (money_token_starts_here(clause, token.start()) and normalize_money(token[0]) == old_amount
                    and _paid_price_reference(key, clause, token)):
                number = format_money(new_amount)
                # Use the invariant currency sign for numbers where the case
                # depends on the surrounding verb/preposition.
                unit = ' ₽' if ',' in number or number.endswith(('1', '2', '3', '4')) else ' рублей'
                amount = number + unit
                parts[index] = parts[index][:token.start()] + amount + parts[index][token.end():]
    return ''.join(parts)


def sync_consumer_amount_correction(before, state, changed):
    """Update price-dependent facts once, keeping the original quotes for audit."""
    if not state.get('scenario', '').startswith('pretense_consumer_'):
        return
    old_amount = before['fields'].get('amount', {}).get('value')
    current = state['fields'].get('amount', {})
    if not old_amount or current.get('status') != 'filled' or old_amount == current['value']:
        return
    _sync_consumer_price_references(state, old_amount, changed)


def _sync_consumer_price_references(state, old_amount, changed):
    current = state['fields']['amount']
    current['price_references_synced'] = True
    for key in ('purchase', 'payment_evidence', 'facts', 'requests'):
        field = state['fields'].get(key, {})
        if key in changed or field.get('status') != 'filled' or not field.get('value'):
            continue
        value = reprice_consumer_text(key, field['value'], old_amount, current['value'])
        if value != field['value']:
            field.setdefault('price_reference', {'value': field['value'], 'amount': old_amount})
            field.update(value=value, origin='corrected_purchase_price',
                         source_quotes=list(dict.fromkeys([*(field.get('source_quotes') or []),
                                                          current['evidence']])))


def _repair_saved_price_correction(state):
    """Recover the old price of a legacy corrected draft from transaction evidence."""
    current = state['fields'].get('amount', {})
    if (not state['scenario'].startswith('pretense_consumer_') or current.get('status') != 'filled'
            or current.get('origin') != 'user_correction' or current.get('price_references_synced')
            or not current.get('evidence')):
        return
    from app.services.document_workflow import normalize_money
    old_amounts = set()
    def collect(key, value, evidence):
        if key == 'amount' and (price := normalize_money(value)) and price != current['value']:
            old_amounts.add(price)
    for turn in dict.fromkeys([state.get('request') or '', *state.get('user_turns', ())]):
        collect_consumer_facts(state, turn, collect)
    if len(old_amounts) == 1:
        independent_edits = {k for k, item in state['fields'].items() if item.get('origin') == 'user_correction'}
        _sync_consumer_price_references(state, old_amounts.pop(), independent_edits)


def prepare_consumer_facts(state):
    if 'consumer' not in state.get('scenario', ''):
        return
    _repair_saved_price_correction(state)
    from app.services.document_scenarios import SCENARIOS
    has_model = any(f.key == 'goods_category' for f in SCENARIOS[state['scenario']].fields)
    fields = state['fields']
    seller_key = _seller_field(state)
    for key in ('goods_category', seller_key):
        saved = fields.get(key, {})
        quote = saved.get('value') or ''
        evidence = saved.get('evidence') or quote
        if (not quote or saved.get('status') != 'filled' or key in state.get('narrative_decisions', {})
                or str(saved.get('origin') or '').startswith('manual') or not _RECEIPT_LOCATOR.search(evidence)):
            continue
        checked = consumer_role_quote(key, quote, evidence, evidence)
        if checked and checked[0] != quote:
            saved.update(value=checked[0], original=checked[0], evidence=checked[1])
        elif checked is None and key == 'goods_category':
            # Recover the product from its own purchase evidence when an older
            # session put a seller's packaging / receipt sentence in this slot.
            del fields[key]
            purchase = fields.get('purchase', {})
            def recover_product(field, value, proof):
                if field == 'goods_category':
                    from app.services.document_case_facts import set_field
                    set_field(state, field, value, proof)
            collect_consumer_facts(state, purchase.get('evidence') or purchase.get('value') or '', recover_product)
    # A real source sentence can answer multiple questions. Older chats and
    # overly broad model quotes stored it as the value of each compact slot.
    # Reuse the intake splitter on the saved value; keep the full evidence.
    for key in ('consumer_status', 'goods_category', 'payment', seller_key):
        item = fields.get(key, {})
        source = item.get('value')
        if (item.get('status') != 'filled' or not source or not isinstance(source, str)
                or str(item.get('origin', '')).startswith('manual')):
            continue
        parts = []
        def capture(field, value, evidence):
            if field == key and value not in parts:
                parts.append(value)
        collect_consumer_facts(state, source, capture)
        if len(parts) == 1 and parts[0] != source and parts[0].casefold() in source.casefold():
            item.update(value=parts[0], original=parts[0])
    seller = fields.get(seller_key, {})
    if seller.get('origin') == 'consumer_seller_conflict':
        choices = seller.get('seller_choices') or []
        if (len(choices) == 2 and (company := _purchase_seller_name(choices[0]))
                and _seller_name_key(company) == _seller_name_key(choices[1])):
            from app.services.document_case_facts import set_field
            # Recover older sessions stopped at a choice between the same party and its purchase sentence.
            set_field(state, seller_key, choices[1], choices[0])
            seller = fields[seller_key]
            state.pop('consumer_disputed_purchase', None)
    if seller.get('status') == 'filled' and (company := _purchase_seller_name(seller.get('value') or '')):
        seller.update(value=company, original=seller.get('original') or seller['value'])
    if (seller.get('status') == 'filled' and seller.get('origin') != 'manual'
            and (pair := _product_at_seller(seller.get('value') or ''))):
        seller.update(value=pair[1], original=seller.get('original') or seller['value'])
        category = fields.get('goods_category', {})
        if has_model and not category.get('status'):
            from app.services.document_case_facts import set_field
            set_field(state, 'goods_category', pair[0], seller.get('evidence') or seller['original'])
    purchase=fields.get('purchase',{})
    if purchase.get('status')=='filled':
        # A model may select just the product phrase from a dated purchase
        # statement. Its own cited sentence already answers the date question.
        value = purchase.get('value') or ''
        if value and _purchase_date_error(value):
            for sentence in source_sentences(purchase.get('evidence') or ''):
                if value in sentence and _PURCHASE_VERB.search(sentence) and not _purchase_date_error(sentence):
                    purchase.update(value=sentence, original=sentence)
                    break
        _reconcile_purchase_seller(state, purchase)
        source=purchase.get('value') or ''
        if error := _purchase_date_error(source):
            purchase.update(status='incomplete',error=error)
    if not has_model:
        return
    category = fields.get('goods_category', {})
    if category.get('status') in {'unknown', 'not_applicable'}:
        return
    purchase = fields.get('purchase', {})
    source = purchase.get('value') or ''
    product = _named_product(source)
    if product:
        value=category.get('value') or ''
        generic=bool(re.fullmatch(r'бытовая техника|(?:продовольственные )?товары|продукты питания',value,re.I)
                     or _CONSUMER_GOODS.fullmatch(value)
                     or re.search(r'хранени[ея] продуктов',value,re.I))
        if category.get('origin')!='product_vocabulary' and category.get('status')=='filled' and not generic:return
        # A known product kind does not identify its make/model. Ask only for
        # that missing detail, not the already obvious household category.
        model_value = _product_model(product, source)
        fields['goods_category'] = {
            'status': 'filled' if model_value else 'incomplete',
            'value': product[0].lower()+' '+model_value if model_value else product[0].lower(),
            'evidence': source, 'origin': 'product_vocabulary', 'inputs': ['purchase'],
            'error':None if model_value else 'Какие марка и модель указаны на товаре или в чеке? Если не знаете, можно оставить их для уточнения.',
        }
    elif category.get('origin') == 'product_vocabulary':
        fields.pop('goods_category', None)
