from tools.route_airspace_compliance.decision_types import CheckResult, OverallDecision


def test_overall_decision_values() -> None:
    assert OverallDecision.PASS.value == "PASS"
    assert OverallDecision.PASS_WITH_WARNINGS.value == "PASS_WITH_WARNINGS"
    assert OverallDecision.BLOCK.value == "BLOCK"
    assert OverallDecision.NEEDS_INFO.value == "NEEDS_INFO"
    assert OverallDecision.UNKNOWN.value == "UNKNOWN"


def test_check_result_values() -> None:
    assert CheckResult.CLEAR.value == "CLEAR"
    assert CheckResult.WARNING.value == "WARNING"
    assert CheckResult.VIOLATION.value == "VIOLATION"
    assert CheckResult.UNAVAILABLE.value == "UNAVAILABLE"
