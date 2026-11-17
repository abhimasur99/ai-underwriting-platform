"""Request and response models (they become the OpenAPI schema the frontend types come from)."""
from pydantic import BaseModel, Field

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


class FactView(BaseModel):
    key: str
    label: str
    value: str
    source: str            # "deal_summary.pdf, line 8", or "stated in the chat"


class TranscriptMessage(BaseModel):
    # "you" (the sponsor), "agent" (the intake assistant) or "file" (a document received)
    from_: str = Field(alias="from")
    text: str
    ts: str

    model_config = {"populate_by_name": True}


class IntakeStatus(BaseModel):
    """What the external chat may show: a stage and a plain sentence, never ratios or a call."""
    stage: str
    message: str
    checklist: ChecklistStatus
    facts: list[FactView] = []
    files: dict[str, str] = {}      # document type -> the file received


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
    archived: bool = False
    next_action: str = ""
    needs_you: bool = False


class ChiefChatRequest(BaseModel):
    message: str


class ChiefChatResponse(BaseModel):
    reply: str
    intent: str
    patch: Patch | None = None
    suggestions: list[str] = []         # follow-up questions to offer next


class DecisionRequest(BaseModel):
    decision: str            # approve | send_back | reject | request_info
    rationale: str = ""


class StateResponse(BaseModel):
    state: str


class FileRow(BaseModel):
    file_id: str
    deal_id: str
    filename: str
    label: str | None = None
    size: int
    uploaded_at: str = ""


class FileText(BaseModel):
    file_id: str
    filename: str
    label: str | None
    kind: str                 # "text" or "table"
    lines: list[str]


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


class RenameRequest(BaseModel):
    name: str


class ArchiveResponse(BaseModel):
    deal_id: str
    archived: bool


class RenameResponse(BaseModel):
    deal_id: str
    name: str
