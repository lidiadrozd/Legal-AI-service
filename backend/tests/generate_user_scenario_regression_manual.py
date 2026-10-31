"""Export seven fictional acceptance scenarios through the live document API.

This is deliberately opt-in and only creates a temporary synthetic user.  It
uses the same persisted interview state, export endpoint and DOCX template
pipeline as the product, then removes the temporary DB/storage records.  The
downloaded acceptance artifacts remain under ``/app/tests`` for visual QA.
"""
import asyncio
from io import BytesIO
import json
from pathlib import Path
import re
import secrets
import sys

sys.path.insert(0, "/app")

import httpx
from docx import Document as WordDocument
from sqlalchemy import delete, select

from app.core.security import create_access_token, get_password_hash
from app.db.session import AsyncSessionLocal
from app.models.chat import ChatSession
from app.models.document import Document
from app.models.llm_usage import LlmUsageEvent
from app.models.user import User
from app.services.document_case_composition import prepare_case_document, prepare_case_rules
from app.services.document_case_facts import collect_case_turn
from app.services.document_drafting import facts_digest
from app.services.document_export_contract import EDITOR_VERSION
from app.services.document_form_composition import prepare_form_document
from app.services.document_form_rules import prepare_form_rules
from app.services.document_scenarios import SCENARIOS, field_is_active
from app.services.document_template_library import load_text_package
from app.services.document_workflow import new_state, normalize_field, pending_fields


OUTPUT = Path("/app/tests/user-scenario-regression-output")
MANAGED = {"legal_basis", "fee", "jurisdiction", "claim_price", "indexation"}


CASES = (
    {
        "scenario": "contract_employment",
        "filename": "01-трудовой-договор-менеджер-по-продажам.docx",
        "prompt": "Нужен трудовой договор между компанией и менеджером по продажам.",
        "values": {
            "sender": "ООО «Северный Контур»",
            "sender_address": "г. Екатеринбург, ул. Ленина, д. 24",
            "sender_details": "ИНН 6671000000; генеральный директор Орлов Сергей Петрович.",
            "authority_basis": "Устав ООО «Северный Контур».",
            "recipient": "Иванова Ольга Викторовна",
            "recipient_address": "г. Екатеринбург, ул. Мира, д. 55, кв. 67",
            "recipient_details": "Паспорт: серия 6500 № 123456, выдан 15.03.2018 ОМВД России по г. Екатеринбургу.",
            "position": "менеджер по продажам",
            "workplace": "ООО «Северный Контур», отдел продаж, г. Екатеринбург, ул. Ленина, д. 24.",
            "job_function": "Работник осуществляет поиск клиентов, консультирование покупателей, оформление заказов и сопровождение продаж.",
            "employment_type": "основная работа",
            "start_date": "01.11.2026",
            "term_type": "на неопределённый срок",
            "amount": "85000 рублей",
            "pay_conditions": "Оклад установлен за полный календарный месяц работы; ежемесячная премия выплачивается при выполнении утверждённых показателей премирования.",
            "payment": "Заработная плата выплачивается 10 и 25 числа каждого месяца путём перечисления на банковский счёт работника.",
            "schedule": "Рабочая неделя устанавливается как пятидневная с понедельника по пятницу; рабочее время установлено с 09:00 до 18:00, перерыв для отдыха и питания — с 13:00 до 14:00, выходные дни — суббота и воскресенье.",
            "work_conditions": "Условия труда на рабочем месте соответствуют классу 2 по карте специальной оценки условий труда № 18 от 15.09.2026.",
            "compensations": "Дополнительные гарантии и компенсации не установлены.",
            "is_pedagogue": "нет",
            "vacation": "28 календарных дней",
            "probation": "Испытание не устанавливается.",
            "additional_terms": "Дополнительные условия не согласованы.",
            "contacts": "Телефон: +79000000001; электронная почта: hr@example.invalid.",
            "attachments": "Должностная инструкция менеджера по продажам.",
            "place": "Екатеринбург",
            "date": "30.10.2026",
            "signature": "Орлов Сергей Петрович",
            "counterparty_signature": "Иванова Ольга Викторовна",
        },
    },
    {
        "scenario": "motion_restore_term",
        "filename": "02-заявление-о-восстановлении-процессуального-срока.docx",
        "prompt": "Нужно заявление о восстановлении пропущенного процессуального срока.",
        "values": {
            "sender": "Петрова Анна Сергеевна, ответчик",
            "sender_address": "г. Екатеринбург, ул. Луначарского, д. 80, кв. 12",
            "sender_details": "Дата рождения: 12.05.1990; место рождения: Екатеринбург; ИНН: 660000000001.",
            "recipient": "ООО «Городские услуги», истец",
            "recipient_address": "г. Екатеринбург, ул. Московская, д. 15",
            "court": "Кировский районный суд города Екатеринбурга",
            "party_details": "ИНН истца: 6671000000; ОГРН: 1026600000000.",
            "case_number": "2-3456/2026",
            "case_subject": "взыскание задолженности по договору оказания услуг",
            "missed_action": "подача возражений относительно исполнения судебного приказа",
            "deadline": "Копия судебного приказа получена 01.10.2026; срок подачи возражений пропущен в период лечения",
            "reasons": "С 01.10.2026 по 14.10.2026 я находилась на стационарном лечении, вследствие чего своевременная подача возражений была невозможна.",
            "evidence": "листок нетрудоспособности и выписка из медицинской карты",
            "concurrent_action": "Одновременно с настоящим заявлением подаю возражения относительно исполнения судебного приказа.",
            "requests": "Прошу восстановить пропущенный процессуальный срок для подачи возражений относительно исполнения судебного приказа.",
            "copy_notice": "Копия заявления направлена истцу 29.10.2026 заказным письмом; почтовая квитанция прилагается.",
            "contacts": "Телефон: +79000000002; электронная почта: petrova@example.invalid.",
            "attachments": "Листок нетрудоспособности.\nВыписка из медицинской карты.\nВозражения относительно исполнения судебного приказа.",
            "date": "30.10.2026",
            "signature": "Петрова Анна Сергеевна",
        },
    },
    {
        "scenario": "power_of_attorney",
        "filename": "03-доверенность-на-внесудебные-действия.docx",
        "prompt": "Нужна доверенность на внесудебные действия в управляющей организации.",
        "values": {
            "sender": "Соколова Марина Андреевна",
            "sender_address": "г. Екатеринбург, ул. Мира, д. 55, кв. 67",
            "recipient": "Кузнецов Илья Петрович",
            "recipient_address": "г. Екатеринбург, ул. Белинского, д. 150, кв. 41",
            "principal_details": "Паспорт: серия 6500 № 222333, выдан 10.04.2019 ОМВД России по г. Екатеринбургу.",
            "agent_details": "Паспорт: серия 6501 № 444555, выдан 18.06.2020 ОМВД России по г. Екатеринбургу.",
            "place": "Екатеринбург",
            "powers": "Представлять интересы доверителя в управляющей организации ООО «ДомСервис»: подавать заявления и документы, получать ответы, справки и копии документов по вопросам начисления коммунальных платежей.",
            "validity": "1 год",
            "substitution": "Без права передоверия",
            "form_check": "Необходимость специальной формы доверенности подлежит проверке перед использованием документа.",
            "contacts": "Телефон: +79000000003; электронная почта: sokolova@example.invalid.",
            "attachments": "Копия паспорта доверителя.",
            "date": "30.10.2026",
            "signature": "Соколова Марина Андреевна",
        },
    },
    {
        "scenario": "claim_alimony_fixed",
        "filename": "04-иск-о-взыскании-алиментов-в-твердой-сумме.docx",
        "prompt": "Нужен иск о взыскании алиментов на несовершеннолетнего ребёнка в твёрдой денежной сумме.",
        "values": {
            "sender": "Сидорова Елена Андреевна",
            "sender_address": "г. Екатеринбург, ул. Академическая, д. 17, кв. 39",
            "recipient": "Сидоров Алексей Викторович",
            "recipient_address": "г. Екатеринбург, ул. Восточная, д. 68, кв. 24",
            "court": "Кировский районный суд города Екатеринбурга",
            "party_details": "Дата рождения: 15.04.1988; место работы: ООО «Урал-Сервис».",
            "children": "Сидорова Мария Алексеевна, 15.06.2018.",
            "parentage": "Ответчик является отцом ребёнка; отцовство подтверждается свидетельством о рождении и не оспаривается.",
            "living": "Ребёнок проживает со мной.",
            "existing_support": "Ранее алименты не устанавливались; нотариального соглашения нет.",
            "other_dependants": "Других детей нет.",
            "assistance": "Нет",
            "fixed_grounds": "Доход ответчика носит нерегулярный характер; ответчик получает доход от выполнения разовых заказов.",
            "monthly_amount": "20000 рублей",
            "maintenance_calculation": "Общие ежемесячные расходы на ребёнка составляют 40000 рублей.",
            "start": "Со дня обращения в суд.",
            "pretrial": "Предложение о добровольной уплате алиментов направлено ответчику 10.10.2026; ответ не получен.",
            "calculation": "Требование состоит из ежемесячных алиментов в твёрдой денежной сумме.",
            "requests": "Прошу взыскать алименты в твёрдой денежной сумме.",
            "other_participants": "Отсутствуют.",
            "copy_notice": "Копия иска и приложений направлена ответчику 29.10.2026 заказным письмом; почтовая квитанция прилагается.",
            "contacts": "Телефон: +79000000004; электронная почта: sidorova@example.invalid.",
            "attachments": "Копия свидетельства о рождении ребёнка.\nДокументы о расходах на ребёнка.\nПочтовая квитанция о направлении иска.",
            "date": "30.10.2026",
            "signature": "Сидорова Елена Андреевна",
            "sender_details": "Дата рождения: 12.05.1990; место рождения: Екатеринбург; ИНН: 660000000001.",
        },
    },
    {
        "scenario": "pretense_debt_services",
        "filename": "05-претензия-о-задолженности-по-договору-услуг.docx",
        "prompt": "Нужна претензия о задолженности по договору оказания услуг.",
        "values": {
            "sender": "ООО «Альфа-Консалт»",
            "sender_address": "г. Екатеринбург, ул. Куйбышева, д. 44",
            "recipient": "ООО «Вектор»",
            "recipient_address": "г. Екатеринбург, ул. Челюскинцев, д. 90",
            "agreement": "Договор оказания услуг № 18 от 01.09.2026.",
            "performance": "Услуги по разработке рекламной кампании оказаны 30.09.2026; результат принят заказчиком по акту № 7 от 30.09.2026.",
            "due_date": "Оплата услуг должна быть произведена не позднее 10.10.2026.",
            "facts": "Заказчик оплату в установленный срок не произвёл; денежные средства не поступили.",
            "amount": "120000 рублей",
            "requests": "Прошу оплатить основной долг в размере 120000 рублей.",
            "response_term": "В течение 10 календарных дней со дня получения настоящей претензии.",
            "payment_details": "Банковский перевод на расчётный счёт исполнителя, реквизиты которого указаны в договоре.",
            "attachments": "Договор оказания услуг № 18.\nАкт оказанных услуг № 7.\nСчёт на оплату.",
            "date": "30.10.2026",
            "signature": "Орлов Сергей Петрович",
        },
    },
    {
        "scenario": "appeal_civil",
        "filename": "06-апелляционная-жалоба-по-гражданскому-делу.docx",
        "prompt": "Нужна апелляционная жалоба на решение районного суда по гражданскому делу.",
        "values": {
            "sender": "Иванов Дмитрий Сергеевич, ответчик",
            "sender_address": "г. Екатеринбург, ул. Первомайская, д. 31, кв. 7",
            "recipient": "Смирнова Анна Павловна, истец",
            "recipient_address": "г. Екатеринбург, ул. Бажова, д. 101, кв. 55",
            "procedure": "гражданское судопроизводство",
            "court": "Свердловский областной суд",
            "party_details": "Телефон заявителя: +79000000005; электронная почта: ivanov@example.invalid.",
            "case_number": "2-1234/2026",
            "first_court": "Кировский районный суд города Екатеринбурга",
            "challenged_act": "Решение Кировского районного суда города Екатеринбурга от 20.09.2026 по делу № 2-1234/2026.",
            "act_date": "20.09.2026",
            "grounds": "Суд первой инстанции не дал оценку банковской выписке от 15.09.2026, подтверждающей исполнение обязательства. Вывод о наличии задолженности не соответствует указанному доказательству.",
            "appeal_term": "Копия решения получена 25.09.2026; апелляционная жалоба подаётся в установленный процессуальный срок.",
            "fee": "Государственная пошлина уплачена в размере 3000 рублей; квитанция от 30.10.2026 прилагается.",
            "requests": "Прошу отменить решение Кировского районного суда города Екатеринбурга от 20.09.2026 и принять по делу новое решение об отказе в удовлетворении исковых требований.",
            "jurisdiction": "Апелляционная жалоба подаётся через Кировский районный суд города Екатеринбурга в Свердловский областной суд.",
            "other_participants": "Отсутствуют.",
            "copy_notice": "Копия жалобы и приложений направлена истцу 30.10.2026 заказным письмом; почтовая квитанция прилагается.",
            "attachments": "Копия обжалуемого решения.\nБанковская выписка от 15.09.2026.\nКвитанция об уплате государственной пошлины.\nПочтовая квитанция о направлении жалобы.",
            "date": "30.10.2026",
            "signature": "Иванов Дмитрий Сергеевич",
        },
    },
    {
        "scenario": "contract_sale_nonresidential",
        "filename": "07-договор-купли-продажи-нежилого-помещения.docx",
        "prompt": "Нужен договор купли-продажи нежилого помещения.",
        "values": {
            "sender": "ООО «Урал-Инвест»",
            "sender_address": "г. Екатеринбург, ул. Малышева, д. 36",
            "recipient": "ООО «Деловой Центр»",
            "recipient_address": "г. Екатеринбург, ул. Радищева, д. 28",
            "seller_details": "ОГРН 1026600000001; ИНН 6671000001; генеральный директор Орлов Сергей Петрович.",
            "buyer_details": "ОГРН 1026600000002; ИНН 6671000002; генеральный директор Иванова Ольга Викторовна.",
            "property_address": "г. Екатеринбург, ул. Малышева, д. 36, помещение 14",
            "cadastral_number": "66:41:0401001:1234",
            "area": "86,4",
            "property_description": "Помещение имеет назначение «нежилое» и расположено на первом этаже.",
            "ownership": "Право собственности зарегистрировано на основании договора купли-продажи от 12.03.2020; запись ЕГРН № 66:41:0401001:1234-66/001/2020-1.",
            "encumbrances": "Обременения и права третьих лиц отсутствуют",
            "land_rights": "Сведения о правах на земельный участок отражены в выписке ЕГРН.",
            "amount": "5500000 рублей",
            "payment_method": "Оплата производится безналичным переводом на расчётный счёт Продавца.",
            "payment_date": "Не позднее 05.11.2026",
            "payment_details": "р/с 40702810000000000001 в ПАО «Банк», БИК 046577000",
            "handover": "Продавец передаёт помещение по передаточному акту не позднее трёх рабочих дней после полной оплаты.",
            "registration": "Стороны совместно подают документы для государственной регистрации перехода права в течение трёх рабочих дней после подписания договора.",
            "expenses": "Расходы на государственную регистрацию стороны несут поровну",
            "additional_terms": "Стороны подтверждают, что осмотрели помещение и согласовали его состояние",
            "place": "Екатеринбург",
            "counterparty_signature": "Иванова Ольга Викторовна",
            "attachments": "Выписка ЕГРН.\nПередаточный акт.",
            "date": "30.10.2026",
            "signature": "Орлов Сергей Петрович",
        },
    },
)


def _store(state, spec, raw):
    value, error = normalize_field(spec, raw)
    if error:
        raise ValueError(f"{state['scenario']}:{spec.key}: {error}")
    state["fields"][spec.key] = {
        "status": "filled",
        "value": value,
        "original": raw,
        "evidence": raw,
        "origin": "synthetic_acceptance_fact",
        "error": None,
    }


async def _state(case):
    key = case["scenario"]
    scenario = SCENARIOS[key]
    state = new_state(case["prompt"], filename=Path(case["filename"]).stem, output_format="docx")
    state.update(scenario=key, phase="ready", text_package=load_text_package(scenario), last_questions=[])
    values = case["values"]
    for spec in scenario.fields:
        if spec.key in values:
            _store(state, spec, values[spec.key])
    for spec in scenario.fields:
        if field_is_active(spec, state["fields"]):
            if spec.key in state["fields"] or spec.key in MANAGED:
                continue
            if spec.optional:
                state["fields"][spec.key] = {"status": "not_applicable", "value": None,
                                               "origin": "synthetic_absent", "error": None}
                continue
            raise ValueError(f"{key}: no synthetic source value for active field {spec.key}")
        state["fields"][spec.key] = {"status": "not_applicable", "value": None,
                                       "origin": "inactive_branch", "error": None}

    if key == "claim_alimony_fixed":
        # Replay the same fact parser used for actual turns.  The final
        # "пополам" is a separate follow-up answer to the calculation question.
        for field in ("party_details", "children", "parentage", "living", "existing_support",
                      "other_dependants", "assistance", "fixed_grounds", "maintenance_calculation",
                      "start", "attachments"):
            item = state["fields"].get(field, {})
            if item.get("status") == "filled":
                collect_case_turn(state, item["original"], field)
        collect_case_turn(state, "пополам", "maintenance_calculation")
        prepare_case_rules(state)
        state = prepare_case_document(state)
    else:
        prepare_form_rules(state)
        state, _ = await prepare_form_document(state, None)
        if state.get("form_review_fields"):
            raise ValueError(f"{key}: local formalisation gaps: {state['form_review_fields']}")

    if pending_fields(state):
        raise ValueError(f"{key}: pending fields: {[item.key for item in pending_fields(state)]}")
    state["phase"] = "ready"
    state["last_questions"] = []
    state["draft_version"] = EDITOR_VERSION
    state["draft_digest"] = facts_digest(state["fields"])
    return state


def _document_text(payload):
    document = WordDocument(BytesIO(payload))
    chunks = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            chunks.extend(cell.text for cell in row.cells)
    return "\n".join(chunk for chunk in chunks if chunk).strip()


def _assert_clean(case, text):
    marker = re.search(r"\{\{|\}\}|\[[^\]\r\n]{1,220}\]|требуется\s+редакция|source[_ ]?text|&DNR", text, re.I)
    if marker:
        raise AssertionError(f"{case['scenario']}: unresolved document marker: {marker.group(0)!r}")
    if case["scenario"] == "contract_employment" and re.search(r"педагогическ|учебн\w* нагрузк", text, re.I):
        raise AssertionError("contract_employment: pedagogical rule leaked into sales-manager contract")
    if case["scenario"] == "claim_alimony_fixed" and re.search(r"отношени[ея]\s+суммы\s+алиментов", text, re.I):
        raise AssertionError("claim_alimony_fixed: unverified living-wage ratio marker leaked into document")
    if case["scenario"] == "appeal_civil" and "3 000 рублей" not in text:
        raise AssertionError("appeal_civil: user-confirmed state-fee amount was not preserved")


async def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    email = "scenario-regression-" + secrets.token_hex(8) + "@example.invalid"
    uid = None
    storage_paths = []
    manifest = []
    try:
        states = [(case, await _state(case)) for case in CASES]
        async with AsyncSessionLocal() as db:
            user = User(email=email, full_name="Synthetic scenario regression", hashed_password=get_password_hash(secrets.token_hex(24)),
                        is_active=True, consent_given=True)
            db.add(user)
            await db.flush()
            uid = user.id
            chats = []
            for case, state in states:
                chat = ChatSession(user_id=uid, title="QA — " + SCENARIOS[case["scenario"]].title,
                                   document_workflow=state)
                db.add(chat)
                chats.append((case, chat))
            await db.flush()
            chat_ids = [(case, chat.id) for case, chat in chats]
            await db.commit()

        token = create_access_token({"sub": email})
        async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", trust_env=False, timeout=180,
                                     headers={"Authorization": "Bearer " + token}) as client:
            for case, chat_id in chat_ids:
                response = await client.post(f"/documents/interviews/{chat_id}/export")
                if response.status_code != 201:
                    raise RuntimeError(f"{case['scenario']}: export {response.status_code}: {response.text}")
                payload = response.json()
                download = await client.get(f"/documents/{payload['document_id']}/download")
                if download.status_code != 200 or not download.content.startswith(b"PK"):
                    raise RuntimeError(f"{case['scenario']}: download {download.status_code}")
                text = _document_text(download.content)
                _assert_clean(case, text)
                destination = OUTPUT / case["filename"]
                destination.write_bytes(download.content)
                manifest.append({
                    "scenario": case["scenario"],
                    "title": SCENARIOS[case["scenario"]].title,
                    "file": destination.name,
                    "bytes": len(download.content),
                    "chat_id": chat_id,
                    "document_id": payload["document_id"],
                    "checks": "no unresolved markers",
                })
                print(json.dumps({"exported": case["scenario"], "file": destination.name,
                                  "bytes": len(download.content)}, ensure_ascii=False), flush=True)

        (OUTPUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"result": "ok", "directory": str(OUTPUT), "count": len(manifest)}, ensure_ascii=False), flush=True)
    finally:
        if uid is not None:
            async with AsyncSessionLocal() as db:
                storage_paths = (await db.execute(select(Document.file_path).where(Document.user_id == uid))).scalars().all()
                await db.execute(delete(LlmUsageEvent).where(LlmUsageEvent.user_id == uid))
                await db.execute(delete(Document).where(Document.user_id == uid))
                await db.execute(delete(ChatSession).where(ChatSession.user_id == uid))
                await db.execute(delete(User).where(User.id == uid))
                await db.commit()
            for path in storage_paths:
                if path:
                    Path(path).unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(main())
