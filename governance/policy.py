from enum import Enum


class Tier(str, Enum):
    # Permissions for a user or role
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


POLICIES: dict[str, Tier] = {
    # Read-only: safe to call freely.
    "list_drones": Tier.ALLOW,
    "summarize_flight_inspection": Tier.ALLOW,
    
    # State-changing: a pilot must approve before these run.
    "testing_tool": Tier.REQUIRE_APPROVAL,
    "set_drone_note": Tier.REQUIRE_APPROVAL,
    "takeoff": Tier.REQUIRE_APPROVAL,
}

def get_tier_for_tool(tool_name: str) -> Tier:
    """Get the tier for a given tool name."""
    return POLICIES.get(tool_name, Tier.DENY)