"""Build original adaptations from researched forms and statutory requirements.

Does not reproduce proprietary GARANT forms. Source records and editorial status
travel with each package; none is represented as reviewed by a human lawyer.
"""
from datetime import date
from importlib.util import spec_from_file_location, module_from_spec
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/document_templates_2026-10-24_fixed"
PACKAGES = ROOT / "backend/app/templates/documents"


def module(name, path):
    spec = spec_from_file_location(name, path)
    loaded = module_from_spec(spec)
    sys.modules[name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


catalog = module("form_catalog", ROOT / "backend/app/services/document_scenarios.py")
layout = module("legal_docx_layout", ROOT / "backend/app/services/document_workflow_docx.py")
SCENARIOS = catalog.SCENARIOS


def b(text, role="body"):
    return {"text": text, "role": role}


def title(text): return b(text.replace("о оплате", "об оплате"), "title")
def heading(text): return b(text, "heading")
def letter_header():
    return [b("Кому: {{recipient}}\nАдрес: {{recipient_address}}\n\nОт: {{sender}}\nАдрес: {{sender_address}}", "addressee")]


def court_header(appeal=False, claim=False):
    blocks = [b("В {{court}}", "addressee")]
    if appeal: blocks.append(b("Через {{first_court}}", "addressee"))
    first, second = ("Истец", "Ответчик") if claim else ("Заявитель", "Другая сторона")
    blocks.append(b(first + ": {{sender}}\nАдрес: {{sender_address}}\n" + second + ": {{recipient}}\nАдрес: {{recipient_address}}\nИные участники: {{other_participants}}\nДополнительные сведения: {{party_details}}", "addressee"))
    return blocks


def ending(two=False):
    blocks = [heading("Приложения"), b("{{attachments}}", "attachments"), b("Дата: {{date}}", "place_date"),
              b("Подпись: __________________ / {{signature}} /", "signature")]
    if two: blocks.append(b("Подпись второй стороны: __________________ / {{counterparty_signature}} /", "signature"))
    return blocks


def package(key, blocks, *, basis, limitations=(), layout_name="letter"):
    scenario = SCENARIOS[key]
    record = SOURCES[key]
    urls = [record["url"]] if record.get("url") else []
    return {"scenario": key, "version": 1, "source": "Открытые формы и нормативные требования; самостоятельная редакция для сервиса",
            "source_urls": urls, "usage_basis": "Самостоятельно составленный текст; полные авторские формы ГАРАНТа не воспроизводятся",
            "checked_at": "2026-10-24", "review_status": "source_checked_draft", "reviewed_by": None,
            "reviewed_at": None, "layout": layout_name,
            "limitations": ["Сверка с открытыми источниками не заменяет юридическую проверку конкретного документа.", *limitations],
            "blocks": blocks, "legal_basis": basis}


def build_packages():
    result = {}
    debt_names = {"loan": ("возврате суммы займа", "transfer", "Передача денег", "ГК РФ, статьи 807, 808, 810"),
                  "rent": ("внесении задолженности по арендной плате", "property", "Объект и период аренды", "ГК РФ, статьи 309, 310, 614"),
                  "services": ("оплате оказанных услуг", "performance", "Исполнение обязательств", "ГК РФ, статьи 309, 310, 779, 781"),
                  "supply": ("оплате поставленного товара", "goods", "Исполнение поставки", "ГК РФ, статьи 309, 310, 506, 516")}
    for suffix, (name, specific, label, basis) in debt_names.items():
        details = [b("Основание обязательства: {{agreement}}."), b(label + ": {{" + specific + "}}."),
                   b("Согласованный срок исполнения: {{due_date}}. Обстоятельства нарушения: {{facts}}."),
                   b("На дату составления претензии сумма основного долга составляет {{amount}}.")]
        key = f"pretense_debt_{suffix}"
        blocks = letter_header() + [title("Претензия о " + name)] + details + [
            b("Правовое основание требования: " + basis + ". Условия конкретного обязательства определяются указанным выше договором и подтверждающими документами."),
            heading("Требование"), b("{{requests}}", "request"), b("Срок исполнения требования: {{response_term}}. Реквизиты или согласованный способ оплаты: {{payment_details}}."),
            b("Прошу сообщить о результатах рассмотрения по адресу заявителя. При неурегулировании спора вопрос о судебной защите будет решаться с учётом применимого порядка.")]+ending()
        result[key] = package(key, blocks, basis=[basis], limitations=["Проценты и неустойка не начисляются автоматически; при их заявлении требуется отдельный проверенный расчёт."])
        key = f"claim_debt_{suffix}"
        details_claim = [dict(x) for x in details]
        details_claim[-1] = b("Размер заявленного основного долга: {{amount}}.")
        blocks = court_header(claim=True) + [b("Основной долг: {{amount}}\nГоспошлина / льгота: {{fee}}", "addressee"),
                title("Исковое заявление о " + name), heading("Обстоятельства спора")] + details_claim + [
                heading("Досудебное урегулирование и выбор суда"), b("{{pretrial}}"), b("Основание выбора суда и порядка рассмотрения: {{jurisdiction}}. Выбранный процессуальный порядок: {{procedure}}."),
                heading("Обоснование и расчёт"), b(basis + ". {{legal_basis}}"), b("Расчёт взыскиваемых сумм: {{calculation}}."),
                heading("Требования к суду"), b("{{requests}}", "request"), b("Реквизиты для исполнения денежного требования: {{payment_details}}."),
                b("Сведения о направлении копий участникам: {{copy_notice}}.")]+ending()
        result[key] = package(key, blocks, basis=[basis, "ГПК РФ, статьи 131–132; АПК РФ, статьи 125–126 — в зависимости от выбранного порядка"],
            layout_name="claim", limitations=["До подачи необходим выбор между приказным и исковым производством, а также проверка подсудности и процессуальных реквизитов.",
                "Базовый пакет не смешивает ссылки на ГПК и АПК в тексте; процессуальные основания указываются после выбора порядка."])

    for suffix, name, facts_blocks, basis in (
        ("defective_goods", "Претензия о возврате денег за товар с недостатками", [
            b("Сведения о приобретении: {{purchase}}. Сумма, заявленная к возврату: {{amount}}."),
            b("Недостатки товара и обстоятельства их выявления: {{defect}}. Категория товара: {{goods_category}}.")],
            "Закон РФ от 07.02.1992 № 2300-1, статьи 18, 19, 22"),
        ("late_delivery", "Претензия о возврате предоплаты при нарушении срока доставки", [
            b("Сведения о заказе и оплате: {{purchase}}. Требуемая к возврату сумма: {{amount}}."),
            b("Согласованная дата передачи товара: {{delivery_date}}.")],
            "Закон РФ от 07.02.1992 № 2300-1, статья 23.1"),
        ("defective_service", "Претензия в связи с недостатками работы или услуги", [
            b("Заказанная работа или услуга: {{service}}. Недостатки и предыдущие обращения: {{defect}}."),
            b("Заявленная денежная сумма, если требование денежное: {{amount}}.")],
            "Закон РФ от 07.02.1992 № 2300-1, статьи 29–31"),
    ):
        key = f"pretense_consumer_{suffix}"
        blocks = letter_header() + [title(name)] + facts_blocks + [b("Цель приобретения: {{consumer_status}}. Дополнительные обстоятельства: {{facts}}."),
            b("Основание требования: " + basis + "."),
            heading("Требование потребителя"), b("{{requests}}", "request"), b("Реквизиты для возврата денежных средств: {{payment_details}}."),
            b("Прошу сообщить о принятом решении по адресу заявителя. " + ("Готовность предоставить доступ для осмотра результата работы и согласование времени осмотра будут подтверждены отдельно." if suffix == "defective_service" else "Порядок передачи товара для проверки или возврата прошу согласовать с фиксацией его состояния и комплектности."))]+ending()
        result[key] = package(key, blocks, basis=[basis], limitations=[
            "Срок исполнения зависит от выбранного требования; универсальный срок для всех вариантов не установлен.",
            "Неустойка и потребительский штраф требуют отдельной проверки с учётом изменений с 01.02.2026.",
            "Для технически сложного товара и специальных видов услуг нужны дополнительные условия применимости."])

    for suffix, name in (("flood", "ущерба от залива квартиры"), ("property", "имущественного ущерба")):
        description = [b("Повреждённое имущество: {{damage_object}}. Обстоятельства происшествия: {{facts}}."),
            b("Причина повреждения и основания предъявления требования адресату: {{responsibility}}."),
            b("Документы и иные доказательства размера ущерба: {{evidence}}. Заявленная сумма возмещения: {{amount}}.")]
        key = f"pretense_damage_{suffix}"
        blocks = letter_header() + [title("Претензия о возмещении " + name)] + description + [
            b("Требование основано на правилах о возмещении убытков и причинённого вреда — статьи 15 и 1064 ГК РФ, с учётом обстоятельств и распределения ответственности."),
            heading("Требование о возмещении"), b("{{requests}}", "request"), b("Способ исполнения и платёжные реквизиты: {{payment_details}}."),
            b("Прошу письменно сообщить о результатах рассмотрения и предложенном порядке урегулирования.")]+ending()
        result[key] = package(key, blocks, basis=["ГК РФ, статьи 15, 1064"], limitations=["Ответственное лицо и причинная связь не определяются автоматически по факту повреждения имущества."])
        key = f"claim_damage_{suffix}"
        blocks = court_header(claim=True) + [b("Размер денежного требования: {{amount}}\nГоспошлина или льгота: {{fee}}", "addressee"),
            title("Исковое заявление о возмещении " + name)] + description + [
            b("Предпринятые действия по урегулированию: {{pretrial}}."),
            heading("Правовое обоснование"), b("Статьи 15 и 1064 ГК РФ. {{legal_basis}}"),
            b("Расчёт и подтверждающие документы: {{calculation}}. Выбранный порядок: {{procedure}}; основание выбора суда: {{jurisdiction}}."),
            heading("Требования к суду"), b("{{requests}}", "request"), b("Платёжные реквизиты: {{payment_details}}. Направление копий участникам: {{copy_notice}}.")]+ending()
        result[key] = package(key, blocks, basis=["ГК РФ, статьи 15, 1064; ГПК РФ, статьи 131–132"], layout_name="claim", limitations=["Основание ответственности управляющей организации, собственника или иного лица проверяется отдельно."])

    key = "claim_consumer"
    result[key] = package(key, court_header(claim=True) + [b("Основное денежное требование: {{amount}}\nГоспошлина / основание льготы: {{fee}}", "addressee"),
        title("Исковое заявление о защите прав потребителя"), b("Приобретение и его цель: {{purchase}}. Нарушение: {{violation}}."),
        b("Обстоятельства и подтверждения: {{facts}}. Обращения к продавцу или исполнителю: {{seller_response}}."),
        b("Досудебное урегулирование: {{pretrial}}. Выбор суда и порядка: {{jurisdiction}}; {{procedure}}."),
        heading("Обоснование требований"), b("{{legal_basis}}"), b("Состав и расчёт денежных требований: {{calculation}}."),
        heading("Требования к суду"), b("{{requests}}", "request"), b("Реквизиты для исполнения денежного требования: {{payment_details}}."),
        b("Направление копий участникам и подтверждения: {{copy_notice}}.")]+ending(),
        basis=["Закон РФ от 07.02.1992 № 2300-1; ГПК РФ, статьи 131–132; НК РФ, статья 333.36"], layout_name="claim",
        limitations=["Товарный и сервисный спор требуют разных материально-правовых оснований.", "Штраф, неустойка, моральный вред и льгота по госпошлине не добавляются автоматически.",
                     "Учесть изменения Закона № 2300-1, действующие с 01.02.2026; нельзя использовать старый безусловный расчёт штрафа."])

    for suffix, name, basis in (("civil", "по гражданскому делу", "ГПК РФ, статьи 321, 322, 328, 330"),
                                ("arbitration", "по арбитражному делу", "АПК РФ, статьи 257, 259, 260, 269, 270")):
        key = f"appeal_{suffix}"
        blocks = court_header(appeal=True) + [b("Дело № {{case_number}}\nГоспошлина / льгота: {{fee}}", "addressee"),
            title("Апелляционная жалоба " + name), b("Обжалуемый судебный акт: {{challenged_act}}. Дата изготовления решения в окончательной форме: {{act_date}}."),
            heading("Основания обжалования"), b("{{grounds}}"), b("Соблюдение срока обжалования или сведения о его пропуске: {{appeal_term}}."),
            b("Обоснование выбора суда: {{jurisdiction}}. Процессуальный порядок: {{procedure}}."),
            heading("Просьба к суду апелляционной инстанции"), b("{{requests}}", "request"),
            b("Процессуальные основания: " + basis + ". Сведения о направлении копий участникам: {{copy_notice}}.")]+ending()
        result[key] = package(key, blocks, basis=[basis], layout_name="appeal", limitations=[
            "Предназначено для обжалования решения; частные, кассационные и административные жалобы не охватываются.",
            "При пропуске срока требуется самостоятельное ходатайство с причинами и доказательствами; для ГПК учтено изменение порядка с 01.01.2026."])

    for suffix, name in (("consumer_agency", "Жалоба о нарушении прав потребителя"), ("labor_agency", "Жалоба о нарушении трудовых прав")):
        key = f"complaint_{suffix}"
        result[key] = package(key, letter_header() + [title(name), b("Сообщаю о следующих обстоятельствах: {{facts}}."),
            b("Содержание нарушения: {{violation}}. Ранее предпринятые обращения и полученные ответы: {{previous_contact}}."),
            heading("Просьба заявителя"), b("{{requests}}", "request"),
            b("Прошу рассмотреть изложенные сведения в пределах компетенции органа и направить ответ по указанному адресу заявителя.")]+ending(),
            basis=["Федеральный закон от 02.05.2006 № 59-ФЗ, статья 7", "ТК РФ, статьи 356–357" if suffix == "labor_agency" else "Закон РФ № 2300-1, статья 40"],
            limitations=["Обращение в ведомство не заменяет иск и не гарантирует проведение проверки.",
                         "Электронное обращение направляется через актуальный официальный канал с предусмотренной идентификацией; обычная электронная почта не предлагается как универсальный способ."])

    procedural = {
        "postpone": ("Ходатайство об отложении судебного заседания", [b("Заседание назначено на {{hearing_date}}. Обстоятельства, препятствующие участию или рассмотрению дела: {{reasons}}.")], "ГПК РФ, статья 169; АПК РФ, статья 158 — в соответствующем процессе"),
        "attach": ("Ходатайство о приобщении документов", [b("Представляю следующие документы: {{documents}}. Они подтверждают следующие обстоятельства, значимые для дела: {{relevance}}.")], "ГПК РФ, статьи 35, 57; АПК РФ, статьи 41, 66 — в соответствующем процессе"),
        "costs": ("Заявление о взыскании судебных расходов", [b("Результат рассмотрения дела и судебные акты: {{outcome}}. Понесённые расходы и подтверждения: {{costs}}. Общая заявленная сумма: {{amount}}.")], "ГПК РФ, статьи 98, 100, 103.1; АПК РФ, статьи 110, 112 — в соответствующем процессе"),
        "objection": ("Возражения на исковое заявление", [b("Заявленные истцом требования: {{claims}}. Возражения и подтверждающие материалы: {{objections}}.")], "ГПК РФ, статьи 35, 149; для арбитражного процесса применяется отдельный отзыв по статье 131 АПК РФ"),
    }
    for suffix, (name, content, basis) in procedural.items():
        key = f"motion_{suffix}"
        blocks = court_header() + [b("Дело № {{case_number}}", "addressee"), title(name)] + content + [
            b("Процессуальный порядок и основание обращения в этот суд: {{procedure}}; {{jurisdiction}}."),
            heading("Просьба заявителя"), b("{{requests}}", "request"), b("Сведения о направлении копий участникам: {{copy_notice}}.")]+ending()
        result[key] = package(key, blocks, basis=[basis], layout_name="claim", limitations=[
            "Необходимо выбрать процессуальный вариант до подачи. Правила ГПК и АПК не объединены в универсальное правовое основание.",
            "Для возражений в арбитражном процессе нужен отдельный вариант отзыва, а не переименование гражданских возражений."])

    contracts = {
        "services": ("Договор оказания услуг", "Заказчик", "Исполнитель", [
            heading("1 Предмет и сроки"), b("Заказчик {{sender}} поручает, а Исполнитель {{recipient}} принимает обязательство оказать следующие услуги: {{subject}}. Сроки: {{term}}."),
            heading("2 Организация оказания и приёмка"), b("Стороны согласовали следующий порядок оказания услуг и подтверждения исполнения: {{acceptance}}."),
            heading("3 Цена и расчёты"), b("Общая цена услуг: {{amount}}. Условия и сроки оплаты: {{payment}}."),
        ], "ГК РФ, статьи 779–783"),
        "work": ("Договор подряда", "Заказчик", "Подрядчик", [
            heading("1 Работа и её результат"), b("Заказчик {{sender}} поручает Подрядчику {{recipient}} выполнить работу и передать её результат: {{subject}}."),
            b("Техническое задание и распределение обязанностей по материалам: {{materials}}. Начальный, конечный и промежуточные сроки: {{term}}."),
            heading("2 Цена и оплата"), b("Цена работы: {{amount}}. Условия оплаты и аванса: {{payment}}."),
            heading("3 Сдача результата"), b("Порядок приёмки результата и действий при обнаружении недостатков: {{acceptance}}."),
        ], "ГК РФ, статьи 702–729"),
        "housing": ("Договор найма жилого помещения", "Наймодатель", "Наниматель", [
            heading("1 Предоставляемое жильё"), b("Наймодатель {{sender}} предоставляет Нанимателю {{recipient}} для проживания следующее жилое помещение: {{property}}. Основание полномочий Наймодателя: {{ownership}}."),
            b("Лица, проживающие совместно с Нанимателем: {{residents}}. Срок найма и передачи помещения: {{term}}."),
            heading("2 Плата и расходы"), b("Плата за наём за согласованный расчётный период: {{amount}}. Период, сроки и способ оплаты: {{payment}}. Коммунальные платежи и обеспечительный платёж: {{utilities}}."),
            heading("3 Пользование и возврат"), b("Помещение используется для проживания. Состояние помещения, состав передаваемого имущества, ключи и показания приборов учёта фиксируются сторонами при передаче и возврате."),
        ], "ГК РФ, глава 35, в том числе статьи 671, 674, 683, 687"),
        "loan": ("Договор займа", "Займодавец", "Заёмщик", [
            heading("1 Сумма и передача"), b("Займодавец {{sender}} и Заёмщик {{recipient}} согласовали денежный заём в размере {{amount}}. Условия передачи суммы: {{transfer}}."),
            heading("2 Проценты и возврат"), b("Условия о процентах или прямо согласованной беспроцентности: {{interest}}. Срок возврата и действия договора: {{term}}. Способ и график возврата: {{repayment}}."),
            b("Порядок расчётов и платёжные реквизиты: {{payment}}."),
        ], "ГК РФ, статьи 807–810"),
    }
    for suffix, (name, role1, role2, content, basis) in contracts.items():
        key = f"contract_{suffix}"
        tail = 3 if suffix == "loan" else 4
        blocks = [title(name), b("{{place}}                                            {{date}}", "place_date"),
            b(role1 + ": {{sender}}, адрес: {{sender_address}}. " + role2 + ": {{recipient}}, адрес: {{recipient_address}}.")] + content + [
            heading(f"{tail} Ответственность"), b("Согласованные условия ответственности: {{liability}}. Императивные требования закона применяются независимо от согласованных условий."),
            heading(f"{tail+1} Изменение и прекращение"), b("{{termination}}"),
            heading(f"{tail+2} Реквизиты и подписи"), b("{{details}}"),
            b(role1 + ": __________________ / {{signature}} /", "signature"),
            b(role2 + ": __________________ / {{counterparty_signature}} /", "signature"),
            heading("Приложения"), b("{{attachments}}", "attachments")]
        result[key] = package(key, blocks, basis=[basis], layout_name="contract", limitations=[
            "Текст не устанавливает выдуманные штрафы, автоматическую приёмку или ограничения права на отказ от договора.",
            "Специальные виды услуг, трудовые отношения, строительство и потребительские условия требуют отдельных вариантов."])

    for suffix, name in (("services", "Акт оказанных услуг"), ("work", "Акт выполненных работ")):
        key = f"act_{suffix}"
        blocks = [title(name), b("{{place}}                                            {{date}}", "place_date"),
            b("Стороны: {{sender}}, адрес {{sender_address}}, и {{recipient}}, адрес {{recipient_address}}. Основание составления: {{agreement}}."),
            heading("Исполнение"), b("{{performance}}"), b("Стоимость отражённого в настоящем акте исполнения: {{amount}}."),
            heading("Замечания и результат приёмки"), b("{{quality}}"),
            b("Само подписание акта не подтверждает оплату, если факт оплаты не указан сторонами отдельно."),
            heading("Приложения"), b("{{attachments}}", "attachments"),
            b("Заказчик: __________________ / {{signature}} /", "signature"),
            b("Исполнитель: __________________ / {{counterparty_signature}} /", "signature")]
        result[key] = package(key, blocks, basis=["ГК РФ, статьи 720, 783; Федеральный закон от 06.12.2011 № 402-ФЗ, статья 9 — если используется как первичный учётный документ"],
            layout_name="act", limitations=["Не подставлять отсутствие претензий без явного ответа пользователя.",
                "Для первичного учётного документа отдельно проверяются единицы измерения, объём, должности и полномочия подписантов; для строительных работ нужен специализированный акт."])

    key = "act_loan_receipt"
    result[key] = package(key, [title("Расписка о получении суммы займа"), b("{{place}}                                            {{date}}", "place_date"),
        b("Я, {{sender}}, адрес {{sender_address}}, подтверждаю получение от {{recipient}}, адрес {{recipient_address}}, денежных средств в размере {{amount}} в качестве займа."),
        b("Основание: {{agreement}}. Обстоятельства фактической передачи денег: {{transfer}}. Срок и способ возврата: {{repayment}}. Условия о процентах: {{interest}}."),
        b("Подпись заёмщика: __________________ / {{signature}} /", "signature"), heading("Приложения"), b("{{attachments}}", "attachments")],
        basis=["ГК РФ, статьи 807–810"], layout_name="act", limitations=["Расписка подтверждает уже состоявшуюся передачу денег, а не обещание получить их в будущем.",
            "Подпись займодавца не является обязательным элементом расписки заёмщика; данные его подписи не запрашиваются для этого пакета."])

    key = "power_of_attorney"
    result[key] = package(key, [title("Доверенность на внесудебные действия"), b("{{place}}                                            {{date}}", "place_date"),
        b("Доверитель: {{sender}}, адрес {{sender_address}}, дополнительные сведения: {{principal_details}}."),
        b("Уполномоченный представитель: {{recipient}}, адрес {{recipient_address}}, дополнительные сведения: {{agent_details}}."),
        b("Настоящей доверенностью поручаю представителю совершать следующие действия от имени доверителя: {{powers}}."),
        b("Срок полномочий: {{validity}}. Условия передоверия: {{substitution}}."),
        b("Подпись доверителя: __________________ / {{signature}} /", "signature"), heading("Приложения"), b("{{attachments}}", "attachments")],
        basis=["ГК РФ, статьи 185, 185.1, 186, 187"], layout_name="authority", limitations=["Дата совершения доверенности обязательна; проект без даты нельзя использовать как действующую доверенность.",
            "Результат проверки формы хранится отдельно в поле form_check. Для нотариальной или специальной формы этот документ не заменяет требуемое удостоверение."])
    return result


def main():
    global SOURCES
    source_file = OUT / "sources.json"
    if not source_file.exists():
        import shutil
        OUT.mkdir(parents=True, exist_ok=True)
        original = ROOT / "artifacts/document_templates_2026-10-24"
        for name in ("sources.json", "legal_checks.md"):
            shutil.copy2(original / name, OUT / name)
        shutil.copytree(original / "official_originals", OUT / "official_originals", dirs_exist_ok=True)
    SOURCES = {s["scenario"]: s for s in json.loads(source_file.read_text(encoding="utf-8"))}
    docs = OUT / "docx"
    json_out = OUT / "json"
    docs.mkdir(parents=True, exist_ok=True)
    json_out.mkdir(parents=True, exist_ok=True)
    packages = build_packages()
    assert set(packages) == set(SCENARIOS)
    manifest = []
    for number, (key, scenario) in enumerate(SCENARIOS.items(), 1):
        data = packages[key]
        # Editorial notes belong to metadata, not to the signed body.
        legal_basis = data.pop("legal_basis")
        allowed = {f.key for f in scenario.fields}
        used = set(re.findall(r"\{\{([a-z_]+)\}\}", "\n".join(x["text"] for x in data["blocks"])))
        assert used <= allowed, (key, used - allowed)
        name = f"{number:02d}_{key}"
        for target in (PACKAGES / f"{key}.json", json_out / f"{name}.json"):
            target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        doc_path = docs / f"{name}.docx"
        doc_path.write_bytes(layout.build_legal_docx(scenario.title, data["blocks"],
            review_note="Проект по открытым источникам от 24.10.2026. Проверка юристом не выполнена."))
        manifest.append({"number": number, "scenario": key, "title": scenario.title,
            "docx": doc_path.relative_to(OUT).as_posix(), "json": f"json/{name}.json", "source": SOURCES[key],
            "legal_basis": legal_basis, "status": data["review_status"], "limitations": data["limitations"],
            "fields_used": sorted(used), "fields_for_interview_only": sorted(allowed - used)})
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Библиотека шаблонов документов", "", "Подготовлено 24 октября 2026 года.", "",
        "32 DOCX-шаблона с текстом и оформлением и 32 JSON-пакета для сервиса. Это самостоятельные адаптации, а не скачанные коммерческие Word-файлы ГАРАНТа.",
        "Исследованы реальные открытые формы. Источник, доступность и ограничения указаны отдельно. Дата проверки ссылки не означает дату обновления формы.",
        "Проверка действующих требований выполнена в объёме, перечисленном в legal_checks.md. Полная проверка юристом не выполнена.", "",
        "Макет: A4; Times New Roman 14; левое поле 30 мм, правое 15 мм; верхнее и нижнее 20 мм; межстрочный интервал 1,15. Это выбранный макет, а не универсальное требование закона.", "",
        "Поля {{имя_поля}} заменяются из JSON. Неизвестные сведения становятся подписанными заполнителями. Проценты, штрафы, подсудность и льготы не выдумываются.", "",
        "## Состав", "", "| № | Документ | Источник |", "|---|---|---|"]
    for item in manifest:
        source = item["source"]
        link = f"[открыть]({source['url']})" if source.get("url") else "самостоятельная форма по нормативным требованиям"
        lines.append(f"| {item['number']} | [{item['title']}]({item['docx']}) | {link} |")
    lines += ["", "Подробные ограничения каждого шаблона находятся в manifest.json и JSON-пакетах. Не используйте незаполненные проекты для подачи или подписания."]
    (OUT / "README.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Created {len(packages)} DOCX and JSON packages in {OUT}")


if __name__ == "__main__": main()
