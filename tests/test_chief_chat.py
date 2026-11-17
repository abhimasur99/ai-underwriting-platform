"""Chief chat: answers only from tool output, proposes patches, never decides."""
import pytest
from bridge.agents.chief import Chief
from bridge.agents.chief_chat import ChiefChat
from bridge.agents.runner import CachedRunner
from bridge.store.db import Store

from tests.conftest import DEALS_DIR


def setup(tmp_path, name="bronx_mf"):
    chief = Chief(Store(tmp_path / "t.db"), CachedRunner(), tmp_path / "out", tmp_path / "up")
    deal_id = chief.create_deal()
    chief.ingest_directory(deal_id, DEALS_DIR / name)
    assert chief.process(deal_id) == "NEEDS_REVIEW"
    return chief, ChiefChat(chief, CachedRunner()), deal_id


def test_numeric_answers_come_from_tools_with_formula_inputs_and_sources(tmp_path):
    _, chat, deal_id = setup(tmp_path)
    out = chat.handle(deal_id, "What is the loan to cost?")
    assert out["intent"] == "question"
    r = out["reply"]
    assert "Loan to cost is 70.65%" in r
    assert "loan_commitment / total_cost" in r
    assert "loan_commitment = $6,500,000" in r and "total_cost = $9,200,000" in r
    assert "deal_summary.md line" in r


@pytest.mark.parametrize("question,expected", [
    ("what's the exit DSCR", "Exit DSCR is 1.79x"),
    ("what is the take-out", "Take-out maximum is $8,235,294"),
    ("how big is the cushion", "Refi cushion is $1,735,294"),
    ("show me the stress case", "Refi cushion under stress is $700,000"),
    ("what's the debt yield", "Stabilized debt yield is 10.77%"),
    ("what is the implied cap rate", "Implied cap rate is 5.60%"),
    ("how does the rent roll compare", "Rent roll vs T-12 gap is 2.13%"),
])
def test_other_metric_questions(tmp_path, question, expected):
    _, chat, deal_id = setup(tmp_path)
    assert expected in chat.handle(deal_id, question)["reply"]


def test_why_question_lists_every_reason(tmp_path):
    _, chat, deal_id = setup(tmp_path, "overleveraged_bk")
    reply = chat.handle(deal_id, "why is this a decline?")["reply"]
    for code in ("LTC_DECLINE", "REFI_CUSHION_NEGATIVE_BASE", "RENT_ROLL_VS_T12_DECLINE"):
        assert code in reply
    assert "DECLINE" in reply


def test_summary_and_outside_questions(tmp_path):
    _, chat, deal_id = setup(tmp_path)
    assert "Call: SCREEN" in chat.handle(deal_id, "give me a summary")["reply"]
    for message in ("what does your real lender policy say", "how about the weather"):
        assert "outside what I can help with" in chat.handle(deal_id, message)["reply"]


def test_data_edit_proposes_a_patch_and_applies_nothing(tmp_path):
    chief, chat, deal_id = setup(tmp_path)
    out = chat.handle(deal_id, "change the ARV to 9,000,000 because the broker cut it")
    assert out["intent"] == "data_edit"
    patch = out["patch"]
    assert (patch["path"], patch["old"], patch["new"], patch["status"]) == (
        "valuation.arv", 12_500_000, 9_000_000, "proposed")
    assert "$12,500,000 to $9,000,000" in out["reply"] and "version 2" in out["reply"]
    assert "Nothing changes until you confirm" in out["reply"]
    assert chief.store.versions(deal_id) == [1]
    chief.confirm_patch(deal_id, patch["patch_id"])           # the reviewer's click
    assert chief.store.versions(deal_id) == [1, 2]


def test_rent_edit_finds_the_unit(tmp_path):
    _, chat, deal_id = setup(tmp_path)
    out = chat.handle(deal_id, "set unit 101 rent to 2100 because signed lease")
    assert out["patch"]["path"] == "rent_roll.units[0].monthly_rent"
    assert out["patch"]["old"] == 1320
    assert "couldn't find unit 999" in chat.handle(deal_id, "set unit 999 rent to 100")["reply"]


def test_note_rate_edit_is_read_as_a_percent(tmp_path):
    _, chat, deal_id = setup(tmp_path)
    out = chat.handle(deal_id, "update the note rate to 11% because repriced")
    assert out["patch"]["new"] == pytest.approx(0.11)
    assert "10.50% to 11.00%" in out["reply"]


def test_narrative_edit_and_the_digit_rule(tmp_path):
    chief, chat, deal_id = setup(tmp_path)
    ok = chat.handle(deal_id, "reword the summary to: Leverage of {{metrics.ltc}} is acceptable")
    assert ok["intent"] == "narrative_edit" and ok["patch"]["kind"] == "narrative"
    bad = chat.handle(deal_id, "reword the risks to: leverage is about 70 percent")
    assert bad["patch"] is None and "digits outside placeholders" in bad["reply"]


def test_override_needs_a_reason_first(tmp_path):
    chief, chat, deal_id = setup(tmp_path)
    no_reason = chat.handle(deal_id, "override: comfortable with the stress case")
    assert no_reason["patch"] is None and "needs a reason" in no_reason["reply"]
    ok = chat.handle(deal_id, "override: comfortable with the stress case because strong sponsor")
    assert ok["patch"]["kind"] == "override" and ok["patch"]["reason"] == "strong sponsor"


@pytest.mark.parametrize("message", ["approve it", "please reject this", "send it back"])
def test_actions_are_never_executed_by_the_chat(tmp_path, message):
    chief, chat, deal_id = setup(tmp_path)
    out = chat.handle(deal_id, message)
    assert out["intent"] == "action" and "Please use" in out["reply"]
    assert "the decision is yours" in out["reply"]
    assert chief.state(deal_id) == "NEEDS_REVIEW"


def test_edits_outside_review_are_refused_politely(tmp_path):
    chief, chat, deal_id = setup(tmp_path)
    chief.decide(deal_id, "reject", "no")
    out = chat.handle(deal_id, "change the ARV to 9,000,000 because x")
    assert out["patch"] is None and "in review" in out["reply"]


def test_an_override_or_narrative_edit_with_no_text_is_never_proposed(tmp_path):
    from bridge.agents.runner_types import ChiefTurn, PatchRequest
    chief, chat, deal_id = setup(tmp_path)
    for kind, intent in (("override", "override"), ("narrative", "narrative_edit")):
        chat.runner = type("R", (), {"interpret_chief": staticmethod(lambda _m, k=kind, i=intent:
                                     ChiefTurn(i, patch=PatchRequest(k, section="risks", text=None,
                                                                     reason="because")))})()
        out = chat.handle(deal_id, "whatever")
        assert out["patch"] is None and "I need" in out["reply"]
    assert chief.store.patches(deal_id, status="proposed") == []
