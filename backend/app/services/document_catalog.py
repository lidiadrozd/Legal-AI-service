"""Authoritative product coverage, separate from legacy draft structures."""
from functools import lru_cache
import json
import re
from pathlib import Path


# The common product names belong in routing evidence, not in a separate
# template.  A sofa, wardrobe or kitchen set is still a consumer good, and a
# user should not have to call it a generic "товар" for the appropriate form
# to be selected.
_CONSUMER_GOODS = r'(?:товар|заказ|телефон|ноутбук|холодильник|стиральн\w* машин|телевизор|техник\w*|диван\w*|мебел\w*|шкаф\w*|кресл\w*|матрас\w*|стол\w*|стул\w*|кухн\w*)'


def is_rent_deposit_return(text):
    """A housing security payment, not unpaid rent or a bank deposit."""
    return bool(
        re.search(r'обеспечительн\w*\s+плат[её]ж|депозит|залог', text, re.I)
        and re.search(r'квартир|жиль|жил\w*\s+помещен|найм|аренд|собственник|съех|выех', text, re.I)
        and re.search(r'возврат|возвращ|верну|верн[её]|удерж|не\s+отда', text, re.I)
    )

@lru_cache(maxsize=1)
def catalog_forms():
    path=Path(__file__).resolve().parents[1]/'templates/catalog40.json'
    rows=json.loads(path.read_text(encoding='utf-8'))['forms']
    for row in rows:
        package_path=path.parent/'documents'/f"{row['scenario']}.json"
        package=json.loads(package_path.read_text(encoding='utf-8'))
        row['content_status']={'legal_document':'case_composer_tested','clause_document':'clause_composer_tested'}.get(package.get('composition'),'requires_content_review')
    return tuple(rows)

def is_catalog_form(key):
    return any(row['scenario']==key for row in catalog_forms())


def catalog_kind(text):
    if re.search(r'приобщ|(?:добавить|представить).{0,30}(?:доказател|документ).{0,20}(?:суд|дел)',text,re.I):return 'procedural'
    if re.search(r'судебн\w* приказ.{0,100}(?:не соглас|возраж|отмен)',text,re.I):return 'procedural'
    if re.search(r'заявлен.{0,50}(?:восстанов.{0,45}срок|исполнительн\w* лист)',text,re.I):return 'procedural'
    if re.search(r'дополнител\w* соглашен',text,re.I):return 'contract'
    if re.search(r'возражен.{0,50}приказ|отмен.{0,30}судебн\w* приказ',text,re.I):return 'procedural'
    if re.search(r'заявлен.{0,35}увольнен|уволить.{0,25}собственн|увольнен.{0,25}собственн\w* желан',text,re.I) and not re.search(r'иск|восстанов|расч[её]т|невыплат',text,re.I):return 'employment_statement'
    if re.search(r'приказ.{0,40}алимент|алимент.{0,40}приказ',text,re.I):return 'court_order'
    if re.search(r'пристав.{0,50}(?:расч[её]т|определ|задолжен)|(?:расч[её]т|определ).{0,50}задолжен.{0,25}алимент',text,re.I):return 'enforcement'
    return None


def infer_catalog_scenario(kind,text):
    """Specific purpose wins before broad transaction keywords such as rent."""
    t=text.lower()
    if kind in {'claim', 'pretense'} and is_rent_deposit_return(t):
        return kind + '_rent_deposit'
    if kind=='contract' and re.search(r'(?:трудов|рудов)\w* (?:договор|контракт)|работа учител|работ[ау]\s+(?:учител|педагог)',t):return 'contract_employment'
    if kind=='contract' and re.search(r'дополнител\w* соглашен',t) and re.search(r'найм|квартир|жил|аренд',t):return 'contract_housing_addendum'
    if kind=='act' and re.search(r'квартир|жил|найм',t):
        if re.search(r'возврат|возвращ',t):return 'act_housing_return'
        if re.search(r'передач|передат|при[её]м',t):return 'act_housing_handover'
    if kind=='employment_statement':return 'labor_resignation'
    if kind=='complaint' and re.search(r'пристав|фссп',t):return 'complaint_bailiff_superior'
    if kind=='procedural':
        for pattern,key in [
            (r'приказ.{0,40}(?:отмен|возраж)|(?:возраж|отмен).{0,50}приказ','motion_order_objection'),
            (r'восстанов.{0,35}(?:процессуальн\w* )?срок','motion_restore_term'),
            (r'исполнительн\w* лист','motion_enforcement_writ'),
            (r'приобщ|добавить.{0,30}доказател','motion_attach'),
            (r'судебн\w* расход|расход.{0,25}представител','motion_costs'),
            (r'возраж|отзыв.{0,15}иск','motion_objection')]:
            if re.search(pattern,t):return key
    if re.search(r'алимент',t):
        if kind=='enforcement':return 'bailiff_alimony_arrears'
        if kind=='claim' and re.search(r'неустойк|пен[яи]|просрочк.{0,15}санкц',t):return 'claim_alimony_penalty'
        if re.search(r'не (?:плат|выпла)|задолжен|долг|за прошл|за прошед',t):return None
        if kind=='court_order':return 'order_alimony'
        if kind=='claim':
            if re.search(r'тв[её]рд|фиксирован',t):return 'claim_alimony_fixed'
            if re.search(r'дол[яию]|долях|процент.{0,15}доход',t):return 'claim_alimony_share'
        return None
    if kind=='claim':
        if re.search(r'расторжен.{0,15}брак|развод',t):return 'claim_divorce'
        if re.search(r'восстанов.{0,20}работ|незаконн.{0,15}увольнен',t):return 'claim_labor_reinstatement'
        if re.search(r'зарплат|заработн\w* плат|расч[её]т.{0,20}увольнен',t):return 'claim_labor_salary'
        # Consumer claims split by their factual basis before the broad
        # consumer form: delayed delivery concerns prepayment and the agreed
        # transfer date, whereas defective goods concern a product defect.
        if (re.search(_CONSUMER_GOODS,t)
                and re.search(r'достав|передач|привез|получ|срок.{0,20}(?:наруш|просроч)|просроч.{0,20}(?:достав|передач)',t)
                and re.search(r'предоплат|оплат|оплачен|заказ|достав|передач',t)):
            return 'claim_consumer_late_delivery'
        if (re.search(_CONSUMER_GOODS,t)
                and re.search(r'недостат|некачествен|брак|дефект|слом\w*|не работает',t)):
            return 'claim_consumer_defective_goods'
        # The usual request wording is "взыскать ущерб".  At this stage a
        # user need not already know the adjective "имущественный" or the
        # exact accident; the dedicated intake collects those facts.
        if re.search(r'поврежд|разбил|сломал|имущественн\w* ущерб|(?:взыскан|возмещен)\w*.{0,35}ущерб|ущерб.{0,35}(?:взыскан|возмещен)',t) and not re.search(r'залив|затоп|потребител|товар',t):return 'claim_damage_property'
    if kind=='pretense':
        if re.search(r'работодател|зарплат|увольнен|заработн\w* плат',t):return 'pretense_labor_settlement'
        if re.search(r'недостат|некачествен|плох|нарушен',t) and re.search(r'услуг|ремонт|\bработ(?:ы|у|ам|ах)\b',t):
            return 'pretense_consumer_defective_service'
        if re.search(_CONSUMER_GOODS,t) and re.search(r'недостат|некачествен|брак|дефект|плох|слом\w*|не работает|перестал\w*\s+\w+',t):
            return 'pretense_consumer_defective_goods'
        if re.search(r'достав|не (?:привез|достав|передал).{0,20}товар',t):return 'pretense_consumer_late_delivery'
        if re.search(r'недостат|некачествен|плох|нарушен',t) and re.search(r'услуг|ремонт|работ',t):return 'pretense_consumer_defective_service'
        if re.search(r'поврежд|разбил|сломал|имущественн\w* ущерб|(?:возмещен|взыскан)\w*.{0,35}ущерб|ущерб.{0,35}(?:возмещен|взыскан)',t) and not re.search(r'залив|затоп|потребител|товар',t):return 'pretense_damage_property'
    return None


def catalog_clarification(state):
    text=' '.join([state.get('request',''),state.get('context',''),*state.get('user_turns',[])])
    if re.search(r'алимент',text,re.I):
        if re.search(r'задолжен|не (?:плат|выпла)|долг|за прошл|за прошед',text,re.I):
            return 'Нужно определить задолженность у пристава, взыскать неустойку или впервые установить алименты? Это разные формы; уже установленный размер выплат не заменяет выбор нужного обращения.'
        return 'Алименты нужно установить в долях к доходу или в твёрдой денежной сумме? Если не знаете, можно попросить объяснить разницу; для судебного приказа дополнительно проверяются условия применения.'
    return None
