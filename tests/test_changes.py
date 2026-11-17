"""What changed between two versions of a deal: the inputs that moved, the metrics they moved,
and whether the call changed."""
import pytest
from bridge.agents.chief import Chief
from bridge.agents.runner import CachedRunner
from bridge.core.diff import compare
from bridge.store.db import Store

from tests.conftest import DEALS_DIR


@pytest.fixture
def chief(tmp_path):
    c = Chief(Store(tmp_path / "t.db"), CachedRunner(), tmp_path / "out", tmp_path / "up")
    deal_id = c.create_deal()
    c.ingest_directory(deal_id, DEALS_DIR / "bronx_mf")
    c.process(deal_id)
    return c, deal_id


def edit(chief, deal_id, path, value, reason):
    patch = chief.propose_patch(deal_id, "data", path, value, reason)
    chief.confirm_patch(deal_id, patch.patch_id)


def test_the_first_version_has_nothing_to_compare(chief):
    c, deal_id = chief
    diff = c.version_diff(deal_id)
    assert diff.from_version == diff.to_version == 1 and diff.metrics == [] and diff.inputs == []


def test_an_edit_shows_the_input_that_moved_and_the_metrics_it_moved(chief):
    c, deal_id = chief
    edit(c, deal_id, "valuation.arv", 11_000_000, "the appraisal came in lower")
    diff = c.version_diff(deal_id)
    assert (diff.from_version, diff.to_version) == (1, 2)
    assert [i.path for i in diff.inputs] == ["valuation.arv"]
    assert diff.inputs[0].old == "12500000.0" and diff.inputs[0].new == "11000000.0"
    assert diff.inputs[0].reason == "the appraisal came in lower"
    moved = {m.key: m for m in diff.metrics}
    assert moved["loan_to_arv"].before == pytest.approx(0.52)
    assert moved["loan_to_arv"].after == pytest.approx(6_500_000 / 11_000_000)
    assert "ltc" not in moved                      # ARV does not touch cost: only what moved
    assert diff.call_before == diff.call_after == "screen"


def test_a_change_that_flips_the_call_says_so_and_names_the_new_reasons(chief):
    c, deal_id = chief
    edit(c, deal_id, "loan_request.loan_commitment", 7_400_000, "the sponsor asked for more")
    diff = c.version_diff(deal_id)
    assert diff.call_before == "screen" and diff.call_after != "screen"
    assert diff.reasons_added and not diff.reasons_removed


def test_compare_is_symmetric_about_what_it_reports(chief):
    c, deal_id = chief
    before = c.latest(deal_id)[1]
    edit(c, deal_id, "valuation.arv", 11_000_000, "x")
    after = c.latest(deal_id)[1]
    forward, backward = compare(before, after, []), compare(after, before, [])
    assert {m.key for m in forward.metrics} == {m.key for m in backward.metrics}
    assert compare(before, before, []).metrics == []
