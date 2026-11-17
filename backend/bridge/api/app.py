"""FastAPI app: routes and SSE streams from docs/ui.md. The API layer only calls the agents."""
import asyncio
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from bridge.agents import intake_replies as say
from bridge.agents import patches as patching
from bridge.agents.broker_reply import ReplyError
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
from bridge.core.diff import VersionDiff
from bridge.core.parsers.errors import ParseError
from bridge.core.parsers.view import document_lines
from bridge.core.scenario import Outcome, ScenarioError, run_scenario
from bridge.core.schema import Event, ReplyDraft
from bridge.core.sizing import Sizing, max_loan
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
    app = FastAPI(title="AI Lending Platform (sample data only)",
                  description="Screening-layer demo. Made-up data; illustrative thresholds.")

    app.state.store = store

    def need(deal_id: str) -> str:
        if not store.deal_exists(deal_id):
            raise HTTPException(404, f"no deal {deal_id}")
        return deal_id

    @app.get("/api/deals/{deal_id}/changes", response_model=VersionDiff)
    def changes(deal_id: str):
        """What the latest version changed from the one before it."""
        need(deal_id)
        if store.get_deal(deal_id) is None or store.latest_result(deal_id) is None:
            raise HTTPException(409, "the deal has not been underwritten yet")
        return chief.version_diff(deal_id)

    def _underwritten(deal_id: str):
        need(deal_id)
        if store.get_deal(deal_id) is None or store.latest_result(deal_id) is None:
            raise HTTPException(409, "the deal has not been underwritten yet")
        return chief.latest(deal_id)[0]

    @app.post("/api/deals/{deal_id}/what-if", response_model=Outcome)
    def what_if(deal_id: str, body: m.WhatIfRequest):
        """The current case against one with some assumptions changed. Nothing is saved: no
        version, no event, no change to the deal."""
        deal = _underwritten(deal_id)
        try:
            return run_scenario(deal, chief.rules, body.params)
        except ScenarioError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/deals/{deal_id}/max-loan", response_model=Sizing)
    def largest_loan(deal_id: str, target: str = "screen"):
        """The largest loan that still gets the call (screen, or watch to avoid a decline)."""
        if target not in ("screen", "watch"):
            raise HTTPException(422, "target must be screen or watch")
        return max_loan(_underwritten(deal_id), chief.rules, target)

    @app.get("/api/deals/{deal_id}/chief-transcript", response_model=list[m.TranscriptMessage])
    def chief_transcript(deal_id: str):
        """The reviewer's conversation with the chief, so the chat can be restored on reload."""
        need(deal_id)
        roles = {"chat.reviewer": "you", "chat.chief": "agent"}
        return [{"from": roles[e.type], "ts": e.ts, "text": e.payload.get("text", "")}
                for e in store.events(deal_id) if e.type in roles]

    def _guard(fn, *args):
        try:
            return fn(*args)
        except (DecisionError, InvalidTransition) as exc:
            raise HTTPException(409, str(exc)) from exc
        except (patching.PatchError, ReplyError) as exc:
            raise HTTPException(422, str(exc)) from exc

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
    def list_deals(include_archived: bool = False):
        return [asdict(s) for s in projections.queue(store, include_archived)]

    @app.delete("/api/deals/{deal_id}", response_model=m.ArchiveResponse)
    def archive_deal(deal_id: str):
        """Archive, not delete: the event log is append-only. Restorable."""
        need(deal_id)
        _guard(chief.archive, deal_id)
        return {"deal_id": deal_id, "archived": True}

    @app.post("/api/deals/{deal_id}/restore", response_model=m.ArchiveResponse)
    def restore_deal(deal_id: str):
        need(deal_id)
        chief.restore(deal_id)
        return {"deal_id": deal_id, "archived": False}

    @app.patch("/api/deals/{deal_id}", response_model=m.RenameResponse)
    def rename_deal(deal_id: str, body: m.RenameRequest):
        need(deal_id)
        try:
            name = chief.rename(deal_id, body.name)
        except DecisionError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"deal_id": deal_id, "name": name}

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
            "files": _current_files(deal_id),
            "checklist": completeness.status(labels, store.facts(deal_id)).model_dump(),
            "pending_patches": [p.model_dump() for p in store.patches(deal_id, status="proposed")],
        }

    def _current_files(deal_id: str) -> list[dict]:
        """One row per document type: the latest upload (an earlier one was replaced)."""
        latest: dict[str, dict] = {}
        for row in store.files(deal_id):                # oldest first, so the last one wins
            latest[row["label"] or row["file_id"]] = row
        return list(latest.values())

    @app.get("/api/deals/{deal_id}/files/{file_id}/text", response_model=m.FileText)
    def file_text(deal_id: str, file_id: str):
        need(deal_id)
        row = next((f for f in _current_files(deal_id) if f["file_id"] == file_id), None)
        if row is None or not Path(row["path"]).exists():
            raise HTTPException(404, "no such file (it may have been replaced)")
        try:
            kind, lines = document_lines(Path(row["path"]), row["label"])
        except ParseError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"file_id": file_id, "filename": row["filename"], "label": row["label"],
                "kind": kind, "lines": lines}

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
        sources = {}
        for e in store.events(deal_id):
            if e.type == "fact.recorded":
                sources[e.payload.get("key")] = e.payload.get("source") or "stated in the chat"
        facts = store.facts(deal_id)
        return {"stage": st.stage, "message": intake.status_message(deal_id),
                "checklist": completeness.status(labels, facts),
                "facts": [{"key": k, "label": say.FACT_NAME[k].capitalize(), "value": facts[k],
                           "source": sources.get(k, "stated in the chat")}
                          for k in say.FACT_NAME if k in facts],
                "files": {f["label"]: f["filename"] for f in _current_files(deal_id)
                          if f["label"]}}

    @app.get("/api/deals/{deal_id}/transcript", response_model=list[m.TranscriptMessage])
    def transcript(deal_id: str):
        """The sponsor's conversation only (what they said, what the assistant said, which files
        arrived), so the intake page can restore it. Never any internal event."""
        need(deal_id)
        roles = {"chat.sponsor": "you", "chat.assistant": "agent", "file.uploaded": "file"}
        return [{"from": roles[e.type], "ts": e.ts,
                 "text": e.summary.removesuffix(" uploaded") if e.type == "file.uploaded"
                 else e.payload.get("text", "")}
                for e in store.events(deal_id) if e.type in roles]

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
        if body.decision not in ("approve", "send_back", "reject", "request_info"):
            raise HTTPException(
                422, "decision must be approve, send_back, reject or request_info")
        return {"state": _guard(chief.decide, deal_id, body.decision, body.rationale)}

    # ---- the draft reply to the broker (never sent)
    @app.get("/api/deals/{deal_id}/reply-draft", response_model=ReplyDraft | None)
    def get_reply_draft(deal_id: str):
        need(deal_id)
        return chief.reply_draft(deal_id)

    @app.post("/api/deals/{deal_id}/reply-draft", response_model=ReplyDraft)
    def draft_reply(deal_id: str):
        """Draft the reply for a decided deal, or start over on it."""
        need(deal_id)
        return _guard(chief.draft_reply, deal_id)

    @app.put("/api/deals/{deal_id}/reply-draft", response_model=ReplyDraft)
    def edit_reply(deal_id: str, body: m.ReplyTextRequest):
        need(deal_id)
        return _guard(chief.edit_reply, deal_id, body.text)

    @app.post("/api/deals/{deal_id}/reply-draft/approve", response_model=ReplyDraft)
    def approve_reply(deal_id: str):
        need(deal_id)
        return _guard(chief.approve_reply, deal_id)

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
