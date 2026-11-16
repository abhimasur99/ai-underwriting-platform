"""AgentRunner: the only place a model may be involved. Two implementations:
CachedRunner (offline, deterministic; used by demos, tests and CI) and ClaudeRunner (--live).
"""
import json
from pathlib import Path
from typing import Protocol

from bridge.agents import cached_nlu
from bridge.agents.runner_types import ChiefTurn, IntakeTurn
from bridge.core.narrative import default_narrative
from bridge.core.parsers import parse_deal_dir
from bridge.core.schema import CheckReport, Deal, Mismatch, UnderwritingResult


class AgentRunner(Protocol):
    mode: str

    def extract_deal(self, deal_dir: Path) -> Deal: ...

    def write_narrative(self, result: UnderwritingResult, feedback: str | None = None
                        ) -> dict[str, str]: ...

    def explain_mismatch(self, mismatch: Mismatch) -> str: ...

    def explain_check(self, report: CheckReport) -> str: ...

    def interpret_intake(self, message: str) -> IntakeTurn: ...

    def interpret_chief(self, message: str) -> ChiefTurn: ...


_INPUT_HINTS = {
    "ltc": "loan_commitment or total cost (sum of uses)",
    "ltv_as_is": "initial_advance or as_is_value",
    "loan_to_arv": "loan_commitment or arv",
    "dscr_in_place": "in-place NOI (T-12 parse), initial_advance or note_rate",
    "debt_yield_stabilized": "stabilized_noi or loan_commitment",
    "implied_cap_rate": "stabilized_noi or arv",
    "total_cost": "the uses rows",
    "rent_roll_vs_t12_gap": "the rent roll or T-12 parse",
    "sources_vs_uses_gap": "the sources or uses rows",
}


class CachedRunner:
    """Offline runner. Reads `cached/*.json` next to a sample deal when present, otherwise falls
    back to deterministic code (parsers, template narrative, templated explanations)."""

    mode = "cached"

    def extract_deal(self, deal_dir: Path) -> Deal:
        cached = Path(deal_dir) / "cached" / "extracted.json"
        if cached.exists():
            return Deal.model_validate_json(cached.read_text())
        return parse_deal_dir(deal_dir)

    def write_narrative(self, result: UnderwritingResult, feedback: str | None = None
                        ) -> dict[str, str]:
        return default_narrative(result)

    def explain_mismatch(self, m: Mismatch) -> str:
        hint = _INPUT_HINTS.get(m.field)
        if m.field.endswith("binding") or m.field in ("binding", "stress_binding"):
            return "The two sizing paths picked a different binding cap, so an input to one " \
                   "of the three caps differs."
        if hint:
            return f"Different input or parsing of {hint}; the formulas agree only if the " \
                   "inputs agree."
        return "Cause unknown from the tool output."

    def explain_check(self, report: CheckReport) -> str:
        if report.status == "pass":
            return "Independent recompute matches on all metrics; artifacts trace to the sources."
        bad = [c.name for c in report.checks if c.status != "pass"]
        fields = ", ".join(m.field for m in report.mismatches[:5])
        text = f"Check {report.status}: {', '.join(bad)}."
        return text + (f" Mismatched fields: {fields}." if fields else "")


    def interpret_intake(self, message: str) -> IntakeTurn:
        return cached_nlu.interpret_intake(message)

    def interpret_chief(self, message: str) -> ChiefTurn:
        return cached_nlu.interpret_chief(message)


def load_cached_json(path: Path) -> dict:
    return json.loads(path.read_text())

