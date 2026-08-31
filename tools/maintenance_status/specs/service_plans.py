"""Local service plan table — the FALLBACK, not the primary source.

Plex does expose maintenance plans at GET /aircraft/maintenance-plans, and the
client reads them first. This table only answers when that endpoint has no plan
for the drone, which keeps the tool useful rather than returning NEEDS_INFO the
moment the sandbox has no plan configured.

Same pattern as the readiness tool's specs/model_limits.py: a known model gets
locally-sourced values with the assumption recorded, an unknown model gets
nothing and the caller returns NEEDS_INFO rather than inventing an interval.

PLACEHOLDER VALUES from general small-UAS practice. The shared tool contract's
worked example uses a 100-hour interval, which is the figure to expect from a
real plan. If Garuda has a servicing schedule or a manual checklist, that is
the specification and it replaces this table wholesale.
"""

from tools.maintenance_status.request_response_schemas import ServicePlan

# A drone this close to its interval is DUE_SOON rather than OK. Expressed as
# a fraction of the interval so it scales with the airframe.
WARNING_BAND_FRACTION = 0.10

LOCAL_SOURCE = "local_specs_table"

SERVICE_PLANS: dict[str, ServicePlan] = {
    # --- models actually present in the NTU sandbox fleet --------------------
    # Verified live: /aircraft/maintenance-plans returns zero records, so Plex
    # has no plan for any of these and the tool falls through to here. Without
    # these entries every real drone returns NEEDS_INFO.
    "cerana one pro": ServicePlan(
        model="Cerana ONE Pro",
        interval_hours=100.0,
        interval_months=6,
        source=LOCAL_SOURCE,
    ),
    "garuda robotics v220": ServicePlan(
        model="Garuda Robotics V220",
        interval_hours=100.0,
        interval_months=6,
        source=LOCAL_SOURCE,
    ),
    # --- speculative entries, kept for models not in this sandbox -----------
    "matrice 4": ServicePlan(
        model="Matrice 4",
        interval_hours=200.0,
        interval_months=6,
        source=LOCAL_SOURCE,
    ),
    "matrice 350 rtk": ServicePlan(
        model="Matrice 350 RTK",
        interval_hours=200.0,
        interval_months=6,
        source=LOCAL_SOURCE,
    ),
    "mavic 3 enterprise": ServicePlan(
        model="Mavic 3 Enterprise",
        interval_hours=150.0,
        interval_months=6,
        source=LOCAL_SOURCE,
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
