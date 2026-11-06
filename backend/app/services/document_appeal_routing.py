"""Choose an appeal from the dispute, without guessing a court or deadline."""
import re


def appeal_proceeding(text):
    if re.search(r'уголовн|приговор|\bУПК\b',text,re.I):
        return 'criminal'
    if re.search(r'административн|\bКАС\b|\bКоАП\b',text,re.I):
        return 'administrative'
    if re.search(r'арбитраж',text,re.I):
        return 'arbitration'
    if re.search(r'гражданск\w*\s+дел|районн\w*\s+суд|миров\w*\s+судь|суд\w*\s+общей\s+юрисдикц',text,re.I):
        return 'civil'
    # A personal debt judgment with a stated repayment is enough to start
    # the civil form. The court, act, dates and evidence remain intake fields.
    if (re.search(r'суд\w*|решени\w*',text,re.I)
            and re.search(r'взыск\w*',text,re.I)
            and re.search(r'долг|задолжен|кредит|за[её]м|займ',text,re.I)
            and re.search(r'с\s+меня|я\s+(?:(?:уже|частично|часть|его)\s+){0,3}(?:вернул|погасил|оплатил|выплатил)',text,re.I)
            and not re.search(r'\bИП\b|\bООО\b|предпринимател|коммерческ|налог|штраф',text,re.I)):
        return 'civil'
    return None


def appeal_clarification(text):
    kind=appeal_proceeding(text)
    if kind in {'criminal','administrative','arbitration'}:
        name={'criminal':'по уголовному делу','administrative':'по административному делу',
              'arbitration':'по арбитражному делу'}[kind]
        return (f'Для апелляционной жалобы {name} в сервисе пока нет доступной формы. '
                'Доступна апелляционная жалоба по гражданскому делу. '
                'Описание сохранено; могу помочь разобрать необходимые сведения в режиме консультации.')
    return ('Апелляционная жалоба по гражданскому делу есть в библиотеке. '
            'Укажите название суда, который вынес решение, или вид дела: гражданское, '
            'арбитражное, административное либо уголовное. Можно просто описать, о чём был спор.')
