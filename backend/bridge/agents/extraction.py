"""Extraction agent: documents in, a sourced Deal out. Never guesses a missing required field;
it returns `needs_input` naming what is missing. Cached mode loads cached/extracted.json."""
from dataclasses import dataclass, field
from pathlib import Path

from bridge.agents.recorder import Recorder
from bridge.agents.runner import AgentRunner
from bridge.core.parsers.errors import MissingRequiredFieldError, ParseError
from bridge.core.schema import Deal

LOW_CONFIDENCE = 0.80


@dataclass
class ExtractionOutcome:
    status: str                       # "ok" or "needs_input"
    deal: Deal | None = None
    missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def run_extraction(deal_dir: Path, runner: AgentRunner, rec: Recorder) -> ExtractionOutcome:
    try:
        deal = runner.extract_deal(Path(deal_dir))
    except MissingRequiredFieldError as exc:
        rec.tool_call("extraction", "extract.documents", {"mode": runner.mode}, None,
                      {"missing": exc.missing})
        return ExtractionOutcome("needs_input", missing=exc.missing)
    except FileNotFoundError as exc:
        rec.tool_call("extraction", "extract.documents", {"mode": runner.mode}, None,
                      {"missing_document": str(exc)})
        return ExtractionOutcome("needs_input", missing=[str(exc)])
    except ParseError as exc:
        rec.tool_call("extraction", "extract.documents", {"mode": runner.mode}, None,
                      {"parse_error": str(exc)})
        return ExtractionOutcome("needs_input", missing=[str(exc)])
    low = [n for n in ("purchase_price", "renovation_budget", "loan_commitment",
                       "initial_advance", "as_is_value", "arv", "stabilized_noi", "unit_count",
                       "note_rate") if deal.key_field(n).confidence < LOW_CONFIDENCE]
    notes = [f.message for f in deal.flags]
    rec.tool_call("extraction", "extract.documents", {"mode": runner.mode}, None,
                  {"deal_id": deal.deal_id, "units": len(deal.rent_roll.units),
                   "flags": [f.code for f in deal.flags], "low_confidence": low})
    rec.event("extraction", "extraction.completed", f"extracted {deal.deal_id}",
              {"flags": [f.code for f in deal.flags], "low_confidence": low})
    return ExtractionOutcome("ok", deal=deal, notes=notes)
