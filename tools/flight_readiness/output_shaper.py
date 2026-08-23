"""Shape the response for the model.

This is the per-tool trim stage of the governance read path:

    API client -> clean and mask -> per-tool trim -> model

Output is shaped, not raw. A drone record in Plex nests its full model
specification; only the fields that answer the question are returned. Empty
collections are dropped so the model is not handed a wall of empty lists.
"""

from datetime import date, datetime

from tools.flight_readiness.request_response_schemas import (
    CheckDetail,
    Confidence,
    FlightReadinessResponse,
)


def shape_flight_readiness_response(response: FlightReadinessResponse) -> dict:
    shaped: dict[str, object] = {"decision": response.decision.value}

    if response.confidence is not None:
        shaped["confidence"] = _shape_confidence(response.confidence)

    if response.checks:
        shaped["checks"] = [_shape_check(check) for check in response.checks]

    for key, values in (
        ("blocking_factors", response.blocking_factors),
        ("warnings", response.warnings),
        ("missing_inputs", response.missing_inputs),
        ("assumptions", response.assumptions),
        ("recommended_actions", response.recommended_actions),
    ):
        if values:
            shaped[key] = list(values)

    if response.data_checked_at is not None:
        shaped["data_checked_at"] = response.data_checked_at.isoformat()

    return shaped


def _shape_confidence(confidence: Confidence) -> dict:
    shaped: dict[str, object] = {"level": confidence.level.value}
    if confidence.reasons:
        shaped["reasons"] = list(confidence.reasons)
    if confidence.recommended_recheck is not None:
        shaped["recommended_recheck"] = confidence.recommended_recheck.isoformat()
    return shaped


def _shape_check(check: CheckDetail) -> dict:
    shaped: dict[str, object] = {
        "check_id": check.check_id,
        "category": check.category,
        "result": check.result.value,
    }
    if check.observed:
        shaped["observed"] = _clean(check.observed)
    if check.threshold:
        shaped["threshold"] = _clean(check.threshold)
    if check.source:
        shaped["source"] = check.source
    if check.message:
        shaped["message"] = check.message
    return shaped


def _clean(values: dict[str, object]) -> dict[str, object]:
    """Drop keys whose value is None and make dates JSON-safe.

    A None threshold tells the model nothing; omitting it keeps the payload to
    the numbers the verdict was actually reached from.
    """
    cleaned: dict[str, object] = {}
    for key, value in values.items():
        if value is None:
            continue
        if isinstance(value, (datetime, date)):
            cleaned[key] = value.isoformat()
        elif isinstance(value, float):
            cleaned[key] = round(value, 3)
        else:
            cleaned[key] = value
    return cleaned
