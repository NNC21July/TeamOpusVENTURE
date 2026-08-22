from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class RequestStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    CONSUMED = "CONSUMED" # this is to ensure we dont perform an action twice. 
                          # SO once an action is approved and acted on, we change its status to consumed

@dataclass
class Request:
    request_id: str
    tool_name: str
    params_hash: str
    preview: str
    status: RequestStatus
    created_at: datetime
    pilot_id: str | None = None
    decided_at: datetime | None = None


class AuditEvent(str, Enum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    EXECUTED = "EXECUTED"
    BLOCKED = "BLOCKED"


@dataclass
class AuditRecord:
    ts: datetime
    event: AuditEvent
    tool: str
    params_hash: str
    request_id: str | None
    pilot_id: str | None
    prev_hash: str
    hash: str