"""Схема анализа закона и принудительная генерация аргументов GigaChat v1."""

CONDITION_KINDS = {"role", "region", "activity", "threshold", "time", "exclusion", "other"}

LAW_ANALYSIS_RESPONSE_FORMAT = {
    "type": "json_schema",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["sufficient", "summary", "groups"],
        "properties": {
            "sufficient": {"type": "boolean"},
            "summary": {"type": "string"},
            "groups": {"type": "array",
                "description": "Альтернативные категории: достаточно одной группы. ИЛИ между группами.",
                "items": {
                "type": "object", "additionalProperties": False,
                "required": ["id", "conditions"],
                "properties": {
                    "id": {"type": "string"},
                    "conditions": {"type": "array",
                        "description": "Совместные обязательные факты одной категории: нужны ВСЕ. Каждый факт отдельно.",
                        "items": {
                        "type": "object", "additionalProperties": False,
                        "required": ["id", "kind", "requirement", "source_quote"],
                        "properties": {
                            "id": {"type": "string"},
                            "kind": {"type": "string", "enum": sorted(CONDITION_KINDS)},
                            "requirement": {"type": "string", "description": "Один независимый проверяемый факт о человеке или ситуации."},
                            "source_quote": {"type": "string"},
                        },
                    }},
                },
            }},
        },
    },
}


LAW_ANALYSIS_FUNCTION = {
    "name": "extract_law_conditions",
    "description": "Извлеки условия применимости изменения закона без данных пользователя. "
                   "Каждый независимый факт — отдельное условие; альтернативные категории — отдельные группы.",
    "parameters": LAW_ANALYSIS_RESPONSE_FORMAT["schema"],
}

# Обучающие примеры схемы: вымышленные правила, не контрольные сценарии.
LAW_ANALYSIS_FUNCTION["few_shot_examples"] = [
    {
        "request": "Новая льгота предусмотрена для самозанятых, ведущих ремонтную деятельность в городе Н.",
        "params": {
            "sufficient": True, "summary": "Новая льгота для указанной категории самозанятых",
            "groups": [{"id": "g1", "conditions": [
                {"id": "c1", "kind": "role", "requirement": "Человек является самозанятым",
                 "source_quote": "самозанятых"},
                {"id": "c2", "kind": "activity", "requirement": "Человек ведёт ремонтную деятельность",
                 "source_quote": "ведущих ремонтную деятельность"},
                {"id": "c3", "kind": "region", "requirement": "Деятельность ведётся в городе Н",
                 "source_quote": "в городе Н"},
            ]}],
        },
    },
    {
        "request": "Новая скидка полагается студентам или преподавателям. Достаточно принадлежать к любой одной категории.",
        "params": {
            "sufficient": True, "summary": "Новая скидка для двух альтернативных категорий",
            "groups": [
                {"id": "g1", "conditions": [{"id": "c1", "kind": "role",
                 "requirement": "Человек является студентом", "source_quote": "студентам"}]},
                {"id": "g2", "conditions": [{"id": "c2", "kind": "role",
                 "requirement": "Человек является преподавателем", "source_quote": "преподавателям"}]},
            ],
        },
    },
]



def build_user_match_function(condition_ids: list[str]) -> dict:
    """Схема оценок только для условий уже проверенного анализа закона."""
    return {
        "name": "assess_user_conditions",
        "description": "Оцени КАЖДОЕ переданное условие отдельно по заявлениям пользователя. "
                       "Не объединяй условия. Верни все id ровно по одному разу.",
        "parameters": {
            "type": "object", "required": ["assessments"], "additionalProperties": False,
            "properties": {"assessments": {
                "type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["id", "verdict", "fact", "evidence"],
                    "properties": {
                        "id": {"type": "string", "enum": condition_ids},
                        "verdict": {"type": "string", "enum": ["met", "not_met", "unknown"]},
                        "fact": {"type": "string"},
                        "evidence": {"type": "string"},
                    },
                },
            }},
        },
    }
