from enum import Enum


class Tier(str, Enum):
    # Permissions for a user or role
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


POLICIES: dict[str, Tier] = {
    "list_drones": Tier.ALLOW,
    "summarize_flight_inspection": Tier.ALLOW,
    "book_airspace": Tier.REQUIRE_APPROVAL,
    "testing_tool": Tier.REQUIRE_APPROVAL,
    "takeoff": Tier.REQUIRE_APPROVAL
}

def get_tier_for_tool(tool_name: str) -> Tier:
    """Get the tier for a given tool name."""
    return POLICIES.get(tool_name, Tier.DENY)