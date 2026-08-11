import pytest

from governance import audit
from governance.schemas import AuditEvent


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    monkeypatch.setattr(audit, "STATE_DIR", state_dir)
    monkeypatch.setattr(audit, "AUDIT_FILE", state_dir / "audit.jsonl")


def test_first_record_chains_from_genesis():
    record = audit.record_event(AuditEvent.PROPOSED, "book_airspace", params_hash="abc")
    assert record.prev_hash == audit.GENESIS_HASH
    assert record.hash != audit.GENESIS_HASH


def test_records_chain_to_each_other():
    first = audit.record_event(AuditEvent.PROPOSED, "book_airspace", params_hash="abc")
    second = audit.record_event(AuditEvent.APPROVED, "book_airspace", params_hash="abc", pilot_id="pilot-1")
    assert second.prev_hash == first.hash


def test_read_all_returns_records_in_order():
    audit.record_event(AuditEvent.PROPOSED, "book_airspace", params_hash="abc")
    audit.record_event(AuditEvent.APPROVED, "book_airspace", params_hash="abc", pilot_id="pilot-1")
    audit.record_event(AuditEvent.EXECUTED, "book_airspace", params_hash="abc", pilot_id="pilot-1")

    events = [r.event for r in audit.read_all()]
    assert events == [AuditEvent.PROPOSED, AuditEvent.APPROVED, AuditEvent.EXECUTED]


def test_verify_chain_passes_on_untouched_log():
    audit.record_event(AuditEvent.PROPOSED, "book_airspace", params_hash="abc")
    audit.record_event(AuditEvent.BLOCKED, "book_airspace", params_hash="abc")

    ok, reason = audit.verify_chain()
    assert ok is True
    assert reason is None


def test_verify_chain_empty_log_is_valid():
    ok, reason = audit.verify_chain()
    assert ok is True
    assert reason is None


def test_verify_chain_detects_altered_record():
    audit.record_event(AuditEvent.PROPOSED, "book_airspace", params_hash="abc")
    audit.record_event(AuditEvent.EXECUTED, "book_airspace", params_hash="abc", pilot_id="pilot-1")

    # Tamper: rewrite the first line with a different tool name, same hash.
    lines = audit.AUDIT_FILE.read_text().splitlines()
    import json
    first = json.loads(lines[0])
    first["tool"] = "tampered_tool"
    lines[0] = json.dumps(first)
    audit.AUDIT_FILE.write_text("\n".join(lines) + "\n")

    ok, reason = audit.verify_chain()
    assert ok is False
    assert reason is not None


def test_verify_chain_detects_broken_link():
    audit.record_event(AuditEvent.PROPOSED, "book_airspace", params_hash="abc")
    audit.record_event(AuditEvent.EXECUTED, "book_airspace", params_hash="abc", pilot_id="pilot-1")

    # Tamper: delete the first line, leaving the second with a dangling prev_hash.
    lines = audit.AUDIT_FILE.read_text().splitlines()
    audit.AUDIT_FILE.write_text(lines[1] + "\n")

    ok, reason = audit.verify_chain()
    assert ok is False
    assert reason is not None
