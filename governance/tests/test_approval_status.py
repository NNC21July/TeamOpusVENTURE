"""Tests for the read-only approval-status lookup.

The point of this tool is feedback: after the pilot is told to run approve.py,
Claude needs a way to see what actually happened instead of retrying blind.
It must never be able to change a decision.
"""

import pytest

import server
from governance import approvals
from governance.schemas import RequestStatus


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    monkeypatch.setattr(approvals, "STATE_DIR", state_dir)
    monkeypatch.setattr(approvals, "REQUESTS_FILE", state_dir / "requests.json")


def test_unknown_id_returns_error_not_crash():
    result = server.check_approval_status("no-such-id")
    assert "error" in result


def test_reports_pending_before_any_decision():
    req = approvals.create_request("takeoff", {"drone": "A"})
    result = server.check_approval_status(req.request_id)
    assert result["status"] == "PENDING"
    assert result["decided_by"] is None
    assert "approve.py" in result["next_step"]


def test_reports_approved_with_the_deciding_pilot():
    req = approvals.create_request("takeoff", {"drone": "A"})
    approvals.approve(req.request_id, "pilot-1")
    result = server.check_approval_status(req.request_id)
    assert result["status"] == "APPROVED"
    assert result["decided_by"] == "pilot-1"


def test_reports_denied_and_says_do_not_retry():
    req = approvals.create_request("takeoff", {"drone": "A"})
    approvals.deny(req.request_id, "pilot-1")
    result = server.check_approval_status(req.request_id)
    assert result["status"] == "DENIED"
    assert "not retry" in result["next_step"].lower()


def test_reports_consumed_after_use():
    req = approvals.create_request("takeoff", {"drone": "A"})
    approvals.approve(req.request_id, "pilot-1")
    approvals.consume(req.request_id, "takeoff", {"drone": "A"})
    result = server.check_approval_status(req.request_id)
    assert result["status"] == "CONSUMED"


def test_checking_status_never_changes_it():
    """Reading must not approve, deny, or consume anything."""
    req = approvals.create_request("takeoff", {"drone": "A"})
    for _ in range(3):
        server.check_approval_status(req.request_id)
    assert approvals.get_request(req.request_id).status == RequestStatus.PENDING
