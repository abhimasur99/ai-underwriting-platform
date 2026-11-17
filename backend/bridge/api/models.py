"""Request and response models (they become the OpenAPI schema the frontend types come from)."""
from pydantic import BaseModel

from bridge.core.completeness import ChecklistStatus
from bridge.core.schema import CheckReport, Deal, Patch, UnderwritingResult


class CreateDealResponse(BaseModel):
    deal_id: str
    checklist: ChecklistStatus


class ChatRequest(BaseModel):
    message: str = ""
    files: list[str] = []


class ChatResponse(BaseModel):
    reply: str
    checklist: ChecklistStatus


class FileResponse_(BaseModel):
    reply: str
    checklist: ChecklistStatus
    submitted: bool = False


class IntakeStatus(BaseModel):
    """What the external chat may show: a stage and a plain sentence, never ratios or a call."""
    stage: str
    message: str
    checklist: ChecklistStatus


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
    patch: Patch | None = None


class DecisionRequest(BaseModel):
    decision: str            # approve | send_back | reject
    rationale: str = ""


class StateResponse(BaseModel):
    state: str


class FileRow(BaseModel):
    file_id: str
    deal_id: str
    filename: str
    label: str | None = None
    size: int


class DealDetail(BaseModel):
    status: QueueRow
    deal: Deal | None
    result: UnderwritingResult | None
    check: CheckReport | None
    versions: list[int]
    files: list[FileRow]
    checklist: ChecklistStatus
    pending_patches: list[Patch]


class WorkbookCell(BaseModel):
    ref: str
    row: int
    col: int
    value: float | int | str | None = None
    formula: str | None = None
    format: str = "General"
    error: str | None = None


class WorkbookSheet(BaseModel):
    name: str
    rows: int
    cols: int
    cells: list[WorkbookCell]


class WorkbookView(BaseModel):
    sheets: list[WorkbookSheet]
