from dataclasses import asdict
from pathlib import Path
from governance.schemas import Request, RequestStatus
import uuid
from datetime import datetime
import hashlib
import json


STATE_DIR = Path(__file__).parent / "state"
REQUESTS_FILE = STATE_DIR / "requests.json"

def _request_to_dict(r: Request) -> dict:
    d = asdict(r)
    d["status"] = r.status.value
    d["created_at"] = r.created_at.isoformat()
    d["decided_at"] = r.decided_at.isoformat() if r.decided_at else None
    return d

def _dict_to_request(d: dict) -> Request:
    return Request(
        **{**d,
           "status": RequestStatus(d["status"]),
           "created_at": datetime.fromisoformat(d["created_at"]),
           "decided_at": datetime.fromisoformat(d["decided_at"]) if d["decided_at"] else None}
    )

def _load_requests() -> dict[str, Request]:
    if not REQUESTS_FILE.exists():
        return {}
    raw = json.loads(REQUESTS_FILE.read_text())
    return {rid: _dict_to_request(d) for rid, d in raw.items()}

def _save_requests(requests: dict[str, Request]) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    raw = {rid: _request_to_dict(r) for rid, r in requests.items()}
    tmp = REQUESTS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(raw, indent=2))
    tmp.replace(REQUESTS_FILE)   # atomic swap — real file is never half-written

def list_requests(status: RequestStatus | None = None) -> list[Request]:
    if status is None:
        return list(_load_requests().values())
    else:
        reqs = _load_requests().values()
        return [i for i in reqs if i.status == status]

def hash_params(tool: str, params: dict) -> str:
    canonical = json.dumps({"tool": tool, "params": params}, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def create_request(tool: str, params: dict) -> Request:
    requests = _load_requests()
    params_hash = hash_params(tool, params)

    for existing in requests.values():
        if existing.params_hash == params_hash and existing.status == RequestStatus.PENDING:
            return existing

    request = Request(
        request_id=str(uuid.uuid4()),
        tool_name=tool,
        params_hash=params_hash,
        preview=f"{tool}({params})",
        status=RequestStatus.PENDING,
        created_at=datetime.now(),
    )
    requests[request.request_id] = request
    _save_requests(requests)
    return request


def approve(request_id: str, pilot_id: str) -> None:
    requests = _load_requests()
    request = requests.get(request_id)

    if request is None:
        raise ValueError(f"Request {request_id} not found")
    if request.status != RequestStatus.PENDING:
        raise ValueError(f"Request {request_id} is {request.status}, not PENDING")

    request.status = RequestStatus.APPROVED
    request.pilot_id = pilot_id
    request.decided_at = datetime.now()
    _save_requests(requests)


def deny(request_id: str, pilot_id: str) -> None:
    requests = _load_requests()
    request = requests.get(request_id)

    if request is None:
        raise ValueError(f"Request {request_id} not found")
    if request.status != RequestStatus.PENDING:
        raise ValueError(f"Request {request_id} is {request.status}, not PENDING")

    request.status = RequestStatus.DENIED
    request.pilot_id = pilot_id
    request.decided_at = datetime.now()
    _save_requests(requests)


def consume(request_id: str, tool: str, params: dict) -> Request:
    requests = _load_requests()
    request = requests.get(request_id)

    if request is None:
        raise ValueError(f"Request {request_id} not found")
    if request.status != RequestStatus.APPROVED:
        raise ValueError(f"Request {request_id} is {request.status}, not APPROVED")
    if request.params_hash != hash_params(tool, params):
        raise ValueError(f"Request {request_id} params do not match this call")

    request.status = RequestStatus.CONSUMED
    _save_requests(requests)
    
    return request