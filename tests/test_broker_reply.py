"""The draft reply to the broker: written by code from the decision, free of figures, edited and
approved by the reviewer, logged, and never sent."""
import pytest
from bridge.agents.broker_reply import ReplyError, compose, placeholders, themes
from bridge.agents.chief import Chief, DecisionError
from bridge.agents.phrasing import numbers, valid_broker
from bridge.agents.runner import CachedRunner
from bridge.store import projections
from bridge.store.db import Store

from tests.conftest import DEAL_NAMES, DEALS_DIR
from tests.test_api import make_client, submitted_deal
from tests.test_phrasing import Live


def reviewed(tmp_path, name="bronx_mf", runner=None):
    chief = Chief(Store(tmp_path / "t.db"), runner or CachedRunner(), tmp_path / "out",
                  tmp_path / "up")
    deal_id = chief.create_deal()
    chief.ingest_directory(deal_id, DEALS_DIR / name)
    assert chief.process(deal_id) == "NEEDS_REVIEW"
    return chief, deal_id


def types(chief, deal_id):
    return [e.type for e in chief.store.events(deal_id) if e.type.startswith("reply.")]


# ---- what the draft says
@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_a_draft_never_carries_a_figure_from_the_calculations(tmp_path, decision, deal_name):
    chief, deal_id = reviewed(tmp_path, deal_name)
    deal, result, _ = chief.latest(deal_id)
    text = compose(deal, result, decision)
    allowed = numbers(deal.property.address.value + " " + deal.sponsor.name.value
                      + " ".join(result.open_questions))
    assert numbers(text) <= allowed
    assert "%" not in text and "$" not in text
    # the questions are the reviewer's own list for the sponsor, shown as written (and may use a
    # term like DSCR); the wording the draft adds around them must stay plain
    own = text
    for question in result.open_questions:
        own = own.replace(question, "")
    text = own
    for word in ("DSCR", "LTC", "LTV", "debt yield", "cap rate", "stress"):
        assert word.lower() not in text.lower()


def test_an_approval_asks_for_what_is_still_open_and_promises_nothing(tmp_path):
    chief, deal_id = reviewed(tmp_path, "yonkers_leaseup")
    deal, result, _ = chief.latest(deal_id)
    text = compose(deal, result, "approve")
    assert text.startswith(f"Subject: {deal.property.address.value}: next steps")
    assert "not a commitment to lend" in text
    for question in result.open_questions:
        assert f"- {question}" in text
    assert placeholders(text) == ["[Your name]", "[Your title]"]


def test_a_rejection_gives_themes_not_numbers(tmp_path):
    chief, deal_id = reviewed(tmp_path, "overleveraged_bk")
    deal, result, _ = chief.latest(deal_id)
    assert result.call == "decline"
    text = compose(deal, result, "reject")
    why = themes(result)
    assert why and all(f"- {t}" in text for t in why)
    assert len(why) == len(set(why))                     # leverage reasons collapse to one line
    assert "not able to move forward" in text and "welcome to send it again" in text


def test_a_rejection_with_no_rule_reason_invents_none(tmp_path):
    chief, deal_id = reviewed(tmp_path, "bronx_mf")        # a clean Screen the reviewer rejects
    deal, result, _ = chief.latest(deal_id)
    result = result.model_copy(update={"reasons": []})
    assert "main considerations" not in compose(deal, result, "reject")


def test_only_approve_and_reject_have_a_reply(tmp_path):
    chief, deal_id = reviewed(tmp_path)
    deal, result, _ = chief.latest(deal_id)
    with pytest.raises(ReplyError):
        compose(deal, result, "request_info")


# ---- when it is drafted
@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_a_decision_logs_a_draft(tmp_path, decision):
    chief, deal_id = reviewed(tmp_path)
    chief.decide(deal_id, decision, "")
    assert types(chief, deal_id) == ["reply.drafted"]
    draft = chief.reply_draft(deal_id)
    assert (draft.decision, draft.status, draft.wording, draft.edited) == (
        decision, "draft", "template", False)
    assert draft.approved_at is None


def test_asking_for_info_or_a_rerun_drafts_nothing(tmp_path):
    chief, deal_id = reviewed(tmp_path)
    chief.decide(deal_id, "request_info", "Please send the tax bill")
    assert chief.reply_draft(deal_id) is None
    chief2, deal2 = reviewed(tmp_path / "b")
    chief2.decide(deal2, "send_back", "")
    assert chief2.reply_draft(deal2) is None


def test_no_draft_before_a_decision_and_no_edit_without_one(tmp_path):
    chief, deal_id = reviewed(tmp_path)
    with pytest.raises(DecisionError):
        chief.draft_reply(deal_id)
    with pytest.raises(DecisionError):
        chief.edit_reply(deal_id, "hello")
    with pytest.raises(DecisionError):
        chief.approve_reply(deal_id)


# ---- the reviewer's part
def test_edit_then_approve_is_logged_and_nothing_is_sent(tmp_path):
    chief, deal_id = reviewed(tmp_path)
    chief.decide(deal_id, "approve", "")
    with pytest.raises(ReplyError, match=r"\[Your name\]"):
        chief.approve_reply(deal_id)                       # the blanks are still there
    text = chief.reply_draft(deal_id).text.replace("[Your name]", "Alex Reviewer").replace(
        "[Your title]", "Credit Analyst")
    edited = chief.edit_reply(deal_id, text)
    assert edited.edited and edited.status == "draft"
    done = chief.approve_reply(deal_id)
    assert done.status == "approved" and done.approved_at and "Alex Reviewer" in done.text
    assert types(chief, deal_id) == ["reply.drafted", "reply.edited", "reply.approved"]
    assert not any(e.type.startswith(("email", "message.sent"))
                   for e in chief.store.events(deal_id))


def test_editing_after_approval_needs_a_new_approval(tmp_path):
    chief, deal_id = reviewed(tmp_path)
    chief.decide(deal_id, "reject", "")
    chief.edit_reply(deal_id, "Hello,\n\nThank you. We cannot proceed.\n\nAlex")
    assert chief.approve_reply(deal_id).status == "approved"
    again = chief.edit_reply(deal_id, "Hello,\n\nThank you. We cannot proceed now.\n\nAlex")
    assert again.status == "draft" and again.approved_at is None


@pytest.mark.parametrize("text", ["", "   \n", "x" * 7000])
def test_an_empty_or_enormous_reply_is_refused(tmp_path, text):
    chief, deal_id = reviewed(tmp_path)
    chief.decide(deal_id, "approve", "")
    with pytest.raises(ReplyError):
        chief.edit_reply(deal_id, text)


def test_starting_over_replaces_the_edits_and_keeps_the_history(tmp_path):
    chief, deal_id = reviewed(tmp_path)
    chief.decide(deal_id, "approve", "")
    chief.edit_reply(deal_id, "My own words.")
    fresh = chief.draft_reply(deal_id)
    assert fresh.text.startswith("Subject:") and not fresh.edited and fresh.status == "draft"
    assert types(chief, deal_id) == ["reply.drafted", "reply.edited", "reply.drafted"]


def test_the_draft_is_rebuilt_from_the_log_alone(tmp_path):
    chief, deal_id = reviewed(tmp_path)
    chief.decide(deal_id, "approve", "")
    chief.edit_reply(deal_id, "Hello. Fine.")
    chief.approve_reply(deal_id)
    assert projections.reply_draft(Store(tmp_path / "t.db"), deal_id).status == "approved"


# ---- live wording
def test_live_wording_is_used_only_when_it_passes_the_check(tmp_path):
    chief, deal_id = reviewed(tmp_path)
    deal, result, _ = chief.latest(deal_id)
    plain = compose(deal, result, "reject")
    friendly = plain.replace("Hello,", "Good afternoon,")
    chief2, deal2 = reviewed(tmp_path / "b", runner=Live(friendly))
    chief2.decide(deal2, "reject", "")
    draft = chief2.reply_draft(deal2)
    assert draft.wording == "claude" and draft.text.startswith("Subject:") \
        and "Good afternoon," in draft.text


@pytest.mark.parametrize("change", [
    lambda t: t + "\nWe would offer up to 5 million.",                 # a new figure
    lambda t: t.replace("[Your name]", "Alex"),                        # a blank filled in for them
    lambda t: t.replace("\n- ", "\n"),                                 # the list flattened
    lambda t: t.replace("not able to move forward", "pleased to approve"),   # a changed outcome
    lambda t: t + "\nSee https://example.com",                         # a link
])
def test_wording_that_adds_or_drops_something_is_replaced_by_the_draft(tmp_path, change):
    chief, deal_id = reviewed(tmp_path, "overleveraged_bk")
    deal, result, _ = chief.latest(deal_id)
    plain = compose(deal, result, "reject")
    assert valid_broker(plain, plain) and not valid_broker(change(plain), plain)
    chief2, deal2 = reviewed(tmp_path / "b", "overleveraged_bk", runner=Live(change(plain)))
    chief2.decide(deal2, "reject", "")
    assert chief2.reply_draft(deal2).text == plain
    assert chief2.reply_draft(deal2).wording == "template"


def test_a_model_failure_leaves_the_template_draft(tmp_path):
    chief, deal_id = reviewed(tmp_path, runner=Live(RuntimeError("API down")))
    assert chief.decide(deal_id, "approve", "") == "RELEASED"
    assert chief.reply_draft(deal_id).wording == "template"


def test_a_drafting_failure_never_undoes_the_decision(tmp_path, monkeypatch):
    chief, deal_id = reviewed(tmp_path)
    monkeypatch.setattr("bridge.agents.chief.compose", lambda *a: 1 / 0)
    assert chief.decide(deal_id, "reject", "") == "REJECTED"
    assert chief.reply_draft(deal_id) is None
    assert any(e.type == "error" and "reply" in e.summary for e in chief.store.events(deal_id))


# ---- the API
def test_the_reply_routes(tmp_path):
    client = make_client(tmp_path)
    deal_id = submitted_deal(client)
    url = f"/api/deals/{deal_id}/reply-draft"
    assert client.get(url).json() is None
    assert client.post(url).status_code == 409                  # not decided yet
    assert client.put(url, json={"text": "x"}).status_code == 409
    client.post(f"/api/deals/{deal_id}/decision", json={"decision": "approve"})
    draft = client.get(url).json()
    assert draft["status"] == "draft" and draft["decision"] == "approve"
    assert client.post(f"{url}/approve").status_code == 422     # blanks still there
    assert client.put(url, json={"text": ""}).status_code == 422
    edited = client.put(url, json={"text": "Hello,\n\nThanks.\n\nAlex"}).json()
    assert edited["edited"] is True
    approved = client.post(f"{url}/approve").json()
    assert approved["status"] == "approved" and approved["text"].endswith("Alex\n")
    assert client.get("/api/deals/missing/reply-draft").status_code == 404
    assert client.post(url).json()["status"] == "draft"          # start over


def test_every_sample_deal_gets_a_logged_draft_on_either_decision(tmp_path):
    for i, name in enumerate(DEAL_NAMES):
        chief, deal_id = reviewed(tmp_path / str(i), name)
        chief.decide(deal_id, "approve" if i % 2 else "reject", "")
        draft = chief.reply_draft(deal_id)
        assert draft and draft.text.startswith("Subject:")
