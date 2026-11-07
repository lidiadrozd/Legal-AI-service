import re

# Kept for cleaning legacy model replies; the notice is now shown once in the UI.
LEGAL_DISCLAIMER = "Не является юридической консультацией."


def with_legal_disclaimer(text: str) -> str:
    body = re.sub(
        r"(?m)^\s*Не является юридической консультацией\.\s*", "", text or ""
    ).strip()
    body = re.sub(
        r"(?:\*{1,2})?\bconfidence\s*[:=]\s*(high|medium|low)\b(?:\*{1,2})?",
        "",
        body, flags=re.IGNORECASE,
    )
    body = re.sub(r"\[РЕКОМЕНДАЦИЯ\]\s*", "\n\n**Рекомендация:** ", body, flags=re.IGNORECASE)
    body = re.sub(
        r"\*{0,2}(?:Уверенность|Достоверность)\*{0,2}\s*:\*{0,2}\s*(высокая|средняя|низкая)\*{0,2}[^\S\n]*\.?",
        "",
        body, flags=re.IGNORECASE,
    )
    body = re.sub(r"\*{0,2}Рекомендация\*{0,2}\s*:\*{0,2}\s*", "\n\n**Рекомендация:** ", body, flags=re.IGNORECASE)
    return re.sub(r"\n{3,}", "\n\n", body).strip()
