from governance.policy import Tier, get_tier_for_tool

def test_read_only_tools_are_allowed() -> None:
    assert get_tier_for_tool("list_drones") == Tier.ALLOW
    assert get_tier_for_tool("summarize_flight_inspection") == Tier.ALLOW

def test_state_changing_tools_require_approval() -> None:
    assert get_tier_for_tool("set_drone_note") == Tier.REQUIRE_APPROVAL
    assert get_tier_for_tool("takeoff") == Tier.REQUIRE_APPROVAL
    assert get_tier_for_tool("testing_tool") == Tier.REQUIRE_APPROVAL

def test_unknown_tool_fails_closed() -> None:
    # Anything not in the table is denied, so forgetting to register a new
    # tool blocks it rather than silently allowing it.
    assert get_tier_for_tool("non_existent_tool") == Tier.DENY

def test_every_policy_entry_matches_a_registered_tool() -> None:
    # Guards against the table drifting from reality (e.g. an entry for a tool
    # that was never built, which reads as protection that does not exist).
    import server
    from governance.policy import POLICIES
    registered = {t.name for t in server.mcp._tool_manager.list_tools()}
    assert set(POLICIES) <= registered, f"policy lists unknown tools: {set(POLICIES) - registered}"
