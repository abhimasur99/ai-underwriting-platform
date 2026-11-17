"""Next action for the queue, and Request info: the reviewer asks the sponsor for something, the
sponsor replies in the intake chat, and the deal returns to review."""
import shutil

import pytest
from bridge.agents.chief import Chief, DecisionError
from bridge.agents.intake import IncomingFile, IntakeAgent
from bridge.agents.runner import CachedRunner
from bridge.store import projections
from bridge.store.db import Store

from tests.conftest import DEALS_DIR


def make(tmp_path, name="bronx_mf"):
    chief = Chief(Store(tmp_path / "t.db"), CachedRunner(), tmp_path / "out", tmp_path / "up")
    deal_id = chief.create_deal()
    chief.ingest_directory(deal_id, DEALS_DIR / name)
    return chief, IntakeAgent(chief, CachedRunner()), deal_id


def reviewed(tmp_path, name="bronx_mf"):
    chief, intake, deal_id = make(tmp_path, name)
    assert chief.process(deal_id) == "NEEDS_REVIEW"
    return chief, intake, deal_id


def next_action(chief, deal_id):
    s = projections.status(chief.store, deal_id)
    return s.next_action, s.needs_you


# ---- next action
def test_next_action_follows_the_deal_through_its_life(tmp_path):
    chief = Chief(Store(tmp_path / "t.db"), CachedRunner(), tmp_path / "out", tmp_path / "up")
    deal_id = chief.create_deal()
    assert next_action(chief, deal_id) == ("Waiting on sponsor: documents", False)
    chief.ingest_directory(deal_id, DEALS_DIR / "bronx_mf")
    assert next_action(chief, deal_id) == ("Running", False)          # READY: about to run
    chief.process(deal_id)
    assert next_action(chief, deal_id) == ("Your review", True)
    chief.decide(deal_id, "approve", "ok")
    assert next_action(chief, deal_id) == ("Done: approved", False)


def test_a_rejected_deal_and_an_escalated_one(tmp_path):
    chief, _, deal_id = reviewed(tmp_path)
    chief.decide(deal_id, "reject", "no")
    assert next_action(chief, deal_id) == ("Done: rejected", False)


def test_a_deal_that_stopped_for_missing_fields_says_what_it_waits_for(tmp_path):
    chief = Chief(Store(tmp_path / "t.db"), CachedRunner(), tmp_path / "out", tmp_path / "up")
    deal_id = chief.create_deal()
    folder = tmp_path / "ridgewood"
    shutil.copytree(DEALS_DIR / "ridgewood_missing_arv", folder,
                    ignore=shutil.ignore_patterns("cached", "followup"))
    chief.ingest_directory(deal_id, folder)
    for key, value in {"property_address": "x", "asset_type": "multifamily", "unit_count": "16",
                       "loan_amount_requested": "2600000", "purchase_price": "3300000",
                       "renovation_budget": "500000", "sponsor_name": "S"}.items():
        chief.record_fact(deal_id, key, value)
    chief.process(deal_id)
    assert chief.state(deal_id) == "NEEDS_INPUT"
    assert next_action(chief, deal_id) == ("Waiting on sponsor: arv", False)


def test_the_queue_lists_what_needs_the_reviewer_first(tmp_path):
    chief, _, review_id = reviewed(tmp_path)
    waiting_id = chief.create_deal()                         # created later, so newer
    order = [r.deal_id for r in projections.queue(chief.store)]
    assert order == [review_id, waiting_id]


def test_an_archived_deal_has_no_next_action(tmp_path):
    chief, _, deal_id = reviewed(tmp_path)
    chief.archive(deal_id)
    assert projections.status(chief.store, deal_id).next_action == "Archived"


# ---- request info
def test_requesting_info_needs_a_note_and_a_deal_in_review(tmp_path):
    chief, _, deal_id = reviewed(tmp_path)
    with pytest.raises(DecisionError, match="note"):
        chief.decide(deal_id, "request_info", "   ")
    chief.decide(deal_id, "request_info", "Please send the 2025 tax bill.")
    assert chief.state(deal_id) == "NEEDS_INPUT"
    with pytest.raises(DecisionError):                       # no longer in review
        chief.decide(deal_id, "approve", "")


def test_the_request_is_logged_and_shown_in_the_queue(tmp_path):
    chief, _, deal_id = reviewed(tmp_path)
    chief.decide(deal_id, "request_info", "Please send the 2025 tax bill.")
    types = [e.type for e in chief.store.events(deal_id)]
    assert "info.requested" in types and "decision.recorded" in types
    action, needs_you = next_action(chief, deal_id)
    assert action == "Waiting on sponsor: Please send the 2025 tax bill." and not needs_you


def test_the_sponsor_chat_shows_the_reviewers_note(tmp_path):
    chief, intake, deal_id = reviewed(tmp_path)
    chief.decide(deal_id, "request_info", "Please send the 2025 tax bill.")
    message = intake.status_message(deal_id)
    assert "Please send the 2025 tax bill." in message and "reply here" in message.lower()
    for forbidden in ("screen", "watch", "decline", "ltc", "%"):    # never a call or a number
        assert forbidden not in message.lower()


def test_a_text_reply_returns_the_deal_to_review_without_re_extracting(tmp_path):
    chief, intake, deal_id = reviewed(tmp_path)
    chief.decide(deal_id, "request_info", "Is the sponsor's guarantee full recourse?")
    out = intake.handle(deal_id, "Yes, full recourse, signed by both principals.")
    assert chief.state(deal_id) == "NEEDS_REVIEW"
    assert chief.store.versions(deal_id) == [1]              # nothing re-extracted, edits safe
    replied = next(e for e in chief.store.events(deal_id) if e.type == "info.replied")
    assert replied.payload["text"] == "Yes, full recourse, signed by both principals."
    assert "passed" in out["reply"].lower() and out["submitted"] is False
    assert next_action(chief, deal_id) == ("Your review", True)


def test_a_new_file_reruns_the_deal_as_a_new_version(tmp_path):
    chief, intake, deal_id = reviewed(tmp_path)
    chief.decide(deal_id, "request_info", "Please resend the T-12.")
    corrected = (DEALS_DIR / "bronx_mf" / "t12.csv").read_bytes() + b"\n"    # a new file, new size
    out = intake.handle(deal_id, files=[IncomingFile("t12.csv", corrected)])
    assert out["submitted"] is True
    chief.process(deal_id)
    assert chief.state(deal_id) == "NEEDS_REVIEW"
    assert chief.store.versions(deal_id) == [1, 2]
    events = chief.store.events(deal_id)
    created = [e for e in events if e.type == "version.created"]
    assert created[-1].payload["to"] == 2
    replied = [e for e in events if e.type == "info.replied"]
    assert replied and "t12.csv" in replied[-1].payload["files"]
    assert projections.status(chief.store, deal_id).deal_version == 2


def test_a_failed_re_extraction_does_not_advance_the_displayed_version(tmp_path):
    chief, intake, deal_id = reviewed(tmp_path)
    chief.decide(deal_id, "request_info", "Please resend the rent roll.")
    bad = "unit,unit_type,status\n101,studio,occupied\n"       # no monthly_rent column
    intake.handle(deal_id, files=[IncomingFile("rent_roll.csv", bad.encode())])
    chief.process(deal_id)
    assert chief.state(deal_id) == "NEEDS_INPUT"
    assert chief.store.versions(deal_id) == [1]
    assert projections.status(chief.store, deal_id).deal_version == 1


def test_an_identical_re_upload_or_a_refused_file_keeps_the_deal_waiting(tmp_path):
    chief, intake, deal_id = reviewed(tmp_path)
    chief.decide(deal_id, "request_info", "Please resend the T-12.")
    same = (DEALS_DIR / "bronx_mf" / "t12.csv").read_bytes()
    out = intake.handle(deal_id, files=[IncomingFile("t12.csv", same)])
    assert "already have" in out["reply"] and "still waiting" in out["reply"]
    out = intake.handle(deal_id, files=[IncomingFile("notes.exe", b"x")])
    assert "can't accept" in out["reply"] and out["submitted"] is False
    assert chief.state(deal_id) == "NEEDS_INPUT"
    assert not [e for e in chief.store.events(deal_id) if e.type == "info.replied"]


def test_asking_about_the_decision_while_replying_is_still_refused(tmp_path):
    chief, intake, deal_id = reviewed(tmp_path)
    chief.decide(deal_id, "request_info", "Is the guarantee full recourse?")
    out = intake.handle(deal_id, "Yes, full recourse. So will you approve it?")
    assert "can't discuss underwriting" in out["reply"].lower()
    assert chief.state(deal_id) == "NEEDS_REVIEW"
