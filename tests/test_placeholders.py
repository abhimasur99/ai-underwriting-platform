"""Memo narrative contract: the model writes placeholders, code fills numbers, and a digit
outside a placeholder fails validation."""
import pytest
from bridge.core.parsers import parse_deal_dir
from bridge.core.placeholders import (
    NarrativeError,
    fill,
    find_stray_digits,
    placeholder_values,
    validate_narrative,
)
from bridge.core.underwrite import underwrite

from tests.conftest import DEALS_DIR


@pytest.fixture
def bronx():
    return underwrite(parse_deal_dir(DEALS_DIR / "bronx_mf"))


def test_fill_formats_numbers_from_the_result(bronx):
    text = ("LTC {{metrics.ltc}}, take-out {{exit.takeout_max}}, cushion {{exit.refi_cushion}}, "
            "DSCR {{exit.exit_dscr}}, binding {{exit.binding}}, call {{call}}")
    out = fill(text, bronx)
    assert out == ("LTC 70.65%, take-out $8,235,294, cushion $1,735,294, DSCR 1.79x, "
                   "binding debt yield, call SCREEN")


def test_unknown_placeholder_fails_loudly(bronx):
    with pytest.raises(NarrativeError):
        fill("Value {{metrics.made_up}}", bronx)


@pytest.mark.parametrize("text,digits", [
    ("LTC is {{metrics.ltc}} and about 70%", ["70"]),
    ("Costs rose in 2026", ["2026"]),
    ("Only {{metrics.ltc}} here", []),
    ("No numbers at all", []),
])
def test_stray_digits_found_outside_placeholders_only(text, digits):
    assert find_stray_digits(text) == digits


def test_validate_rejects_digits_outside_placeholders():
    with pytest.raises(NarrativeError):
        validate_narrative({"summary": "LTC is {{metrics.ltc}}", "risks": "about 70% leverage"})


def test_default_narrative_is_valid_and_fills_for_every_deal(deal_dir):
    r = underwrite(deal_dir and parse_deal_dir(deal_dir))
    validate_narrative(r.narrative)
    for text in r.narrative.values():
        assert "{{" not in fill(text, r)


def test_every_placeholder_key_resolves(bronx):
    values = placeholder_values(bronx)
    assert values["metrics.ltc"] == "70.65%"
    assert values["recon.rent_roll_vs_t12"] == "2.13%"
    assert values["stress.takeout_max"] == "$7,200,000"
    assert values["reasons.count"] == "0"
