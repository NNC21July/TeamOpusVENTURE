"""Every registered MCP tool must appear in the policy table.

The table is the readable answer to "what is this server allowed to do?", so a
tool missing from it is a gap in that answer even when the tool is harmless.
This test fails when someone registers a tool without declaring its tier, which
is the moment to decide whether it needs approval - not later.

Note what this does NOT prove: the table is only consulted for tools wrapped in
@governed. An undecorated tool never reaches get_tier_for_tool, so listing it
here documents the intent rather than enforcing it.
"""

import server
from governance import policy


def _registered_tool_names() -> set[str]:
    return set(server.mcp._tool_manager._tools)


def test_every_registered_tool_has_a_policy_entry():
    undeclared = _registered_tool_names() - set(policy.POLICIES)
    assert not undeclared, (
        f"registered but missing from POLICIES: {sorted(undeclared)}. "
        "Add each to governance/policy.py with the tier it should run at."
    )


def test_policy_table_has_no_entries_for_tools_that_no_longer_exist():
    stale = set(policy.POLICIES) - _registered_tool_names()
    assert not stale, f"in POLICIES but not registered: {sorted(stale)}"
