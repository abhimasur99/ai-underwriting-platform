"""Underwriter tool registry. Every tool calls core code; no tool lets a model do arithmetic."""
from pathlib import Path

from bridge.agents.recorder import Recorder
from bridge.agents.tools.registry import Tool, ToolRegistry, number_schema
from bridge.core import calc
from bridge.core.builders.memo import render_memo
from bridge.core.builders.workbook import build_workbook
from bridge.core.reconcile import reconcile_all
from bridge.core.rules import RulesConfig, evaluate
from bridge.core.schema import Deal


def build_underwriter_tools(rec: Recorder, rules: RulesConfig, deal: Deal,
                            state: dict) -> ToolRegistry:
    """`state['result']` is set by the agent before the render tools run (keeps logs compact)."""
    reg = ToolRegistry("underwriter", rec)
    f = calc.FORMULAS
    tk, st = rules.takeout_params(), rules.stress_params()
    scalar = [
        ("calc.total_cost", "Sum of uses", lambda uses: calc.total_cost(uses), f["total_cost"],
         {"type": "object", "properties": {"uses": {"type": "array", "items": {"type": "number"}}},
          "required": ["uses"]}),
        ("calc.ltc", "Loan to cost", calc.ltc, f["ltc"],
         number_schema("loan_commitment", "total_cost")),
        ("calc.ltv_as_is", "Loan to as-is value", calc.ltv_as_is, f["ltv_as_is"],
         number_schema("initial_advance", "as_is_value")),
        ("calc.loan_to_arv", "Loan to ARV", calc.loan_to_arv, f["loan_to_arv"],
         number_schema("loan_commitment", "arv")),
        ("calc.dscr_in_place", "In-place DSCR", calc.dscr_in_place, f["dscr_in_place"],
         number_schema("in_place_noi", "initial_advance", "note_rate")),
        ("calc.debt_yield", "Stabilized debt yield", calc.debt_yield_stabilized,
         f["debt_yield_stabilized"], number_schema("stabilized_noi", "loan_commitment")),
        ("calc.implied_cap_rate", "Implied cap rate", calc.implied_cap_rate,
         f["implied_cap_rate"], number_schema("stabilized_noi", "arv")),
        ("exit.analyze", "Take-out sizing, base case",
         lambda noi, arv, loan_commitment: calc.exit_analysis(noi, arv, loan_commitment, tk),
         f["takeout_max"], number_schema("noi", "arv", "loan_commitment")),
        ("exit.stress", "Take-out sizing under stress",
         lambda noi, arv, loan_commitment: calc.stress_analysis(noi, arv, loan_commitment, tk, st),
         f["stress_noi"] + "; " + f["stress_rate"], number_schema("noi", "arv", "loan_commitment")),
    ]
    for name, desc, fn, formula, schema in scalar:
        reg.add(Tool(name, desc, fn, schema, formula))
    reg.add(Tool("reconcile.all", "Rent roll vs T-12, sources vs uses, unit count",
                 lambda: reconcile_all(deal, rules), formula=f["reconciliation_gap"]))
    reg.add(Tool("rules.evaluate", "Call and reason codes from the rules; final",
                 lambda metrics, exit_, stress, reconciliation: evaluate(
                     deal, metrics, exit_, stress, reconciliation, rules),
                 formula="config/rules.yaml thresholds, strict boundaries"))
    reg.add(Tool("render.workbook", "Write the XLSX workbook (live formulas)",
                 lambda path: str(build_workbook(deal, state["result"], rules, Path(path))),
                 {"type": "object", "properties": {"path": {"type": "string"}},
                  "required": ["path"]}))
    reg.add(Tool("render.memo", "Write the one-page memo PDF",
                 lambda path: str(render_memo(deal, state["result"], Path(path))),
                 {"type": "object", "properties": {"path": {"type": "string"}},
                  "required": ["path"]}))
    return reg


def render_paths(outputs_dir: Path, deal_id: str, version: int) -> tuple[Path, Path]:
    base = Path(outputs_dir) / deal_id / f"v{version}"
    return base / "memo.pdf", base / "workbook.xlsx"

