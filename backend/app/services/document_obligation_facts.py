"""Explicit obligation facts reused across turns, never guessed from amounts.

Contract price, an advance and the unpaid balance are different facts. A
factual sentence may answer several questions, but only its matching clauses
are stored in each field. All derivations retain their literal evidence.
"""
import re

NUMBER=r'\d+(?:[ \u00a0]\d{3})*(?:[.,]\d{1,2})?'
SUM=NUMBER+r'\s*(?:тысяч(?:а|и)?\b|тыс\.?\b|млн\.?)?(?:\s*(?:руб(?:лей|ля|ль|\.)?|₽))?'


def collect_obligation_turn(state,text,current,put):
    from app.services.document_scenarios import SCENARIOS
    from app.services.document_workflow import normalize_money
    specs={f.key:f for f in SCENARIOS[state['scenario']].fields}
    # Debt templates do not all use the same vocabulary.  A services claim,
    # for example, has ``performance`` instead of the loan-specific
    # ``payments`` slot.  Requiring that one optional shape made a detailed
    # services narrative look like an answer to just the current question and
    # caused the interview to ask the rest of its already-stated facts again.
    if 'agreement' not in specs or not ({'amount','performance','due_date','facts'} & set(specs)):
        return set()
    from app.services.document_dialogue import asks_for_help,leaves_blank
    if asks_for_help(text) or leaves_blank(text):return set()
    consumed=set();ledger=state.setdefault('obligation_facts',{})
    def save(key,value,evidence,status='filled'):
        if key not in specs:return
        before=state['fields'].get(key)
        put(key,value,evidence,status)
        if state['fields'].get(key)!=before:consumed.add(key)
    def fact(key,literal,evidence):
        normalized=normalize_money(literal.strip(' .'))
        if normalized:
            ledger[key]={'value':normalized,'evidence':evidence,'source':'user','field':current}
        return normalized
    # Require an explicit monetary role. A bare contract price is never debt.
    debt=re.search(r'(?:задолженность|основной долг|(?:не\s+(?:выплатил\w*|оплатил\w*|вернул\w*)\s+(?:оставш\w*\s+)?)|(?:остаток\s+(?:долга\s+)?(?:составляет|—|:)))\s*(?:составляет\s*|в размере\s*|—\s*|:\s*)?('+SUM+r')',text,re.I)
    if not debt:
        # "Остаток 50 000 рублей должен был быть оплачен ..." is an
        # ordinary way to state outstanding principal.  It is not a contract
        # price or an advance and therefore belongs in ``amount``.
        debt=re.search(r'\bостаток(?:\s+(?:долга|оплаты|к\s+оплате))?\s+('+SUM+r')(?=\s*(?:должен\w*|подлеж\w*|не\s+(?:поступ|оплач|перечисл)|[,. ;]|$))',text,re.I)
    if debt:
        amount=fact('balance',debt[1],debt[0])
        if amount:save('amount',debt[1].strip(' .'),debt[0])
    total=re.search(r'(?:стоимость(?:\s+договора)?|цена(?:\s+договора)?|общая сумма(?:\s+договора)?)\s*(?:составляет\s*|—\s*|:\s*|-\s*)?('+SUM+r')',text,re.I)
    if total:fact('contract_price',total[1],total[0])
    advance=re.search(r'(?:аванс|предоплата)\s*(?:в размере\s*|—\s*|:\s*)?('+SUM+r')\s*(?:получен\w*|оплачен\w*|поступил\w*|внес[её]н\w*)',text,re.I)
    if advance:
        fact('advance',advance[1],advance[0]);save('payments',advance[0],advance[0])
    # Split prose at sentence boundaries but not decimal points or dates.
    clauses=[x.strip(' ,;') for x in re.split(r'(?<!\d)[.!]\s+|;\s*|,\s+(?=(?:акт\s|аванс\s|остаток\s|есть\s))',text,flags=re.I) if x.strip(' ,;')]
    contract=next((x for x in clauses if re.search(r'договор\w*.*?(?:№|от\s+\d)',x,re.I)),None)
    if contract and current in {'agreement',None}:
        # Only the agreement reference is placed in the agreement slot.  The
        # same sentence can also describe work performed, and copying it into
        # both slots is what produced duplicated document paragraphs.
        reference=re.search(r'\bдоговор(?:у|а)?\s*(?:№\s*[\w/-]+)?\s*от\s+\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+\d{4}(?:\s*г(?:ода|\.))?',contract,re.I)
        agreement=reference[0] if reference else contract
        agreement=re.sub(r'^договору\b','Договор',agreement,flags=re.I)
        save('agreement',agreement,reference[0] if reference else contract)
    performance=[]
    for clause in clauses:
        performed=re.search(r'\b(?:я\s+)?(?:разработал\w*|выполнил\w*|оказал\w*)\s+.+?(?=\s+(?:по\s+договор\w*|на\s+основании)\b|[.!]|$)',clause,re.I)
        accepted=re.search(r'\bакт\s+(?:подписан|при[её]мки)|\bработ\w*\s+принят',clause,re.I)
        if performed:performance.append(performed[0].strip())
        elif accepted:performance.append(clause)
    if performance and (current in {'agreement','performance',None} or re.search(r'акт\s+подписан',text,re.I)):
        save('performance','. '.join(dict.fromkeys(x.rstrip('.') for x in performance)),text)
    due=next((x for x in clauses if re.search(r'(?:оплат\w*|оплач\w*|перечисл\w*|возврат\w*|верну\w*).*?\bдо\s+\d',x,re.I)),None)
    if due and 'due_date' in specs:
        date_phrase=re.search(r'\bдо\s+\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)(?:\s+\d{4}(?:\s*г(?:ода|\.))?)?',due,re.I)
        save('due_date',date_phrase[0] if date_phrase else due,date_phrase[0] if date_phrase else due)
    violation=next((x for x in clauses if re.search(r'\b(?:деньги|оплата|плат[её]ж)\s+не\s+(?:поступ|оплач|перечисл)|\bне\s+(?:поступил|оплачен|перечислен)\w*',x,re.I)),None)
    if violation and 'facts' in specs:
        sentence=re.search(r'(?:но\s+)?(?:деньги|оплата|плат[её]ж)\s+не\s+(?:поступ|оплач|перечисл)\w*',violation,re.I)
        save('facts',sentence[0] if sentence else violation,sentence[0] if sentence else violation)
    if current=='calculation' and re.fullmatch(r'(?:только\s+)?основной\s+долг[.! ]*',text,re.I):
        amount=state['fields'].get('amount',{})
        if amount.get('status')=='filled':
            from app.services.document_case_composition import _money
            value='Основной долг составляет '+_money(amount['value'])+'. Дополнительные начисления не заявляются.'
            save('calculation',value,text)
    return consumed
