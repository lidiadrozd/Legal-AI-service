"""Authority complaint form; never borrow the seller-pretense remedy verbatim."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'backend/app/templates'
def f(key,label,question,kind='text',optional=False): return dict(key=key,label=label,question=question,kind=kind,optional=optional)
def b(text,role='body',**extra): return dict(text=text,role=role,**extra)
key='complaint_consumer_agency'
fields=[f('sender','Заявитель','Укажите полное ФИО заявителя.'),
    f('sender_address','Адрес заявителя','Какой полный адрес заявителя нужно указать?','address'),
    f('contacts','Контакты и адрес для ответа','Какой адрес для ответа и известные контакты заявителя укажем? Если ответ нужен на уже указанный почтовый адрес, так и напишите.'),
    f('recipient','Ведомство','В какое территориальное подразделение Роспотребнадзора направляется жалоба? Неизвестное подразделение можно уточнить позже.'),
    f('recipient_address','Адрес ведомства','Какой почтовый адрес подразделения известен? Если неизвестен, можно дополнить позже.','address'),
    f('seller','Продавец или исполнитель','На какого продавца или исполнителя подаёте жалобу? Укажите известное название организации или ИП, название магазина и реквизиты.'),
    f('seller_address','Место нарушения или адрес продавца','По какому адресу находится магазин или исполнитель, действия которого обжалуете?','address'),
    f('purchase','Покупка или заказ','Что, когда, у какого продавца или исполнителя и за какую цену приобретено или заказано?'),
    f('facts','Обстоятельства нарушения','В чём заключается нарушение, когда оно обнаружено и чем подтверждается? Установленные факты нужно отличить от предположений.'),
    f('previous_contact','Предыдущие обращения','Обращались ли вы к продавцу, исполнителю или в ведомство? Укажите дату, способ, содержание обращения и полученный ответ либо отсутствие обращения.'),
    f('requests','Просьба к ведомству','Какие действия в пределах компетенции Роспотребнадзора просите совершить? Например, рассмотреть обстоятельства и принять предусмотренные меры.'),
    f('attachments','Приложения','Какие документы прилагаете? Перечислите имеющиеся чек, фотографии, обращения и ответы; отсутствующие документы не добавляем.'),
    f('date','Дата обращения','Какую дату обращения указываем?','date'),f('signature','Подписант','Кто подпишет обращение от имени заявителя?')]
blocks=[b('В {{recipient}}\nАдрес: {{recipient_address}}\nЗаявитель: {{sender}}\nАдрес: {{sender_address}}\nКонтакты и адрес для ответа: {{contacts}}','addressee'),
    b('Жалоба о нарушении прав потребителя','title'),
    b('Продавец или исполнитель, в отношении которого направляется обращение: {{seller}}. Адрес места нарушения или продавца: {{seller_address}}.'),
    b('Обстоятельства обращения','heading'),b('{{purchase}}'),b('{{facts}}'),b('Предыдущие обращения','heading'),b('{{previous_contact}}'),
    b('Просьба заявителя','heading'),b('{{requests}} Ответ на обращение прошу направить по указанному адресу для ответа.','request'),
    b('Приложения','heading'),b('{{attachments}}','attachments'),b('Дата: {{date}}','place_date'),b('Подпись: __________________ / {{signature}} /','signature')]
package=dict(scenario=key,version=2,schema_version=2,coverage='structured',source='Самостоятельная форма обращения с учётом структуры официальных рекомендаций Роспотребнадзора',
    usage_basis='Самостоятельный текст; рекомендации органа служат источником состава сведений.',
    source_urls=['https://zpp.rospotrebnadzor.ru/news/federal/572274','https://zpp.rospotrebnadzor.ru/handbook/finance/memos/210401','https://petition.rospotrebnadzor.ru/petition/'],
    checked_at='2026-10-25',review_status='source_checked_draft',reviewed_by=None,reviewed_at=None,layout='letter',
    limitations=['Жалоба в ведомство отличается от претензии продавцу и иска в суд.','Обращение не гарантирует назначение контрольного мероприятия или взыскание денег.'],blocks=blocks)
(ROOT/'intake').mkdir(exist_ok=True)
(ROOT/'intake'/(key+'.json')).write_text(json.dumps(dict(scenario=key,version=2,fields=fields),ensure_ascii=False,indent=2),encoding='utf-8')
(ROOT/'documents'/(key+'.json')).write_text(json.dumps(package,ensure_ascii=False,indent=2),encoding='utf-8')
print('Updated consumer authority complaint and its intake')
