"""Exercise the live GigaChat editorial path through the document API.

This opt-in smoke test deliberately starts with everyday answers from the
consumer-delivery flow.  It does *not* prepare ``draft_fields`` locally:
``POST /documents/interviews/{id}/export`` must obtain and verify editorial
slots itself.  A temporary synthetic account, chat and generated storage item
are removed afterwards; the downloaded DOCX is retained under ``/app/tests``
for manual QA.
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
from app.services.document_drafting import draft_is_current, narrative_keys
from app.services.document_form_rules import prepare_form_rules
from app.services.document_scenarios import SCENARIOS, field_is_active
from app.services.document_template_library import load_text_package
from app.services.document_workflow import new_state, normalize_field, pending_fields


OUTPUT = Path("/app/tests/live-editor-smoke-output")
SCENARIO_KEY = "pretense_consumer_late_delivery"
RAW_PURPOSE = "лежать"
RAW_DELIVERY = "Диван не доставлен. Я не знаю где он. Уже 28 октября"
MANAGED = {"legal_basis", "fee", "jurisdiction"}

# These are fictional facts used only for the smoke test.  The two raw values
# above are intentionally unpolished, so we can detect an accidental bypass of
# the live editor rather than merely testing DOCX filling.
VALUES = {
    "sender": "Соколова Марина Андреевна",
    "sender_address": "г. Екатеринбург, ул. Мира, д. 55, кв. 67",
    "recipient": "ООО «Тест-Мебель»",
    "recipient_address": "г. Екатеринбург, ул. Ленина, д. 10",
    "purchase": "Я приобрела диван по договору № 45633 от 01.09.2026.",
    "amount": "85 000 рублей",
    "payment_evidence": "Есть договор, чек и переписка с магазином.",
    "consumer_status": RAW_PURPOSE,
    "delivery_due": "Доставка обещана до 25 сентября, прописано в договоре.",
    "delivery_status": RAW_DELIVERY,
    "facts": "Обращалась в магазин с вопросом о сроке доставки, ответа нет. Дивана тоже нет.",
    "seller_response": "Обращалась в магазин с вопросом о сроке доставки, ответа нет. Дивана тоже нет.",
    "requests": "возврат оплаты",
    "additional_claims": "Дополнительные требования отсутствуют.",
    "payment": "на карту, с которой был произведён платёж",
    "contacts": "+79000339474",
    "attachments": "Договор.\nКассовый чек.\nПереписка с магазином.",
    "date": "30.10.2026",
    "signature": "Соколова Марина Андреевна",
}


def _store(state, spec, raw):
    value, error = normalize_field(spec, raw)
    if error:
        raise ValueError(f"{spec.key}: {error}")
    state["fields"][spec.key] = {
        "status": "filled",
        "value": value,
        "original": raw,
        "evidence": raw,
        "origin": "synthetic_live_editor_source",
        "error": None,
    }


def _state():
    scenario = SCENARIOS[SCENARIO_KEY]
    state = new_state(
        "Заказала диван и полностью оплатила его, но магазин переносит доставку. Хочу вернуть деньги.",
        filename="08-live-editor-smoke-consumer-late-delivery",
        output_format="docx",
    )
    state.update(
        scenario=SCENARIO_KEY,
        phase="ready",
        text_package=load_text_package(scenario),
        last_questions=[],
    )
    for spec in scenario.fields:
        if spec.key in VALUES:
            _store(state, spec, VALUES[spec.key])
    for spec in scenario.fields:
        if not field_is_active(spec, state["fields"]):
            state["fields"][spec.key] = {
                "status": "not_applicable", "value": None,
                "origin": "inactive_branch", "error": None,
            }
        elif spec.key not in state["fields"] and spec.key not in MANAGED:
            if spec.optional:
                state["fields"][spec.key] = {
                    "status": "not_applicable", "value": None,
                    "origin": "synthetic_absent", "error": None,
                }
            else:
                raise ValueError(f"Missing synthetic value for {spec.key}")

    # This adds only rule-owned legal context.  In particular, do not call
    # prepare_form_document here and do not place anything in draft_fields.
    prepare_form_rules(state)
    pending = pending_fields(state)
    if pending:
        raise ValueError("Pending fields: " + ", ".join(item.key for item in pending))
    targets = set(narrative_keys(state))
    required_targets = {"consumer_status", "delivery_status"}
    if not required_targets.issubset(targets):
        raise AssertionError(f"Raw slots do not reach the editor: {targets}")
    if draft_is_current(state) or state.get("draft_fields"):
        raise AssertionError("Smoke state unexpectedly contains a prepared local draft")
    return state


def _document_text(payload):
    document = WordDocument(BytesIO(payload))
    chunks = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            chunks.extend(cell.text for cell in row.cells)
    return "\n".join(chunk for chunk in chunks if chunk).strip()


def _assert_formalised(text, state, usage_total):
    low = text.casefold()
    for fragment in ("лежать", "я не знаю где он", "дивана тоже нет"):
        if fragment in low:
            raise AssertionError(f"Raw conversational fragment leaked into DOCX: {fragment!r}")
    markers = re.search(r"\{\{|\}\}|\[[^\]\r\n]{1,220}\]|требуется\s+редакция|source[_ ]?text|&DNR", text, re.I)
    if markers:
        raise AssertionError(f"Unresolved document marker: {markers.group(0)!r}")
    if "отдых" not in low:
        raise AssertionError("Consumer purpose was not formalised as personal use for rest")
    if "28 октября" not in low:
        raise AssertionError("The stated date was lost during editorial processing")
    if not re.search(r"мне\s+не\s*известн|не\s+располагаю\s+сведения|не\s+знаю", low):
        raise AssertionError("The user's uncertainty about the item's location was lost")
    drafts = state.get("draft_fields", {})
    if drafts.get("consumer_status", "").casefold() == RAW_PURPOSE:
        raise AssertionError("Consumer-purpose draft was copied without editing")
    if drafts.get("delivery_status", "").casefold() == RAW_DELIVERY.casefold():
        raise AssertionError("Delivery-status draft was copied without editing")
    for key in ("consumer_status", "delivery_status"):
        verdict = state.get("draft_review", {}).get(key, {})
        if not all(verdict.get(name) is True for name in ("meaning_preserved", "business_style", "fits_context")):
            raise AssertionError(f"Live verification did not approve {key}: {verdict!r}")
    if usage_total <= 0:
        raise AssertionError("No live editorial-model token usage was recorded")


async def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    email = "live-editor-smoke-" + secrets.token_hex(8) + "@example.invalid"
    user_id = None
    storage_paths = []
    try:
        state = _state()
        async with AsyncSessionLocal() as db:
            user = User(
                email=email,
                full_name="Synthetic live editor smoke",
                hashed_password=get_password_hash(secrets.token_hex(24)),
                is_active=True,
                consent_given=True,
            )
            db.add(user)
            await db.flush()
            user_id = user.id
            chat = ChatSession(user_id=user_id, title="QA — live editor formalisation", document_workflow=state)
            db.add(chat)
            await db.flush()
            chat_id = chat.id
            await db.commit()

        token = create_access_token({"sub": email})
        async with httpx.AsyncClient(
            base_url="http://127.0.0.1:8000",
            trust_env=False,
            timeout=300,
            headers={"Authorization": "Bearer " + token},
        ) as client:
            response = await client.post(f"/documents/interviews/{chat_id}/export")
            if response.status_code != 201:
                raise RuntimeError(f"export {response.status_code}: {response.text}")
            payload = response.json()
            download = await client.get(f"/documents/{payload['document_id']}/download")
            if download.status_code != 200 or not download.content.startswith(b"PK"):
                raise RuntimeError(f"download {download.status_code}")
            detail = await client.get(f"/documents/interviews/{chat_id}")
            if detail.status_code != 200:
                raise RuntimeError(f"interview read {detail.status_code}")
            exported_state = detail.json()

        async with AsyncSessionLocal() as db:
            events = (await db.execute(
                select(LlmUsageEvent).where(LlmUsageEvent.user_id == user_id)
            )).scalars().all()
            usage_total = sum(event.total_tokens for event in events)

        text = _document_text(download.content)
        _assert_formalised(text, exported_state, usage_total)
        destination = OUTPUT / "08-live-editor-smoke-consumer-late-delivery.docx"
        destination.write_bytes(download.content)
        manifest = {
            "scenario": SCENARIO_KEY,
            "file": destination.name,
            "bytes": len(download.content),
            "used_live_editor": True,
            "llm_total_tokens": usage_total,
            "formalised_slots": {
                key: exported_state["draft_fields"][key]
                for key in ("consumer_status", "delivery_status")
            },
            "checks": "no raw conversational fragments or unresolved markers",
        }
        (OUTPUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"result": "ok", **manifest}, ensure_ascii=False), flush=True)
    finally:
        if user_id is not None:
            async with AsyncSessionLocal() as db:
                storage_paths = (await db.execute(
                    select(Document.file_path).where(Document.user_id == user_id)
                )).scalars().all()
                await db.execute(delete(LlmUsageEvent).where(LlmUsageEvent.user_id == user_id))
                await db.execute(delete(Document).where(Document.user_id == user_id))
                await db.execute(delete(ChatSession).where(ChatSession.user_id == user_id))
                await db.execute(delete(User).where(User.id == user_id))
                await db.commit()
            for path in storage_paths:
                if path:
                    Path(path).unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(main())
