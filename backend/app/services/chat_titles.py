"""Concise document subjects, with no provider call or personal identifiers."""
import re


def generic_title(title):
    return (title or '').strip().casefold() in {'','новый чат','подготовка документа','подготовка документов'}


def suggest_chat_title(state=None, text=''):
    state=state or {}
    source=' '.join([state.get('request',''),*state.get('user_turns',[]),text])
    key=state.get('scenario')
    if not key:
        from app.services.document_dialogue import infer_scenario
        key=infer_scenario({**state,'request':state.get('request') or text},'')
    titles={
        'contract_employment':'Трудовой договор','motion_attach':'Приобщение документов',
        'motion_order_objection':'Возражения на судебный приказ',
        'pretense_consumer_late_delivery':'Претензия о возврате оплаты',
        'pretense_consumer_defective_goods':'Претензия о недостатках товара',
        'labor_resignation':'Заявление об увольнении',
    }
    if key:
        from app.services.document_scenarios import SCENARIOS
        title=titles.get(key) or (SCENARIOS[key].title if key in SCENARIOS else '')
        topic=next((name for pattern,name in [(r'учител','учитель'),(r'ноутбук','ноутбук'),(r'диван','диван'),(r'телефон','телефон')] if re.search(pattern,source,re.I)),None)
        if topic:title+=' · '+topic
    else:
        title=re.sub(r'\s+',' ',state.get('request') or text).strip()
        title=re.sub(r'^(?:привет[!,. ]*|здравствуйте[!,. ]*|помоги(?:те)?\s+|составь(?:те)?\s+|нуж(?:ен|на|но)\s+)','',title,flags=re.I)
        title=title[:1].upper()+title[1:]
    if not title:return 'Новый чат'
    return title if len(title)<=64 else title[:61].rsplit(' ',1)[0].rstrip('.,:;')+'…'


def update_automatic_title(chat,state,text=''):
    if state.get('title_manual'):return
    if generic_title(chat.title) or chat.title==state.get('automatic_title'):
        chat.title=suggest_chat_title(state,text)
        state['automatic_title']=chat.title
