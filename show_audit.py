"""Print the governance audit log and verify its hash chain.

Read-only. Exists so the log can be shown without a shell one-liner full of
escaped quotes - PowerShell mangles those, and this has to be legible on a
screen share.

    python show_audit.py
"""

from __future__ import annotations

from governance import audit


def main() -> int:
    records = audit.read_all()
    if not records:
        print("Audit log is empty.")
        return 0

    print(f"{'TIME':10} {'EVENT':10} {'TOOL':18} {'PILOT':16} REQUEST")
    print("-" * 72)
    for record in records:
        print(
            f"{record.ts:%H:%M:%S}   "
            f"{record.event.value:10} "
            f"{record.tool:18} "
            f"{record.pilot_id or '-':16} "
            f"{(record.request_id or '-')[:8]}"
        )

    intact, problem = audit.verify_chain()
    print()
    if intact:
        print(f"Hash chain verified: all {len(records)} records intact.")
    else:
        print(f"CHAIN BROKEN: {problem}")
    return 0 if intact else 1


if __name__ == "__main__":
    raise SystemExit(main())
