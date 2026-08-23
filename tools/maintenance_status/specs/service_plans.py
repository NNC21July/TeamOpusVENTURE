"""Local service plan table.

Garuda Plex exposes no maintenance endpoint. The API client covers three
services — Aircraft/Fleet, Media and Geo AI — and none of them carries service
records, so there is nowhere to read an interval from.

This table supplies the interval so the tool can still return a real verdict
from real flight hours. It is the same fallback pattern the readiness tool uses
in specs/model_limits.py: known model gets locally-sourced values with the
assumption recorded, unknown model gets nothing and the caller returns
NEEDS_INFO rather than guessing.

PLACEHOLDER VALUES from general small-UAS practice. Replace with Garuda's own
maintenance schedule as soon as it is available — and if a manual servicing
checklist already exists, that checklist is the specification.
"""

from dataclasses import dataclass

# A drone this close to its interval is DUE_SOON rather than OK. Expressed as
# a fraction of the interval so it scales with the airframe.
WARNING_BAND_FRACTION = 0.10


@dataclass(frozen=True)
class ServicePlan:
    # None means the plan does not state it. Never substitute a permissive
    # default: an unknown interval must surface as NEEDS_INFO.
    model: str
    interval_hours: float | None = None
    interval_months: int | None = None


SERVICE_PLANS: dict[str, ServicePlan] = {
    "matrice 4": ServicePlan(
        model="Matrice 4", interval_hours=200.0, interval_months=6
    ),
    "matrice 350 rtk": ServicePlan(
        model="Matrice 350 RTK", interval_hours=200.0, interval_months=6
    ),
    "mavic 3 enterprise": ServicePlan(
        model="Mavic 3 Enterprise", interval_hours=150.0, interval_months=6
    ),
}


def get_service_plan(model: str | None) -> ServicePlan | None:
    """Look up a service plan by model name, or None if the model is unknown.

    Returning None is meaningful: an unknown airframe has no plan on record,
    which is NEEDS_INFO, not "no servicing required".
    """
    if not model or not model.strip():
        return None
    return SERVICE_PLANS.get(model.strip().casefold())


def warning_band_hours(interval_hours: float) -> float:
    """Hours before the interval at which status becomes DUE_SOON."""
    return interval_hours * WARNING_BAND_FRACTION
