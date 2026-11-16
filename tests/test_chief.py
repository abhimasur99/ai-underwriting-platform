"""Chief: state machine, handoffs, retry and escalation, decisions, patches."""
import json

import pytest
from bridge.agents import patches as patching
from bridge.agents.chief import Chief, DecisionError
from bridge.agents.runner import CachedRunner
from bridge.agents.states import STATES, TRANSITIONS, InvalidTransition, check_transition
from bridge.agents.underwriter import FaultPlan
from bridge.core.placeholders import NarrativeError
from bridge.store import projections
from bridge.store.db import Store

from tests.conftest import DEALS_DIR


def make_chief(tmp_path, faults=None, runner=None):
    store = Store(tmp_path / "t.db")
    return Chief(store, runner or CachedRunner(), tmp_path / "out", tmp_path / "up", faults=faults)


def ready(tmp_path, name="bronx_mf", **kw):
    chief = make_chief(tmp_path, **kw)
    deal_id = chief.create_deal()
    chief.ingest_directory(deal_id, DEALS_DIR / name)
    return chief, deal_id


def states(chief, deal_id):
    return [e.payload["to"] for e in chief.store.events(deal_id) if e.type == "state.changed"]


def review(tmp_path, name="bronx_mf", **kw):
    chief, deal_id = ready(tmp_path, name, **kw)
    assert chief.process(deal_id) == "NEEDS_REVIEW"
    return chief, deal_id


# ---- transition table
def test_every_documented_transition_is_allowed_and_nothing_else():
    for a, b in TRANSITIONS:
        check_transition(a, b)
    assert {s for pair in TRANSITIONS for s in pair} <= set(STATES)
    for bad in [("READY", "UNDERWRITING"), ("EXTRACTED", "NEEDS_REVIEW"), ("APPROVED", "READY"),
                ("REJECTED", "UNDERWRITING"), ("CHECKING", "APPROVED"), ("CREATED", "CHECKING")]:
        with pytest.raises(InvalidTransition):
            check_transition(*bad)
    check_transition("EXTRACTING", "FAILED")           # any state may fail


# ---- intake side
def test_checklist_drives_awaiting_docs_then_ready(tmp_path):
    chief = make_chief(tmp_path)
    deal_id = chief.create_deal()
    assert chief.state(deal_id) == "CREATED"
    src = DEALS_DIR / "bronx_mf"
    status = chief.register_file(deal_id, "rent_roll.csv", (src / "rent_roll.csv").read_bytes(),
                                 "rent_roll")
    assert status["received"] == ["rent_roll"] and not status["ready"]
    assert chief.state(deal_id) == "AWAITING_DOCS"
    chief.ingest_directory(deal_id, src)
    assert chief.state(deal_id) == "READY"


# ---- happy path
def test_full_run_reaches_review_with_handoffs_and_events(tmp_path, deal_name):
    chief, deal_id = review(tmp_path, deal_name)
    assert states(chief, deal_id)[-8:] == [
        "READY", "EXTRACTING", "EXTRACTED", "UNDERWRITING", "UNDERWRITTEN", "CHECKING",
        "CHECKED", "NEEDS_REVIEW"]
    events = chief.store.events(deal_id)
    sent = [e.payload["to"] for e in events if e.type == "handoff.sent"]
    returned = [e.actor for e in events if e.type == "handoff.returned"]
    assert sent == ["extraction", "underwriter", "checker"]
    assert returned == ["extraction", "underwriter", "checker"]
    assert all(e.payload["from"] == "chief" for e in events if e.type == "handoff.sent")
    st = projections.status(chief.store, deal_id)
    assert st.state == "NEEDS_REVIEW" and not st.escalation and st.call is not None
    deal, result, check = chief.latest(deal_id)
    assert check.status in ("pass", "warn") and result.deal_id == deal_id


def test_specialist_agents_never_call_each_other(tmp_path):
    chief, deal_id = review(tmp_path)
    for e in chief.store.events(deal_id):
        if e.type == "handoff.sent":
            assert e.payload["from"] == "chief"
        if e.type == "handoff.returned":
            assert e.summary.endswith("-> chief: ok")


def test_process_requires_a_ready_deal_and_does_not_fail_it(tmp_path):
    chief = make_chief(tmp_path)
    deal_id = chief.create_deal()
    with pytest.raises(InvalidTransition):
        chief.process(deal_id)
    assert chief.state(deal_id) == "CREATED"          # still recoverable


def test_missing_required_field_goes_to_needs_input(tmp_path):
    chief, deal_id = ready(tmp_path)
    (chief.deal_dir(deal_id) / "cached" / "extracted.json").unlink()
    p = chief.deal_dir(deal_id) / "deal_summary.md"
    p.write_text(p.read_text().replace("- Note rate: 10.50% interest-only\n", ""))
    assert chief.process(deal_id) == "NEEDS_INPUT"
    event = next(e for e in chief.store.events(deal_id)
                 if e.type == "state.changed" and e.payload["to"] == "NEEDS_INPUT")
    assert "note_rate" in event.payload["missing"]


def test_an_unexpected_error_becomes_a_visible_failed_state(tmp_path):
    class Boom(CachedRunner):
        def write_narrative(self, result, feedback=None):
            raise RuntimeError("model unavailable")

    chief, deal_id = ready(tmp_path, runner=Boom())
    assert chief.process(deal_id) == "FAILED"
    err = next(e for e in chief.store.events(deal_id) if e.type == "error")
    assert "model unavailable" in err.summary


# ---- retry loop and escalation
def test_a_check_failure_retries_and_then_passes(tmp_path):
    chief, deal_id = ready(tmp_path, faults=FaultPlan("ltc", 0.01, frozenset({1})))
    assert chief.process(deal_id) == "NEEDS_REVIEW"
    events = chief.store.events(deal_id)
    assert [e.type for e in events].count("check.retry") == 1
    assert [e.payload["to"] for e in events if e.type == "handoff.sent"] == [
        "extraction", "underwriter", "checker", "underwriter", "checker"]
    st = projections.status(chief.store, deal_id)
    assert not st.escalation and st.retry_count == 1
    assert chief.latest(deal_id)[2].status in ("pass", "warn")


def test_a_persistent_mismatch_retries_twice_then_escalates(tmp_path):
    chief, deal_id = ready(tmp_path, faults=FaultPlan("ltc", 0.01, frozenset({1, 2, 3})))
    assert chief.process(deal_id) == "NEEDS_REVIEW"
    events = chief.store.events(deal_id)
    assert [e.type for e in events].count("check.retry") == 2
    assert [e.payload["to"] for e in events if e.type == "handoff.sent"] == [
        "extraction", "underwriter", "checker", "underwriter", "checker", "underwriter",
        "checker"]
    final = [e for e in events if e.type == "state.changed"][-1]
    assert final.payload["to"] == "NEEDS_REVIEW" and final.payload["escalation"] is True
    st = projections.status(chief.store, deal_id)
    assert st.escalation and st.retry_count == 2 and st.flags >= 1
    deal, result, check = chief.latest(deal_id)
    assert check.status == "fail" and check.mismatches[0].field == "ltc"
    review_event = [e for e in events if e.type == "review.requested"][-1]
    assert review_event.payload["escalation"] is True


# ---- decisions
def test_approve_records_the_human_decision_and_locks_a_snapshot(tmp_path):
    chief, deal_id = review(tmp_path)
    assert chief.decide(deal_id, "approve", "Looks fine") == "RELEASED"
    assert states(chief, deal_id)[-2:] == ["APPROVED", "RELEASED"]
    decision = next(e for e in chief.store.events(deal_id) if e.type == "decision.recorded")
    assert decision.actor == "reviewer" and decision.payload["ai_call"] == "screen"
    deal, result, _ = chief.latest(deal_id)
    snap = json.loads((tmp_path / "out" / deal_id / "v1" / "released.json").read_text())
    assert snap["decision"]["decision"] == "approve"


def test_reject_and_wrong_state(tmp_path):
    chief, deal_id = review(tmp_path)
    assert chief.decide(deal_id, "reject", "Not a fit") == "REJECTED"
    with pytest.raises(DecisionError):
        chief.decide(deal_id, "approve")


def test_send_back_reruns_underwriting_and_returns_to_review(tmp_path):
    chief, deal_id = review(tmp_path)
    assert chief.decide(deal_id, "send_back", "recheck") == "NEEDS_REVIEW"
    seq = states(chief, deal_id)
    assert "SENT_BACK" in seq and seq[-1] == "NEEDS_REVIEW"
    assert seq[seq.index("SENT_BACK") + 1] == "UNDERWRITING"


# ---- patches
def test_data_patch_needs_a_confirm_then_bumps_the_version(tmp_path):
    chief, deal_id = review(tmp_path)
    p = chief.propose_patch(deal_id, "data", "valuation.arv", 9_000_000, "Reviewer: broker cut ARV")
    assert (p.old, p.new, p.status) == (12_500_000, 9_000_000.0, "proposed")
    assert chief.store.get_deal(deal_id).version == 1       # nothing applied yet
    assert chief.confirm_patch(deal_id, p.patch_id) == "NEEDS_REVIEW"
    deal, result, check = chief.latest(deal_id)
    assert deal.version == 2 and deal.valuation.arv.value == 9_000_000
    assert deal.valuation.arv.source.kind == "override"
    assert result.call == "decline" and result.metrics.loan_to_arv == pytest.approx(6.5 / 9)
    assert check.status in ("pass", "warn")                  # checker applies the override too
    assert chief.store.get_deal(deal_id, 1).valuation.arv.value == 12_500_000   # old readable
    assert (tmp_path / "out" / deal_id / "v2" / "memo.pdf").exists()
    assert chief.store.versions(deal_id) == [1, 2]
    types = [e.type for e in chief.store.events(deal_id)]
    assert {"patch.proposed", "patch.confirmed", "version.created"} <= set(types)


def test_rent_edit_recomputes_derived_totals_and_checker_agrees(tmp_path):
    chief, deal_id = review(tmp_path)
    p = chief.propose_patch(deal_id, "data", "rent_roll.units[0].monthly_rent", 2100,
                            "Reviewer: signed lease shows 2,100")
    assert p.old == 1320
    chief.confirm_patch(deal_id, p.patch_id)
    deal, result, check = chief.latest(deal_id)
    assert deal.rent_roll.annual_occupied_rent.value == 730_320 - 12 * 1320 + 12 * 2100
    assert check.status in ("pass", "warn")


def test_cancelled_patch_changes_nothing(tmp_path):
    chief, deal_id = review(tmp_path)
    p = chief.propose_patch(deal_id, "data", "valuation.arv", 9_000_000, "x")
    chief.cancel_patch(deal_id, p.patch_id)
    with pytest.raises(patching.PatchError):
        chief.confirm_patch(deal_id, p.patch_id)
    assert chief.store.versions(deal_id) == [1]


def test_unsupported_edit_paths_are_refused(tmp_path):
    chief, deal_id = review(tmp_path)
    with pytest.raises(patching.PatchError):
        chief.propose_patch(deal_id, "data", "purchase.purchase_price", 1, "x")


def test_patch_needs_review_state(tmp_path):
    chief, deal_id = ready(tmp_path)
    with pytest.raises(Exception):  # noqa: B017  (no result yet, or not in review)
        chief.propose_patch(deal_id, "data", "valuation.arv", 1, "x")


def underwriter_calls(chief, deal_id):
    return sum(1 for e in chief.store.events(deal_id)
               if e.type == "tool.called" and e.actor == "underwriter")


def test_narrative_edit_rerenders_the_memo_only(tmp_path):
    chief, deal_id = review(tmp_path)
    before, calls = chief.latest(deal_id)[1], underwriter_calls(chief, deal_id)
    p = chief.propose_patch(deal_id, "narrative", "narrative.summary",
                            "Reviewer view: leverage of {{metrics.ltc}} is acceptable here.", "")
    chief.confirm_patch(deal_id, p.patch_id)
    deal, after, check = chief.latest(deal_id)
    assert after.narrative["summary"].startswith("Reviewer view")
    assert after.metrics == before.metrics and deal.version == 1
    assert underwriter_calls(chief, deal_id) == calls          # nothing recomputed
    assert check.status in ("pass", "warn")
    assert any(e.type == "check.completed" and e.payload.get("scope") == "memo_number_match"
               for e in chief.store.events(deal_id))


def test_narrative_edit_with_digits_is_rejected(tmp_path):
    chief, deal_id = review(tmp_path)
    with pytest.raises(NarrativeError):
        chief.propose_patch(deal_id, "narrative", "narrative.summary", "About 70% leverage.", "")


def test_override_needs_a_reason_and_leaves_numbers_unchanged(tmp_path):
    chief, deal_id = review(tmp_path)
    with pytest.raises(patching.PatchError):
        chief.propose_patch(deal_id, "override", "judgment", "Comfortable with stress case", "")
    before = chief.latest(deal_id)[1]
    p = chief.propose_patch(deal_id, "override", "judgment", "Comfortable with the stress case",
                            "Sponsor has a strong track record")
    chief.confirm_patch(deal_id, p.patch_id)
    deal, after, check = chief.latest(deal_id)
    assert after.metrics == before.metrics and after.call == before.call
    assert after.overrides == ["Comfortable with the stress case (reason: Sponsor has a strong "
                               "track record)"]
    assert any(e.type == "override.recorded" for e in chief.store.events(deal_id))
    from bridge.core.independent.pdftext import extract_pdf_text
    assert "Reviewer overrides" in extract_pdf_text(after.artifacts["memo_pdf"])
    assert check.status in ("pass", "warn")


def test_the_queue_reflects_each_deal(tmp_path):
    chief, deal_id = review(tmp_path)
    other = chief.create_deal()
    rows = {r.deal_id: r for r in projections.queue(chief.store)}
    assert rows[deal_id].stage == "Review" and rows[other].stage == "Awaiting docs"
