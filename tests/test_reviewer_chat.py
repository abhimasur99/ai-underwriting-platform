"""The reviewer's chat: professional wording, the new things it can be asked, and a kept record."""
import re

import pytest
from bridge.agents.chief import Chief
from bridge.agents.chief_chat import ChiefChat, explain_exceptions
from bridge.agents.runner import CachedRunner
from bridge.core.schema import Flag
from bridge.store.db import Store

from tests.conftest import DEALS_DIR


def setup(tmp_path, name="bronx_mf"):
    chief = Chief(Store(tmp_path / "t.db"), CachedRunner(), tmp_path / "out", tmp_path / "up")
    deal_id = chief.create_deal()
    chief.ingest_directory(deal_id, DEALS_DIR / name)
    assert chief.process(deal_id) == "NEEDS_REVIEW"
    return chief, ChiefChat(chief, CachedRunner()), deal_id


def ask(chat, deal_id, message):
    return chat.handle(deal_id, message)


def test_a_greeting_is_answered_politely_with_suggestions(tmp_path):
    _, chat, deal_id = setup(tmp_path)
    out = ask(chat, deal_id, "hello")
    assert out["reply"].startswith("Hello") and "How can I help" in out["reply"]
    assert 1 <= len(out["suggestions"]) <= 6


def test_asking_what_it_can_do_lists_the_capabilities_and_the_confirm_rule(tmp_path):
    _, chat, deal_id = setup(tmp_path)
    reply = ask(chat, deal_id, "what can you do?")["reply"]
    for word in ("calculations", "exceptions", "what changed", "edits", "confirm"):
        assert word in reply


def test_thanks_gets_a_courteous_close(tmp_path):
    _, chat, deal_id = setup(tmp_path)
    assert "welcome" in ask(chat, deal_id, "thanks")["reply"].lower()


def test_a_question_outside_the_deal_gets_a_courteous_redirect(tmp_path):
    _, chat, deal_id = setup(tmp_path)
    reply = ask(chat, deal_id, "how about the weather")["reply"]
    assert "outside what I can help with" in reply and "calculations" in reply


# ---- exceptions and questions for the sponsor
def test_a_clean_deal_has_no_exceptions(tmp_path):
    _, chat, deal_id = setup(tmp_path)
    assert "no exceptions" in ask(chat, deal_id, "what are the exceptions?")["reply"]


def test_exceptions_and_sponsor_questions_are_listed_for_a_deal_that_has_them(tmp_path):
    chief, chat, deal_id = setup(tmp_path, "yonkers_leaseup")
    reply = ask(chat, deal_id, "what are the exceptions")["reply"]
    assert "Questions for the sponsor" in reply and "equity" in reply


def test_explain_exceptions_names_each_code_and_its_message():
    chief_result = type("R", (), {})()
    chief_result.flags = [Flag(code="T12_ROW_TOTAL_MISMATCH", message="months do not sum",
                               field="t12")]
    chief_result.open_questions = ["Please confirm the rent roll date."]
    text = explain_exceptions(chief_result)
    assert "1 exception" in text and "T12_ROW_TOTAL_MISMATCH: months do not sum" in text
    assert "Questions for the sponsor" in text and "Please confirm the rent roll date." in text


# ---- what changed in this version
def test_the_first_version_has_nothing_to_compare(tmp_path):
    _, chat, deal_id = setup(tmp_path)
    reply = ask(chat, deal_id, "what changed in this version?")["reply"]
    assert "first version" in reply and "nothing to compare" in reply


def test_after_an_edit_the_chat_says_what_moved_and_that_the_call_is_unchanged(tmp_path):
    chief, chat, deal_id = setup(tmp_path)
    patch = chief.propose_patch(deal_id, "data", "valuation.arv", 11_000_000, "appraisal lower")
    chief.confirm_patch(deal_id, patch.patch_id)
    reply = ask(chat, deal_id, "what changed in this version?")["reply"]
    assert "Version 2 changed" in reply and "valuation.arv: $12,500,000 to $11,000,000" in reply
    assert "appraisal lower" in reply and "Loan to ARV: 52.00% to 59.09%" in reply
    assert "The call is unchanged (Screen)" in reply and "Loan to cost" not in reply


def test_a_change_that_flips_the_call_says_where_it_moved(tmp_path):
    chief, chat, deal_id = setup(tmp_path)
    patch = chief.propose_patch(deal_id, "data", "loan_request.loan_commitment", 7_400_000, "more")
    chief.confirm_patch(deal_id, patch.patch_id)
    reply = ask(chat, deal_id, "what changed since the last version")["reply"]
    assert "The call moved from Screen to" in reply and "New concerns" in reply


# ---- follow-ups, the record, and the numbers rule
@pytest.mark.parametrize("message", ["give me a summary", "why is this call what it is?",
                                     "what is the loan to cost?", "what are the exceptions?"])
def test_every_answer_offers_sensible_follow_ups(tmp_path, message):
    _, chat, deal_id = setup(tmp_path)
    out = ask(chat, deal_id, message)
    assert out["suggestions"]
    assert message.lower() not in [s.lower() for s in out["suggestions"]]


def test_a_proposed_edit_offers_no_follow_ups_because_the_card_is_the_next_step(tmp_path):
    _, chat, deal_id = setup(tmp_path)
    out = ask(chat, deal_id, "change the ARV to 11,000,000 because the appraisal came in lower")
    assert out["patch"] is not None and out["suggestions"] == []


def test_the_conversation_is_recorded_for_the_reviewer_only(tmp_path):
    chief, chat, deal_id = setup(tmp_path)
    ask(chat, deal_id, "hello")
    kinds = [e.type for e in chief.store.events(deal_id)]
    assert kinds.count("chat.reviewer") == 1 and kinds.count("chat.chief") == 1


def test_numbers_in_a_reply_all_come_from_the_calculations(tmp_path):
    chief, chat, deal_id = setup(tmp_path)
    _, result, _ = chief.latest(deal_id)
    reply = ask(chat, deal_id, "give me a summary")["reply"]
    for token in re.findall(r"\$[\d,]+", reply):
        assert any(token.replace("$", "").replace(",", "") in blob.replace(",", "") for blob in
                   [result.model_dump_json(), chief.store.get_deal(deal_id).model_dump_json()])
