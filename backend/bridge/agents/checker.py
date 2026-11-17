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


def _inputs_from_deal(deal: Deal) -> dict:
    """The same keys the checker's own parser produces, read from the extracted deal instead. Used
    only when a model had to read the documents and the checker's regexes cannot (so there is no
    second parse); the source trace below then carries the weight."""
    units = deal.rent_roll.units
    return {
        **_deal_inputs(deal),
        "deal_id": deal.deal_id, "asset_type": deal.property.asset_type.value,
        "unit_count": deal.property.unit_count.value,
        "occupied_units": deal.property.occupied_units.value,
        "sources": [{"name": r.name, "amount": r.amount} for r in deal.sources_uses.sources],
        "uses": [{"name": r.name, "amount": r.amount} for r in deal.sources_uses.uses],
        "sources_stated_total": deal.sources_uses.stated_total_sources.value,
        "uses_stated_total": deal.sources_uses.stated_total_uses.value,
        "rent_roll_rows": len(units),
        "rent_roll_units": [{"unit": u.unit, "status": u.status, "rent": u.monthly_rent}
                            for u in units],
        "rent_roll_annual": deal.rent_roll.annual_occupied_rent.value,
        "t12_rental_income": deal.t12.rental_income.value,
        "t12_total_income": deal.t12.total_income.value,
        "t12_total_expenses": deal.t12.total_expenses.value,
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
    def independent_parse() -> dict:
        try:
            return parse.independent_parse(deal_dir)
        except (ValueError, KeyError, IndexError, StopIteration, FileNotFoundError) as exc:
            if not any(f.code == "MODEL_ASSISTED_EXTRACTION" for f in deal.flags):
                raise                     # a deterministic deal the checker cannot parse is a bug
            return {**_inputs_from_deal(deal), "_not_reparsed": str(exc)[:200]}

    reg.add(Tool("independent_parse", "Parse the raw files with the checker's own parser",
                 independent_parse))
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
    not_reparsed = state["inputs"].pop("_not_reparsed", None)
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
    # LOW_CONFIDENCE_FIELD is an extraction concept the checker has no view on, so the call it can
    # reproduce is the underwriter's call without those reasons.
    rule_reasons = [r for r in result.reasons if r.code != "LOW_CONFIDENCE_FIELD"]
    codes_u = [r.code for r in rule_reasons]
    call_u = ("decline" if any(r.severity == "decline" for r in rule_reasons)
              else "watch" if rule_reasons else "screen")
    recon_u = {i.name: i.status for i in result.reconciliation}
    recon_disagree = [n for n, v in recon_i.items() if recon_u.get(n) != v["status"]]
    max_diff = max((m.diff for m in mismatches if m.diff is not None), default=0.0)

    checks = [
        CheckItem(name="recompute_metrics", status="fail" if mismatches else "pass",
                  detail={"max_abs_diff": max_diff, "fields": [m.field for m in mismatches]}),
        CheckItem(name="extraction_match",
                  status="warn" if not_reparsed else ("fail" if extraction_diffs else "pass"),
                  detail={"fields": [d["field"] for d in extraction_diffs],
                          "independently_reparsed": not_reparsed is None,
                          **({"reason": "a model read these documents and the checker's own "
                                        "parser could not read them, so the figures were not "
                                        "parsed a second time; the quotes were traced instead"}
                             if not_reparsed else {})}),
        CheckItem(name="rules_recheck",
                  status="warn" if (call_i != call_u or codes_i != codes_u) else "pass",
                  detail={"independent_call": call_i, "independent_reasons": codes_i,
                          "underwriter_call": call_u, "underwriter_reasons": codes_u}),
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


def recheck_memo(report: CheckReport, deal: Deal, result: UnderwritingResult, deal_dir: Path,
                 overrides: list[dict] | None = None) -> CheckReport:
    """After a narrative edit or an override: re-run only the memo number match."""
    cfg = formulas.load_config()
    inputs = parse.independent_parse(deal_dir)
    if overrides:
        inputs = apply_overrides(inputs, overrides)
    metrics = formulas.independent_recompute(inputs, cfg)
    check = pdftext.memo_number_match(Path(result.artifacts["memo_pdf"]), inputs, metrics, cfg,
                                      result.call)
    bad = bool(check["unmatched"]) or not check["call_ok"]
    item = CheckItem(name="memo_number_match", status="fail" if bad else "pass",
                     detail={"unmatched_numbers": check["unmatched"], "call_ok": check["call_ok"]})
    checks = [item if c.name == "memo_number_match" else c for c in report.checks]
    return report.model_copy(update={
        "checks": checks, "status": _status(*[c.status for c in checks])})
