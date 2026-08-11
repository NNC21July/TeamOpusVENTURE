import pytest

from governance import approvals
from governance.schemas import RequestStatus


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Point the approvals store at a throwaway directory for every test,
    so tests never touch the real governance/state/requests.json and never
    leak state between tests."""
    state_dir = tmp_path / "state"
    monkeypatch.setattr(approvals, "STATE_DIR", state_dir)
    monkeypatch.setattr(approvals, "REQUESTS_FILE", state_dir / "requests.json")


def test_create_request_is_pending():
    request = approvals.create_request("book_airspace", {"zone": "A"})
    assert request.status == RequestStatus.PENDING
    assert request.pilot_id is None
    assert request.decided_at is None


def test_create_request_dedupes_identical_pending_calls():
    first = approvals.create_request("book_airspace", {"zone": "A"})
    second = approvals.create_request("book_airspace", {"zone": "A"})
    assert first.request_id == second.request_id


def test_create_request_does_not_dedupe_different_params():
    first = approvals.create_request("book_airspace", {"zone": "A"})
    second = approvals.create_request("book_airspace", {"zone": "B"})
    assert first.request_id != second.request_id


def test_approve_records_pilot_and_persists():
    request = approvals.create_request("book_airspace", {"zone": "A"})
    approvals.approve(request.request_id, pilot_id="pilot-1")

    stored = approvals._load_requests()[request.request_id]
    assert stored.status == RequestStatus.APPROVED
    assert stored.pilot_id == "pilot-1"
    assert stored.decided_at is not None


def test_approve_rejects_unknown_request_id():
    with pytest.raises(ValueError):
        approvals.approve("does-not-exist", pilot_id="pilot-1")


def test_deny_blocks_future_approval():
    request = approvals.create_request("book_airspace", {"zone": "A"})
    approvals.deny(request.request_id, pilot_id="pilot-1")

    with pytest.raises(ValueError):
        approvals.approve(request.request_id, pilot_id="pilot-2")


def test_consume_rejects_unapproved_request():
    request = approvals.create_request("book_airspace", {"zone": "A"})

    with pytest.raises(ValueError):
        approvals.consume(request.request_id, "book_airspace", {"zone": "A"})


def test_consume_rejects_mismatched_params():
    request = approvals.create_request("book_airspace", {"zone": "A"})
    approvals.approve(request.request_id, pilot_id="pilot-1")

    with pytest.raises(ValueError):
        approvals.consume(request.request_id, "book_airspace", {"zone": "B"})


def test_approve_then_consume_succeeds_exactly_once():
    request = approvals.create_request("book_airspace", {"zone": "A"})
    approvals.approve(request.request_id, pilot_id="pilot-1")

    approvals.consume(request.request_id, "book_airspace", {"zone": "A"})

    with pytest.raises(ValueError):
        approvals.consume(request.request_id, "book_airspace", {"zone": "A"})


def test_state_persists_across_separate_loads():
    """Simulates two processes (server + CLI) touching the same file."""
    request = approvals.create_request("book_airspace", {"zone": "A"})
    approvals.approve(request.request_id, pilot_id="pilot-1")

    reloaded = approvals._load_requests()[request.request_id]
    assert reloaded.status == RequestStatus.APPROVED
    assert reloaded.pilot_id == "pilot-1"
