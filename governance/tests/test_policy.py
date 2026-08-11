from governance.policy import Tier, get_tier_for_tool

def test_testing_tool_policy() -> None:
    tier = get_tier_for_tool("list_drones")
    assert tier == "ALLOW"
    tier = get_tier_for_tool("book_airspace")
    assert tier == "REQUIRE_APPROVAL"
    tier = get_tier_for_tool("testing_tool")
    assert tier == "REQUIRE_APPROVAL"
    tier = get_tier_for_tool("non_existent_tool")
    assert tier == "DENY"
