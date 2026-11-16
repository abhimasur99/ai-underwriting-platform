"""Reconciliation: rent roll vs T-12, sources vs uses, unit count (clean and broken input)."""
import pytest
from bridge.core.parsers import parse_deal_dir
from bridge.core.reconcile import reconcile_all
from bridge.core.rules import load_rules

from tests.conftest import DEALS_DIR


@pytest.fixture(scope="module")
def rules():
    return load_rules()


@pytest.fixture
def bronx():
    return parse_deal_dir(DEALS_DIR / "bronx_mf")


def by_name(items):
    return {i.name: i for i in items}


def test_clean_deal_passes_everything(bronx, rules):
    items, flags = reconcile_all(bronx, rules)
    got = by_name(items)
    assert [i.status for i in items] == ["pass", "pass", "pass"]
    assert got["rent_roll_vs_t12"].gap == pytest.approx(0.021278, abs=1e-6)
    assert got["sources_vs_uses"].gap == 0
    assert flags == []


def test_matches_answer_key(deal_dir, expected, rules):
    items, _ = reconcile_all(parse_deal_dir(deal_dir), rules)
    got, m = by_name(items), expected["metrics"]
    assert got["rent_roll_vs_t12"].gap == pytest.approx(m["rr_vs_t12_gap"], abs=1e-4)
    assert got["sources_vs_uses"].gap == pytest.approx(m["sources_vs_uses_gap"], abs=1e-4)
    assert (got["unit_count"].status == "pass") == m["unit_count_match"]


@pytest.mark.parametrize("rent,status", [
    (715_104 * 1.05, "pass"),        # exactly at the pass limit: not a reason
    (715_104 * 1.0501, "watch"),
    (715_104 * 1.10, "watch"),       # exactly at the decline limit: still watch
    (715_104 * 1.1001, "decline"),
])
def test_rent_roll_vs_t12_boundaries(bronx, rules, rent, status):
    bronx.rent_roll.annual_occupied_rent.value = rent
    assert by_name(reconcile_all(bronx, rules)[0])["rent_roll_vs_t12"].status == status


@pytest.mark.parametrize("extra,status", [
    (0, "pass"), (9_200_000 * 0.005, "pass"), (9_200_000 * 0.0051, "watch"),
    (9_200_000 * 0.01, "watch"), (9_200_000 * 0.0101, "decline"),
])
def test_sources_vs_uses_boundaries(bronx, rules, extra, status):
    bronx.sources_uses.sources[-1].amount += extra
    assert by_name(reconcile_all(bronx, rules)[0])["sources_vs_uses"].status == status


def test_sources_vs_uses_uses_components_not_stated_totals(bronx, rules):
    bronx.sources_uses.sources[0].amount += 500_000   # stated totals untouched
    item = by_name(reconcile_all(bronx, rules)[0])["sources_vs_uses"]
    assert item.gap == pytest.approx(500_000 / 9_200_000)


def test_stated_total_that_differs_from_components_is_flagged(bronx, rules):
    bronx.sources_uses.stated_total_uses.value = 9_000_000
    codes = [f.code for f in reconcile_all(bronx, rules)[1]]
    assert codes == ["USES_TOTAL_MISMATCH"]


def test_unit_count_mismatch_is_watch(bronx, rules):
    bronx.property.unit_count.value = 41
    item = by_name(reconcile_all(bronx, rules)[0])["unit_count"]
    assert item.status == "watch"
    assert (item.a, item.b) == (41, 40)
