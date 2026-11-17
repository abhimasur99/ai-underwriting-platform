"""FastAPI app: routes and SSE streams from docs/ui.md. The API layer only calls the agents."""
import asyncio
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from bridge.agents import patches as patching
from bridge.agents.chief import Chief, DecisionError
from bridge.agents.chief_chat import ChiefChat
from bridge.agents.intake import IncomingFile, IntakeAgent
from bridge.agents.runner import AgentRunner, CachedRunner
from bridge.agents.states import InvalidTransition
from bridge.agents.underwriter import FaultPlan
from bridge.api import models as m
from bridge.api.sse import event_stream
from bridge.core import completeness
from bridge.core.builders.workbook_view import workbook_view
from bridge.core.schema import Event
from bridge.settings import Settings, get_settings
from bridge.store import projections
from bridge.store.db import Store

ARTIFACTS = {"memo.pdf": ("memo_pdf", "application/pdf"),
             "workbook.xlsx": ("workbook", "application/vnd.openxmlformats-officedocument."
                                           "spreadsheetml.sheet")}


def create_app(settings: Settings | None = None, runner: AgentRunner | None = None,
               faults: FaultPlan | None = None) -> FastAPI:
    settings = settings or get_settings()
    runner = runner or _default_runner(settings)
    store = Store(settings.database_path)
    if faults is None and settings.force_mismatch:
        faults = FaultPlan("ltc", 0.0078, frozenset({1} if settings.force_mismatch == "once"
                                                    else {1, 2, 3}))
    chief = Chief(store, runner, settings.outputs_dir, settings.uploads_dir, faults=faults,
                  pace=settings.step_delay)
    intake, chat = IntakeAgent(chief, runner), ChiefChat(chief, runner)
    app = FastAPI(title="Bridge Loan Platform (sample data only)",
                  description="Screening-layer demo. Made-up data; illustrative thresholds.")

    def need(deal_id: str) -> str:
        if not store.deal_exists(deal_id):
            raise HTTPException(404, f"no deal {deal_id}")
        return deal_id

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "mode": runner.mode}

    # ---- external intake
    @app.post("/api/deals", response_model=m.CreateDealResponse)
    def create_deal():
        deal_id = chief.create_deal()
        return {"deal_id": deal_id, "checklist": chief.update_checklist(deal_id)}

    @app.post("/api/deals/{deal_id}/chat", response_model=m.ChatResponse)
    def post_chat(deal_id: str, body: m.ChatRequest, tasks: BackgroundTasks):
        need(deal_id)
        out = intake.handle(deal_id, body.message)
        if out["submitted"]:
            tasks.add_task(chief.process, deal_id)
        return {"reply": out["reply"], "checklist": out["checklist"]}

    @app.post("/api/deals/{deal_id}/files", response_model=m.FileResponse_)
    async def upload_file(deal_id: str, tasks: BackgroundTasks, file: Annotated[UploadFile, File()],
                          label: Annotated[str | None, Form()] = None):
        need(deal_id)
        content = await file.read()
        out = await asyncio.to_thread(intake.handle, deal_id, "", [
            IncomingFile(file.filename or "upload", content, label)])
        if out["submitted"]:
            tasks.add_task(chief.process, deal_id)
        return out

    # ---- queue and deal views
    @app.get("/api/deals", response_model=list[m.QueueRow])
    def list_deals():
        return [asdict(s) for s in projections.queue(store)]

    @app.get("/api/deals/{deal_id}", response_model=m.DealDetail)
    def get_deal(deal_id: str):
        need(deal_id)
        deal = store.get_deal(deal_id)
        row = store.latest_result(deal_id, deal.version) if deal else None
        labels = [f["label"] for f in store.files(deal_id) if f["label"]]
        return {
            "status": asdict(projections.status(store, deal_id)),
            "deal": deal.model_dump() if deal else None,
            "result": row["result"] if row else None,
            "check": row["check"] if row else None,
            "versions": store.versions(deal_id),
            "files": store.files(deal_id),
            "checklist": completeness.status(labels, store.facts(deal_id)).model_dump(),
            "pending_patches": [p.model_dump() for p in store.patches(deal_id, status="proposed")],
        }

    @app.get("/api/deals/{deal_id}/events", response_model=list[Event])
    def get_events(deal_id: str, after: int = 0):
        need(deal_id)
        return store.events(deal_id, after)

    @app.get("/api/deals/{deal_id}/stream")
    async def deal_stream(deal_id: str, request: Request, after: int = 0, once: bool = False):
        need(deal_id)
        last = request.headers.get("last-event-id")
        gen = event_stream(store, deal_id, int(last) if last else after, once=once,
                           is_disconnected=request.is_disconnected)
        return StreamingResponse(gen, media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    @app.get("/api/stream")
    async def queue_stream(request: Request, after: int = 0, once: bool = False):
        last = request.headers.get("last-event-id")
        gen = event_stream(store, None, int(last) if last else after, once=once,
                           is_disconnected=request.is_disconnected)
        return StreamingResponse(gen, media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    @app.get("/api/deals/{deal_id}/intake-status", response_model=m.IntakeStatus)
    def intake_status(deal_id: str):
        need(deal_id)
        st = projections.status(store, deal_id)
        labels = [f["label"] for f in store.files(deal_id) if f["label"]]
        return {"stage": st.stage, "message": intake.status_message(deal_id),
                "checklist": completeness.status(labels, store.facts(deal_id))}

    @app.get("/api/deals/{deal_id}/workbook", response_model=m.WorkbookView)
    def workbook(deal_id: str):
        need(deal_id)
        deal = store.get_deal(deal_id)
        row = store.latest_result(deal_id, deal.version) if deal else None
        path = Path(row["result"]["artifacts"].get("workbook", "")) if row else None
        if not path or not path.exists():
            raise HTTPException(404, "not generated yet")
        return workbook_view(path)

    @app.get("/api/deals/{deal_id}/artifacts/{name}")
    def artifact(deal_id: str, name: str):
        need(deal_id)
        if name not in ARTIFACTS:
            raise HTTPException(404, "unknown artifact")
        deal = store.get_deal(deal_id)
        row = store.latest_result(deal_id, deal.version) if deal else None
        key, media = ARTIFACTS[name]
        path = Path(row["result"]["artifacts"].get(key, "")) if row else None
        if not path or not path.exists():
            raise HTTPException(404, "not generated yet")
        # the memo opens inline (the UI shows it in a viewer); the workbook downloads
        return FileResponse(path, media_type=media, filename=name,
                            content_disposition_type="inline" if name.endswith(".pdf")
                            else "attachment")

    # ---- internal chat, patches, decision
    @app.post("/api/deals/{deal_id}/chief-chat", response_model=m.ChiefChatResponse)
    def chief_chat(deal_id: str, body: m.ChiefChatRequest):
        need(deal_id)
        if store.get_deal(deal_id) is None or store.latest_result(deal_id) is None:
            raise HTTPException(409, "the deal has not been underwritten yet")
        return chat.handle(deal_id, body.message)

    def _guard(fn, *args):
        try:
            return fn(*args)
        except (DecisionError, InvalidTransition) as exc:
            raise HTTPException(409, str(exc)) from exc
        except patching.PatchError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/deals/{deal_id}/patches/{patch_id}/confirm", response_model=m.StateResponse)
    def confirm_patch(deal_id: str, patch_id: str):
        need(deal_id)
        return {"state": _guard(chief.confirm_patch, deal_id, patch_id)}

    @app.post("/api/deals/{deal_id}/patches/{patch_id}/cancel", response_model=m.StateResponse)
    def cancel_patch(deal_id: str, patch_id: str):
        need(deal_id)
        _guard(chief.cancel_patch, deal_id, patch_id)
        return {"state": chief.state(deal_id)}

    @app.post("/api/deals/{deal_id}/decision", response_model=m.StateResponse)
    def decision(deal_id: str, body: m.DecisionRequest):
        need(deal_id)
        if body.decision not in ("approve", "send_back", "reject"):
            raise HTTPException(422, "decision must be approve, send_back or reject")
        return {"state": _guard(chief.decide, deal_id, body.decision, body.rationale)}

    return app


def _default_runner(settings: Settings) -> AgentRunner:
    """Offline by default. BRIDGE_MODE=live uses Claude for narrative, checker wording and chat
    interpretation; the numbers are computed by code either way."""
    if settings.mode == "live":
        if not settings.api_key:
            raise RuntimeError(
                "BRIDGE_MODE=live needs ANTHROPIC_API_KEY (copy .env.example to .env)")
        from bridge.agents.claude_runner import ClaudeRunner
        return ClaudeRunner.from_settings(settings)
    if settings.mode != "cached":
        raise RuntimeError(f"BRIDGE_MODE must be 'cached' or 'live', not {settings.mode!r}")
    return CachedRunner()
