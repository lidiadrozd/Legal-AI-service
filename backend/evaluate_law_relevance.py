"""Ручная оценка реального GigaChat на вымышленных данных, без БД и рассылки.

Из backend: ../.venv/Scripts/python.exe evaluate_law_relevance.py
Конфигурация загружается стандартным механизмом приложения; секреты не выводятся.
"""

import asyncio
import argparse
import json
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.models.law_changes import LawChange
from app.models.user_law_interest import UserLawInterest
from app.models.chat_law_reference import ChatLawReference
from app.services.law_relevance_service import (assess_law_change_relevance, assess_law_reference_relevance,
                                               LAW_ANALYSIS_PROMPT, USER_MATCH_PROMPT)
from app.services.law_analysis_schema import LAW_ANALYSIS_FUNCTION, build_user_match_function
from app.services.gigachat_client import get_gigachat_client
from law_evaluation_coverage import check_law_coverage

ROOT = Path(__file__).resolve().parent
CASES_PATH = ROOT / "tests/fixtures/law_relevance_cases.json"
REPORT_PATH = ROOT.parent / "docs/law_relevance_evaluation.json"
FIXED_LAW_ANALYSIS = False


async def main() -> int:
    # В live-прогоне сохраняем только безопасный статус ошибки, без traceback.
    logging.disable(logging.CRITICAL)
    fixture = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    report = {
        "notice": fixture["notice"],
        "model": settings.GIGACHAT_MODEL,
        "analysis_origin": "manual_fixture" if FIXED_LAW_ANALYSIS else "model",
        "fixture_sha256": hashlib.sha256(CASES_PATH.read_bytes()).hexdigest(),
        "checker_sha256": hashlib.sha256(json.dumps({
            "law_prompt": LAW_ANALYSIS_PROMPT, "user_prompt": USER_MATCH_PROMPT,
            "law_function": LAW_ANALYSIS_FUNCTION, "user_function": build_user_match_function([]),
        }, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "state": "running", "results": [],
    }

    def save():
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if not settings.GIGACHAT_CLIENT_ID or not settings.GIGACHAT_CLIENT_SECRET:
        report["state"] = "configuration_missing"
        save()
        print("GigaChat: отсутствуют необходимые настройки. Секреты не выводятся.")
        return 2

    save()
    try:
        await get_gigachat_client()
    except Exception as exc:
        cause = exc.__cause__
        response = getattr(cause, "response", None)
        report["state"] = "connection_error"
        report["diagnostic"] = {
            "error_type": type(exc).__name__,
            "cause_type": type(cause).__name__,
            "http_status": getattr(response, "status_code", None),
            "tls_verification_failed": "CERTIFICATE_VERIFY_FAILED" in str(cause),
        }
        save()
        print(json.dumps(report["diagnostic"]))
        return 2

    for index, case in enumerate(fixture["cases"], start=1):
        change = LawChange(id=index, change_title="Вымышленное учебное изменение",
                           description=case["description"], old_version=case.get("old_version"),
                           new_version=case.get("new_version"), diff={"category": "Учебная проверка"})
        interest = UserLawInterest(id=index, user_id=1, topic_key="educational",
                                   topic_label="Учебная ситуация", keywords=[],
                                   source_excerpt=case["excerpt"])
        result = None
        try:
            if "prior_legal_basis" in case:
                basis = dict(case["prior_legal_basis"])
                basis["situation_excerpt"] = basis.pop("situation_anchor")
                reference = ChatLawReference(id=index, **basis)
                operation = assess_law_reference_relevance(
                    change, reference, user_context=case["context"],
                    law_analysis=fixture["manual_law_analysis"] if FIXED_LAW_ANALYSIS else None)
            else:
                operation = assess_law_change_relevance(change, interest, user_context=case["context"])
            result = await asyncio.wait_for(operation, timeout=300)
            actual, reason = result.status, result.reason
        except asyncio.TimeoutError:
            actual, reason = "error", "Превышено время ожидания."
        row = {"id": case["id"], "expected": case["expected"], "actual": actual,
               "passed": actual == case["expected"], "reason": reason,
               "rationale": case["rationale"]}
        row["conditions"] = list(getattr(result, "conditions", ())) if actual != "error" else []
        row["law_analysis"] = getattr(result, "law_analysis", None)
        row["law_coverage"] = check_law_coverage(row["law_analysis"], case.get("expected_law"))
        if actual == "error":
            row["failure_stage"] = getattr(result, "failure_stage", "timeout")
            row["error_code"] = getattr(result, "error_code", "timeout")
        report["results"].append(row)
        print(f"{case['id']}: expected={case['expected']}, actual={actual}")
        save()

    report["state"] = "completed"
    report["passed"] = sum(row["passed"] for row in report["results"])
    report["total"] = len(fixture["cases"])
    report["errors"] = sum(row["actual"] == "error" for row in report["results"])
    coverage = [row["law_coverage"] for row in report["results"] if row["law_coverage"]["passed"] is not None]
    report["law_coverage_passed"] = sum(row["passed"] for row in coverage)
    report["law_coverage_total"] = len(coverage)
    report["false_positives"] = sum(row["actual"] == "relevant" and row["expected"] != "relevant"
                                    for row in report["results"])
    save()
    print(f"Совпадений: {report['passed']}/{report['total']}")
    return 2 if report["errors"] else 0 if (report["passed"] == report["total"]
                                             and report["law_coverage_passed"] == len(coverage)) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Оценка проверки релевантности на вымышленных данных")
    parser.add_argument("--suite", choices=["development", "holdout", "logic", "references"], default="development")
    parser.add_argument("--model", choices=["GigaChat", "GigaChat-2", "GigaChat-2-Pro", "GigaChat-2-Max"],
                        help="Модель только для этого прогона; .env и настройки приложения не меняются")
    parser.add_argument("--fixed-law-analysis", action="store_true",
                        help="Только suite=references: вручную размеченные условия для изоляции этапа проверки пользователя")
    args = parser.parse_args()
    if args.fixed_law_analysis and args.suite != "references":
        parser.error("--fixed-law-analysis поддерживается только для --suite references")
    if args.suite == "holdout":
        CASES_PATH = ROOT / "tests/fixtures/law_relevance_holdout.json"
        REPORT_PATH = ROOT.parent / "docs/law_relevance_evaluation_holdout.json"
    elif args.suite == "logic":
        CASES_PATH = ROOT / "tests/fixtures/law_relevance_logic_validation.json"
        REPORT_PATH = ROOT.parent / "docs/law_relevance_evaluation_logic.json"
    if args.suite == "references":
        CASES_PATH = ROOT / "tests/fixtures/law_relevance_references.json"
        REPORT_PATH = ROOT.parent / "docs/law_relevance_evaluation_references.json"
    if args.fixed_law_analysis:
        FIXED_LAW_ANALYSIS = True
        REPORT_PATH = REPORT_PATH.with_name(f"{REPORT_PATH.stem}_fixed_conditions.json")
    if args.model:
        settings.GIGACHAT_MODEL = args.model
        REPORT_PATH = REPORT_PATH.with_name(f"{REPORT_PATH.stem}_{args.model}.json")
    raise SystemExit(asyncio.run(main()))
