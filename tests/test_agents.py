"""Underwriter, extraction and checker agents (offline, cached runner)."""
import shutil

import pytest
from bridge.agents.checker import flatten_result, run_checker
from bridge.agents.extraction import run_extraction
from bridge.agents.recorder import Recorder
from bridge.agents.runner import CachedRunner
from bridge.agents.underwriter import FaultPlan, run_underwriter
from bridge.core.parsers import parse_deal_dir
from bridge.core.placeholders import NarrativeError
from bridge.core.rules import load_rules
from bridge.core.schema import Flag
from bridge.core.underwrite import underwrite
from bridge.store.db import Store
from openpyxl import load_workbook

from tests.conftest import DEALS_DIR


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    s.create_deal("D-X", "x")
    return s


def rec_for(store, deal):
    return Recorder(store, "D-X", deal.version)


def run_pipeline(store, tmp_path, deal_dir, faults=None, attempt=1):
    runner = CachedRunner()
    rec = Recorder(store, "D-X")
    deal = run_extraction(deal_dir, runner, rec).deal
    result = run_underwriter(deal, rec, load_rules(), runner, tmp_path / "out", attempt=attempt,
                             faults=faults)
    return deal, result, rec, runner


# ---- extraction
def test_cached_extraction_loads_the_cached_deal(store, deal_dir):
    out = run_extraction(deal_dir, CachedRunner(), Recorder(store, "D-X"))
    assert out.status == "ok"
    assert out.deal == parse_deal_dir(deal_dir)


def test_extraction_without_cache_parses_documents(store, tmp_path):
    d = tmp_path / "deal"
    shutil.copytree(DEALS_DIR / "bronx_mf", d)
    shutil.rmtree(d / "cached")
    assert run_extraction(d, CachedRunner(), Recorder(store, "D-X")).status == "ok"


def test_extraction_never_guesses_missing_fields(store, tmp_path):
    d = tmp_path / "deal"
    shutil.copytree(DEALS_DIR / "bronx_mf", d)
    shutil.rmtree(d / "cached")
    p = d / "deal_summary.md"
    p.write_text(p.read_text().replace("- Note rate: 10.50% interest-only\n", ""))
    out = run_extraction(d, CachedRunner(), Recorder(store, "D-X"))
    assert out.status == "needs_input" and "note_rate" in out.missing and out.deal is None


def test_extraction_with_missing_document_needs_input(store, tmp_path):
    d = tmp_path / "deal"
    shutil.copytree(DEALS_DIR / "bronx_mf", d)
    shutil.rmtree(d / "cached")
    (d / "t12.csv").unlink()
    assert run_extraction(d, CachedRunner(), Recorder(store, "D-X")).status == "needs_input"


# ---- underwriter
def test_agent_result_equals_the_core_pipeline(store, tmp_path, deal_dir):
    deal, result, _, _ = run_pipeline(store, tmp_path, deal_dir)
    core = underwrite(deal)
    assert result.call == core.call
    assert [r.code for r in result.reasons] == [r.code for r in core.reasons]
    assert result.metrics == core.metrics and result.exit == core.exit
    assert result.stress == core.stress and result.reconciliation == core.reconciliation
    assert result.open_questions == core.open_questions


def test_every_tool_call_is_logged_with_formula_and_output(store, tmp_path):
    run_pipeline(store, tmp_path, DEALS_DIR / "bronx_mf")
    calls = [e.payload for e in store.events("D-X") if e.type == "tool.called"
             and e.actor == "underwriter"]
    names = [c["tool"] for c in calls]
    assert names[:2] == ["calc.total_cost", "calc.ltc"]
    for needed in ("calc.ltv_as_is", "calc.loan_to_arv", "calc.dscr_in_place", "calc.debt_yield",
                   "calc.implied_cap_rate", "reconcile.all", "exit.analyze", "exit.stress",
                   "rules.evaluate", "narrative.write", "render.workbook", "render.memo"):
        assert needed in names
    ltc = next(c for c in calls if c["tool"] == "calc.ltc")
    assert ltc["formula"] == "loan_commitment / total_cost"
    assert ltc["inputs"] == {"loan_commitment": 6_500_000, "total_cost": 9_200_000}
    assert ltc["output"] == pytest.approx(0.706522, abs=1e-6)
    assert ltc["call_id"].startswith("t-")


def test_artifacts_are_written_and_events_recorded(store, tmp_path):
    _, result, _, _ = run_pipeline(store, tmp_path, DEALS_DIR / "bronx_mf")
    assert (tmp_path / "out" / "D-0042" / "v1" / "memo.pdf").exists()
    assert (tmp_path / "out" / "D-0042" / "v1" / "workbook.xlsx").exists()
    types = [e.type for e in store.events("D-X")]
    assert "memo.rendered" in types and "underwriting.completed" in types
    assert set(result.artifacts) == {"memo_pdf", "workbook"}


class _BadNarrative(CachedRunner):
    def write_narrative(self, result, feedback=None):
        self.calls = getattr(self, "calls", 0) + 1
        good = super().write_narrative(result)
        return {**good, "summary": "LTC is about 70 percent"} if self.calls == 1 or self.always \
            else good

    always = False


def test_narrative_with_a_stray_digit_is_regenerated_once(store, tmp_path):
    runner = _BadNarrative()
    rec = Recorder(store, "D-X")
    deal = parse_deal_dir(DEALS_DIR / "bronx_mf")
    result = run_underwriter(deal, rec, load_rules(), runner, tmp_path / "o")
    assert runner.calls == 2 and "70" not in result.narrative["summary"]


def test_narrative_that_keeps_breaking_the_contract_fails_the_step(store, tmp_path):
    runner = _BadNarrative()
    runner.always = True
    deal = parse_deal_dir(DEALS_DIR / "bronx_mf")
    with pytest.raises(NarrativeError):
        run_underwriter(deal, Recorder(store, "D-X"), load_rules(), runner, tmp_path / "o")
    assert runner.calls == 2


# ---- checker
def check(store, tmp_path, deal_dir, **kw):
    deal, result, rec, runner = run_pipeline(store, tmp_path, deal_dir, **kw)
    return deal, result, run_checker(deal, result, deal_dir, rec, runner)


def test_checker_agrees_on_every_sample_deal(store, tmp_path, deal_dir):
    _, _, report = check(store, tmp_path, deal_dir)
    assert report.status == "pass", [c for c in report.checks if c.status != "pass"]
    assert report.mismatches == []
    assert {c.name for c in report.checks} == {
        "recompute_metrics", "extraction_match", "rules_recheck", "reconcile_recheck",
        "source_trace", "workbook_audit", "memo_number_match", "open_flags"}


def test_checker_uses_only_independent_tools(store, tmp_path):
    check(store, tmp_path, DEALS_DIR / "bronx_mf")
    tools = {e.payload["tool"] for e in store.events("D-X")
             if e.type == "tool.called" and e.actor == "checker"}
    assert tools == {"independent_parse", "independent_recompute", "compare_metrics",
                     "rules_recheck", "reconcile_recheck", "source_trace", "workbook_audit",
                     "memo_number_match"}


def test_forced_mismatch_fails_the_check_with_field_values_and_cause(store, tmp_path):
    _, result, report = check(store, tmp_path, DEALS_DIR / "bronx_mf",
                              faults=FaultPlan("ltc", 0.0078))
    assert report.status == "fail"
    m = next(x for x in report.mismatches if x.field == "ltc")
    assert m.underwriter == pytest.approx(0.7143, abs=1e-4)
    assert m.independent == pytest.approx(0.7065, abs=1e-4)
    assert m.diff == pytest.approx(0.0078, abs=1e-6)
    assert "loan_commitment" in m.likely_cause
    names = {c.name for c in report.checks if c.status == "fail"}
    assert {"recompute_metrics", "memo_number_match"} <= names
    assert result.metrics.ltc == pytest.approx(0.7143, abs=1e-4)


def test_fault_only_applies_on_planned_attempts(store, tmp_path):
    plan = FaultPlan("ltc", 0.01, attempts=frozenset({1}))
    _, _, bad = check(store, tmp_path, DEALS_DIR / "bronx_mf", faults=plan, attempt=1)
    _, _, good = check(store, tmp_path, DEALS_DIR / "bronx_mf", faults=plan, attempt=2)
    assert (bad.status, good.status) == ("fail", "pass")


def test_hardcoded_metric_cell_fails_the_check(store, tmp_path):
    deal_dir = DEALS_DIR / "bronx_mf"
    deal, result, rec, runner = run_pipeline(store, tmp_path, deal_dir)
    wb = load_workbook(result.artifacts["workbook"])
    wb["Metrics"]["B3"] = 0.7065
    wb.save(result.artifacts["workbook"])
    report = run_checker(deal, result, deal_dir, rec, runner)
    audit = next(c for c in report.checks if c.name == "workbook_audit")
    assert report.status == "fail" and "ltc" in audit.detail["hardcoded_metric_cells"]


def test_extraction_error_is_caught(store, tmp_path):
    deal_dir = DEALS_DIR / "bronx_mf"
    deal, result, rec, runner = run_pipeline(store, tmp_path, deal_dir)
    deal.valuation.arv.value = 13_000_000          # extraction disagrees with the documents
    report = run_checker(deal, result, deal_dir, rec, runner)
    assert report.status == "fail"
    assert "arv" in next(c for c in report.checks if c.name == "extraction_match").detail["fields"]


def test_non_numeric_concerns_are_warnings(store, tmp_path):
    deal_dir = DEALS_DIR / "bronx_mf"
    deal, result, rec, runner = run_pipeline(store, tmp_path, deal_dir)
    result.flags.append(Flag(code="TEST_FLAG", message="check this"))
    report = run_checker(deal, result, deal_dir, rec, runner)
    assert report.status == "warn"


def test_flatten_result_covers_independent_metric_keys(store, tmp_path):
    from bridge.core.independent import formulas, parse
    _, result, _, _ = run_pipeline(store, tmp_path, DEALS_DIR / "bronx_mf")
    independent = formulas.independent_recompute(
        parse.independent_parse(DEALS_DIR / "bronx_mf"), formulas.load_config())
    assert set(independent) == set(flatten_result(result))
