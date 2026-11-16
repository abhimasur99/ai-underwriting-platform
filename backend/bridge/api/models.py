"""Request and response models (they become the OpenAPI schema the frontend types come from)."""
from pydantic import BaseModel


class CreateDealResponse(BaseModel):
    deal_id: str
    checklist: dict


class ChatRequest(BaseModel):
    message: str = ""
    files: list[str] = []


class ChatResponse(BaseModel):
    reply: str
    checklist: dict


class FileResponse_(BaseModel):
    reply: str
    checklist: dict
    submitted: bool = False


class QueueRow(BaseModel):
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


class ChiefChatRequest(BaseModel):
    message: str


class ChiefChatResponse(BaseModel):
    reply: str
    intent: str
    patch: dict | None = None


class DecisionRequest(BaseModel):
    decision: str            # approve | send_back | reject
    rationale: str = ""


class StateResponse(BaseModel):
    state: str


class DealDetail(BaseModel):
    status: QueueRow
    deal: dict | None
    result: dict | None
    check: dict | None
    versions: list[int]
    files: list[dict]
    checklist: dict
    pending_patches: list[dict]
