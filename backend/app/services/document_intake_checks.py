"""Clarify likely identity typos instead of silently rewriting a person's name."""
import re


def identity_suggestion(value):
    names=value.strip(' .').split()
    if len(names)!=3 or not all(re.fullmatch(r'[А-Яа-яЁё-]+',x) for x in names):return None
    last=names[-1]
    if re.search(r'(?:ович|евич|инич|овна|евна|инична|ична)$',last,re.I):return None
    if re.search(r'(?:овн|евн|ичн)$',last,re.I):names[-1]=last+'а'
    else:
        extra=re.fullmatch(r'(.+(?:ович|евич|инич|овна|евна|инична|ична))[а-яё]',last,re.I)
        if not extra:return None
        names[-1]=extra[1]
    return ' '.join(names)


def check_identity_turn(state,text,key):
    if key not in {'sender','recipient','signature','counterparty_signature'}:return False
    from app.services.document_case_facts import set_field
    pending=state.get('identity_confirmation',{})
    if pending.get('field')==key:
        if re.fullmatch(r'\s*(?:да|верно|правильно|подтверждаю)[.! ]*',text,re.I):
            set_field(state,key,pending['suggested'],pending['original']+'\nПодтверждение: '+text)
            state.setdefault('confirmed_identity_values',{})[key]=pending['suggested']
            state.pop('identity_confirmation',None)
            return True
        if re.fullmatch(r'\s*(?:так в паспорте|так в документе|оставить как есть)[.! ]*',text,re.I):
            set_field(state,key,pending['original'],text)
            state.setdefault('confirmed_identity_values',{})[key]=pending['original']
            state.pop('identity_confirmation',None)
            return True
        if re.fullmatch(r'\s*нет[.! ]*',text,re.I):
            state['fields'][key]['error']='Укажите полное ФИО точно как в документе.'
            return True
    suggested=identity_suggestion(text)
    if not suggested:
        if pending.get('field')==key:state.pop('identity_confirmation',None)
        return False
    state['identity_confirmation']={'field':key,'original':text.strip(),'suggested':suggested}
    set_field(state,key,text,text)
    state['fields'][key].update(status='incomplete',error=f'Возможно, в ФИО опечатка. Верно ли «{suggested}»? Подтвердите или укажите ФИО как в документе.')
    return True
