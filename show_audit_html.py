"""Render the governance audit log to a standalone HTML file.

Read-only. Same data as show_audit.py, formatted for a screen share.

    python show_audit_html.py            -> writes audit.html
    python show_audit_html.py out.html   -> writes out.html
"""

from __future__ import annotations

import html
import sys
import webbrowser
from pathlib import Path

from governance import audit

_EVENT_CLASS = {
    "PROPOSED": "proposed",
    "APPROVED": "approved",
    "DENIED": "denied",
    "EXECUTED": "executed",
    "FAILED": "failed",
    "BLOCKED": "blocked",
}

_CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; padding: 48px 32px; background: #0f1115; color: #e6e8eb;
       font: 15px/1.5 "Segoe UI", system-ui, sans-serif; }
main { max-width: 900px; margin: 0 auto; }
h1 { font-size: 20px; font-weight: 600; margin: 0 0 4px; letter-spacing: -0.01em; }
.sub { color: #8b929c; font-size: 13px; margin: 0 0 28px; }
table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
th { text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em;
     color: #8b929c; font-weight: 600; padding: 0 12px 10px; border-bottom: 1px solid #262a31; }
td { padding: 11px 12px; border-bottom: 1px solid #1a1d23; }
tr:last-child td { border-bottom: none; }
.mono { font-family: "Cascadia Mono", Consolas, monospace; font-size: 13px; color: #a8b0ba; }
.badge { display: inline-block; padding: 3px 10px; border-radius: 999px;
         font-size: 12px; font-weight: 600; letter-spacing: 0.02em; }
.proposed { background: #1c2733; color: #7dafe0; }
.approved { background: #14301f; color: #6bcf94; }
.executed { background: #14301f; color: #6bcf94; }
.failed   { background: #341c1c; color: #e88b8b; }
.denied   { background: #341c1c; color: #e88b8b; }
.blocked  { background: #33291a; color: #e0b072; }
.pilot { color: #e6e8eb; }
.none { color: #565c66; }
.chain { margin-top: 28px; padding: 14px 18px; border-radius: 8px; font-size: 14px; }
.ok { background: #10241a; border: 1px solid #1f4230; color: #6bcf94; }
.broken { background: #2a1414; border: 1px solid #4a2020; color: #e88b8b; }
.empty { color: #8b929c; padding: 40px 0; }
"""


def _render(records, intact, problem) -> str:
    rows = []
    for record in records:
        event = record.event.value
        pilot = (f'<span class="pilot">{html.escape(record.pilot_id)}</span>'
                 if record.pilot_id else '<span class="none">-</span>')
        rows.append(
            f'<tr><td class="mono">{record.ts:%H:%M:%S}</td>'
            f'<td><span class="badge {_EVENT_CLASS.get(event, "proposed")}">{event}</span></td>'
            f'<td>{html.escape(record.tool)}</td>'
            f'<td>{pilot}</td>'
            f'<td class="mono">{html.escape((record.request_id or "-")[:8])}</td></tr>'
        )

    if records:
        body = (
            "<table><thead><tr><th>Time</th><th>Event</th><th>Tool</th>"
            "<th>Pilot</th><th>Request</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )
    else:
        body = '<p class="empty">Audit log is empty.</p>'

    if intact:
        chain = (f'<div class="chain ok">Hash chain verified &mdash; '
                 f'all {len(records)} records intact.</div>')
    else:
        chain = f'<div class="chain broken">CHAIN BROKEN: {html.escape(str(problem))}</div>'

    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>Governance Audit Log</title><style>{_CSS}</style></head><body><main>'
        '<h1>Governance Audit Log</h1>'
        '<p class="sub">Append-only, hash-chained. Every gated decision, whether it ran or not.</p>'
        f'{body}{chain}</main></body></html>'
    )


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else Path("audit.html")
    records = audit.read_all()
    intact, problem = audit.verify_chain()
    out.write_text(_render(records, intact, problem), encoding="utf-8")
    print(f"Wrote {out.resolve()}")
    webbrowser.open(out.resolve().as_uri())
    return 0 if intact else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
