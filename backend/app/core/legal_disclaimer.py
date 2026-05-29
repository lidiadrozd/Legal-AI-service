LEGAL_DISCLAIMER = "Не является юридической консультацией."


def with_legal_disclaimer(text: str) -> str:
    body = (text or "").rstrip()
    if not body:
        return LEGAL_DISCLAIMER
    if LEGAL_DISCLAIMER in body:
        return body
    return f"{body}\n\n{LEGAL_DISCLAIMER}"
