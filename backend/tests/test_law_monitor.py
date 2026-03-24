import asyncio
from app.services.law_monitor_service import get_law_monitor_service


async def test():
    service = get_law_monitor_service()
    articles = await service.get_law_updates(use_cache=False)

    from collections import Counter
    sources = Counter(a["source"] for a in articles)
    print("По источникам:", dict(sources))

asyncio.run(test())