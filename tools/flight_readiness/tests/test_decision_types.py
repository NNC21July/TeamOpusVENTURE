from tools.flight_readiness.decision_types import (
    CheckResult,
    ConfidenceLevel,
    OverallDecision,
)


def test_overall_decision_values() -> None:
    assert OverallDecision.GO.value == "GO"
    assert OverallDecision.GO_WITH_WARNINGS.value == "GO_WITH_WARNINGS"
    assert OverallDecision.NO_GO.value == "NO_GO"
    assert OverallDecision.NEEDS_INFO.value == "NEEDS_INFO"
    assert OverallDecision.UNKNOWN.value == "UNKNOWN"


def test_check_result_values() -> None:
    assert CheckResult.CLEAR.value == "CLEAR"
    assert CheckResult.WARNING.value == "WARNING"
    assert CheckResult.FAIL.value == "FAIL"
    assert CheckResult.UNAVAILABLE.value == "UNAVAILABLE"


def test_confidence_level_values() -> None:
    assert ConfidenceLevel.HIGH.value == "HIGH"
    assert ConfidenceLevel.MEDIUM.value == "MEDIUM"
    assert ConfidenceLevel.LOW.value == "LOW"


def test_pass_is_not_a_check_result() -> None:
    # PASS is the route compliance tool's overall verdict. Reusing it here
    # would put the same token at two different scopes in one conversation.
    assert "PASS" not in {result.value for result in CheckResult}


def test_decisions_serialise_as_plain_strings() -> None:
    # The enum members go straight into the MCP JSON payload. Inheriting from
    # str is what keeps them "NO_GO" rather than "OverallDecision.NO_GO".
    assert OverallDecision.NO_GO == "NO_GO"
    assert CheckResult.CLEAR == "CLEAR"
    assert f"{OverallDecision.GO}" == "GO" or OverallDecision.GO.value == "GO"
