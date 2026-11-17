"""The chief: a code state machine that routes every handoff. Specialist agents never call each
other. A model is used only for chat intent and wording (see chief_chat.py), never for state."""
import json
import shutil
import threading
import time
from pathlib import Path

from bridge.agents import patches as patching
from bridge.agents.checker import recheck_memo, run_checker
from bridge.agents.extraction import run_extraction
from bridge.agents.recorder import Recorder
from bridge.agents.runner import AgentRunner
from bridge.agents.states import MAX_RETRIES, InvalidTransition, check_transition
from bridge.agents.underwriter import FaultPlan, run_underwriter
from bridge.core import completeness
from bridge.core.builders.memo import render_memo
from bridge.core.parsers import parse_deal_dir
from bridge.core.placeholders import fill, validate_narrative
from bridge.core.rules import RulesConfig, load_rules
from bridge.core.schema import (
    CheckReport,
    Deal,
    Handoff,
    HandoffResult,
    Patch,
    UnderwritingResult,
)
from bridge.store import projections
from bridge.store.db import Store, now

DOC_LABELS = ["deal_summary", "purchase_contract", "rent_roll", "t12", "renovation_budget"]
DOC_EXTENSIONS = (".md", ".txt", ".pdf", ".docx", ".csv", ".xlsx")


class DecisionError(RuntimeError):
    pass


class Chief:
    def __init__(self, store: Store, runner: AgentRunner, outputs_dir: Path, uploads_dir: Path,
                 rules: RulesConfig | None = None, faults: FaultPlan | None = None,
                 max_retries: int = MAX_RETRIES, pace: float = 0.0):
        self.store, self.runner = store, runner
        self.pace = pace          # demo pacing only: how long each agent visibly "works"
        self.outputs_dir, self.uploads_dir = Path(outputs_dir), Path(uploads_dir)
        self.rules = rules or load_rules()
        self.faults, self.max_retries = faults, max_retries
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    # ------------------------------------------------------------------ plumbing
    def _lock(self, deal_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(deal_id, threading.Lock())

    def deal_dir(self, deal_id: str) -> Path:
        return self.uploads_dir / deal_id

    def state(self, deal_id: str) -> str:
        return projections.status(self.store, deal_id).state

    def _set_state(self, deal_id: str, new: str, version: int = 1, **payload) -> None:
        current = self.state(deal_id)
        check_transition(current, new)
        Recorder(self.store, deal_id, version).event(
            "chief", "state.changed", f"{current} -> {new}",
            {"from": current, "to": new, **payload})

    def _handoff(self, rec: Recorder, to: str, task: str, attempt: int, inputs_ref: str):
        n = sum(1 for e in self.store.events(rec.deal_id) if e.type == "handoff.sent") + 1
        h = Handoff(handoff_id=f"h-{n:04d}", **{"from": "chief"}, to=to, deal_id=rec.deal_id,
                    deal_version=rec.version, task=task, attempt=attempt,
                    inputs_ref=inputs_ref, ts=now())
        rec.event("chief", "handoff.sent", f"chief -> {to}: {task}",
                  h.model_dump(by_alias=True))
        if self.pace:
            time.sleep(self.pace)
        return h, time.monotonic()

    def _returned(self, rec: Recorder, h: Handoff, started: float, status: str = "ok",
                  outputs_ref: str | None = None, summary: str = "") -> None:
        r = HandoffResult(handoff_id=h.handoff_id, deal_id=h.deal_id, deal_version=h.deal_version,
                          status=status, outputs_ref=outputs_ref, summary=summary,
                          duration_ms=int((time.monotonic() - started) * 1000))
        rec.event(h.to, "handoff.returned", f"{h.to} -> chief: {status}", r.model_dump())

    def _fail(self, deal_id: str, exc: Exception) -> None:
        version = projections.status(self.store, deal_id).deal_version
        Recorder(self.store, deal_id, version).event(
            "chief", "error", f"{type(exc).__name__}: {exc}", {"error": str(exc)})
        self._set_state(deal_id, "FAILED", version, reason=str(exc))

    def _overrides(self, deal_id: str) -> list[dict]:
        return [{"path": p.path, "new": p.new}
                for p in self.store.patches(deal_id, kind="data", status="confirmed")]

    # ------------------------------------------------------------------ intake side
    def create_deal(self, deal_id: str | None = None, name: str = "") -> str:
        deal_id = deal_id or self.store.next_deal_id()
        self.store.create_deal(deal_id, name)
        self.deal_dir(deal_id).mkdir(parents=True, exist_ok=True)
        Recorder(self.store, deal_id).event("chief", "deal.created", f"deal {deal_id} created")
        return deal_id

    def register_file(self, deal_id: str, filename: str, content: bytes, label: str) -> dict:
        """Store an uploaded file under its canonical name and refresh the checklist."""
        ext = Path(filename).suffix.lower()
        target = self.deal_dir(deal_id) / f"{label}{ext}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        for stale in target.parent.glob(f"{label}.*"):      # a replacement in another format
            if stale != target:
                stale.unlink()
        # a cached extraction describes the files it was made from; a changed file voids it
        (target.parent / "cached" / "extracted.json").unlink(missing_ok=True)
        n = len(self.store.files(deal_id)) + 1
        file_id = f"f-{deal_id}-{n:03d}"
        self.store.add_file(file_id, deal_id, filename, label, str(target), len(content))
        rec = Recorder(self.store, deal_id)
        rec.event("intake", "file.uploaded", f"{filename} uploaded", {"file_id": file_id})
        rec.event("intake", "file.classified", f"{filename} -> {label}",
                  {"file_id": file_id, "label": label})
        return self.update_checklist(deal_id)

    def record_fact(self, deal_id: str, key: str, value: str) -> dict:
        self.store.record_fact(deal_id, key, value)
        Recorder(self.store, deal_id).event("intake", "fact.recorded", f"{key} recorded",
                                            {"key": key})
        return self.update_checklist(deal_id)

    def checklist(self, deal_id: str) -> dict:
        """The checklist as it stands, without changing the deal's state or logging anything."""
        labels = [f["label"] for f in self.store.files(deal_id) if f["label"]]
        return completeness.status(labels, self.store.facts(deal_id)).model_dump()

    def update_checklist(self, deal_id: str) -> dict:
        labels = [f["label"] for f in self.store.files(deal_id) if f["label"]]
        status = completeness.status(labels, self.store.facts(deal_id))
        Recorder(self.store, deal_id).event(
            "chief", "checklist.updated", "checklist updated", status.model_dump())
        current = self.state(deal_id)
        target = "READY" if status.ready else "AWAITING_DOCS"
        if current in ("CREATED", "AWAITING_DOCS", "NEEDS_INPUT") and (
                current, target) in {("CREATED", "AWAITING_DOCS"), ("CREATED", "READY"),
                                     ("AWAITING_DOCS", "AWAITING_DOCS"),
                                     ("AWAITING_DOCS", "READY"), ("NEEDS_INPUT", "READY"),
                                     ("NEEDS_INPUT", "AWAITING_DOCS")}:
            self._set_state(deal_id, target)
        return status.model_dump()

    def ingest_directory(self, deal_id: str, source: Path) -> dict:
        """Load a sample deal folder (CLI and tests): copy documents, record the facts the
        documents provide, and refresh the checklist. Cached fixtures come along."""
        source = Path(source)
        for label in DOC_LABELS:
            for ext in DOC_EXTENSIONS:
                src = source / f"{label}{ext}"
                if src.exists():
                    self.register_file(deal_id, src.name, src.read_bytes(), label)
                    break
        if (source / "cached").exists():
            shutil.copytree(source / "cached", self.deal_dir(deal_id) / "cached",
                            dirs_exist_ok=True)
        try:
            deal = parse_deal_dir(source)
        except Exception:
            return self.update_checklist(deal_id)
        for key, value in completeness.facts_from_deal(deal).items():
            self.store.record_fact(deal_id, key, str(value))
        return self.update_checklist(deal_id)

    # ------------------------------------------------------------------ pipeline
    def process(self, deal_id: str) -> str:
        """Run extraction, underwriting and checking until the deal reaches review (or stops).
        Raises InvalidTransition (without failing the deal) if it is not ready to run."""
        state = self.state(deal_id)
        if state not in ("READY", "SENT_BACK", "UNDERWRITING"):
            raise InvalidTransition(f"cannot process a deal in state {state}")
        with self._lock(deal_id):
            try:
                self._process(deal_id)
            except Exception as exc:  # noqa: BLE001  (surface every failure as a visible state)
                self._fail(deal_id, exc)
        return self.state(deal_id)

    def _process(self, deal_id: str) -> None:
        state = self.state(deal_id)
        if state == "READY":
            deal = self._extract(deal_id)
            if deal is None:
                return
        else:
            deal = self.store.get_deal(deal_id)
            if state == "SENT_BACK":
                self._set_state(deal_id, "UNDERWRITING", deal.version)
        self._underwrite_and_check(deal_id, deal)

    def _extract(self, deal_id: str) -> Deal | None:
        """Extract the documents into a deal. A re-extraction (new files after the reviewer asked
        for something) becomes the next version; until it succeeds, everything is logged at the
        version the deal is already on, so a failed attempt never advances the displayed version."""
        versions = self.store.versions(deal_id)
        current, new_version = (versions[-1] if versions else 1), (versions[-1] + 1 if versions
                                                                    else 1)
        rec = Recorder(self.store, deal_id, current)
        h, t0 = self._handoff(rec, "extraction", "extract_deal", 1, f"files@{deal_id}")
        self._set_state(deal_id, "EXTRACTING", current)
        outcome = run_extraction(self.deal_dir(deal_id), self.runner, rec)
        if outcome.status == "needs_input":
            self._returned(rec, h, t0, "needs_input", summary=", ".join(outcome.missing))
            self._set_state(deal_id, "NEEDS_INPUT", current, missing=outcome.missing)
            return None
        deal = outcome.deal.model_copy(update={"deal_id": deal_id, "version": new_version})
        self.store.save_deal(deal)
        self.store.set_name(deal_id, deal.name)
        rec = Recorder(self.store, deal_id, new_version)
        if new_version > 1:
            rec.event("chief", "version.created", f"deal version {new_version} created",
                      {"from": current, "to": new_version,
                       "reason": "re-extracted from new documents"})
        self._returned(rec, h, t0, outputs_ref=f"deal_record@v{new_version}",
                       summary=f"extracted {deal.name}")
        self._set_state(deal_id, "EXTRACTED", new_version)
        self._set_state(deal_id, "UNDERWRITING", new_version)
        return deal

    def _underwrite_and_check(self, deal_id: str, deal: Deal) -> None:
        retries, feedback = 0, None
        deal_dir = self.deal_dir(deal_id)
        while True:
            attempt = retries + 1
            rec = Recorder(self.store, deal_id, deal.version)
            h, t0 = self._handoff(rec, "underwriter", "size_and_compute", attempt,
                                  f"deal_record@v{deal.version}")
            result = run_underwriter(deal, rec, self.rules, self.runner, self.outputs_dir,
                                     attempt, feedback, self.faults)
            self.store.save_result(deal_id, deal.version, attempt, result.model_dump_json())
            self._returned(rec, h, t0, outputs_ref=f"result@v{deal.version}.{attempt}",
                           summary=f"call {result.call}")
            self._set_state(deal_id, "UNDERWRITTEN", deal.version, retry_count=retries)
            self._set_state(deal_id, "CHECKING", deal.version, retry_count=retries)

            h, t0 = self._handoff(rec, "checker", "verify", attempt,
                                  f"result@v{deal.version}.{attempt}")
            report = run_checker(deal, result, deal_dir, rec, self.runner,
                                 overrides=self._overrides(deal_id))
            self.store.set_check(deal_id, deal.version, attempt, report.model_dump_json())
            self._returned(rec, h, t0, summary=f"check {report.status}")

            if report.status in ("pass", "warn"):
                self._set_state(deal_id, "CHECKED", deal.version, retry_count=retries)
                self._set_state(deal_id, "NEEDS_REVIEW", deal.version, retry_count=retries,
                                escalation=False)
                rec.event("chief", "review.requested", "ready for review",
                          {"escalation": False, "check": report.status})
                return
            fields = [m.field for m in report.mismatches]
            if retries < self.max_retries:
                retries += 1
                feedback = f"checker mismatches: {', '.join(fields) or report.summary}"
                rec.event("chief", "check.retry", f"retry {retries}: {feedback}",
                          {"retry_count": retries, "mismatches": fields})
                self._set_state(deal_id, "UNDERWRITING", deal.version, retry_count=retries,
                                retry=True)
                continue
            self._set_state(deal_id, "NEEDS_REVIEW", deal.version, retry_count=retries,
                            escalation=True)
            rec.event("chief", "review.requested", "escalated: check still failing",
                      {"escalation": True, "check": report.status, "mismatches": fields})
            return

    # ------------------------------------------------------------------ housekeeping
    # A deal is never deleted: the log is append-only and IDs must not be reused. Archiving is a
    # logged event that hides the deal from the queue; restoring undoes it.
    BUSY = {"EXTRACTING", "EXTRACTED", "UNDERWRITING", "UNDERWRITTEN", "CHECKING", "CHECKED",
            "SENT_BACK"}

    def archive(self, deal_id: str) -> None:
        status = projections.status(self.store, deal_id)
        if status.state in self.BUSY:
            raise DecisionError(f"deal is still running (state {status.state}); try again when "
                                "it reaches review")
        if not status.archived:
            Recorder(self.store, deal_id, status.deal_version).event(
                "reviewer", "deal.archived", f"archived {deal_id}", {"state": status.state})

    def restore(self, deal_id: str) -> None:
        status = projections.status(self.store, deal_id)
        if status.archived:
            Recorder(self.store, deal_id, status.deal_version).event(
                "reviewer", "deal.restored", f"restored {deal_id}")

    def rename(self, deal_id: str, name: str) -> str:
        name = " ".join(name.split())
        if not name:
            raise DecisionError("a deal name cannot be empty")
        if len(name) > 80:
            raise DecisionError("a deal name is limited to 80 characters")
        status = projections.status(self.store, deal_id)
        self.store.set_name(deal_id, name)
        Recorder(self.store, deal_id, status.deal_version).event(
            "reviewer", "deal.renamed", f"renamed to {name}", {"from": status.name, "to": name})
        return name

    # ------------------------------------------------------------------ reviewer actions
    def latest(self, deal_id: str) -> tuple[Deal, UnderwritingResult, CheckReport | None]:
        deal = self.store.get_deal(deal_id)
        row = self.store.latest_result(deal_id, deal.version)
        result = UnderwritingResult.model_validate(row["result"])
        check = CheckReport.model_validate(row["check"]) if row["check"] else None
        return deal, result, check

    def decide(self, deal_id: str, decision: str, rationale: str = "") -> str:
        """Record the human decision. The AI call is a recommendation only."""
        if self.state(deal_id) != "NEEDS_REVIEW":
            raise DecisionError(f"deal is not awaiting review (state {self.state(deal_id)})")
        if decision == "request_info" and not rationale.strip():
            raise DecisionError("say what you need from the sponsor (a note is required)")
        deal, result, check = self.latest(deal_id)
        rec = Recorder(self.store, deal_id, deal.version)
        status = projections.status(self.store, deal_id)
        rec.event("reviewer", "decision.recorded", f"{decision}: {rationale}".strip(": "),
                  {"decision": decision, "rationale": rationale, "ai_call": result.call,
                   "escalation": status.escalation})
        if decision == "approve":
            self._set_state(deal_id, "APPROVED", deal.version)
            snapshot = Path(result.artifacts["memo_pdf"]).parent / "released.json"
            snapshot.write_text(json.dumps({
                "deal": json.loads(deal.model_dump_json()),
                "result": json.loads(result.model_dump_json()),
                "check": json.loads(check.model_dump_json()) if check else None,
                "decision": {"decision": decision, "rationale": rationale, "ts": now()},
            }, indent=1))
            self._set_state(deal_id, "RELEASED", deal.version)
        elif decision == "reject":
            self._set_state(deal_id, "REJECTED", deal.version)
        elif decision == "send_back":
            self._set_state(deal_id, "SENT_BACK", deal.version)
            self.process(deal_id)
        elif decision == "request_info":
            rec.event("reviewer", "info.requested", f"asked the sponsor: {rationale.strip()}",
                      {"note": rationale.strip()})
            self._set_state(deal_id, "NEEDS_INPUT", deal.version, awaiting="sponsor")
        else:
            raise DecisionError(f"unknown decision {decision!r}")
        return self.state(deal_id)

    # ------------------------------------------------------------------ sponsor replies
    def awaiting_sponsor(self, deal_id: str) -> bool:
        """The reviewer asked for something: the deal has a result and waits on the sponsor."""
        return (self.state(deal_id) == "NEEDS_INPUT"
                and self.store.latest_result(deal_id) is not None)

    def record_reply(self, deal_id: str, text: str = "", files: list[str] | None = None) -> None:
        """What the sponsor said or sent in answer to a request; shown to the reviewer."""
        version = projections.status(self.store, deal_id).deal_version
        Recorder(self.store, deal_id, version).event(
            "intake", "info.replied", "the sponsor replied",
            {"text": text.strip()[:2000], "files": list(files or [])})

    def resume_review(self, deal_id: str) -> None:
        """A reply in words changes no document, so the deal goes straight back to the reviewer
        at the same version (nothing is re-extracted, so confirmed edits are safe)."""
        version = projections.status(self.store, deal_id).deal_version
        self._set_state(deal_id, "NEEDS_REVIEW", version)
        Recorder(self.store, deal_id, version).event(
            "chief", "review.requested", "back in review: the sponsor replied",
            {"escalation": False, "reason": "sponsor replied"})

    # ------------------------------------------------------------------ patches
    def propose_patch(self, deal_id: str, kind: str, path: str, new, reason: str) -> Patch:
        deal, result, _ = self.latest(deal_id)
        if self.state(deal_id) != "NEEDS_REVIEW":
            raise DecisionError("edits are only accepted while the deal is in review")
        if kind == "data":
            old = patching.get_value(deal, path)
            new = float(new)
        elif kind == "narrative":
            section = path.removeprefix("narrative.")
            if section not in result.narrative:
                raise patching.PatchError(f"unknown narrative section {section!r}")
            validate_narrative({section: str(new)})
            fill(str(new), result)                       # unknown placeholders fail loudly
            old = result.narrative[section]
        elif kind == "override":
            if not reason.strip():
                raise patching.PatchError("an override needs a reason")
            old = None
        else:
            raise patching.PatchError(f"unknown patch kind {kind!r}")
        patch = Patch(patch_id=self.store.next_patch_id(), deal_id=deal_id, kind=kind, path=path,
                      old=old, new=new, reason=reason)
        self.store.add_patch(patch)
        Recorder(self.store, deal_id, deal.version).event(
            "chief", "patch.proposed", f"{kind} patch proposed: {path}", patch.model_dump())
        return patch

    def cancel_patch(self, deal_id: str, patch_id: str) -> None:
        patch = self._proposed(deal_id, patch_id)
        self.store.set_patch_status(patch.patch_id, "cancelled")
        Recorder(self.store, deal_id, self.store.get_deal(deal_id).version).event(
            "reviewer", "patch.cancelled", f"patch {patch_id} cancelled", {"patch_id": patch_id})

    def _proposed(self, deal_id: str, patch_id: str) -> Patch:
        patch = self.store.get_patch(patch_id)
        if not patch or patch.deal_id != deal_id or patch.status != "proposed":
            raise patching.PatchError(f"no proposed patch {patch_id} on {deal_id}")
        return patch

    def confirm_patch(self, deal_id: str, patch_id: str) -> str:
        """Only a reviewer's click calls this; a model never does."""
        with self._lock(deal_id):
            patch = self._proposed(deal_id, patch_id)
            deal, result, check = self.latest(deal_id)
            self.store.set_patch_status(patch_id, "confirmed")
            rec = Recorder(self.store, deal_id, deal.version)
            rec.event("reviewer", "patch.confirmed", f"patch {patch_id} confirmed",
                      {"patch_id": patch_id, "kind": patch.kind, "path": patch.path})
            try:
                if patch.kind == "data":
                    self._confirm_data(deal_id, deal, patch)
                else:
                    self._confirm_text(deal_id, deal, result, check, patch)
            except Exception as exc:  # noqa: BLE001
                self._fail(deal_id, exc)
        return self.state(deal_id)

    def _confirm_data(self, deal_id: str, deal: Deal, patch: Patch) -> None:
        new_deal = patching.apply_data_patch(deal, patch.path, patch.new, patch.reason)
        self.store.save_deal(new_deal)
        Recorder(self.store, deal_id, new_deal.version).event(
            "chief", "version.created", f"deal version {new_deal.version} created",
            {"from": deal.version, "to": new_deal.version, "patch_id": patch.patch_id})
        self._set_state(deal_id, "UNDERWRITING", new_deal.version, retry_count=0)
        self._underwrite_and_check(deal_id, new_deal)

    def _confirm_text(self, deal_id: str, deal: Deal, result: UnderwritingResult,
                      check: CheckReport | None, patch: Patch) -> None:
        """Narrative edit or override: re-render the memo only, then re-run the memo check."""
        rec = Recorder(self.store, deal_id, deal.version)
        if patch.kind == "narrative":
            section = patch.path.removeprefix("narrative.")
            validate_narrative({section: str(patch.new)})
            result.narrative[section] = str(patch.new)
        else:
            result.overrides.append(f"{patch.new} (reason: {patch.reason})")
            rec.event("reviewer", "override.recorded", f"override recorded: {patch.new}",
                      {"patch_id": patch.patch_id, "reason": patch.reason})
        render_memo(deal, result, Path(result.artifacts["memo_pdf"]))
        rec.event("chief", "memo.rendered", "memo re-rendered",
                  {"memo_pdf": result.artifacts["memo_pdf"], "edit": patch.kind})
        row = self.store.latest_result(deal_id, deal.version)
        report = recheck_memo(check, deal, result, self.deal_dir(deal_id),
                              self._overrides(deal_id)) if check else None
        self.store.save_result(deal_id, deal.version, row["attempt"], result.model_dump_json(),
                               report.model_dump_json() if report else None)
        rec.event("checker", "check.completed",
                  f"memo re-checked: {report.status if report else 'n/a'}",
                  {"status": report.status if report else None, "scope": "memo_number_match"})
