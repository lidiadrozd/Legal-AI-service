"""Opt-in provider smoke test; synthetic facts only, no database writes."""
import asyncio

from app.services.document_workflow import advance_interview, new_state


async def main():
    prompt = "Нужен договор купли-продажи нежилого помещения"
    state, answer, _ = await advance_interview(new_state(prompt), prompt)
    print("START STATE:", state["scenario"], state["last_questions"], state["fields"], flush=True)
    print("FIRST:", answer, flush=True)
    assert state["scenario"] == "contract_sale_nonresidential"
    assert state["last_questions"] == ["sender"]
    state, answer, _ = await advance_interview(state, "Иванов Иван Иванович")
    assert state["last_questions"] == ["sender_address"]
    print("NEXT:", answer)
    state, answer, _ = await advance_interview(state, "Чей адрес нужно указать?")
    assert state["last_questions"] == ["sender_address"]
    assert "продав" in answer.lower()
    assert answer.count("?") <= 1
    print("HELP:", answer)
    state, answer, _ = await advance_interview(state, "не знаю")
    assert state["last_questions"] == ["recipient"]
    print("UNKNOWN THEN NEXT:", answer)


if __name__ == "__main__":
    asyncio.run(main())
