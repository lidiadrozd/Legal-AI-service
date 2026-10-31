"""Opt-in transport probe: three synthetic requests, no user data or DB writes."""
import asyncio
import json
import time

from app.core.config import settings
from app.services.gigachat_client import get_gigachat_client, close_gigachat_client
from app.services.document_workflow import provider_failure_kind


async def main():
    results = []
    try:
        client = await get_gigachat_client()
        for number in range(1, 4):
            started = time.monotonic()
            try:
                reply = await asyncio.wait_for(client.chat_completion([
                    {"role": "user", "content": "Ответь одним словом: готово."}], settings.GIGACHAT_MODEL), timeout=45)
                results.append({"request": number, "ok": True, "seconds": round(time.monotonic() - started, 2), "tokens": reply.usage.total_tokens})
            except (RuntimeError, ValueError, TimeoutError) as error:
                results.append({"request": number, "ok": False, "seconds": round(time.monotonic() - started, 2), "kind": provider_failure_kind(error)})
                break
            print(json.dumps(results[-1], ensure_ascii=False), flush=True)
    finally:
        await close_gigachat_client()
        print(json.dumps({"results": results}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
