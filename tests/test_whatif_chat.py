"""What-ifs and the largest loan, asked in the reviewer's chat: understood offline, answered
from the scenario engine and the solver, and never saved."""
import re

import pytest
from bridge.agents.cached_nlu import interpret_chief, parse_what_if, wants_max_loan
from bridge.agents.chief import Chief
from bridge.agents.chief_chat import ChiefChat
from bridge.agents.runner import CachedRunner
from bridge.store.db import Store

from tests.conftest import DEALS_DIR


# ---- understanding the question
@pytest.mark.parametrize("message,expected", [
    ("what if the take-out rate is 7%?", {"takeout_rate": 0.07}),
    ("what if the takeout rate were 6.5 percent", {"takeout_rate": 0.065}),
    ("what if rates go up 200 bps", {"takeout_rate_change_bps": 200}),
    ("what if rates rise by 1%", {"takeout_rate_change_bps": 100}),
    ("what if rates fall 50 basis points", {"takeout_rate_change_bps": -50}),
    ("what if NOI drops 10%", {"noi_change_pct": -0.10}),
    ("what if NOI is 15% lower", {"noi_change_pct": -0.15}),
    ("what if NOI is 5% higher", {"noi_change_pct": 0.05}),
    ("what if the cap rate is 6.5%", {"cap_rate": 0.065}),
    ("what if the loan were $5.5 million", {"loan_amount": 5_500_000}),
    ("what if the loan amount is 5,800,000", {"loan_amount": 5_800_000}),
    ("what if the ARV is 11m", {"arv": 11_000_000}),
    ("what if the minimum DSCR is 1.35x", {"min_dscr": 1.35}),
    ("what if max LTV is 65%", {"max_ltv": 0.65}),
    ("what if the minimum debt yield is 9%", {"min_debt_yield": 0.09}),
    ("what if the stress haircut is 15%", {"stress_noi_haircut": 0.15}),
    ("what if the stress rate shock is 200 bps", {"stress_rate_bump_bps": 200}),
    ("suppose NOI is 10% lower and rates rise 100 bps",
     {"noi_change_pct": -0.10, "takeout_rate_change_bps": 100}),
])
def test_what_if_phrasings_are_understood(message, expected):
    assert parse_what_if(message) == pytest.approx(expected)
    turn = interpret_chief(message)
    assert turn.intent == "question" and turn.topic == "what_if"
    assert turn.what_if == pytest.approx(expected)


@pytest.mark.parametrize("message", [
    "what if the weather is bad", "what is the loan to cost?", "what is the exit DSCR?",
    "change the ARV to 11,000,000 because the appraisal came in lower",
    "set the loan amount to 5,500,000 because the sponsor asked", "rates are high", "summarize"])
def test_other_messages_are_not_mistaken_for_what_ifs(message):
    assert interpret_chief(message).topic != "what_if"


@pytest.mark.parametrize("message,target", [
    ("what is the largest loan that still screens?", "screen"),
    ("what's the maximum loan we can do and still screen", "screen"),
    ("how much can we lend before it stops screening?", "screen"),
    ("what is the biggest loan that avoids a decline?", "watch"),
    ("max loan that stays at least a watch", "watch"),
])
def test_the_largest_loan_question_is_understood(message, target):
    assert wants_max_loan(message) == target
    assert interpret_chief(message).topic == "max_loan"


def test_questions_about_the_loan_are_not_mistaken_for_sizing():
    assert wants_max_loan("what is the loan to cost?") is None
    assert wants_max_loan("what if the loan were $5.5 million") is None


# ---- the answers
def setup(tmp_path, name="bronx_mf"):
    chief = Chief(Store(tmp_path / "t.db"), CachedRunner(), tmp_path / "out", tmp_path / "up")
    deal_id = chief.create_deal()
    chief.ingest_directory(deal_id, DEALS_DIR / name)
    assert chief.process(deal_id) == "NEEDS_REVIEW"
    return chief, ChiefChat(chief, CachedRunner()), deal_id


def test_a_what_if_answer_shows_before_and_after_and_says_nothing_was_saved(tmp_path):
    chief, chat, deal_id = setup(tmp_path)
    out = chat.handle(deal_id, "what if the take-out rate is 7%?")
    r = out["reply"]
    assert "Take-out rate 6.00% to 7.00%" in r and "Exit DSCR: 1.79x to 1.54x" in r
    assert "Take-out maximum: $8,235,294 to $8,000,000" in r
    # at 7% the stress case runs at 8%: the DSCR cap falls to 6.3M, under the 6.5M loan
    assert "The call would move from Screen to Watch" in r
    assert "does not cover the payoff under stress" in r and "nothing has been saved" in r
    assert "REFI_CUSHION" not in r
    assert out["scenario"]["call_after"] == "watch" and out["patch"] is None
    assert chief.store.versions(deal_id) == [1]                    # the deal is untouched
    assert chief.state(deal_id) == "NEEDS_REVIEW" and not chief.store.patches(deal_id)


def test_a_milder_what_if_leaves_the_call_where_it_is(tmp_path):
    _, chat, deal_id = setup(tmp_path)
    out = chat.handle(deal_id, "what if the take-out rate is 6.5%?")
    assert "The call would stay Screen" in out["reply"]
    assert out["scenario"]["call_before"] == out["scenario"]["call_after"] == "screen"


def test_a_what_if_that_changes_the_call_says_so(tmp_path):
    _, chat, deal_id = setup(tmp_path)
    r = chat.handle(deal_id, "what if NOI is 35% lower?")["reply"]
    assert "The call would move from Screen to" in r and "New concerns" in r


def test_two_assumptions_at_once(tmp_path):
    _, chat, deal_id = setup(tmp_path)
    out = chat.handle(deal_id, "suppose NOI is 10% lower and rates rise 100 bps")
    r = out["reply"]
    assert "Stabilized NOI $700,000 to $630,000" in r and "Take-out rate 6.00% to 7.00%" in r
    assert len(out["scenario"]["assumptions"]) == 2


def test_an_unreasonable_what_if_is_declined_with_the_range(tmp_path):
    _, chat, deal_id = setup(tmp_path)
    out = chat.handle(deal_id, "what if the take-out rate is 90%")
    assert out["scenario"] is None
    assert "take-out rate" in out["reply"] and "range" in out["reply"]


def test_the_largest_loan_that_screens_is_answered_with_the_limit(tmp_path):
    _, chat, deal_id = setup(tmp_path, "yonkers_leaseup")
    out = chat.handle(deal_id, "what is the largest loan that still screens?")
    r = out["reply"]
    assert "$4,125,000" in r and "current $4,200,000" in r and "Loan to cost (limit 75.00%)" in r
    assert "initial advance and the holdback scale together" in r
    assert out["sizing"]["max_loan"] == pytest.approx(4_125_000, abs=2)
    assert out["scenario"]["assumptions"][0]["after"] == pytest.approx(4_125_000, abs=2)


def test_a_deal_that_already_screens_says_how_much_more_it_could_carry(tmp_path):
    _, chat, deal_id = setup(tmp_path)
    r = chat.handle(deal_id, "what is the largest loan that still screens?")["reply"]
    assert "current $6,500,000 request screens" in r.replace("The current $", "current $") or \
        "screens" in r
    assert re.search(r"\$[\d,]+", r)


def test_a_deal_no_loan_size_can_fix_says_why(tmp_path):
    _, chat, deal_id = setup(tmp_path, "overleveraged_bk")
    out = chat.handle(deal_id, "what is the largest loan that still screens?")
    assert out["sizing"]["max_loan"] is None and out["scenario"] is None
    assert "No loan size would screen" in out["reply"]
    assert "Rent roll and T-12 income disagree" in out["reply"]


def test_what_ifs_offer_the_next_sensible_questions(tmp_path):
    _, chat, deal_id = setup(tmp_path)
    out = chat.handle(deal_id, "what if the take-out rate is 7%?")
    assert "What is the largest loan that still screens?" in out["suggestions"]


def test_the_starters_now_include_a_what_if_and_the_largest_loan(tmp_path):
    _, chat, deal_id = setup(tmp_path)
    out = chat.handle(deal_id, "what can you do?")
    assert any("what if" in s.lower() for s in out["suggestions"])
    assert any("largest loan" in s.lower() for s in out["suggestions"])
    assert "what-if" in out["reply"].lower() or "what if" in out["reply"].lower()


# ---- the live reader hands over the same typed question
def test_the_live_reader_returns_a_what_if_as_named_assumptions():
    from bridge.agents.claude_runner import ClaudeRunner

    from tests.test_claude_runner import FakeClient, ok
    reply = {"intent": "question", "metric": "none", "topic": "what_if", "action": "none",
             "patch_kind": "none", "patch_field": "none", "patch_value": 0, "patch_unit": "",
             "patch_section": "none", "patch_text": "", "patch_reason": "",
             "what_if": [{"param": "noi_change_pct", "value": -0.1},
                         {"param": "takeout_rate_change_bps", "value": 100}],
             "sizing_target": "none"}
    client = FakeClient(ok(reply))
    turn = ClaudeRunner(client, "claude-sonnet-5-5").interpret_chief(
        "suppose income is a tenth lower and rates are a point higher")
    assert turn.topic == "what_if" and turn.what_if == {"noi_change_pct": -0.1,
                                                         "takeout_rate_change_bps": 100}
    schema = client.requests[0]["output_config"]["format"]["schema"]["properties"]
    assert set(schema["what_if"]["items"]["properties"]["param"]["enum"]) >= {"takeout_rate",
                                                                               "loan_amount"}
    assert "what_if" in schema["topic"]["enum"] and "max_loan" in schema["topic"]["enum"]


def test_the_live_reader_returns_the_largest_loan_question_with_its_target():
    from bridge.agents.claude_runner import ClaudeRunner

    from tests.test_claude_runner import FakeClient, ok
    reply = {"intent": "question", "metric": "none", "topic": "max_loan", "action": "none",
             "patch_kind": "none", "patch_field": "none", "patch_value": 0, "patch_unit": "",
             "patch_section": "none", "patch_text": "", "patch_reason": "", "what_if": [],
             "sizing_target": "watch"}
    turn = ClaudeRunner(FakeClient(ok(reply)), "claude-sonnet-5-5").interpret_chief("x")
    assert turn.topic == "max_loan" and turn.sizing_target == "watch" and turn.what_if == {}
