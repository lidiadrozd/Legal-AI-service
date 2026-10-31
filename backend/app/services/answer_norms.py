"""Explicit law identities from assistant citations, independent of local RAG files.
A citation is evidence of what the assistant used, not verification of legal advice.
"""
from datetime import datetime
import hashlib
import re
from app.services.legal_sources import LegalSource, NormIdentity

TK_KEY = "ru:197-fz:2001-12-30"
GK_KEY = "ru:51-fz:1994-11-30"
GK_PARTS = ((1, 453, GK_KEY), (454, 1109, "ru:14-fz:1996-01-26"),
            (1110, 1224, "ru:146-fz:2001-11-26"), (1225, 1551, "ru:230-fz:2006-12-18"))
ZPP_KEY = "ru:2300-1:1992-02-07"
CODE_URLS = {TK_KEY: "https://www.consultant.ru/document/cons_doc_LAW_34683/",
             GK_KEY: "https://www.consultant.ru/document/cons_doc_LAW_5142/",
             "ru:14-fz:1996-01-26": "https://www.consultant.ru/document/cons_doc_LAW_9027/",
             "ru:146-fz:2001-11-26": "https://www.consultant.ru/document/cons_doc_LAW_34154/",
             "ru:230-fz:2006-12-18": "https://www.consultant.ru/document/cons_doc_LAW_64629/",
             ZPP_KEY: "https://www.consultant.ru/document/cons_doc_LAW_305/"}
TK = r"(?:ТК\s+РФ|трудов(?:ой|ого|ому|ым|ом)\s+кодекс(?:а|у|ом|е)?\s+(?:РФ|Российской\s+Федерации))"
GK = r"(?:ГК\s+РФ|гражданск(?:ий|ого|ому|им|ом)\s+кодекс(?:а|у|ом|е)?\s+(?:РФ|Российской\s+Федерации))"
ZPP = r"(?:ЗОЗПП|закон(?:а|у|ом|е)?\s+(?:РФ\s+)?[«\"]О\s+защите\s+прав\s+потребителей[»\"])"
ACT = r"(?:(?:федеральн\w*\s+)?закон\w*(?:\s+РФ)?\s+)?от\s+(\d{2}\.\d{2}\.\d{4})\s+(?:№|N)\s*(\d+\s*[-–]\s*(?:ФЗ|ФКЗ|\d+))"
ARTICLE = r"(?:ст\.|стать(?:я|и|е|ю|ей|ёй))\s*(\d+(?:\.\d+)*)"
PART = r"(?:(?:ч\.|част[ьи])\s*(\d+(?:\.\d+)*)\s+)?"


def act_key(date, number):
    try:
        issued = datetime.strptime(date, "%d.%m.%Y").date().isoformat()
    except ValueError:
        return None
    number = re.sub(r"\s+", "", number).replace("–", "-").casefold()
    return f"ru:{number.replace('фкз', 'fkz').replace('фз', 'fz')}:{issued}"


def heading_document_key(heading):
    match = re.search(ACT, heading, re.I)
    return act_key(*match.groups()) if match else None


def document_label(key):
    if key == TK_KEY:
        return "ТК РФ"
    if key == GK_KEY:
        return "ГК РФ (часть первая)"
    if key == ZPP_KEY:
        return "Закон РФ «О защите прав потребителей»"
    for index, (_, _, part_key) in enumerate(GK_PARTS, start=1):
        if key == part_key:
            return f"ГК РФ (часть {index})"
    match = re.fullmatch(r"ru:(\d+)-(fz|fkz):(\d{4}-\d{2}-\d{2})", key)
    if match:
        number, kind, date = match.groups()
        return f"Закон № {number}-{'ФЗ' if kind == 'fz' else 'ФКЗ'} от {date}"
    return key


def civil_key(article):
    base = int(article.split(".")[0])
    return next((key for low, high, key in GK_PARTS if low <= base <= high), None)


def extract_answer_norms(answer):
    result, seen = [], set()
    for code, key in ((TK, TK_KEY), (GK, GK_KEY), (ZPP, ZPP_KEY)):
        # Civil-code article numbers belong to disjoint parts with distinct acts.
        patterns = (PART + ARTICLE + r"\s*[,()]?\s*" + code,
                    code + r"\s*[,():—-]?\s*" + PART + ARTICLE)
        for index, pattern in enumerate(patterns):
            for match in re.finditer(pattern, answer or "", re.I):
                part, article = match.groups()
                resolved = civil_key(article) if key == GK_KEY else key
                if resolved:
                    _append(result, seen, NormIdentity(resolved, article, part or ""), match.group(0))
    # Dated, numbered laws work without registering each law in advance.
    for pattern, before in ((PART + ARTICLE + r"\s+" + ACT, True),
                            (ACT + r"\s*[,():—-]?\s*" + PART + ARTICLE, False)):
        for match in re.finditer(pattern, answer or "", re.I):
            groups = match.groups()
            part, article, date, number = groups if before else (groups[2], groups[3], groups[0], groups[1])
            key = act_key(date, number)
            if key:
                _append(result, seen, NormIdentity(key, article, part or ""), match.group(0))
    # Resolve an explicit anaphor only when the answer names one legal document.
    # Never attach arbitrary bare article numbers or cross a multi-law ambiguity.
    named = {act_key(*m.groups()) for m in re.finditer(ACT, answer or "", re.I)} - {None}
    for pattern, key in ((TK, TK_KEY), (GK, "civil-code"), (ZPP, ZPP_KEY)):
        if re.search(pattern, answer or "", re.I):
            named.add(key)
    if len(named) == 1:
        key = next(iter(named))
        for match in re.finditer(PART + ARTICLE + r"\s+(?:указанн|данн|эт)(?:ого)\s+(?:закона|кодекса)", answer or "", re.I):
            part, article = match.groups()
            resolved = civil_key(article) if key == "civil-code" else key
            if resolved:
                _append(result, seen, NormIdentity(resolved, article, part or ""), match.group(0))
    # A dated law or TK may be used as a whole, without an article number.
    for match in re.finditer(ACT, answer or "", re.I):
        key = act_key(*match.groups())
        if key and not any(r["legal_source"].norm.document_key == key for r in result):
            _append(result, seen, NormIdentity(key), match.group(0))
    for pattern, key in ((TK, TK_KEY), (ZPP, ZPP_KEY)):
        if re.search(pattern, answer or "", re.I) and not any(r["legal_source"].norm.document_key == key for r in result):
            _append(result, seen, NormIdentity(key), re.search(pattern, answer, re.I).group(0))
    return tuple(result)


def _append(result, seen, norm, citation):
    if len(norm.document_key) > 200 or any(len(v) > 50 for v in (norm.article, norm.part, norm.point)) or norm.article == "0":
        return
    if norm in seen:
        return
    seen.add(norm)
    digest = hashlib.sha256(citation.encode("utf-8")).hexdigest()
    result.append({"legal_source": LegalSource(norm, CODE_URLS.get(norm.document_key, ""),
                    "assistant-citation", digest), "text": citation,
                   "citation_text": citation, "origin": "assistant_citation"})


def answer_references(answer, offered):
    from app.services.legal_sources import cited_legal_sources
    curated = cited_legal_sources(answer, offered)
    identities = {r["legal_source"].norm for r in curated}
    return curated + tuple(r for r in extract_answer_norms(answer) if r["legal_source"].norm not in identities)


def has_mismatched_source_markers(answer, offered):
    """Reject a marker for article A attached to a paragraph citing only article B."""
    by_id = {str(r["citation_id"]): r["legal_source"].norm for r in offered}
    for paragraph in re.split(r"\n\s*\n|\n(?=\d+\.)", answer):
        explicit = { (r["legal_source"].norm.document_key, r["legal_source"].norm.article)
                    for r in extract_answer_norms(paragraph) if r["legal_source"].norm.article }
        for marker in re.findall(r"\[Источник\s+(\d+)\]", paragraph):
            norm = by_id.get(marker)
            if norm and explicit and (norm.document_key, norm.article) not in explicit:
                return True
    return False


def grounding_issues(answer, offered):
    issues = []
    uses_worker_initiative = any(r["legal_source"].norm.document_key == TK_KEY and r["legal_source"].norm.article == "80" for r in extract_answer_norms(answer))
    if uses_worker_initiative and re.search(r"увольнение возможно только на основании (?:его )?письменного заявления|(?:работника|сотрудника) можно уволить (?:исключительно|только) по (?:его )?заявлению|по инициативе работодателя без его письменного заявления", answer, re.I):
        issues.append("Статья 80 относится только к инициативе работника. Нельзя утверждать, что любое увольнение требует заявления работника; уточни основание прямо в кратком выводе.")
    if has_mismatched_source_markers(answer, offered):
        issues.append("Метка источника относится к другой статье.")
    deadline = any(r["legal_source"].norm.document_key == TK_KEY and r["legal_source"].norm.article == "140" for r in offered)
    if deadline:
        if re.search(r"следующ\w+\s+дн", answer, re.I) and not re.search(r"если[^\n]*(?:не работал|отсутствовал)", answer, re.I):
            issues.append("Срок после требования применим только если работник в день увольнения не работал; это не свободная альтернатива расчёту в день увольнения.")
        if re.search(r"следующ\w+\s+рабоч\w+\s+дн", answer, re.I):
            issues.append("Статья 140 устанавливает следующий день, а не следующий рабочий день.")
        if re.search(r"до дня увольнения", answer, re.I):
            issues.append("В статье 140 исключение связано с тем, что в день увольнения работник не работал; не с требованием до увольнения.")
        if re.search(r"(?:независимо от (?:количества|числа) отработанных|независимо от стажа)", answer, re.I):
            issues.append("Нельзя обещать положительную компенсацию без данных о начисленных и использованных днях отпуска; короткий стаж сам по себе не определяет сумму.")
        if re.search(r"хотя бы один день|(?:один|1) день в последнем месяце", answer, re.I):
            issues.append("Условие о единственном отработанном дне не подтверждено предоставленными источниками.")
    return issues
