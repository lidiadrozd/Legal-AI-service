import copy

from law_evaluation_coverage import check_law_coverage

EXPECTED = {"sufficient": True, "groups": [[
    {"kind": "role", "source_contains": ["owner"], "requirement_any": ["owner"]},
    {"kind": "threshold", "source_contains": ["ten"], "requirement_any": ["ten"]}]]}
ANALYSIS = {"sufficient": True, "groups": [{"conditions": [
    {"kind": "role", "source_quote": "owner", "requirement": "owner"},
    {"kind": "threshold", "source_quote": "ten", "requirement": "ten workers"}]}]}


def test_complete_conditions_pass_regardless_of_order():
    analysis = copy.deepcopy(ANALYSIS)
    analysis["groups"][0]["conditions"].reverse()
    assert check_law_coverage(analysis, EXPECTED)["passed"]


def test_merged_condition_does_not_hide_missing_role():
    analysis = copy.deepcopy(ANALYSIS)
    analysis["groups"][0]["conditions"] = [
        {"kind": "threshold", "source_quote": "owner ten", "requirement": "owner ten workers"}]
    assert not check_law_coverage(analysis, EXPECTED)["passed"]


def test_missing_alternative_group_is_detected():
    expected = copy.deepcopy(EXPECTED)
    expected["groups"].append(expected["groups"][0])
    assert check_law_coverage(ANALYSIS, expected)["state"] == "wrong_group_count"


def test_wrong_kind_and_extra_conditions_are_detected():
    analysis = copy.deepcopy(ANALYSIS)
    analysis["groups"][0]["conditions"][0]["kind"] = "activity"
    assert not check_law_coverage(analysis, EXPECTED)["passed"]
    analysis = copy.deepcopy(ANALYSIS)
    analysis["groups"][0]["conditions"].append(analysis["groups"][0]["conditions"][0])
    assert not check_law_coverage(analysis, EXPECTED)["passed"]


def test_missing_analysis_and_insufficient_text():
    assert not check_law_coverage(None, EXPECTED)["passed"]
    assert check_law_coverage({"sufficient": False, "groups": []},
                              {"sufficient": False, "groups": []})["passed"]
