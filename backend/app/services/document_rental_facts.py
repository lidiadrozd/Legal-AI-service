"""Source-bound rental facts: separate the payment, return and contract terms."""
import re


def collect_rental_turn(state,text,current,put):
    from app.services.document_scenarios import SCENARIOS
    from app.services.document_case_facts import MONEY,DATE
    specs={f.key:f for f in SCENARIOS[state['scenario']].fields}
    if not {'deposit_payment','deposit_terms','return_facts'}<=set(specs):return set()
    consumed=set()
    def save(key,value,evidence):
        before=state['fields'].get(key)
        put(key,value,evidence)
        if state['fields'].get(key)!=before:consumed.add(key)
    requested=re.search(r'(?:обеспечительн\w* плат[её]ж|депозит)\s*[—:-]?\s*('+MONEY+r')',text,re.I)
    if requested and re.search(r'не возвращ|не вернул|возврат',text,re.I):save('amount',requested[1],requested[0])
    pending=state.get('rental_payment_confirmation')
    if current=='deposit_payment' and pending:
        if re.search(r'обеспечительн\w* плат[её]ж',text,re.I):
            # The legal name changes only after the user confirms it.
            literal=pending.get('amount')
            from app.services.document_workflow import normalize_money
            from app.services.document_case_composition import _money
            amount=normalize_money(literal.rstrip(' .')) if literal else None
            value=('Внесён обеспечительный платёж в размере '+_money(amount)+'.') if amount else pending['original']
            if pending.get('receipt'):value+=' Имеется чек.'
            save(current,value,pending['original']+'\nУточнение: '+text)
            state.pop('rental_payment_confirmation',None)
            return consumed
        if re.fullmatch(r'\s*(?:это )?аванс[.! ]*',text,re.I):
            state['fields'][current].update(status='incomplete',error='Понял: в договоре указан аванс. Этот шаблон предназначен для обеспечительного платежа. Приведите условие договора о назначении и возврате аванса, чтобы проверить подходящую форму.')
            return {current}
    if current=='deposit_payment':
        amounts=re.findall(MONEY,text,re.I)
        if len(amounts)==1:save('amount',amounts[0],amounts[0])
        if re.search(r'\bаванс\b',text,re.I) and not re.search(r'не аванс|назвал\w* авансом',text,re.I):
            save(current,text,text)
            state['rental_payment_confirmation']={'original':text,'amount':amounts[0] if len(amounts)==1 else None,'receipt':bool(re.search(r'есть чек|имеется чек',text,re.I))}
            state['fields'][current].update(status='incomplete',error='Вы назвали сумму авансом, а готовим документ о возврате обеспечительного платежа. Как именно эта сумма названа в договоре: «аванс» или «обеспечительный платёж»?')
            return consumed
    # Mechanical removal of an accidental slash between letters preserves the
    # source spelling otherwise. Keep the untouched message as evidence.
    clean=re.sub(r'(?<=[А-Яа-яЁё])\\(?=[А-Яа-яЁё])','',text)
    clauses=[x.strip(' .') for x in re.split(r'(?<=[.!?])\s+(?=[А-Яа-яЁё])',clean) if x.strip(' .')]
    if current in {'deposit_terms','return_facts'}:
        returned=[x for x in clauses if re.search(r'(?:квартир|жиль|помещени|ключ)\w*\s+возвращ[её]н',x,re.I)]
        no_debt=[x for x in clauses if re.search(r'долг\w*\s+(?:по оплате\s+)?нет|задолженность отсутствует',x,re.I)]
        terms=[x for x in clauses if x not in returned+no_debt and re.search(r'по договору|плат[её]ж возвращается|срок\w* возврата',x,re.I)]
        if returned:
            no_debt=['Задолженность по оплате отсутствует' if re.fullmatch(r'долгов по оплате нет',x,re.I) else x for x in no_debt]
            save('return_facts','. '.join(returned+no_debt)+'.',text)
            if current=='deposit_terms' and terms:save(current,'. '.join(terms)+'.',text)
        if current=='return_facts' and re.fullmatch(r'\s*'+DATE+r'\s+нет[.! ]*',text,re.I):
            save(current,text,text)
            state['fields'][current].update(status='incomplete',error='Дата сохранена. «Нет» относится к акту возврата или к замечаниям по квартире?')
    return consumed
