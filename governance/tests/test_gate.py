import pytest

from governance import approvals, audit, gate, policy
from governance.schemas import AuditEvent


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Redirect the approvals store AND the audit log to a throwaway directory
    for every test, so tests never touch real state or leak into each other."""
    state_dir = tmp_path / "state"
    monkeypatch.setattr(approvals, "STATE_DIR", state_dir)
    monkeypatch.setattr(approvals, "REQUESTS_FILE", state_dir / "requests.json")
    monkeypatch.setattr(audit, "STATE_DIR", state_dir)
    monkeypatch.setattr(audit, "AUDIT_FILE", state_dir / "audit.jsonl")


@pytest.fixture
def call_log():
    """Records every time the real (wrapped) function actually ran."""
    return []


@pytest.fixture
def fake_tool(call_log):
    @gate.governed("fake_tool")
    def _fake_tool(value: str, approval_request_id: str | None = None) -> str:
        call_log.append(value)
        return f"did {value}"
    return _fake_tool


def test_allow_tier_runs_immediately(monkeypatch, fake_tool, call_log):
    monkeypatch.setitem(policy.POLICIES, "fake_tool", policy.Tier.ALLOW)

    result = fake_tool(value="x")

    assert result == "did x"
    assert call_log == ["x"]


def test_deny_tier_never_runs(monkeypatch, fake_tool, call_log):
    monkeypatch.setitem(policy.POLICIES, "fake_tool", policy.Tier.DENY)

    result = fake_tool(value="x")

    assert result["status"] == "BLOCKED"
    assert call_log == []


def test_unknown_tool_fails_closed(call_log):
    @gate.governed("never_registered_tool")
    def _unregistered(value: str, approval_request_id: str | None = None) -> str:
        call_log.append(value)
        return f"did {value}"

    result = _unregistered(value="x")

    assert result["status"] == "BLOCKED"
    assert call_log == []


def test_require_approval_first_call_is_pending_and_does_not_run(monkeypatch, fake_tool, call_log):
    monkeypatch.setitem(policy.POLICIES, "fake_tool", policy.Tier.REQUIRE_APPROVAL)

    result = fake_tool(value="x")

    assert result["status"] == "PENDING_APPROVAL"
    assert "request_id" in result
    assert call_log == []


def test_require_approval_runs_exactly_once_after_approval(monkeypatch, fake_tool, call_log):
    monkeypatch.setitem(policy.POLICIES, "fake_tool", policy.Tier.REQUIRE_APPROVAL)

    pending = fake_tool(value="x")
    request_id = pending["request_id"]
    approvals.approve(request_id, pilot_id="pilot-1")

    result = fake_tool(value="x", approval_request_id=request_id)
    assert result == "did x"
    assert call_log == ["x"]

    # Retrying the same (now-consumed) approval must NOT run it a second time.
    second = fake_tool(value="x", approval_request_id=request_id)
    assert second["status"] == "BLOCKED"
    assert call_log == ["x"]


def test_require_approval_blocks_without_approval(monkeypatch, fake_tool, call_log):
    monkeypatch.setitem(policy.POLICIES, "fake_tool", policy.Tier.REQUIRE_APPROVAL)

    fake_tool(value="x")  # creates the pending request, never approved

    result = fake_tool(value="x", approval_request_id="not-a-real-id")
    assert result["status"] == "BLOCKED"
    assert call_log == []


def test_executed_call_is_audited_with_approving_pilot(monkeypatch, fake_tool, call_log):
    monkeypatch.setitem(policy.POLICIES, "fake_tool", policy.Tier.REQUIRE_APPROVAL)

    pending = fake_tool(value="x")
    request_id = pending["request_id"]
    approvals.approve(request_id, pilot_id="pilot-1")
    fake_tool(value="x", approval_request_id=request_id)

    records = audit.read_all()
    events = [r.event for r in records]
    assert events == [AuditEvent.PROPOSED, AuditEvent.EXECUTED]
    assert records[-1].pilot_id == "pilot-1"


# --- Outcome recording -------------------------------------------------------
# A governed tool that fails must not leave an EXECUTED record behind. The log
# is the only evidence of what really happened to the fleet, and a false
# EXECUTED is worse than no record at all.

@pytest.fixture
def failing_tool():
    """A tool that reports failure the way this server's tools do: by
    returning {"error": ...} rather than raising."""
    @gate.governed("fake_tool")
    def _failing_tool(value: str, approval_request_id: str | None = None) -> dict:
        return {"error": "arm returned 404"}
    return _failing_tool


@pytest.fixture
def raising_tool():
    @gate.governed("fake_tool")
    def _raising_tool(value: str, approval_request_id: str | None = None) -> dict:
        raise RuntimeError("network died")
    return _raising_tool


def _approved_id(tool_name: str, params: dict) -> str:
    request = approvals.create_request(tool_name, params)
    approvals.approve(request.request_id, "test-pilot")
    return request.request_id


def _events() -> list[AuditEvent]:
    return [record.event for record in audit.read_all()]


def test_error_return_is_recorded_as_failed_not_executed(monkeypatch, failing_tool):
    monkeypatch.setitem(policy.POLICIES, "fake_tool", policy.Tier.REQUIRE_APPROVAL)
    request_id = _approved_id("fake_tool", {"value": "x"})

    result = failing_tool(value="x", approval_request_id=request_id)

    assert "error" in result
    assert AuditEvent.FAILED in _events()
    assert AuditEvent.EXECUTED not in _events()


def test_raising_tool_is_recorded_as_failed_and_reraises(monkeypatch, raising_tool):
    monkeypatch.setitem(policy.POLICIES, "fake_tool", policy.Tier.REQUIRE_APPROVAL)
    request_id = _approved_id("fake_tool", {"value": "x"})

    with pytest.raises(RuntimeError):
        raising_tool(value="x", approval_request_id=request_id)

    assert AuditEvent.FAILED in _events()
    assert AuditEvent.EXECUTED not in _events()


def test_successful_tool_still_records_executed(monkeypatch, fake_tool):
    monkeypatch.setitem(policy.POLICIES, "fake_tool", policy.Tier.REQUIRE_APPROVAL)
    request_id = _approved_id("fake_tool", {"value": "x"})

    fake_tool(value="x", approval_request_id=request_id)

    assert AuditEvent.EXECUTED in _events()
    assert AuditEvent.FAILED not in _events()


def test_failed_call_still_consumes_the_approval(monkeypatch, failing_tool):
    """Single-use is a security property. A failed attempt still spends the
    approval - the pilot must consciously approve a retry."""
    monkeypatch.setitem(policy.POLICIES, "fake_tool", policy.Tier.REQUIRE_APPROVAL)
    request_id = _approved_id("fake_tool", {"value": "x"})

    failing_tool(value="x", approval_request_id=request_id)
    retry = failing_tool(value="x", approval_request_id=request_id)

    assert retry["status"] == "BLOCKED"
    assert "CONSUMED" in retry["reason"]


def test_failed_record_keeps_the_chain_verifiable(monkeypatch, failing_tool):
    monkeypatch.setitem(policy.POLICIES, "fake_tool", policy.Tier.REQUIRE_APPROVAL)
    request_id = _approved_id("fake_tool", {"value": "x"})

    failing_tool(value="x", approval_request_id=request_id)

    assert audit.verify_chain() == (True, None)
