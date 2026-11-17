"""Intake chat agent (external). Collects the documents and facts the checklist needs.

It never sees file contents beyond classification hints, never reads deals or outputs, and never
says anything about underwriting. Reply text is composed here from checklist status only; the
runner's job is limited to reading the person's message (facts, and whether they are asking for a
decision). Tools: classify_file, record_fact (allowlisted keys), submit_deal (only when ready).
"""
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

from bridge.agents.chief import Chief
from bridge.agents.recorder import Recorder
from bridge.agents.runner import AgentRunner
from bridge.core.completeness import DEFAULT_CHECKLIST_PATH
from bridge.core.parsers.classify import classify
from bridge.core.parsers.documents import read_document_text
from bridge.core.parsers.errors import ParseError
from bridge.core.parsers.pdftable import pdf_grid
from bridge.store import projections

HUMAN = {"deal_summary": "deal summary", "purchase_contract": "purchase contract",
         "rent_roll": "rent roll", "t12": "T-12", "renovation_budget": "renovation budget"}
FACT_PROMPT = {
    "property_address": "the property address", "asset_type": "the asset type (multifamily or "
    "mixed use)", "unit_count": "how many units the property has",
    "loan_amount_requested": "the loan amount you are requesting",
    "purchase_price": "the purchase price", "renovation_budget": "the renovation budget",
    "sponsor_name": "the sponsor's name",
}
FACT_HUMAN = {"property_address": "address", "asset_type": "asset type", "unit_count": "unit count",
              "loan_amount_requested": "requested loan amount", "purchase_price": "purchase price",
              "renovation_budget": "renovation budget", "sponsor_name": "sponsor name"}
REFUSAL = ("I can't discuss underwriting results, rates, or approval odds. The team will follow "
           "up after review.")
TABLE_LABELS = {"rent_roll", "t12", "renovation_budget"}
SAMPLE_REMINDER = "This is a sample-data prototype, so please use sample data only."


@dataclass
class IncomingFile:
    filename: str
    content: bytes
    label: str | None = None          # set when the person confirms what a file is


class IntakeAgent:
    def __init__(self, chief: Chief, runner: AgentRunner, checklist_path: Path | None = None):
        self.chief, self.runner = chief, runner
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

    # ---- one chat turn
    def handle(self, deal_id: str, message: str = "", files: list[IncomingFile] | None = None
               ) -> dict:
        notes: list[str] = []
        for f in files or []:
            notes.append(self._take_file(deal_id, f))
        asked_for_decision = False
        if message.strip():
            turn = self.runner.interpret_intake(message)
            asked_for_decision = turn.asks_for_decision
            for key, value in turn.facts.items():
                if key in FACT_PROMPT:                      # allowlist
                    self.chief.record_fact(deal_id, key, value)
                    notes.append(f"Noted the {FACT_HUMAN[key]}.")
        checklist = self.chief.update_checklist(deal_id)
        submitted = False
        if checklist["ready"] and self.chief.state(deal_id) == "READY":
            submitted = self.submit_deal(deal_id)
        parts = notes[:]
        if asked_for_decision:
            parts.append(REFUSAL)
        parts.append(self._next_step(checklist))
        return {"reply": " ".join(p for p in parts if p), "checklist": checklist,
                "submitted": submitted}

    def _take_file(self, deal_id: str, f: IncomingFile) -> str:
        ext = Path(f.filename).suffix.lower().lstrip(".")
        if ext not in self.allowed:
            return f"I can't accept .{ext or 'unknown'} files. Allowed: " \
                   f"{', '.join(sorted(self.allowed))}."
        if len(f.content) > self.max_bytes:
            return f"{f.filename} is larger than {self.max_bytes // (1024 * 1024)} MB."
        existing = self.chief.store.files(deal_id)
        if any(x["filename"] == f.filename and x["size"] == len(f.content) for x in existing):
            return f"I already have {f.filename}."
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
        return f"{'Updated' if replaced else 'Got'} your {HUMAN[label]}."

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

    def _next_step(self, checklist: dict) -> str:
        if checklist["ready"]:
            return "That's everything I need. The team will review your package and follow up."
        if checklist["missing"]:
            have = [HUMAN[d] for d in checklist["received"]]
            prefix = f"So far I have your {', '.join(have)}. " if have else ""
            return f"{prefix}Next I need your {HUMAN[checklist['missing'][0]]}."
        return f"One last thing: could you tell me {FACT_PROMPT[checklist['facts_missing'][0]]}?"

    # ---- status posted into the chat from deal state (never ratios, reasons or decisions)
    def status_message(self, deal_id: str) -> str:
        state = projections.status(self.chief.store, deal_id).state
        if state in ("CREATED", "AWAITING_DOCS"):
            return self._next_step(self.chief.update_checklist(deal_id))
        if state == "NEEDS_INPUT":
            return "We need one more item from you; the team will be in touch."
        if state in ("REJECTED", "APPROVED", "RELEASED"):
            return "The team has finished its review and will follow up with you."
        if state == "FAILED":
            return "Something went wrong on our side; the team will follow up."
        return "Under review."
