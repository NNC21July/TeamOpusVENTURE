"""Pilot approval interface for governed (state-changing) tools.

The AI can propose a risky action, but it cannot approve one. Approval happens
here, in a separate program the pilot runs, which is the whole point: nothing
the model does can reach this. Usage:

    python approve.py list
    python approve.py approve <request_id> <pilot_id>
    python approve.py deny    <request_id> <pilot_id>

After approving, tell the assistant to retry the action with the request id.
"""

from __future__ import annotations

import argparse
import sys

from governance import approvals
from governance.schemas import RequestStatus


def cmd_list(_args: argparse.Namespace) -> int:
    pending = approvals.list_requests(RequestStatus.PENDING)
    if not pending:
        print("No requests awaiting approval.")
        return 0

    print(f"{len(pending)} request(s) awaiting approval:\n")
    for request in sorted(pending, key=lambda r: r.created_at):
        print(f"  id      : {request.request_id}")
        print(f"  action  : {request.preview}")
        print(f"  asked at: {request.created_at:%Y-%m-%d %H:%M:%S}")
        print()
    print("Approve with: python approve.py approve <id> <your_pilot_id>")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    try:
        request = approvals.approve(args.request_id, args.pilot_id)
    except ValueError as exc:
        print(f"Could not approve: {exc}", file=sys.stderr)
        return 1
    print(f"Approved by {args.pilot_id}: {request.preview}")
    print("The action still has to be retried with this request id to run.")
    return 0


def cmd_deny(args: argparse.Namespace) -> int:
    try:
        approvals.deny(args.request_id, args.pilot_id)
    except ValueError as exc:
        print(f"Could not deny: {exc}", file=sys.stderr)
        return 1
    print(f"Denied by {args.pilot_id}. The action cannot run.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Approve or deny risky drone actions.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="show requests awaiting approval")
    list_parser.set_defaults(func=cmd_list)

    approve_parser = subparsers.add_parser("approve", help="approve a pending request")
    approve_parser.add_argument("request_id")
    approve_parser.add_argument("pilot_id", help="who is approving (recorded in the audit log)")
    approve_parser.set_defaults(func=cmd_approve)

    deny_parser = subparsers.add_parser("deny", help="deny a pending request")
    deny_parser.add_argument("request_id")
    deny_parser.add_argument("pilot_id", help="who is denying (recorded in the audit log)")
    deny_parser.set_defaults(func=cmd_deny)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
