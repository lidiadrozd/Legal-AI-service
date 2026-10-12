"""Проверка покрытия вручную размеченных признаков; не юридический арбитр."""


def check_law_coverage(analysis: dict | None, expected: dict | None) -> dict:
    if expected is None:
        return {"state": "not_annotated", "passed": None}
    if analysis is None:
        return {"state": "missing_analysis", "passed": False}
    if analysis.get("sufficient") != expected["sufficient"]:
        return {"state": "wrong_sufficiency", "passed": False}
    if not expected["sufficient"]:
        return {"state": "checked", "passed": not analysis.get("groups")}

    def matches(condition, criterion):
        requirement = " ".join(condition.get("requirement", "").casefold().split())
        quote = " ".join(condition.get("source_quote", "").casefold().split())
        return (condition.get("kind") == criterion["kind"]
                and all(term.casefold() in quote for term in criterion["source_contains"])
                and any(term.casefold() in requirement for term in criterion["requirement_any"]))

    def group_matches(group, criteria):
        conditions = group.get("conditions", [])
        if len(conditions) != len(criteria):
            return False
        # Ожидаемые признаки должны покрываться разными условиями.
        def assign(index, used):
            if index == len(criteria):
                return True
            return any(assign(index + 1, used | {j}) for j, condition in enumerate(conditions)
                       if j not in used and matches(condition, criteria[index]))
        return assign(0, set())

    groups = analysis.get("groups", [])
    expected_groups = expected["groups"]
    if len(groups) != len(expected_groups):
        return {"state": "wrong_group_count", "passed": False}

    def assign_groups(index, used):
        if index == len(expected_groups):
            return True
        return any(assign_groups(index + 1, used | {j}) for j, group in enumerate(groups)
                   if j not in used and group_matches(group, expected_groups[index]))

    passed = assign_groups(0, set())
    return {"state": "checked" if passed else "missing_or_extra_conditions", "passed": passed}
