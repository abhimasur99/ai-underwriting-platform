"""Views over the event log: a deal's status and the queue. Nothing here is stored separately."""
from dataclasses import dataclass

from bridge.core.schema import ReplyDraft
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
    archived: bool = False
    next_action: str = ""       # what happens next, and who must act
    needs_you: bool = False      # true when the reviewer is the one who must act


SYSTEM_STATES = {"READY", "EXTRACTING", "EXTRACTED", "UNDERWRITING", "UNDERWRITTEN", "CHECKING",
                 "CHECKED", "SENT_BACK"}


def _next_action(state: str, archived: bool, escalation: bool, missing: list[str],
                 info_note: str) -> tuple[str, bool]:
    """(what happens next, whether the reviewer must act). Shown in the queue."""
    if archived:
        return "Archived", False
    if state in ("CREATED", "AWAITING_DOCS"):
        return "Waiting on sponsor: documents", False
    if state in SYSTEM_STATES:
        return "Running", False
    if state == "NEEDS_INPUT":
        what = info_note.strip() or ", ".join(missing[:3]) or "more information"
        return f"Waiting on sponsor: {what[:90]}", False
    if state == "NEEDS_REVIEW":
        return ("Your review: the check failed" if escalation else "Your review"), True
    if state in ("APPROVED", "RELEASED"):
        return "Done: approved", False
    if state == "REJECTED":
        return "Done: rejected", False
    return "Failed: see the process view", True


def status(store: Store, deal_id: str) -> DealStatus:
    meta = store.deal_meta(deal_id)
    state, call, flags, retries, escalation, version = "CREATED", None, 0, 0, False, 1
    archived = False
    missing: list[str] = []
    info_note = ""
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
            missing = list(e.payload.get("missing", [])) if state == "NEEDS_INPUT" else []
            if state != "NEEDS_INPUT":
                info_note = ""
        elif e.type == "info.requested":
            info_note = e.payload.get("note", "")
        elif e.type == "underwriting.completed":
            call = e.payload.get("call", call)
            flags = e.payload.get("flags", flags)
        elif e.type == "version.created":
            retries = 0
            escalation = False
        elif e.type in ("deal.archived", "deal.restored"):
            archived = e.type == "deal.archived"
    action, needs_you = _next_action(state, archived, escalation, missing, info_note)
    return DealStatus(deal_id=deal_id, name=meta.get("name", ""), state=state,
                      stage=STAGE.get(state, state), call=call,
                      flags=flags + (1 if escalation else 0),
                      retry_count=retries, escalation=escalation, deal_version=version,
                      created_at=meta.get("created_at", ""), updated_at=updated,
                      owner=meta.get("owner", "unassigned"), archived=archived,
                      next_action=action, needs_you=needs_you)


def queue(store: Store, include_archived: bool = False) -> list[DealStatus]:
    rows = [status(store, d) for d in store.deal_ids()]
    if not include_archived:
        rows = [r for r in rows if not r.archived]
    # what needs the reviewer first, then the most recent activity
    return sorted(sorted(rows, key=lambda s: s.updated_at, reverse=True),
                  key=lambda s: not s.needs_you)


def reply_draft(store: Store, deal_id: str) -> ReplyDraft | None:
    """The current draft reply to the broker: the latest drafting, then any edits and approval."""
    draft: ReplyDraft | None = None
    for e in store.events(deal_id):
        if e.type == "reply.drafted":
            draft = ReplyDraft(decision=e.payload["decision"], text=e.payload["text"],
                               status="draft", wording=e.payload.get("wording", "template"),
                               drafted_at=e.ts)
        elif draft and e.type == "reply.edited":
            draft = draft.model_copy(update={"text": e.payload["text"], "status": "draft",
                                             "edited": True, "approved_at": None})
        elif draft and e.type == "reply.approved":
            draft = draft.model_copy(update={"status": "approved", "approved_at": e.ts})
    return draft
