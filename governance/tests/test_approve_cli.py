"""Tests for approve.py's id resolution.

Short ids are a convenience, but this sits on the security path: resolving a
prefix to the WRONG request would approve an action the pilot never saw. So
ambiguity and unknown prefixes must raise, never guess.
"""

import pytest

import approve
from governance import approvals


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    monkeypatch.setattr(approvals, "STATE_DIR", state_dir)
    monkeypatch.setattr(approvals, "REQUESTS_FILE", state_dir / "requests.json")


def test_resolves_a_unique_prefix():
    req = approvals.create_request("takeoff", {"drone": "A"})
    assert approve._resolve_id(req.request_id[:8]) == req.request_id


def test_full_id_still_works():
    req = approvals.create_request("takeoff", {"drone": "A"})
    assert approve._resolve_id(req.request_id) == req.request_id


def test_unknown_prefix_raises():
    approvals.create_request("takeoff", {"drone": "A"})
    with pytest.raises(ValueError, match="No request"):
        approve._resolve_id("zzzzzzzz")


def test_ambiguous_prefix_raises_rather_than_guessing():
    """An empty prefix matches everything - it must refuse, not pick one."""
    approvals.create_request("takeoff", {"drone": "A"})
    approvals.create_request("takeoff", {"drone": "B"})
    with pytest.raises(ValueError, match="use more characters"):
        approve._resolve_id("")


def test_resolution_does_not_approve_anything():
    """Resolving an id must not change state."""
    req = approvals.create_request("takeoff", {"drone": "A"})
    approve._resolve_id(req.request_id[:8])
    assert approvals.get_request(req.request_id).status.value == "PENDING"
