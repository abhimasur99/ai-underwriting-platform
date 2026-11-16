"""Views over the event log: a deal's status and the queue. Nothing here is stored separately."""
from dataclasses import dataclass

from bridge.store.db import Store

STAGE = {
    "CREATED": "Awaiting docs", "AWAITING_DOCS": "Awaiting docs", "READY": "Awaiting docs",
    "NEEDS_INPUT": "Awaiting docs", "EXTRACTING": "Extraction", "EXTRACTED": "Extraction",
    "UNDERWRITING": "Underwriting", "UNDERWRITTEN": "Underwriting", "CHECKING": "Checker",
    "CHECKED": "Checker", "NEEDS_REVIEW": "Review", "SENT_BACK": "Underwriting",
    "APPROVED": "Done", "RELEASED": "Done", "REJECTED": "Done", "FAILED": "Failed",
}


@dataclass
class DealStatus:
    deal_id: str
    name: str
    state: str
    stage: str
    call: str | None
    flags: int
    retry_count: int
    escalation: bool
    deal_version: int
    created_at: str
    updated_at: str
    owner: str


def status(store: Store, deal_id: str) -> DealStatus:
    meta = store.deal_meta(deal_id)
    state, call, flags, retries, escalation, version = "CREATED", None, 0, 0, False, 1
    updated = meta.get("created_at", "")
    for e in store.events(deal_id):
        updated = e.ts
        version = e.deal_version
        if e.type == "state.changed":
            state = e.payload.get("to", state)
            if "escalation" in e.payload:
                escalation = bool(e.payload["escalation"])
            elif state in ("EXTRACTING", "UNDERWRITING"):
                escalation = False
            retries = e.payload.get("retry_count", retries)
        elif e.type == "underwriting.completed":
            call = e.payload.get("call", call)
            flags = e.payload.get("flags", flags)
        elif e.type == "version.created":
            retries = 0
            escalation = False
    return DealStatus(deal_id=deal_id, name=meta.get("name", ""), state=state,
                      stage=STAGE.get(state, state), call=call,
                      flags=flags + (1 if escalation else 0),
                      retry_count=retries, escalation=escalation, deal_version=version,
                      created_at=meta.get("created_at", ""), updated_at=updated,
                      owner=meta.get("owner", "unassigned"))


def queue(store: Store) -> list[DealStatus]:
    rows = [status(store, d) for d in store.deal_ids()]
    return sorted(rows, key=lambda s: s.updated_at, reverse=True)
