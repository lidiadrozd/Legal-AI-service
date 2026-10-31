"""Small, deterministic gates for answers that cannot be document facts.

The interview intentionally accepts ordinary Russian, so this module is not a
dictionary of "good" words.  It only detects a few structurally impossible
answers: a copied field label, a monetary appraisal in a field asking for an
object, and a legal conclusion in a field asking for a factual connection.
The same gate is used before an answer is accepted and before an older state
is rendered, so a bad saved value cannot bypass a later improvement.
"""
from __future__ import annotations

import re


def _words(text: str) -> list[str]:
    return re.findall(r"[а-яёa-z]+", (text or "").casefold().replace("ё", "е"))


def _compact(text: str) -> str:
    return "".join(_words(text))


def label_echo(value: str, label: str = "") -> bool:
    """Whether the proposed fact is only a copied UI label or placeholder."""
    candidate = _compact(value)
    expected = _compact(label)
    if not candidate:
        return True
    if expected and (candidate == expected or candidate in {"описание" + expected, "сведения" + expected}):
        return True
    return bool(re.fullmatch(r"(?:укажите|заполнить|неизвестно|нет данных|данные отсутствуют)", candidate))


def field_value_problem(key: str, value: str, label: str = "") -> str | None:
    """Return a stable machine code when a slot cannot hold this answer.

    A code rather than a boolean lets the caller give a question that explains
    what factual detail is missing.  It deliberately avoids deciding the case
    or rejecting an unusual, but possible, name or item.
    """
    text = (value or "").strip()
    normalized = " ".join(_words(text))
    if label_echo(text, label):
        return "label_echo"
    if key == "property":
        # "Независимая оценка определила стоимость ремонта 128 500" is a
        # useful amount/evidence, but does not identify what was damaged.
        value_terms = r"оценк\w*|оценщик\w*|стоимост\w*|смет\w*|расход\w*|сумм\w*|рубл\w*|восстановительн\w* ремонт\w*"
        object_terms = r"квартир\w*|комнат\w*|дом\w*|помещен\w*|автомоб\w*|машин\w*|телефон\w*|ноутбук\w*|мебел\w*|диван\w*|техник\w*|вещ\w*|товар\w*|обо\w*|пол\w*|потол\w*|стен\w*"
        if re.search(value_terms, normalized, re.I) and not re.search(object_terms, normalized, re.I):
            return "property_is_appraisal"
        if re.fullmatch(r"(?:поврежден\w*\s+)?имуществ\w*", normalized, re.I):
            return "property_is_generic"
    if key == "damage":
        # A repeated heading, an appraisal, or correspondence is not a list
        # of actual defects.  Do not require a particular object type.
        if re.fullmatch(r"(?:перечень\s+)?(?:поврежден\w*\s+)?(?:имуществ\w*|поврежден\w*)", normalized, re.I):
            return "damage_is_generic"
        if re.search(r"обращал\w*|претензи\w*|ответа\s+нет|переписк\w*", normalized, re.I) and not re.search(r"поврежден\w*|трещин\w*|скол\w*|залит\w*|намок\w*|деформ\w*|разбит\w*|неисправ\w*", normalized, re.I):
            return "damage_is_other_fact"
        if re.search(r"оценк\w*|стоимост\w*|смет\w*|рубл\w*", normalized, re.I) and not re.search(r"поврежден\w*|трещин\w*|скол\w*|залит\w*|намок\w*|деформ\w*|разбит\w*|неисправ\w*", normalized, re.I):
            return "damage_is_appraisal"
    if key == "property_right":
        # It is not a fact if it merely repeats a legal question/conclusion.
        legal_only = r"(?:какое\s+)?(?:мо[её]|ваше|нарушенн\w*|защищаем\w*)?\s*прав\w*"
        factual_relation = r"собственник\w*|собственност\w*|нанимател\w*|владел\w*|аренд\w*|договор\w*|егрн|выписк\w*|свидетельств\w*"
        if re.search(legal_only, normalized, re.I) and not re.search(factual_relation, normalized, re.I):
            return "property_right_is_legal_conclusion"
    return None


def problem_question(code: str) -> str:
    return {
        "label_echo": "В ответ попало название поля, а не факт. Укажите конкретные сведения либо сообщите, что они неизвестны.",
        "property_is_appraisal": "Оценка и сумма ущерба сохранены для расчёта, но здесь нужно назвать само повреждённое имущество: например, квартиру, комнату, вещь или технику. Что именно повреждено?",
        "property_is_generic": "Нужно конкретно назвать повреждённый объект, а не писать только «имущество». Что именно повреждено и где находится?",
        "damage_is_generic": "Нужно описать сами повреждения: какие элементы или вещи пострадали и что с ними произошло. Одного слова «повреждение» недостаточно.",
        "damage_is_other_fact": "Этот ответ относится к обращениям или переписке, а здесь нужен перечень повреждений имущества. Какие дефекты или утраты имеются?",
        "damage_is_appraisal": "Оценка относится к расчёту, а здесь нужен перечень фактических повреждений. Какие вещи, помещения или элементы пострадали?",
        "property_right_is_legal_conclusion": "Не нужно самостоятельно формулировать нарушенное право. Укажите только фактическое основание: вы собственник, наниматель или иной владелец имущества и какой документ это подтверждает.",
    }.get(code, "Уточните фактическое содержание этого поля.")
