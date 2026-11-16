"""End to end from files alone, no model: call, reasons and metrics match expected.json."""
import ast
from pathlib import Path

import pytest
from bridge.core.parsers import parse_deal_dir
from bridge.core.underwrite import underwrite


def test_call_and_reasons_match_answer_key(deal_dir, expected):
    result = underwrite(parse_deal_dir(deal_dir))
    assert result.call == expected["expected_call"]
    assert [r.code for r in result.reasons] == expected["expected_reason_codes"]


def test_three_deals_give_screen_watch_decline():
    from tests.conftest import DEAL_NAMES, DEALS_DIR
    calls = {n: underwrite(parse_deal_dir(DEALS_DIR / n)).call for n in DEAL_NAMES}
    assert calls == {"bronx_mf": "screen", "queens_mixed_use": "watch",
                     "overleveraged_bk": "decline"}


def test_metrics_match_answer_key(deal_dir, expected):
    r, m = underwrite(parse_deal_dir(deal_dir)), expected["metrics"]
    for name in ("total_cost", "ltc", "ltv_as_is", "loan_to_arv", "dscr_in_place",
                 "debt_yield_stabilized", "implied_cap_rate"):
        tolerance = 1 if name == "total_cost" else 1e-4
        assert getattr(r.metrics, name) == pytest.approx(m[name], abs=tolerance)
    assert r.exit.payoff == pytest.approx(m["payoff"], abs=1)
    assert r.exit.caps.dscr == pytest.approx(m["takeout_caps"]["dscr"], abs=1)
    assert r.exit.caps.ltv == pytest.approx(m["takeout_caps"]["ltv"], abs=1)
    assert r.exit.caps.debt_yield == pytest.approx(m["takeout_caps"]["debt_yield"], abs=1)
    assert r.exit.binding == m["takeout_binding"]
    assert r.exit.takeout_max == pytest.approx(m["takeout_max"], abs=1)
    assert r.exit.refi_cushion == pytest.approx(m["refi_cushion"], abs=1)
    assert r.exit.exit_dscr == pytest.approx(m["exit_dscr"], abs=1e-4)
    s = m["stress"]
    assert r.stress.noi == pytest.approx(s["noi"], abs=1)
    assert r.stress.rate == pytest.approx(s["rate"], abs=1e-6)
    assert r.stress.binding == s["takeout_binding"]
    assert r.stress.takeout_max == pytest.approx(s["takeout_max"], abs=1)
    assert r.stress.refi_cushion == pytest.approx(s["refi_cushion"], abs=1)
    assert r.stress.exit_dscr == pytest.approx(s["exit_dscr"], abs=1e-4)
    gaps = {i.name: i.gap for i in r.reconciliation}
    assert gaps["rent_roll_vs_t12"] == pytest.approx(m["rr_vs_t12_gap"], abs=1e-4)
    assert gaps["sources_vs_uses"] == pytest.approx(m["sources_vs_uses_gap"], abs=1e-4)


def test_result_is_traceable_and_labeled(deal_dir):
    deal = parse_deal_dir(deal_dir)
    r = underwrite(deal)
    assert r.deal_id == deal.deal_id and r.deal_version == deal.version
    assert r.rules_version == "0.1-illustrative"
    assert r.rule_checks and r.open_questions is not None
    assert set(r.narrative) == {"summary", "exit", "risks"}


def test_decline_deal_lists_every_failed_rule():
    from tests.conftest import DEALS_DIR
    r = underwrite(parse_deal_dir(DEALS_DIR / "overleveraged_bk"))
    assert {x.code for x in r.reasons if x.severity == "decline"} == {
        "LTC_DECLINE", "LTV_AS_IS_DECLINE", "LOAN_TO_ARV_DECLINE",
        "REFI_CUSHION_NEGATIVE_BASE", "RENT_ROLL_VS_T12_DECLINE", "SOURCES_VS_USES_DECLINE"}
    assert all(q for q in r.open_questions)


def test_core_imports_no_web_or_llm_libraries_and_does_not_reach_up():
    banned = {"anthropic", "fastapi", "starlette", "uvicorn", "httpx", "requests", "openai"}
    upward = {"bridge.api", "bridge.agents", "bridge.store"}
    core = Path(__file__).resolve().parents[1] / "backend" / "bridge" / "core"
    for path in core.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                assert name.split(".")[0] not in banned, f"{path}: imports {name}"
                assert not any(name.startswith(u) for u in upward), f"{path}: imports {name}"
