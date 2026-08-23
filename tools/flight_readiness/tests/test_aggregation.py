from datetime import datetime, timedelta, timezone

from tools.flight_readiness.aggregation import (
    aggregate_decision,
    apply_confidence,
    collect_blocking_factors,
    collect_warnings,
    derive_confidence,
)
from tools.flight_readiness.decision_types import (
    CheckResult,
    ConfidenceLevel,
    OverallDecision,
)
from tools.flight_readiness.request_response_schemas import CheckDetail, Confidence
from tools.flight_readiness.tests.fixtures import battery_states as bat
from tools.flight_readiness.tests.fixtures import maintenance_records as mnt

SG = timezone(timedelta(hours=8))
NOW = datetime(2026, 8, 25, 8, 0, tzinfo=SG)


def check(result: CheckResult, message: str = "msg") -> CheckDetail:
    return CheckDetail(
        check_id="X-001", category="test", result=result, message=message
    )


# --- decision aggregation ---------------------------------------------------


def test_all_clear_is_go() -> None:
    checks = (check(CheckResult.CLEAR), check(CheckResult.CLEAR))
    assert aggregate_decision(checks) is OverallDecision.GO


def test_any_warning_is_go_with_warnings() -> None:
    checks = (check(CheckResult.CLEAR), check(CheckResult.WARNING))
    assert aggregate_decision(checks) is OverallDecision.GO_WITH_WARNINGS


def test_any_fail_is_no_go() -> None:
    checks = (check(CheckResult.CLEAR), check(CheckResult.FAIL))
    assert aggregate_decision(checks) is OverallDecision.NO_GO


def test_any_unavailable_is_unknown() -> None:
    checks = (check(CheckResult.CLEAR), check(CheckResult.UNAVAILABLE))
    assert aggregate_decision(checks) is OverallDecision.UNKNOWN


def test_no_go_outranks_unknown() -> None:
    # The precedence test. Weather source down, battery definitively short:
    # enough is known to refuse. Absence of a verdict is never approval.
    checks = (check(CheckResult.UNAVAILABLE), check(CheckResult.FAIL))
    assert aggregate_decision(checks) is OverallDecision.NO_GO


def test_fail_outranks_warning() -> None:
    checks = (check(CheckResult.WARNING), check(CheckResult.FAIL))
    assert aggregate_decision(checks) is OverallDecision.NO_GO


def test_unavailable_outranks_warning() -> None:
    checks = (check(CheckResult.WARNING), check(CheckResult.UNAVAILABLE))
    assert aggregate_decision(checks) is OverallDecision.UNKNOWN


def test_no_checks_is_unknown() -> None:
    assert aggregate_decision(()) is OverallDecision.UNKNOWN


# --- confidence downgrade ---------------------------------------------------


def test_low_confidence_downgrades_go() -> None:
    low = Confidence(level=ConfidenceLevel.LOW)
    assert apply_confidence(OverallDecision.GO, low) is OverallDecision.GO_WITH_WARNINGS


def test_low_confidence_never_softens_no_go() -> None:
    low = Confidence(level=ConfidenceLevel.LOW)
    assert apply_confidence(OverallDecision.NO_GO, low) is OverallDecision.NO_GO


def test_high_confidence_leaves_go_alone() -> None:
    high = Confidence(level=ConfidenceLevel.HIGH)
    assert apply_confidence(OverallDecision.GO, high) is OverallDecision.GO


def test_confidence_never_upgrades() -> None:
    high = Confidence(level=ConfidenceLevel.HIGH)
    assert (
        apply_confidence(OverallDecision.GO_WITH_WARNINGS, high)
        is OverallDecision.GO_WITH_WARNINGS
    )
    assert apply_confidence(OverallDecision.UNKNOWN, high) is OverallDecision.UNKNOWN


# --- confidence derivation --------------------------------------------------


def test_imminent_flight_is_high_confidence() -> None:
    confidence = derive_confidence(
        now=NOW, planned_start_time=NOW + timedelta(minutes=30)
    )
    assert confidence.level is ConfidenceLevel.HIGH


def test_two_days_out_is_medium() -> None:
    confidence = derive_confidence(now=NOW, planned_start_time=NOW + timedelta(days=2))
    assert confidence.level is ConfidenceLevel.MEDIUM


def test_six_days_out_is_low() -> None:
    confidence = derive_confidence(now=NOW, planned_start_time=NOW + timedelta(days=6))
    assert confidence.level is ConfidenceLevel.LOW
    assert confidence.reasons


def test_six_days_out_all_clear_downgrades_to_go_with_warnings() -> None:
    # Resolves the contradiction between the Research 2 rules and its test
    # table: the rule wins. A week-out forecast never reads as a clean GO.
    checks = (check(CheckResult.CLEAR), check(CheckResult.CLEAR))
    confidence = derive_confidence(now=NOW, planned_start_time=NOW + timedelta(days=6))
    decision = apply_confidence(aggregate_decision(checks), confidence)
    assert decision is OverallDecision.GO_WITH_WARNINGS


def test_stale_battery_lowers_confidence() -> None:
    confidence = derive_confidence(
        now=NOW,
        planned_start_time=NOW + timedelta(minutes=30),
        battery=bat.STALE,
    )
    assert confidence.level is ConfidenceLevel.MEDIUM
    assert any("Battery state" in reason for reason in confidence.reasons)


def test_stale_maintenance_lowers_confidence() -> None:
    confidence = derive_confidence(
        now=NOW,
        planned_start_time=NOW + timedelta(minutes=30),
        maintenance=mnt.STALE_RECORD,
    )
    assert confidence.level is ConfidenceLevel.MEDIUM


def test_derived_mission_duration_lowers_confidence() -> None:
    confidence = derive_confidence(
        now=NOW,
        planned_start_time=NOW + timedelta(minutes=30),
        mission_duration_derived=True,
    )
    assert confidence.level is ConfidenceLevel.MEDIUM


def test_takes_the_weakest_factor() -> None:
    # Horizon says LOW, freshness says MEDIUM. The weakest wins.
    confidence = derive_confidence(
        now=NOW,
        planned_start_time=NOW + timedelta(days=6),
        battery=bat.STALE,
    )
    assert confidence.level is ConfidenceLevel.LOW


def test_recheck_recommended_when_not_high_confidence() -> None:
    confidence = derive_confidence(now=NOW, planned_start_time=NOW + timedelta(days=6))
    assert confidence.recommended_recheck is not None
    assert NOW < confidence.recommended_recheck < NOW + timedelta(days=6)


# --- message collection -----------------------------------------------------


def test_blocking_factors_come_from_failures_only() -> None:
    checks = (
        check(CheckResult.FAIL, "wind too high"),
        check(CheckResult.WARNING, "battery thin"),
        check(CheckResult.CLEAR, "all good"),
    )
    assert collect_blocking_factors(checks) == ("wind too high",)


def test_warnings_include_unavailable() -> None:
    checks = (
        check(CheckResult.WARNING, "battery thin"),
        check(CheckResult.UNAVAILABLE, "weather source down"),
        check(CheckResult.CLEAR, "all good"),
    )
    assert collect_warnings(checks) == ("battery thin", "weather source down")
