from datetime import datetime, timedelta, timezone
from tools.route_airspace_compliance.request_response_schemas import NfzRecord

SG_TIMEZONE = timezone(timedelta(hours=8))

PLANNED_START_TIME = datetime(
    2026,
    8,
    10,
    9,
    0,
    tzinfo=SG_TIMEZONE,
)

PLANNED_END_TIME = datetime(
    2026,
    8,
    10,
    10,
    0,
    tzinfo=SG_TIMEZONE,
)

ACTIVE_RESTRICTED_NFZ = NfzRecord(
    nfz_id="NFZ-001",
    name="Active Restricted Area",
    zone_type="restricted_area",
    minimum_altitude_m=0,
    maximum_altitude_m=120,
    valid_from=datetime(
        2026,
        8,
        10,
        8,
        0,
        tzinfo=SG_TIMEZONE
    ),
    valid_until=datetime(
        2026,
        8,
        10,
        12,
        0,
        tzinfo=SG_TIMEZONE
    )
)

INACTIVE_RESTRICTED_NFZ = NfzRecord(
    nfz_id="NFZ-002",
    name="Expired Restricted Area",
    zone_type="restricted_area",
    minimum_altitude_m=0,
    maximum_altitude_m=120,
    valid_from=datetime(
        2026,
        8,
        9,
        8,
        0,
        tzinfo=SG_TIMEZONE,
    ),
    valid_until=datetime(
        2026,
        8,
        9,
        12,
        0,
        tzinfo=SG_TIMEZONE,
    ),
)

HIGH_ALTITUDE_NFZ = NfzRecord(
    nfz_id="NFZ-003",
    name="High Altitude Restricted Area",
    zone_type="restricted_area",
    minimum_altitude_m=100,
    maximum_altitude_m=200,
    valid_from=datetime(
        2026,
        8,
        10,
        8,
        0,
        tzinfo=SG_TIMEZONE,
    ),
    valid_until=datetime(
        2026,
        8,
        10,
        12,
        0,
        tzinfo=SG_TIMEZONE,
    ),
)