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
NK_FIRST = "ru:146-fz:1998-07-31"
NK_SECOND = "ru:117-fz:2000-08-05"
RF = r"(?:РФ|Российской\s+Федерации)"
CODE_END = r"\s+кодекс\w*\s+" + RF
# Document IDs identify the original code, not an amending act.
OTHER_CODES = (
    ("ГПК РФ", r"гражданск\w*\s+процессуальн\w*" + CODE_END, "ru:138-fz:2002-11-14", 39570),
    ("АПК РФ", r"арбитражн\w*\s+процессуальн\w*" + CODE_END, "ru:95-fz:2002-07-24", 37800),
    ("КАС РФ", r"кодекс\w*\s+административного\s+судопроизводства\s+" + RF, "ru:21-fz:2015-03-08", 176147),
    ("УК РФ", r"уголовн\w*" + CODE_END, "ru:63-fz:1996-06-13", 10699),
    ("КоАП РФ", r"кодекс\w*\s+" + RF + r"\s+об\s+административных\s+правонарушениях", "ru:195-fz:2001-12-30", 34661),
    ("СК РФ", r"семейн\w*" + CODE_END, "ru:223-fz:1995-12-29", 8982),
    ("НК РФ", r"налогов\w*" + CODE_END, NK_FIRST, 19671),
)
CODE_LABELS = {key: label for label, _, key, _ in OTHER_CODES}
CODE_LABELS[NK_SECOND] = "НК РФ"
CODE_URLS.update({key: f"https://www.consultant.ru/document/cons_doc_LAW_{doc_id}/"
                  for _, _, key, doc_id in OTHER_CODES})
CODE_URLS[NK_SECOND] = "https://www.consultant.ru/document/cons_doc_LAW_28165/"
CODE_NAMES = [(TK, TK_KEY), (GK, GK_KEY), (ZPP, ZPP_KEY)]
for label, full_name, key, _ in OTHER_CODES:
    abbreviation = label.replace(" ", r"\s+")
    CODE_NAMES.append((rf"(?:{abbreviation}|{full_name})", key))
# Split codes are commonly cited with a parenthesized part after the name.
CODE_PART = r"(?:\s*\(часть\s+(?:[1-4]|первая|вторая|третья|четвертая|четвёртая)\))?"
CODE_NAMES = [(r"(?<!\w)" + name + r"(?!\w)" + (CODE_PART if key in (GK_KEY, NK_FIRST) else ""), key)
              for name, key in CODE_NAMES]
ACT = r"(?:(?:федеральн\w*\s+)?закон\w*(?:\s+РФ)?\s+)?от\s+(\d{2}\.\d{2}\.\d{4})\s+(?:№|N)\s*(\d+\s*[-–]\s*(?:ФЗ|ФКЗ|\d+))"
ARTICLE = r"(?:ст\.|стать(?:я|и|е|ю|ей|ёй))\s*(\d+(?:\.\d+)*)"
PART = r"(?:(?:ч\.|част[ьи])\s*(\d+(?:\.\d+)*)\s+)?"
POINT = r"(?:(?:п\.|пункт(?:а|у|ом|е)?)\s*(\d+(?:\.\d+)*)\s+)?"
TRAILING_SCOPE = (r"(?:\s*,\s*(?:ч\.|част[ьи])\s*(\d+(?:\.\d+)*))?"
                  r"(?:\s*,\s*(?:п\.|пункт(?:а|у|ом|е)?)\s*(\d+(?:\.\d+)*))?")


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
    if key in CODE_LABELS:
        return CODE_LABELS[key]
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


def _article_key(key, article):
    if len(article) > 50:
        return None
    if key == GK_KEY:
        return civil_key(article)
    if key == NK_FIRST and int(article.split(".")[0]) >= 143:
        return NK_SECOND
    return key


def extract_answer_norms(answer):
    result, seen = [], set()
    for code, key in CODE_NAMES:
        scoped_article = POINT + PART + ARTICLE
        patterns = (scoped_article + r"\s*[,()]?\s*" + code + TRAILING_SCOPE,
                    code + r"\s*[,():—-]?\s*" + scoped_article + TRAILING_SCOPE)
        for pattern in patterns:
            for match in re.finditer(pattern, answer or "", re.I):
                point, part, article, trailing_part, trailing_point = match.groups()
                resolved = _article_key(key, article)
                if resolved:
                    norm = NormIdentity(resolved, article, part or trailing_part or "", point or trailing_point or "")
                    _append(result, seen, norm, match.group(0))
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
    for pattern, key in CODE_NAMES:
        if re.search(pattern, answer or "", re.I):
            named.add(key)
    if len(named) == 1:
        key = next(iter(named))
        for match in re.finditer(PART + ARTICLE + r"\s+(?:указанн|данн|эт)(?:ого)\s+(?:закона|кодекса)", answer or "", re.I):
            part, article = match.groups()
            resolved = _article_key(key, article)
            if resolved:
                _append(result, seen, NormIdentity(resolved, article, part or ""), match.group(0))
    # A dated law or TK may be used as a whole, without an article number.
    for match in re.finditer(ACT, answer or "", re.I):
        key = act_key(*match.groups())
        if key and not any(r["legal_source"].norm.document_key == key for r in result):
            _append(result, seen, NormIdentity(key), match.group(0))
    for pattern, key in CODE_NAMES:
        if key in (TK_KEY, ZPP_KEY) and not any(r["legal_source"].norm.document_key == key for r in result):
            match = re.search(pattern, answer or "", re.I)
            if match:
                _append(result, seen, NormIdentity(key), match.group(0))
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


def _normalized_quote_text(text):
    return re.sub(r"\s+", " ", (text or "").replace("\u00a0", " ")).strip()


def _quoted_passages(answer):
    """Return visibly quoted prose; an unmarked copied sentence is not a quote."""
    passages = []
    for pattern in (r"«([^»]+)»", r'“([^”]+)”', r'(?<!\w)"([^"\n]+)"'):
        passages.extend(_normalized_quote_text(match) for match in re.findall(pattern, answer or "", re.S))
    block = []
    for line in (answer or "").splitlines() + [""]:
        if re.match(r"^\s*>\s?", line):
            block.append(re.sub(r"^\s*>\s?", "", line))
        elif block:
            passages.append(_normalized_quote_text(" ".join(block)))
            block = []
    return tuple(item for item in passages if item)


def has_verified_legal_quote(answer, source):
    """A valid direct quote is visibly marked and copied from curated statute text."""
    if not isinstance(source, LegalSource) or not source.has_verified_excerpt:
        return False
    expected = _normalized_quote_text(source.verbatim_excerpt)
    return any(expected == passage for passage in _quoted_passages(answer))


def legal_quote_issues(answer, offered):
    """Enforce a verified quote for each norm presented as an authoritative citation."""
    issues = []
    by_id = {str(item.get("citation_id")): item for item in offered
             if isinstance(item.get("legal_source"), LegalSource)}
    markers = set(re.findall(r"\[Источник\s+([1-9][0-9]*)\]", answer or ""))
    marker_quotes = {}
    for paragraph in re.split(r"\n\s*\n|\n(?=\d+\.)", answer or ""):
        passages = _quoted_passages(paragraph)
        for marker in re.findall(r"\[Источник\s+([1-9][0-9]*)\]", paragraph):
            marker_quotes.setdefault(marker, []).extend(passages)
    acknowledges_unverified = bool(re.search(
        r"точн\w*\s+текст\w*\s+(?:норм\w*|стать\w*)[^\n.]{0,100}не\s+подтвержд",
        answer or "", re.I,
    )) or bool(re.search(
        r"цитат\w*\s+не\s+привед[^\n.]{0,100}проверенн\w*\s+баз\w*",
        answer or "", re.I,
    ))
    explicit = {item["legal_source"].norm for item in extract_answer_norms(answer)}
    offered_by_norm = {}
    for item in offered:
        source = item.get("legal_source")
        if isinstance(source, LegalSource):
            offered_by_norm.setdefault((source.norm.document_key, source.norm.article), item)

    checked = set()
    for marker in markers:
        item = by_id.get(marker)
        if not item:
            continue
        source = item["legal_source"]
        checked.add(source.norm)
        if source.content_kind == "operator_summary":
            if marker_quotes.get(marker):
                issues.append(f"Источник {marker} — авторское изложение; текст в кавычках нельзя выдавать за цитату нормы.")
            elif not acknowledges_unverified:
                issues.append(f"Источник {marker} — авторское изложение, его нельзя выдавать за прямую цитату нормы.")
        elif not source.has_verified_excerpt:
            if marker_quotes.get(marker):
                issues.append(f"Для источника {marker} нет верифицированного текста, поэтому цитата в кавычках не подтверждена.")
            elif not acknowledges_unverified:
                issues.append(f"Для источника {marker} нет заранее верифицированной дословной цитаты.")
        elif not has_verified_legal_quote(answer, source) and not acknowledges_unverified:
            issues.append(f"Для источника {marker} отсутствует точная короткая цитата из текста нормы.")

    # A model may name an offered article but omit its marker. That must not
    # bypass quote validation by being reclassified as an assistant citation.
    for norm in explicit:
        item = offered_by_norm.get((norm.document_key, norm.article))
        if item:
            source = item["legal_source"]
            marker = str(item["citation_id"])
            if marker not in markers:
                issues.append(f"Для указанной нормы отсутствует метка проверенного источника {marker}.")
            if source.norm not in checked:
                if source.content_kind == "operator_summary":
                    if not acknowledges_unverified:
                        issues.append(f"Источник {marker} содержит только авторское изложение, а не дословный текст нормы.")
                elif not source.has_verified_excerpt:
                    if not acknowledges_unverified:
                        issues.append(f"Для указанной нормы нет заранее верифицированной дословной цитаты.")
                elif not has_verified_legal_quote(answer, source) and not acknowledges_unverified:
                    issues.append(f"Для указанной нормы отсутствует точная короткая цитата из текста статьи.")
            continue
        # No local evidence means there is no safe way to certify model text as
        # a direct quotation, even when the article identifier looks plausible.
        if not acknowledges_unverified:
            issues.append(
                f"Для {document_label(norm.document_key)}, статья {norm.article or 'не указана'} "
                "нет верифицированного текста для прямой цитаты."
            )
    return list(dict.fromkeys(issues))


def grounding_issues(answer, offered):
    issues = legal_quote_issues(answer, offered)
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
