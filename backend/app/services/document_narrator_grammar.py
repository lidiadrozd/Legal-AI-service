"""Meaning-preserving agreement of first-person narration in documents.

The service stores a person's name separately from their free-form facts.
When a past-tense verb in those facts conflicts with an unambiguous Russian
patronymic, correcting the ending is a grammatical repair, not a new fact.
The rules are deliberately narrow: without a clear full name they do nothing,
and they never alter third-person actions of an opposing party.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


_ORGANISATION = re.compile(
    r"\b(?:ооо|ао|пао|зао|гбу|мбу|фгбу|учреждени[ея]|школ[аы]|детск(?:ий|ого)\s+сад)\b",
    re.I,
)
_WORDS = re.compile(r"[А-ЯЁа-яё-]+")

# The mapping is intentionally lexical instead of a suffix rewrite: Russian
# past tense contains many exceptions, and a document generator must prefer
# leaving an uncertain word alone to changing a fact or a third-party action.
_FEMININE_TO_MASCULINE = {
    "была": "был",
    "взяла": "взял",
    "дала": "дал",
    "заказала": "заказал",
    "заключила": "заключил",
    "заплатила": "заплатил",
    "заявила": "заявил",
    "написала": "написал",
    "направила": "направил",
    "обратилась": "обратился",
    "обращалась": "обращался",
    "обнаружила": "обнаружил",
    "оплатила": "оплатил",
    "оплачивала": "оплачивал",
    "отправила": "отправил",
    "передала": "передал",
    "подала": "подал",
    "подписала": "подписал",
    "подтвердила": "подтвердил",
    "получила": "получил",
    "понесла": "понёс",
    "предъявила": "предъявил",
    "приобрела": "приобрёл",
    "приложила": "приложил",
    "проживала": "проживал",
    "сделала": "сделал",
    "составила": "составил",
    "сообщила": "сообщил",
    "требовала": "требовал",
    "уведомила": "уведомил",
    "указала": "указал",
}
_MASCULINE_TO_FEMININE = {value: key for key, value in _FEMININE_TO_MASCULINE.items()}

_MODIFIERS = (
    "уже|ранее|также|лично|сама|сам|впоследствии|неоднократно|своевременно|"
    "сразу|впервые|повторно|добровольно|фактически|дополнительно|полностью|частично|не"
)


def grammatical_gender(value: Any) -> str | None:
    """Infer a person's grammatical gender only from a clear patronymic.

    A first name alone is not sufficiently reliable (for example, Илья and
    Никита), and a company name must never be treated as a narrator.
    """
    if isinstance(value, Mapping):
        value = value.get("value")
    text = str(value or "").strip()
    if not text or _ORGANISATION.search(text):
        return None
    words = [word.casefold() for word in _WORDS.findall(text)]
    if len(words) < 3:
        return None
    # A role can follow the FIO (for example, "... , представитель").  Scan
    # backwards for a patronymic rather than requiring it to be the last word.
    for word in reversed(words):
        if word.endswith(("вна", "чна", "кызы")):
            return "female"
        if word.endswith(("ич", "оглы", "улы", "оглу")):
            return "male"
    return None


def narrator_gender(fields: Mapping[str, Any], state: Mapping[str, Any] | None = None) -> str | None:
    """Use the signer when known, otherwise the document's first party."""
    sources = [fields]
    if state and isinstance(state.get("fields"), Mapping):
        sources.append(state["fields"])
    for source in sources:
        for key in ("signature", "sender"):
            gender = grammatical_gender(source.get(key))
            if gender:
                return gender
    return None


def _preserve_case(source: str, replacement: str) -> str:
    if source.isupper():
        return replacement.upper()
    if source[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _replace_explicit_first_person(text: str, replacements: Mapping[str, str]) -> str:
    forms = "|".join(sorted((re.escape(word) for word in replacements), key=len, reverse=True))
    if not forms:
        return text
    # The optional words cover ordinary document phrasing such as "я ранее
    # направила" while keeping the verb tied to the explicit first person.
    pattern = re.compile(
        r"\bя(?:\s*,?\s*(?:(?:" + _MODIFIERS + r")\s+){0,4})(?P<verb>" + forms + r")\b",
        re.I,
    )

    def replace(match: re.Match[str]) -> str:
        original = match.group("verb")
        return match.group(0)[: match.start("verb") - match.start()] + _preserve_case(
            original, replacements[original.casefold()]
        )

    return pattern.sub(replace, text)


def _replace_unambiguous_elliptical_action(text: str, replacements: Mapping[str, str]) -> str:
    """Repair a subjectless self-action only where no other actor can fit.

    It handles a common factual sentence such as "Претензию ... направила
    1 сентября".  Requiring the next token to be a date or sentence end avoids
    touching "Претензию направила управляющая компания".
    """
    forms = {word: target for word, target in replacements.items()
             if word in {"направила", "направил", "подала", "подал", "подписала", "подписал", "предъявила", "предъявил"}}
    if not forms:
        return text
    alternatives = "|".join(sorted((re.escape(word) for word in forms), key=len, reverse=True))
    objects = (
        r"(?:письменн\w*\s+)?(?:претензи\w*|заявлени\w*|жалоб\w*|"
        r"ходатайств\w*|исков\w*(?:\s+заявлени\w*)?|обращени\w*)"
    )
    date_or_end = (
        r"(?=\s*(?:$|[.!?]|\d{1,2}[./]|\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)))"
    )
    pattern = re.compile(
        r"(?P<prefix>(?:^|(?<=[.!?])\s*)" + objects + r"[^.!?]{0,100}?\s)(?P<verb>" + alternatives + r")\b" + date_or_end,
        re.I,
    )

    def replace(match: re.Match[str]) -> str:
        original = match.group("verb")
        return match.group("prefix") + _preserve_case(original, forms[original.casefold()])

    return pattern.sub(replace, text)


def align_first_person_gender(text: str, gender: str | None) -> str:
    """Correct only a proven mismatch between author FIO and first person."""
    if gender == "male":
        replacements = _FEMININE_TO_MASCULINE
    elif gender == "female":
        replacements = _MASCULINE_TO_FEMININE
    else:
        return text
    revised = _replace_explicit_first_person(text, replacements)
    return _replace_unambiguous_elliptical_action(revised, replacements)


def align_narrator_gender(fields: dict[str, Any], state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Apply a safe author-agreement repair to every rendered text field.

    Callers hand in a presentation copy, so the user's original answer stays
    untouched in workflow state.  This makes the rule reusable by every
    template family and also repairs documents reopened from an older chat.
    """
    gender = narrator_gender(fields, state)
    if not gender:
        return fields
    for item in fields.values():
        if not isinstance(item, dict) or not isinstance(item.get("value"), str):
            continue
        item["value"] = align_first_person_gender(item["value"], gender)
    return fields
