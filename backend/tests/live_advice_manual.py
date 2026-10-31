import asyncio
import json
from pathlib import Path
from app.services.nlp_service import NLPService
from app.services.rag_context import build_rag_bundle

async def main():
    queries = [
        "В какой срок работодатель должен выплатить компенсацию за неиспользованный отпуск при увольнении по ст. 127 ТК РФ, если работник отработал менее 3 месяцев?",
        "В какой срок работодатель обязан выплатить окончательный расчёт после увольнения сотрудника согласно ст. 136 ТК РФ?",
        "Может ли работодатель уволить сотрудника по собственному желанию без заявления на основании ст. 80 ТК РФ, если тот неоднократно опаздывал?",
    ]
    results = []
    for query in queries:
        rag, sources = build_rag_bundle(query)
        answer = await NLPService().generate_response(query, {"rag": rag, "rag_sources": sources}, dialog_state="manual-regression-2026-10-24")
        results.append({"query": query, "answer": answer.text,
                        "articles": [r["legal_source"].norm.article for r in answer.references]})
        print(json.dumps(results[-1], ensure_ascii=False), flush=True)
    Path("/app/tests/live_advice_report.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

asyncio.run(main())
