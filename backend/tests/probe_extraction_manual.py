import asyncio
import app.services.document_workflow as workflow

async def main():
    original = workflow._structured
    async def logged(*args, **kwargs):
        response = await original(*args, **kwargs)
        print("RAW", response.content, flush=True)
        return response
    workflow._structured = logged
    state, answer, _ = await workflow.advance_interview(workflow.new_state("Нужна претензия: знакомый не вернул 7 тысяч рублей по расписке"), "Нужна претензия: знакомый не вернул 7 тысяч рублей по расписке")
    print("INITIAL", state["fields"], answer, flush=True)
    state, answer, _ = await workflow.advance_interview(state, "Вавилов Андрей Андреевич")
    print("NEXT", state["fields"], answer, flush=True)

asyncio.run(main())
