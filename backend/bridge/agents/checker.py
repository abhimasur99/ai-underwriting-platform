"""Checker agent. Uses ONLY core/independent/ (own parser, own formulas) plus the underwriter's
outputs. Status comes from code: a numeric mismatch, an untraceable field, a hardcoded metric cell
or an unmatched memo number is `fail`; non-numeric concerns are `warn`; otherwise `pass`."""
from pathlib import Path

from bridge.agents.recorder import Recorder
from bridge.agents.runner import AgentRunner
from bridge.agents.tools.registry import Tool, ToolRegistry
from bridge.core.independent import formulas, parse, pdftext, trace, xl
from bridge.core.independent.overrides import apply_overrides
from bridge.core.schema import (
    CheckItem,
    CheckReport,
    Deal,
    Flag,
    Mismatch,
    UnderwritingResult,
)

KEY_INPUTS = ["purchase_price", "renovation_budget", "loan_commitment", "initial_advance",
              "as_is_value", "arv", "stabilized_noi", "in_place_noi", "note_rate"]


def flatten_result(r: UnderwritingResult) -> dict:
    """The underwriter's outputs as the same flat keys the checker's recompute uses."""
    flat = r.metrics.model_dump()
    for prefix, a in (("", r.exit), ("stress_", r.stress)):
        flat.update({f"{prefix}cap_{k}": v for k, v in a.caps.model_dump().items()})
        flat.update({f"{prefix}binding": a.binding, f"{prefix}takeout_max": a.takeout_max,
                     f"{prefix}refi_cushion": a.refi_cushion, f"{prefix}exit_dscr": a.exit_dscr})
    flat.update(payoff=r.exit.payoff, stress_noi=r.stress.noi, stress_rate=r.stress.rate)
    gaps = {i.name: i.gap for i in r.reconciliation if i.gap is not None}
    flat["rent_roll_vs_t12_gap"] = gaps["rent_roll_vs_t12"]
    flat["sources_vs_uses_gap"] = gaps["sources_vs_uses"]
    return flat


def _deal_inputs(deal: Deal) -> dict:
    return {
        "purchase_price": deal.purchase.purchase_price.value,
        "renovation_budget": deal.renovation.renovation_budget.value,
        "loan_commitment": deal.loan_request.loan_commitment.value,
        "initial_advance": deal.loan_request.initial_advance.value,
        "as_is_value": deal.valuation.as_is_value.value, "arv": deal.valuation.arv.value,
        "stabilized_noi": deal.pro_forma.stabilized_noi.value,
        "in_place_noi": deal.t12.in_place_noi.value, "note_rate": deal.loan_request.note_rate.value,
    }


def _status(*parts: str) -> str:
    return "fail" if "fail" in parts else ("warn" if "warn" in parts else "pass")


def run_checker(deal: Deal, result: UnderwritingResult, deal_dir: Path, rec: Recorder,
                runner: AgentRunner, rules_path: Path | None = None,
                overrides: list[dict] | None = None) -> CheckReport:
    """`overrides`: confirmed reviewer data patches in effect, as {"path", "new"} dicts."""
    cfg = formulas.load_config(rules_path)
    memo, workbook = Path(result.artifacts["memo_pdf"]), Path(result.artifacts["workbook"])
    reg = ToolRegistry("checker", rec)
    state: dict = {}
    reg.add(Tool("independent_parse", "Parse the raw files with the checker's own parser",
                 lambda: parse.independent_parse(deal_dir)))
    reg.add(Tool("independent_recompute", "Recompute every metric with the checker's formulas",
                 lambda: formulas.independent_recompute(state["inputs"], cfg)))
    reg.add(Tool("compare_metrics", "Compare underwriter and independent metrics",
                 lambda: formulas.compare_metrics(flatten_result(result), state["metrics"])))
    reg.add(Tool("rules_recheck", "Re-run the rules independently",
                 lambda: formulas.rules_recheck(state["inputs"], state["metrics"], cfg)))
    reg.add(Tool("reconcile_recheck", "Re-run reconciliation independently",
                 lambda: formulas.reconcile_recheck(state["inputs"], cfg)))
    reg.add(Tool("source_trace", "Every sourced field must trace to its document",
                 lambda: trace.source_trace(deal, deal_dir)))
    reg.add(Tool("workbook_audit", "Metric cells must be formulas that recalculate correctly",
                 lambda: xl.workbook_audit(workbook, state["metrics"])))
    reg.add(Tool("memo_number_match", "Every memo number must trace to the checker's figures",
                 lambda: pdftext.memo_number_match(memo, state["inputs"], state["metrics"], cfg,
                                                   result.call)))

    state["inputs"] = reg.call("independent_parse")
    if overrides:
        state["inputs"] = apply_overrides(state["inputs"], overrides)
    state["metrics"] = reg.call("independent_recompute")
    raw_mismatches = reg.call("compare_metrics")
    call_i, codes_i = reg.call("rules_recheck")
    recon_i = reg.call("reconcile_recheck")
    problems = reg.call("source_trace")
    audit = reg.call("workbook_audit")
    memo_check = reg.call("memo_number_match")

    mismatches = [Mismatch(field=m["field"], underwriter=m["a"], independent=m["b"],
                           diff=m["diff"]) for m in raw_mismatches]
    for m in mismatches:
        m.likely_cause = runner.explain_mismatch(m)

    extraction_diffs = formulas.compare_metrics(_deal_inputs(deal), {
        k: state["inputs"][k] for k in KEY_INPUTS})
    codes_u = [r.code for r in result.reasons if r.code != "LOW_CONFIDENCE_FIELD"]
    recon_u = {i.name: i.status for i in result.reconciliation}
    recon_disagree = [n for n, v in recon_i.items() if recon_u.get(n) != v["status"]]
    max_diff = max((m.diff for m in mismatches if m.diff is not None), default=0.0)

    checks = [
        CheckItem(name="recompute_metrics", status="fail" if mismatches else "pass",
                  detail={"max_abs_diff": max_diff, "fields": [m.field for m in mismatches]}),
        CheckItem(name="extraction_match", status="fail" if extraction_diffs else "pass",
                  detail={"fields": [d["field"] for d in extraction_diffs]}),
        CheckItem(name="rules_recheck",
                  status="warn" if (call_i != result.call or codes_i != codes_u) else "pass",
                  detail={"independent_call": call_i, "independent_reasons": codes_i,
                          "underwriter_call": result.call, "underwriter_reasons": codes_u}),
        CheckItem(name="reconcile_recheck", status="warn" if recon_disagree else "pass",
                  detail={"disagree": recon_disagree}),
        CheckItem(name="source_trace", status="fail" if problems else "pass",
                  detail={"untraceable_fields": problems}),
        CheckItem(name="workbook_audit",
                  status="fail" if (audit["hardcoded"] or audit["mismatches"]
                                    or audit["missing"]) else "pass",
                  detail={"hardcoded_metric_cells": audit["hardcoded"],
                          "mismatches": audit["mismatches"], "missing": audit["missing"]}),
        CheckItem(name="memo_number_match",
                  status="fail" if (memo_check["unmatched"] or not memo_check["call_ok"])
                  else "pass",
                  detail={"unmatched_numbers": memo_check["unmatched"],
                          "call_ok": memo_check["call_ok"]}),
        CheckItem(name="open_flags", status="warn" if result.flags else "pass",
                  detail={"flags": [f.code for f in result.flags]}),
    ]
    flags = [Flag(code=f.code, message=f.message, field=f.field) for f in result.flags]
    report = CheckReport(deal_id=deal.deal_id, deal_version=deal.version,
                         status=_status(*[c.status for c in checks]), checks=checks,
                         mismatches=mismatches, flags=flags)
    report.summary = runner.explain_check(report)
    rec.event("checker", "check.completed", f"check {report.status}",
              {"status": report.status, "mismatches": [m.field for m in mismatches],
               "attempt": rec.version})
    return report
