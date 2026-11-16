"""Underwriter agent. Calls the tool registry in a fixed order (every call logged), takes the
call from rules.evaluate (final), asks the runner for narrative text with placeholders, validates
that no digit sits outside a placeholder (one regeneration), then renders workbook and memo."""
from dataclasses import dataclass
from pathlib import Path

from bridge.agents.recorder import Recorder
from bridge.agents.runner import AgentRunner
from bridge.agents.tools.underwriter_tools import build_underwriter_tools, render_paths
from bridge.core.placeholders import NarrativeError, validate_narrative
from bridge.core.rules import RulesConfig
from bridge.core.schema import Deal, Metrics, UnderwritingResult
from bridge.core.underwrite import open_questions


@dataclass(frozen=True)
class FaultPlan:
    """Test and demo hook (`--force-mismatch`): nudge one underwriter metric on given attempts so
    the checker has something to catch."""
    metric: str = "ltc"
    delta: float = 0.01
    attempts: frozenset[int] = frozenset({1})

    def apply(self, attempt: int, metrics: dict) -> dict:
        if attempt in self.attempts:
            metrics = {**metrics, self.metric: metrics[self.metric] + self.delta}
        return metrics


def _draft_narrative(runner: AgentRunner, result: UnderwritingResult, rec: Recorder
                     ) -> dict[str, str]:
    feedback = None
    for attempt in (1, 2):
        narrative = runner.write_narrative(result, feedback)
        try:
            validate_narrative(narrative)
        except NarrativeError as exc:
            feedback = str(exc)
            rec.tool_call("underwriter", "narrative.write", {"attempt": attempt}, None,
                          {"rejected": feedback})
            if attempt == 2:
                raise
            continue
        rec.tool_call("underwriter", "narrative.write", {"attempt": attempt}, None,
                      {"sections": sorted(narrative)})
        return narrative
    raise AssertionError("unreachable")


def run_underwriter(deal: Deal, rec: Recorder, rules: RulesConfig, runner: AgentRunner,
                    outputs_dir: Path, attempt: int = 1, feedback: str | None = None,
                    faults: FaultPlan | None = None) -> UnderwritingResult:
    state: dict = {}
    reg = build_underwriter_tools(rec, rules, deal, state)
    lr, val = deal.loan_request, deal.valuation
    commitment, noi, arv = lr.loan_commitment.value, deal.pro_forma.stabilized_noi.value, \
        val.arv.value

    total_cost = reg.call("calc.total_cost", uses=[r.amount for r in deal.sources_uses.uses])
    values = {
        "total_cost": total_cost,
        "ltc": reg.call("calc.ltc", loan_commitment=commitment, total_cost=total_cost),
        "ltv_as_is": reg.call("calc.ltv_as_is", initial_advance=lr.initial_advance.value,
                              as_is_value=val.as_is_value.value),
        "loan_to_arv": reg.call("calc.loan_to_arv", loan_commitment=commitment, arv=arv),
        "dscr_in_place": reg.call("calc.dscr_in_place", in_place_noi=deal.t12.in_place_noi.value,
                                  initial_advance=lr.initial_advance.value,
                                  note_rate=lr.note_rate.value),
        "debt_yield_stabilized": reg.call("calc.debt_yield", stabilized_noi=noi,
                                          loan_commitment=commitment),
        "implied_cap_rate": reg.call("calc.implied_cap_rate", stabilized_noi=noi, arv=arv),
    }
    if faults:
        values = faults.apply(attempt, values)
    metrics = Metrics(**values)
    recon, recon_flags = reg.call("reconcile.all")
    exit_ = reg.call("exit.analyze", noi=noi, arv=arv, loan_commitment=commitment)
    stress = reg.call("exit.stress", noi=noi, arv=arv, loan_commitment=commitment)
    outcome = reg.call("rules.evaluate", metrics=metrics, exit_=exit_, stress=stress,
                       reconciliation=recon)
    flags = [*deal.flags, *recon_flags]
    result = UnderwritingResult(
        deal_id=deal.deal_id, deal_version=deal.version, rules_version=rules.version,
        call=outcome.call, reasons=outcome.reasons, metrics=metrics, exit=exit_, stress=stress,
        reconciliation=recon, rule_checks=outcome.checks, flags=flags,
        open_questions=open_questions(outcome.reasons, flags))
    result.narrative = _draft_narrative(runner, result, rec)

    memo, workbook = render_paths(outputs_dir, deal.deal_id, deal.version)
    state["result"] = result
    reg.call("render.workbook", path=str(workbook))
    reg.call("render.memo", path=str(memo))
    result.artifacts = {"memo_pdf": str(memo), "workbook": str(workbook)}
    rec.event("underwriter", "memo.rendered", "memo.pdf and workbook.xlsx written",
              {"memo_pdf": str(memo), "workbook": str(workbook)})
    rec.event("underwriter", "underwriting.completed", f"call: {result.call}",
              {"call": result.call, "flags": len(flags), "attempt": attempt,
               "reasons": [r.code for r in result.reasons]})
    return result
