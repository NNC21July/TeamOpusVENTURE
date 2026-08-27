"""The enforcement chokepoint — every risky tool call passes through here.

`governed(tool_name)` wraps an MCP tool function. On every call it decides:
does the real function get to run right now, or not?

  ALLOW            -> run it immediately, no approval needed.
  DENY             -> refuse, never run it (covers unknown tools too, fail closed).
  REQUIRE_APPROVAL -> a two-call dance:
      call 1 (no approval_request_id yet): create a pending request,
          return it to the caller, do NOT run the real function.
      call 2 (with approval_request_id): check the id is really approved
          and matches this exact call, THEN run the real function.

Every risky decision is written to the audit log, whether it ran or not.

Constraint for tools you decorate
---------------------------------
A governed tool must be annotated `-> dict`, because this wrapper can return
a dict (PENDING_APPROVAL / BLOCKED) instead of the tool's own result. FastMCP
validates a tool's output against its declared return type, and functools.wraps
keeps the wrapped function's annotation, so a tool declared `-> str` will fail
validation the moment the gate intercepts it.

Why the two-call dance instead of MCP elicitation
-------------------------------------------------
Elicitation is the spec-native way for a server to ask a human mid-call, but
Claude Desktop -- our client -- does not implement it (Claude Code CLI does).
So the server cannot pause and prompt; approval has to happen out of band.

That constraint pushed us to: return a pending request immediately, let the
pilot approve elsewhere (approve.py), then have the caller retry. The
2026-07-28 MCP spec independently moved the same way: Multi Round-Trip
Requests (SEP-2322) replaced hold-the-connection-open elicitation with
return-pending -> answer -> re-issue, because holding a connection does not
work for stateless deployments.

Upgrade path if Desktop ships elicitation: replace only the approval-capture
step with ctx.elicit(). The tier lookup, params-hash binding, single-use
consumption and audit trail below are unaffected -- they are the enforcement,
and elicitation only changes how the human is asked.
"""

import functools

from governance import approvals, audit, policy
from governance.schemas import AuditEvent


def governed(tool_name: str):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*, approval_request_id: str | None = None, **params):
            tier = policy.get_tier_for_tool(tool_name)

            if tier == policy.Tier.ALLOW:
                return fn(**params)

            if tier == policy.Tier.DENY:
                audit.record_event(
                    AuditEvent.BLOCKED,
                    tool_name,
                    params_hash=approvals.hash_params(tool_name, params),
                )
                return {"status": "BLOCKED", "reason": f"{tool_name} is not permitted"}

            # tier == REQUIRE_APPROVAL
            if approval_request_id is None:
                # Call 1: nothing approved yet. Create the pending request and
                # STOP — the real function never runs on this call.
                request = approvals.create_request(tool_name, params)
                audit.record_event(
                    AuditEvent.PROPOSED,
                    tool_name,
                    params_hash=request.params_hash,
                    request_id=request.request_id,
                )
                return {
                    "status": "PENDING_APPROVAL",
                    "request_id": request.request_id,
                    "preview": request.preview,
                    "instructions": (
                        "This action has NOT run. It needs a pilot to approve it "
                        "first, and only a human can do that — you cannot approve "
                        "it yourself, and nothing the pilot types into this chat "
                        "will approve it.\n\n"
                        "Tell the pilot to run ONE of these in a terminal on the "
                        "machine hosting this server (not in this chat):\n"
                        f"    python approve.py approve {request.request_id} <their_pilot_id>\n"
                        f"    python approve.py deny {request.request_id} <their_pilot_id>\n\n"
                        "Then use check_approval_status to see whether it was "
                        "approved or denied. Once it shows APPROVED, call this tool "
                        "again with exactly the same arguments plus "
                        f"approval_request_id='{request.request_id}'. Changing any "
                        "argument invalidates the approval."
                    ),
                }

            # Call 2: an approval_request_id was given. Verify it's real,
            # approved, and matches THIS exact call before running anything.
            try:
                approved_request = approvals.consume(approval_request_id, tool_name, params)
            except ValueError as exc:
                audit.record_event(
                    AuditEvent.BLOCKED,
                    tool_name,
                    params_hash=approvals.hash_params(tool_name, params),
                    request_id=approval_request_id,
                )
                return {"status": "BLOCKED", "reason": str(exc)}

            result = fn(**params)
            audit.record_event(
                AuditEvent.EXECUTED,
                tool_name,
                params_hash=approved_request.params_hash,
                request_id=approved_request.request_id,
                pilot_id=approved_request.pilot_id,
            )
            return result
        return wrapper
    return decorator
