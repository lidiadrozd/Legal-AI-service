"""Literal rouble amounts with whole numeric groups and source offsets."""
import re


THOUSANDS_SEPARATORS = " \u00a0\u202f\u2009"
MONEY_START = r"(?<![\w/№.,+\-\u2212])(?<!\d\s)"
MONEY_INTEGER = r"(?:\d{1,3}(?:[ \u00a0\u202f\u2009]\d{3})+|\d+)"
MONEY_PATTERN = (
    MONEY_START + MONEY_INTEGER + r"(?:[.,]\d{1,2})?\s*"
    r"(?:тыс\.?|тысяч(?:а|и)?|млн\.?)?\s*(?:руб(?:лей|ля|ль|\.)?|₽)(?!\w)"
)
_MONEY = re.compile(MONEY_PATTERN, re.I)


def money_token_starts_here(text: str, start: int) -> bool:
    # A malformed grouped number must not become its valid-looking suffix.
    # Include invalid separators here only to reject them, never to normalize.
    prefix = text[:start].rstrip(THOUSANDS_SEPARATORS + "\t\r\n\u200b")
    return not prefix or (not prefix[-1].isdigit() and prefix[-1] not in '+-\u2212')


def find_money_quotes(text: str) -> list[str]:
    return [match[0] for match in _MONEY.finditer(text)
            if money_token_starts_here(text, match.start())]
