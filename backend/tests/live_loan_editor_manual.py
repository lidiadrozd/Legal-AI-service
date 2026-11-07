"""Synthetic-only editorial diagnosis, no user data or database writes."""
import asyncio
import json
from app.services import document_drafting as editor
from app.services.document_workflow import new_state
from app.services.gigachat_client import get_gigachat_client, close_gigachat_client


async def main():
    state = new_state("Претензия о возврате займа")
    state["scenario"] = "pretense_debt_loan"
    state["fields"] = {key: {"status": "filled", "value": value} for key, value in {
        "agreement": "Расписка от 01.03.2026", "transfer": "Передал наличными 01.03.2026 Михайловой Варваре Максимовне, есть расписка",
        "facts": "Знакомая не вернула 7000 рублей по расписке, срок возврата истёк 15.03.2026",
        "requests": "Вернуть основной долг 7000 рублей"}.items()}
    original = editor.validate_edit
    def checked(text, source):
        ok = original(text, source)
        print(json.dumps({"synthetic_source": source, "edited": text, "passed": ok}, ensure_ascii=False), flush=True)
        return ok
    editor.validate_edit = checked
    try:
        state, _ = await editor.prepare_document_draft(state, await get_gigachat_client())
        print(json.dumps({"editorial": "SUCCESS", "keys": list(state["draft_fields"])}, ensure_ascii=False), flush=True)
    except (RuntimeError, ValueError) as error:
        print("EDITORIAL FAILURE:", str(error), flush=True)
        raise
    finally:
        await close_gigachat_client()


if __name__ == "__main__": asyncio.run(main())
