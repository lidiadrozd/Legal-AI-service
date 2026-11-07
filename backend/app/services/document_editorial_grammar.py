"""Narrow, meaning-preserving grammar repairs shared by new and cached edits."""
import re


def normalize_room_counts(text):
    """Nominative counts in a property list; never alter «из трёх комнат»."""
    def replace(match):
        number=int(match['count'])
        last=number%10
        word='комнат' if 11<=number%100<=14 else ('комната' if last==1 else 'комнаты' if 2<=last<=4 else 'комнат')
        return match['lead']+match['count']+' '+word
    return re.sub(r'(?P<lead>^|[,;:]\s*)(?P<count>\d+)\s+комнат(?:а|ы)?(?=\s*[,;.]|\s*$)',replace,text,flags=re.I)


def repair_editorial_surface(key, source, text):
    if key=='property_description': text=normalize_room_counts(text)
    # Recover this phrase only when the original explicitly contains it at
    # the same anchor. Never infer a penalty base from an unrelated amount.
    if re.search(r'\bсуммы\s+месячной\s+платы\b',source,re.I):
        text=re.sub(r'\b(суммы\s+)меся(?=[.,;:]|\s*$)',r'\1месячной платы',text,flags=re.I)
    return text
def formal_source_candidate(source):
    """Unambiguous grammatical expansion, still requiring independent review.

    Preserve the dative recipient and every literal fact. This is a candidate,
    never permission to publish unreviewed colloquial input.
    """
    import re
    text=re.sub(r'^\s*(?:ну[ ,]+)+','',source.strip(),flags=re.I)
    text,count=re.subn(r'^(мне|нам)\s+не\s+выплатил(?:и|а)?\s+(?:зп|зарплату|заработную плату)\b',
        lambda m:'Заработная плата '+m[1].lower()+' не выплачена',text,flags=re.I)
    if not count:return source
    text=re.sub(r'[,;]\s*(?:долг|задолженность)\s*:?\s*(?=\d)', '. Задолженность составляет ',text,flags=re.I)
    return text.rstrip('.')+'.'


def restore_spelled_source_numbers(source,text):
    """Restore an integer literal only when a spelled value exactly equals it.

    This is formatting, not inference: unmatched/decimal amounts stay untouched
    and fail the ordinary fact gate. Never turn a new model number into a fact.
    """
    from decimal import Decimal,InvalidOperation
    literals={}
    for match in re.finditer(r'\d+(?:[ ]\d{3})*(?:[.,]\d+)?',source):
        if not re.match(r'\s*(?:(?:рабочих|календарных)\s+)?(?:руб|₽|%|процент|дн|день|дня|месяц|год|лет|комнат|экземпляр|комплект|страниц|лист|числа)',source[match.end():],re.I):continue
        try:value=Decimal(match[0].replace(' ','').replace(',','.'))
        except InvalidOperation:continue
        if value==value.to_integral_value():literals.setdefault(int(value),match[0])
    units={'ноль':0,'один':1,'одна':1,'одно':1,'одного':1,'одной':1,'два':2,'две':2,'двух':2,
        'три':3,'трёх':3,'трех':3,'четыре':4,'четырёх':4,'четырех':4,'пять':5,'пяти':5,
        'шесть':6,'шести':6,'семь':7,'семи':7,'восемь':8,'восьми':8,'девять':9,'девяти':9,
        'десять':10,'десяти':10,'одиннадцать':11,'двенадцать':12,'тринадцать':13,'четырнадцать':14,
        'пятнадцать':15,'шестнадцать':16,'семнадцать':17,'восемнадцать':18,'девятнадцать':19,
        'двадцать':20,'тридцать':30,'сорок':40,'пятьдесят':50,'шестьдесят':60,'семьдесят':70,
        'восемьдесят':80,'девяносто':90,'сто':100,'ста':100,'двести':200,'триста':300,'четыреста':400,
        'пятьсот':500,'шестьсот':600,'семьсот':700,'восемьсот':800,'девятьсот':900,'первого':1,'второго':2,'третьего':3,'четвёртого':4,'четвертого':4,'пятого':5,
        'шестого':6,'седьмого':7,'восьмого':8,'девятого':9,'десятого':10}
    scales={'тысяча':1000,'тысячи':1000,'тысяч':1000,'миллион':1000000,'миллиона':1000000,'миллионов':1000000,
        'миллиард':1000000000,'миллиарда':1000000000,'миллиардов':1000000000}
    words='|'.join(sorted([*units,*scales],key=len,reverse=True))
    pattern=r'\b(?:'+words+r')(?:\s+(?:'+words+r'))*\b'
    def replace(match):
        if not re.match(r'\s*(?:(?:рабочих|календарных)\s+)?(?:руб|₽|%|процент|дн|день|дня|месяц|год|лет|комнат|экземпляр|комплект|страниц|лист|числа)',text[match.end():],re.I):return match[0]
        total=group=0
        for word in match[0].lower().split():
            if word in scales:total+=(group or 1)*scales[word];group=0
            else:group+=units[word]
        return literals.get(total+group,match[0])
    return re.sub(pattern,replace,text,flags=re.I)



def requires_prose_edit(text):
    # Recognize sentence boundaries without treating «кв. м» or «ст. 309»
    # as a new lower-case sentence. Apply the same gate to model output.
    return bool(re.search(r'\b(?!(?:руб|кв|ст|ул)\b)[А-Яа-яЁё]{3,}[.!?]\s+[а-яё]|\bтаток\b',text)
        or re.search(r'\bтг\b|^да\s*[,;]|^\s*\d{1,2}[./]\d{1,2}[./]\d{2,4}\s+нет[.! ]*$|^\s*(?:только )?основной долг(?: только)?[.! ]*$',text,re.I)
        or re.search(r'\b(?:я не знаю|не знаю где|где он|где она|тоже нет|также нет|лежать|дивана нет|уже \d{1,2}|прописано|обещана)\b',text,re.I))

