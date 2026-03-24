"""
Тест промта analyze_law_impact — 20 пар (дело + изменение закона).
Оценка:
  ✅ PASS — ожидаемый результат совпал с ответом GigaChat
  ❌ FAIL — не совпал
  ⚠️  ERROR — ошибка вызова
"""

import asyncio

import importlib.util
import os
import sys

from dotenv import load_dotenv
load_dotenv(".env")

# Прямой импорт без __init__.py
def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

load_module("app.core.config", "app/core/config.py")
load_module("app.core.prompts", "app/core/prompts.py")
load_module("app.services.gigachat_client", "app/services/gigachat_client.py")
load_module("app.services.law_impact_service", "app/services/law_impact_service.py")

from app.services.law_impact_service import analyze_law_impact

# ============================================================
# 20 ТЕСТОВЫХ ПАР
# Формат: (case_category, case_description, change, expected_affects)
# ============================================================

TEST_PAIRS = [
    # --- ТРУДОВОЕ ПРАВО ---
    (
        "labor_law",
        "Спор об увольнении по сокращению штата, работник оспаривает законность",
        {"title": "Поправки в ст. 81 ТК РФ об основаниях увольнения по сокращению",
         "category": "labor_law", "summary": "Уточнены процедуры уведомления при сокращении",
         "source": "consultant", "published": "2026-03-01"},
        True,  # должно влиять
    ),
    (
        "labor_law",
        "Спор об увольнении по сокращению штата",
        {"title": "Изменения ставки НДС для малого бизнеса",
         "category": "tax_law", "summary": "НДС снижен с 20% до 15% для МСП",
         "source": "consultant", "published": "2026-03-01"},
        False,  # не должно влиять
    ),
    (
        "labor_law",
        "Взыскание задолженности по зарплате за 6 месяцев",
        {"title": "Изменения в порядке индексации МРОТ",
         "category": "labor_law", "summary": "МРОТ повышен до 25000 рублей",
         "source": "consultant", "published": "2026-02-01"},
        True,
    ),
    (
        "labor_law",
        "Взыскание задолженности по зарплате",
        {"title": "Поправки в ЖК РФ о капитальном ремонте",
         "category": "housing_law", "summary": "Изменён порядок расчёта взносов на капремонт",
         "source": "pravo_gov", "published": "2026-02-15"},
        False,
    ),

    # --- ГРАЖДАНСКОЕ ПРАВО ---
    (
        "civil_law",
        "Взыскание долга по договору займа на сумму 500 000 руб.",
        {"title": "Изменения в ст. 196 ГК РФ о сроках исковой давности",
         "category": "civil_law", "summary": "Уточнён порядок исчисления срока давности по займам",
         "source": "consultant", "published": "2026-01-15"},
        True,
    ),
    (
        "civil_law",
        "Спор о расторжении договора аренды нежилого помещения",
        {"title": "Поправки в ТК РФ об охране труда",
         "category": "labor_law", "summary": "Новые требования к охране труда на производстве",
         "source": "consultant", "published": "2026-02-01"},
        False,
    ),
    (
        "civil_law",
        "Возмещение ущерба от залива квартиры соседом",
        {"title": "Изменения в ст. 1064 ГК РФ о возмещении вреда",
         "category": "civil_law", "summary": "Уточнены условия возмещения имущественного вреда",
         "source": "pravo_gov", "published": "2026-03-05"},
        True,
    ),
    (
        "civil_law",
        "Расторжение договора купли-продажи автомобиля",
        {"title": "Изменения в УК РФ об ответственности за мошенничество",
         "category": "criminal_law", "summary": "Повышены санкции за мошенничество в крупном размере",
         "source": "consultant", "published": "2026-01-20"},
        False,
    ),

    # --- НАЛОГОВОЕ ПРАВО ---
    (
        "tax_law",
        "Оспаривание решения налоговой о доначислении НДС на 2 млн руб.",
        {"title": "Поправки в гл. 21 НК РФ о порядке возмещения НДС",
         "category": "tax_law", "summary": "Изменён порядок камеральной проверки при возврате НДС",
         "source": "consultant", "published": "2026-02-20"},
        True,
    ),
    (
        "tax_law",
        "Оспаривание штрафа ФНС за непредоставление документов",
        {"title": "Изменения в СК РФ о порядке уплаты алиментов",
         "category": "family_law", "summary": "Новый порядок индексации алиментов",
         "source": "pravo_gov", "published": "2026-02-10"},
        False,
    ),
    (
        "tax_law",
        "Спор с ФНС о признании расходов необоснованными",
        {"title": "Поправки в ст. 252 НК РФ об обоснованности расходов",
         "category": "tax_law", "summary": "Уточнены критерии экономической обоснованности расходов",
         "source": "consultant", "published": "2026-03-10"},
        True,
    ),

    # --- СЕМЕЙНОЕ ПРАВО ---
    (
        "family_law",
        "Раздел совместно нажитого имущества при разводе",
        {"title": "Поправки в ст. 38 СК РФ о разделе имущества супругов",
         "category": "family_law", "summary": "Изменён порядок раздела имущества при наличии детей",
         "source": "pravo_gov", "published": "2026-01-25"},
        True,
    ),
    (
        "family_law",
        "Взыскание алиментов на несовершеннолетнего ребёнка",
        {"title": "Изменения в КоАП о штрафах за нарушение ПДД",
         "category": "administrative_law", "summary": "Повышены штрафы за превышение скорости",
         "source": "consultant", "published": "2026-02-05"},
        False,
    ),

    # --- ЖИЛИЩНОЕ ПРАВО ---
    (
        "housing_law",
        "Оспаривание выселения из муниципальной квартиры",
        {"title": "Поправки в ст. 85 ЖК РФ об основаниях выселения",
         "category": "housing_law", "summary": "Уточнены основания выселения из муниципального жилья",
         "source": "pravo_gov", "published": "2026-03-12"},
        True,
    ),
    (
        "housing_law",
        "Спор с управляющей компанией о завышенных тарифах ЖКХ",
        {"title": "Изменения в НК РФ о налоге на имущество организаций",
         "category": "tax_law", "summary": "Изменены ставки налога на имущество для юрлиц",
         "source": "consultant", "published": "2026-01-30"},
        False,
    ),

    # --- АДМИНИСТРАТИВНОЕ ПРАВО ---
    (
        "administrative_law",
        "Оспаривание штрафа Роспотребнадзора за нарушение санитарных норм",
        {"title": "Поправки в КоАП о санкциях за санитарные нарушения",
         "category": "administrative_law", "summary": "Повышены штрафы за нарушение санитарных норм для ИП",
         "source": "consultant", "published": "2026-02-28"},
        True,
    ),
    (
        "administrative_law",
        "Обжалование лишения лицензии на торговлю алкоголем",
        {"title": "Изменения в ГК РФ о договоре поставки",
         "category": "civil_law", "summary": "Уточнены существенные условия договора поставки",
         "source": "pravo_gov", "published": "2026-02-14"},
        False,
    ),

    # --- КОРПОРАТИВНОЕ ПРАВО ---
    (
        "corporate_law",
        "Оспаривание решения общего собрания акционеров об увеличении УК",
        {"title": "Поправки в ФЗ об АО о порядке проведения общих собраний",
         "category": "corporate_law", "summary": "Изменён кворум для принятия решений на собраниях АО",
         "source": "consultant", "published": "2026-03-08"},
        True,
    ),
    (
        "corporate_law",
        "Банкротство ООО, взыскание долга с контролирующих лиц",
        {"title": "Изменения в законе о банкротстве — субсидиарная ответственность",
         "category": "corporate_law", "summary": "Расширены основания субсидиарной ответственности КДЛ",
         "source": "consultant", "published": "2026-03-15"},
        True,
    ),
    (
        "corporate_law",
        "Банкротство ООО, взыскание долга с контролирующих лиц",
        {"title": "Поправки в СК РФ об усыновлении",
         "category": "family_law", "summary": "Упрощён порядок усыновления для одиноких родителей",
         "source": "pravo_gov", "published": "2026-02-20"},
        False,
    ),
]


# ============================================================
# ЗАПУСК ТЕСТОВ
# ============================================================

async def run_tests():
    passed = 0
    failed = 0
    errors = 0

    print(f"\n{'='*60}")
    print(f"Запуск {len(TEST_PAIRS)} тестов...")
    print(f"{'='*60}\n")

    for i, (case_cat, case_desc, change, expected) in enumerate(TEST_PAIRS, 1):
        try:
            result = await analyze_law_impact(case_cat, case_desc, change)
            actual = result.get("affects", False)

            if actual == expected:
                status = "✅ PASS"
                passed += 1
            else:
                status = "❌ FAIL"
                failed += 1

            print(f"[{i:02d}] {status} | {case_cat} | {change['title'][:50]}...")
            if actual != expected:
                print(f"      Ожидалось: affects={expected}")
                print(f"      Получено:  affects={actual}, severity={result.get('severity')}")
                print(f"      Причина:   {result.get('reason', '')}")

        except Exception as e:
            errors += 1
            print(f"[{i:02d}] ⚠️  ERROR | {case_cat} | {e}")

    print(f"\n{'='*60}")
    print(f"ИТОГ: ✅ {passed} passed | ❌ {failed} failed | ⚠️  {errors} errors")
    print(f"Точность: {passed}/{len(TEST_PAIRS)} = {passed/len(TEST_PAIRS)*100:.0f}%")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(run_tests())
