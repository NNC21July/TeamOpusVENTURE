"""Append-only, hash-chained audit log for governance decisions.

Every risky-tool decision (proposed, approved, denied, executed, blocked)
gets one line in governance/state/audit.jsonl. Each line's hash is computed
over its own fields PLUS the previous line's hash, chaining them together:
editing or deleting any past line changes every hash after it. verify_chain()
recomputes the chain and proves whether the log is still intact.

TLDR: A foolproof, tamper proof log of decisions made.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from governance.schemas import AuditEvent, AuditRecord

STATE_DIR = Path(__file__).parent / "state"
AUDIT_FILE = STATE_DIR / "audit.jsonl"

GENESIS_HASH = "0" * 64


def _record_to_dict(r: AuditRecord) -> dict:
    return {
        "ts": r.ts.isoformat(),
        "event": r.event.value,
        "tool": r.tool,
        "params_hash": r.params_hash,
        "request_id": r.request_id,
        "pilot_id": r.pilot_id,
        "prev_hash": r.prev_hash,
        "hash": r.hash,
    }


def _dict_to_record(d: dict) -> AuditRecord:
    return AuditRecord(
        ts=datetime.fromisoformat(d["ts"]),
        event=AuditEvent(d["event"]),
        tool=d["tool"],
        params_hash=d["params_hash"],
        request_id=d["request_id"],
        pilot_id=d["pilot_id"],
        prev_hash=d["prev_hash"],
        hash=d["hash"],
    )


def _compute_hash(
    prev_hash: str,
    ts: datetime,
    event: AuditEvent,
    tool: str,
    params_hash: str,
    request_id: str | None,
    pilot_id: str | None,
) -> str:
    """Hash everything about this record EXCEPT its own hash field."""
    payload = json.dumps(
        {
            "prev_hash": prev_hash,
            "ts": ts.isoformat(),
            "event": event.value,
            "tool": tool,
            "params_hash": params_hash,
            "request_id": request_id,
            "pilot_id": pilot_id,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _last_hash() -> str:
    if not AUDIT_FILE.exists():
        return GENESIS_HASH
    last_line = None
    with AUDIT_FILE.open("r") as f:
        for line in f:
            line = line.strip()
            if line:
                last_line = line
    if last_line is None:
        return GENESIS_HASH
    return json.loads(last_line)["hash"]


def record_event(
    event: AuditEvent,
    tool: str,
    *,
    params_hash: str,
    request_id: str | None = None,
    pilot_id: str | None = None,
) -> AuditRecord:
    """Append one event to the chain and return the record that was written."""
    STATE_DIR.mkdir(exist_ok=True)
    prev_hash = _last_hash()
    ts = datetime.now()
    record_hash = _compute_hash(prev_hash, ts, event, tool, params_hash, request_id, pilot_id)

    record = AuditRecord(
        ts=ts,
        event=event,
        tool=tool,
        params_hash=params_hash,
        request_id=request_id,
        pilot_id=pilot_id,
        prev_hash=prev_hash,
        hash=record_hash,
    )

    with AUDIT_FILE.open("a") as f:
        f.write(json.dumps(_record_to_dict(record)) + "\n")

    return record


def read_all() -> list[AuditRecord]:
    if not AUDIT_FILE.exists():
        return []
    records = []
    with AUDIT_FILE.open("r") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(_dict_to_record(json.loads(line)))
    return records


def verify_chain() -> tuple[bool, str | None]:
    """Recompute every record's hash and check the chain links.

    Returns (True, None) if the whole log is intact, or (False, reason)
    identifying the first record where the chain breaks.
    """
    records = read_all()
    expected_prev = GENESIS_HASH

    for i, record in enumerate(records):
        if record.prev_hash != expected_prev:
            return False, f"record {i} ({record.event}): prev_hash does not chain from the previous record"

        recomputed = _compute_hash(
            record.prev_hash, record.ts, record.event, record.tool,
            record.params_hash, record.request_id, record.pilot_id,
        )
        if recomputed != record.hash:
            return False, f"record {i} ({record.event}): stored hash does not match recomputed hash — record was altered"

        expected_prev = record.hash

    return True, None
