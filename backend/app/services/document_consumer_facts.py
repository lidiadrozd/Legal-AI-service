"""Literal consumer facts shared by consumer letters and claims.

Keep the user's wording as evidence. Product classification here is ordinary
vocabulary, never a determination of the product's statutory legal category.
"""
import re


def collect_consumer_facts(state, text, put):
    if 'consumer' not in state.get('scenario', ''):
        return
    for sentence in re.split(r'(?<=[.!?])\s+(?=[А-ЯЁ]|\d{1,2}\s+[а-яё]+\s+\d{4})|\n+', text):
        if '?' in sentence:
            continue
        if re.search(r'\b(?:купил[аи]?|приобр[её]л[аи]?|заказал[аи]?)\b', sentence, re.I):
            put('purchase', sentence, sentence)
            seller = re.search(r'\b(?:в|у)\s+((?:ООО|АО|ПАО|ЗАО|ОАО)\s*[«"][^»"]+[»"])', sentence)
            if seller:
                put('recipient', seller[1], sentence)
            amounts = re.findall(r'\d+(?:[ \u00a0]\d{3})*(?:[.,]\d{1,2})?\s*(?:рублей|рубля|рубль|руб\.?|₽)', sentence, re.I)
            if len(amounts) == 1:
                put('amount', amounts[0], sentence)
        if re.search(r'перестал\w*\s+\w+|не\s+(?:работает|охлаждает|включается)|обнаружен\w*\s+(?:дефект|недостат)', sentence, re.I):
            put('defect', sentence, sentence)
        if re.fullmatch(r'\s*(?:хочу|прошу|требую)\s+вернуть\s+(?:деньги|оплату|уплаченную сумму)[.! ]*', sentence, re.I):
            put('requests', sentence, sentence)
        if re.fullmatch(r'\s*(?:чек\s+(?:сохранился|есть)|(?:есть|сохранился)\s+чек)[.! ]*', sentence, re.I):
            put('payment_evidence', sentence, sentence)
        if re.search(r'(?:к продавцу|в магазин).{0,15}(?:пока\s+)?не обращал|(?:пока\s+)?не обращал\w*.{0,20}(?:к продавцу|в магазин)|ни к кому не обращал', sentence, re.I):
            put('seller_response', sentence, sentence)
        if re.match(r'\s*(?:Обнаружение неисправности|Дата обнаружения (?:недостатков|неисправности))\s*:',sentence,re.I):
            put('facts', sentence, sentence)


def prepare_consumer_facts(state):
    if 'consumer' not in state.get('scenario', ''):
        return
    fields = state['fields']
    purchase=fields.get('purchase',{})
    if purchase.get('status')=='filled':
        source=purchase.get('value') or ''
        from app.services.document_case_facts import DATE
        if not re.search(DATE,source,re.I) and not re.search(r'\b\d{1,2}\s+(?:январ|феврал|март|апрел|мая|июн|июл|август|сентябр|октябр|ноябр|декабр)',source,re.I):
            purchase.update(status='incomplete',error='Когда приобретён товар? Укажите дату покупки; название товара и продавца повторять не нужно. Если дата неизвестна, так и напишите.')
    from app.services.document_scenarios import SCENARIOS
    if 'goods_category' not in {f.key for f in SCENARIOS[state['scenario']].fields}:
        return
    category = fields.get('goods_category', {})
    if category.get('status') in {'unknown', 'not_applicable'}:
        return
    purchase = fields.get('purchase', {})
    source = purchase.get('value') or ''
    product = re.search(r'\b(?:холодильник|телевизор|стиральная машина|посудомоечная машина|пылесос|микроволновая печь)\b', source, re.I)
    if product:
        value=category.get('value') or ''
        generic=bool(re.fullmatch(r'бытовая техника|(?:продовольственные )?товары|продукты питания|холодильник|телевизор',value,re.I)
                     or re.search(r'хранени[ея] продуктов',value,re.I))
        if category.get('origin')!='product_vocabulary' and category.get('status')=='filled' and not generic:return
        if category.get('status')=='incomplete' and category.get('origin')=='product_vocabulary' and category.get('evidence')==source:return
        # A known product kind does not identify its make/model. Ask only for
        # that missing detail, not the already obvious household category.
        model=re.search(re.escape(product[0])+r'\s+([A-Za-zА-ЯЁ][A-Za-zА-ЯЁ0-9-]*(?:\s+[A-Za-zА-ЯЁ0-9-]+){0,3}\s+[A-Za-zА-ЯЁ0-9-]*\d[A-Za-zА-ЯЁ0-9-]*)\b',source)
        model_known=bool(model or re.search(r'марка\s*[:—]|модель\s*[:—]',source,re.I))
        fields['goods_category'] = {
            'status': 'filled' if model_known else 'incomplete', 'value': product[0].lower()+' '+model[1] if model else source if model_known else product[0].lower(),
            'evidence': source, 'origin': 'product_vocabulary', 'inputs': ['purchase'],
            'error':None if model_known else 'Какие марка и модель указаны на товаре или в чеке? Если не знаете, можно оставить их для уточнения.',
        }
    elif category.get('origin') == 'product_vocabulary':
        fields.pop('goods_category', None)
