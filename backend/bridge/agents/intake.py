"""Intake chat agent (external). Collects the documents and details the checklist needs.

It never sees file contents beyond classification hints and the basic details read from the
documents, never reads deals or outputs, and never says anything about underwriting. Reply text is
composed by code from the checklist and the deal's state (agents/intake_replies.py); the runner's
job is limited to reading the person's message (details, what they are doing, and whether they are
asking for a decision). In live mode a model may rephrase a reply and code checks it first
(agents/phrasing.py). Tools: classify_file, record_fact (allowlisted keys), submit_deal (only when
ready). The conversation is recorded in the event log so it survives a reload.
"""
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

from bridge.agents import intake_replies as say
from bridge.agents.chief import Chief
from bridge.agents.phrasing import Phraser
from bridge.agents.recorder import Recorder
from bridge.agents.runner import AgentRunner
from bridge.agents.runner_types import IntakeTurn
from bridge.core.completeness import DEFAULT_CHECKLIST_PATH
from bridge.core.parsers.classify import classify
from bridge.core.parsers.documents import read_document_text
from bridge.core.parsers.errors import ParseError
from bridge.core.parsers.pdftable import pdf_grid
from bridge.store import projections

HUMAN = say.DOCS
FACT_PROMPT = say.FACT_ASK
FACT_HUMAN = say.FACT_NAME
REFUSAL = say.REFUSAL
TABLE_LABELS = {"rent_roll", "t12", "renovation_budget"}
MONEY_FACTS = {"loan_amount_requested", "purchase_price", "renovation_budget"}


def describe(fact) -> str:
    """One detail as the sponsor would say it: 'address 88 Sample Court', '24 units'."""
    value = f"${int(fact.value):,}" if fact.key in MONEY_FACTS else fact.value
    label = {"unit_count": "units"}.get(fact.key, say.FACT_NAME[fact.key])
    return f"{value} {label}" if fact.key == "unit_count" else f"{label} {value}"


@dataclass
class IncomingFile:
    filename: str
    content: bytes
    label: str | None = None          # set when the person confirms what a file is


class IntakeAgent:
    def __init__(self, chief: Chief, runner: AgentRunner, checklist_path: Path | None = None):
        self.chief, self.runner = chief, runner
        self.phraser = Phraser(runner)
        cfg = yaml.safe_load((checklist_path or DEFAULT_CHECKLIST_PATH).read_text())
        self.max_bytes = int(cfg["upload_limits"]["max_file_mb"]) * 1024 * 1024
        self.allowed = set(cfg["upload_limits"]["allowed_extensions"])
        self.accepted = {d["type"]: set(d["accepted"]) for d in cfg["required_documents"]}

    # ---- tools
    def classify_file(self, f: IncomingFile):
        return classify(f.filename, f.content)

    def submit_deal(self, deal_id: str) -> bool:
        """Allowed only when the checklist says ready; hands the deal to the chief."""
        status = self.chief.update_checklist(deal_id)
        if not status["ready"]:
            raise RuntimeError("cannot submit: the checklist is not complete")
        Recorder(self.chief.store, deal_id).event("intake", "deal.submitted",
                                                  "deal submitted to the chief")
        return True

    # ---- the conversation, kept in the event log
    def _log(self, deal_id: str, actor: str, type_: str, text: str) -> None:
        version = projections.status(self.chief.store, deal_id).deal_version
        Recorder(self.chief.store, deal_id, version).event(actor, type_, text[:120], {"text": text})

    def history(self, deal_id: str) -> list[tuple[str, str]]:
        roles = {"chat.sponsor": "sponsor", "chat.assistant": "assistant"}
        return [(roles[e.type], e.payload.get("text", ""))
                for e in self.chief.store.events(deal_id) if e.type in roles]

    def _ctx(self, deal_id: str, checklist: dict, turn: int) -> say.Ctx:
        store = self.chief.store
        note = next((e.payload.get("note", "") for e in reversed(store.events(deal_id))
                     if e.type == "info.requested"), "")
        return say.Ctx(received=checklist["received"], missing=checklist["missing"],
                       facts_missing=checklist["facts_missing"], ready=checklist["ready"],
                       state=self.chief.state(deal_id), turn=turn, note=note,
                       awaiting=self.chief.awaiting_sponsor(deal_id))

    # ---- one chat turn
    def handle(self, deal_id: str, message: str = "", files: list[IncomingFile] | None = None
               ) -> dict:
        store = self.chief.store
        message = message.strip()
        turns = sum(1 for e in store.events(deal_id) if e.type == "chat.sponsor")
        if message:
            self._log(deal_id, "sponsor", "chat.sponsor", message)
        past = self.history(deal_id)[:-1] if message else self.history(deal_id)

        def finish(draft: str, checklist: dict, submitted: bool) -> dict:
            reply = self.phraser.sponsor(draft, past)
            self._log(deal_id, "intake", "chat.assistant", reply)
            return {"reply": reply, "checklist": checklist, "submitted": submitted}

        awaiting = self.chief.awaiting_sponsor(deal_id)       # the reviewer asked for something
        known = len(store.files(deal_id))
        receipts = [self._take_file(deal_id, f) for f in files or []]
        sent = [x["filename"] for x in store.files(deal_id)[known:]]
        turn = self.runner.interpret_intake(message) if message else IntakeTurn()
        noted: list[str] = []
        if message and not awaiting:      # while a reviewer's question is open, a message is a
            for key, value in turn.facts.items():             # reply, not new deal facts
                if key in say.FACT_ASK:                         # allowlist
                    self.chief.record_fact(deal_id, key, value)
                    noted.append(key)
        if awaiting:
            if files and not sent:       # every upload was refused or a duplicate: keep waiting
                still = "Thank you, but the team is still waiting for what they asked for."
                return finish(" ".join([*receipts, still]), self.chief.checklist(deal_id), False)
            if message or sent:
                self.chief.record_reply(deal_id, message, sent)
                if not sent:             # words only: no document changed, back to the reviewer
                    self.chief.resume_review(deal_id)
                    parts = [say.REFUSAL] if turn.asks_for_decision else []
                    parts.append("Thank you, I've passed that to the team.")
                    return finish(" ".join(parts), self.chief.checklist(deal_id), False)
        checklist = self.chief.update_checklist(deal_id)
        submitted = False
        if checklist["ready"] and self.chief.state(deal_id) == "READY":
            submitted = self.submit_deal(deal_id)
        checklist = self.chief.checklist(deal_id)
        ctx = self._ctx(deal_id, checklist, turns)
        parts = list(receipts)
        if noted:
            parts.append(say.facts_noted(noted))
        if turn.asks_for_decision:
            parts.append(say.refusal(ctx))
        elif message and not receipts and not noted:
            parts.append(say.TOPICS.get(turn.intent, say.unclear)(ctx))
        else:
            parts.append(say.ask_next(ctx, after_receipt=bool(receipts or noted)))
        return finish(" ".join(p for p in parts if p), checklist, submitted)

    def _take_file(self, deal_id: str, f: IncomingFile) -> str:
        ext = Path(f.filename).suffix.lower().lstrip(".")
        if ext not in self.allowed:
            return (f"I'm sorry, I can't accept .{ext or 'unknown'} files. The formats I can take "
                    f"are {', '.join(sorted(self.allowed))}.")
        if len(f.content) > self.max_bytes:
            return (f"{f.filename} is larger than {self.max_bytes // (1024 * 1024)} MB, which is "
                    "more than I can accept. Could you send a smaller copy?")
        existing = self.chief.store.files(deal_id)
        if any(self._same_file(x, f) for x in existing):
            return f"I already have {f.filename}, so there is nothing more to do for it."
        label = f.label
        if label is None:
            c = self.classify_file(f)
            if c.status != "ok":
                options = " or ".join(HUMAN.get(x, x) for x in c.candidates)
                ask = f"Is {f.filename} your {options}?" if options else \
                    f"What kind of document is {f.filename}?"
                return f"I'm not sure what {f.filename} is. {ask}"
            label = c.label
        if label not in HUMAN:
            return f"{label} is not a document type I collect."
        if ext not in self.accepted[label]:
            ok = ", ".join(sorted(self.accepted[label]))
            return f"For the {HUMAN[label]} I can accept: {ok}."
        problem = self._unreadable(f, label, ext)
        if problem:
            return problem
        replaced = any(x["label"] == label for x in existing)
        self.chief.register_file(deal_id, f.filename, f.content, label)
        receipt = say.received(label, replaced)
        read = self.chief.read_details(deal_id)
        if read:
            receipt += (f" From it I read: {'; '.join(describe(r) for r in read)}. "
                        "Please tell me if anything is wrong.")
        return receipt

    @staticmethod
    def _same_file(stored: dict, f: IncomingFile) -> bool:
        """The same name and the same bytes (a corrected file of the same length is not a copy)."""
        path = Path(stored["path"])
        return (stored["filename"] == f.filename and stored["size"] == len(f.content)
                and path.exists() and path.read_bytes() == f.content)

    @staticmethod
    def _unreadable(f: IncomingFile, label: str, ext: str) -> str | None:
        """PDF and Word files are read right away, so a problem is reported in the chat now
        instead of as a stopped deal later. Returns the reply to give, or None if it reads."""
        if ext not in ("pdf", "docx"):
            return None
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"doc.{ext}"
            path.write_bytes(f.content)
            try:
                if label in TABLE_LABELS:
                    pdf_grid(path)          # tables are only accepted as pdf here
                else:
                    read_document_text(path)
            except ParseError:
                if label in TABLE_LABELS:
                    return (f"I couldn't find a table in {f.filename}. Could you send the "
                            f"{HUMAN[label]} as a CSV or Excel file?")
                return (f"I can't read text from {f.filename} (it may be a scan). Could you "
                        f"send a text PDF or a Word file?")
        return None

    # ---- status posted into the chat from deal state (never ratios, reasons or decisions)
    def status_message(self, deal_id: str) -> str:
        checklist = self.chief.checklist(deal_id)
        return say.ask_next(self._ctx(deal_id, checklist, turn=0))
