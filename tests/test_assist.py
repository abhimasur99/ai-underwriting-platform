"""Model-assisted extraction (core side): the model only fills what the deterministic parser could
not find, and only what the document itself supports. Uses a fake assist; no model is involved."""
import csv
import shutil

import pytest
from bridge.core.parsers import parse_deal_dir
from bridge.core.parsers.assist import RawField, RawReading, RawRow
from bridge.core.parsers.errors import MissingRequiredFieldError
from bridge.core.underwrite import underwrite

from scripts.sample_docs import markdown_to_pdf
from tests.conftest import DEALS_DIR

# A broker's summary in its own words: none of our labels, no Deal ID, tables headed differently.
BROKER_SUMMARY = """# Offering memorandum: Maple Court

Prepared for lender review

## The property
- Maple Court Apartments, 55 Maple Court, Yonkers, NY 10701
- 24 apartments (multi-family walk-up), 22 currently leased

## The borrower
- Maple Court Holdings LLC

## Financing requested
- Requested loan: $3,000,000, of which $2,450,000 funds at closing
- Rate: 10.25% interest only for 18 months

## Value
- Value today $3,900,000; value when renovated and stabilized $5,650,000

## Capital stack
| Item | Amount |
| Senior loan | $3,000,000 |
| Equity | $1,450,000 |
| Total capitalization | $4,450,000 |

| Use | Amount |
| Acquisition | $3,900,000 |
| Rehab | $550,000 |
| Total uses | $4,450,000 |

## Projected income at stabilization
- Net operating income: $327,800
"""
BROKER_CONTRACT = """# Agreement of sale

- Seller: Sample Seller LLC
- Price: $3,900,000
"""


UNITS_LINE = "24 apartments (multi-family walk-up), 22 currently leased"


def q(key, value_text, quote):
    return RawField(key, value_text, quote)


GOOD_SUMMARY = RawReading(
    fields=[
        q("address", "55 Maple Court, Yonkers, NY 10701",
          "Maple Court Apartments, 55 Maple Court, Yonkers, NY 10701"),
        q("asset_type", "multi-family", UNITS_LINE),
        q("unit_count", "24", UNITS_LINE),
        q("occupied_units", "22", UNITS_LINE),
        q("sponsor_name", "Maple Court Holdings LLC", "Maple Court Holdings LLC"),
        q("loan_commitment", "$3,000,000",
          "Requested loan: $3,000,000, of which $2,450,000 funds at closing"),
        q("initial_advance", "$2,450,000",
          "Requested loan: $3,000,000, of which $2,450,000 funds at closing"),
        q("note_rate", "10.25%", "Rate: 10.25% interest only for 18 months"),
        q("as_is_value", "$3,900,000",
          "Value today $3,900,000; value when renovated and stabilized $5,650,000"),
        q("arv", "$5,650,000",
          "Value today $3,900,000; value when renovated and stabilized $5,650,000"),
        q("stabilized_noi", "$327,800", "Net operating income: $327,800"),
    ],
    sources=[RawRow("Senior loan", "$3,000,000", "Senior loan | $3,000,000"),
             RawRow("Equity", "$1,450,000", "Equity | $1,450,000")],
    uses=[RawRow("Acquisition", "$3,900,000", "Acquisition | $3,900,000"),
          RawRow("Rehab", "$550,000", "Rehab | $550,000", is_renovation_budget=True)],
    total_sources=RawRow("Total capitalization", "$4,450,000", "Total capitalization | $4,450,000"),
    total_uses=RawRow("Total uses", "$4,450,000", "Total uses | $4,450,000"),
)
GOOD_CONTRACT = RawReading(fields=[q("purchase_price", "$3,900,000", "Price: $3,900,000")])


class FakeAssist:
    def __init__(self, summary=GOOD_SUMMARY, contract=GOOD_CONTRACT, mapping=None):
        self.summary, self.contract, self.mapping = summary, contract, mapping or {}
        self.reads, self.maps = [], []

    def read_document(self, name, text, wanted, want_tables):
        self.reads.append((name, [s.key for s in wanted], want_tables))
        return self.summary if "summary" in name else self.contract

    def map_columns(self, kind, headers, sample):
        self.maps.append((kind, list(headers)))
        return self.mapping


def broker_deal(tmp_path, summary_format="pdf"):
    folder = tmp_path / "broker"
    shutil.copytree(DEALS_DIR / "statenisland_mf", folder,
                    ignore=shutil.ignore_patterns("cached", "expected.json", "README.md",
                                                  "deal_summary.*", "purchase_contract.*"))
    markdown_to_pdf(BROKER_SUMMARY, folder / "deal_summary.pdf", "Offering memorandum")
    markdown_to_pdf(BROKER_CONTRACT, folder / "purchase_contract.pdf", "Agreement of sale")
    return folder


def test_without_an_assist_an_unfamiliar_summary_stops_and_asks(tmp_path):
    with pytest.raises(MissingRequiredFieldError) as exc:
        parse_deal_dir(broker_deal(tmp_path))
    assert {"address", "loan_commitment", "arv", "purchase_price", "sources_table",
            "stabilized_noi"} <= set(exc.value.missing)


def test_with_an_assist_verified_fields_build_a_deal_marked_as_model_read(tmp_path):
    assist = FakeAssist()
    deal = parse_deal_dir(broker_deal(tmp_path), assist=assist)
    assert deal.loan_request.loan_commitment.value == 3_000_000
    assert deal.loan_request.note_rate.value == pytest.approx(0.1025)
    assert deal.property.occupied_units.value == 22 and deal.property.unit_count.value == 24
    assert deal.valuation.arv.value == 5_650_000
    assert deal.purchase.purchase_price.value == 3_900_000
    assert deal.renovation.renovation_budget.value == 550_000
    assert deal.sources_uses.stated_total_uses.value == 4_450_000
    assert deal.deal_id == "broker" and deal.name == "Maple Court"
    assert deal.property.asset_type.value == "multifamily"      # "multi-family" as written
    src = deal.loan_request.loan_commitment
    assert src.confidence == 0.75
    assert src.source.doc == "deal_summary.pdf" and src.source.quote.startswith("Requested loan")
    flag = next(f for f in deal.flags if f.code == "MODEL_ASSISTED_EXTRACTION")
    assert "loan_commitment" in flag.message and "check" in flag.message.lower()


def test_the_model_is_asked_once_per_document_even_though_the_parse_runs_twice(tmp_path):
    assist = FakeAssist()
    parse_deal_dir(broker_deal(tmp_path), assist=assist)
    assert [name for name, *_ in assist.reads].count("deal_summary.pdf") == 1
    assert [name for name, *_ in assist.reads].count("purchase_contract.pdf") == 1


def test_model_read_key_fields_keep_the_call_at_watch_until_a_person_checks(tmp_path):
    result = underwrite(parse_deal_dir(broker_deal(tmp_path), assist=FakeAssist()))
    assert result.call == "watch"
    assert "LOW_CONFIDENCE_FIELD" in [r.code for r in result.reasons]


def test_a_value_that_is_not_in_its_quote_is_refused(tmp_path):
    bad = RawReading(fields=[
        *[f for f in GOOD_SUMMARY.fields if f.key != "loan_commitment"],
        q("loan_commitment", "$3,500,000",
          "Requested loan: $3,000,000, of which $2,450,000 funds at closing")],
        sources=GOOD_SUMMARY.sources, uses=GOOD_SUMMARY.uses,
        total_sources=GOOD_SUMMARY.total_sources, total_uses=GOOD_SUMMARY.total_uses)
    with pytest.raises(MissingRequiredFieldError) as exc:
        parse_deal_dir(broker_deal(tmp_path), assist=FakeAssist(summary=bad))
    assert exc.value.missing == ["loan_commitment"]
    assert "not inside its quote" in exc.value.refused["loan_commitment"]


def test_an_invented_quote_is_refused(tmp_path):
    bad = RawReading(fields=[
        *[f for f in GOOD_SUMMARY.fields if f.key != "arv"],
        q("arv", "$9,000,000", "After-repair value: $9,000,000")],
        sources=GOOD_SUMMARY.sources, uses=GOOD_SUMMARY.uses,
        total_sources=GOOD_SUMMARY.total_sources, total_uses=GOOD_SUMMARY.total_uses)
    with pytest.raises(MissingRequiredFieldError) as exc:
        parse_deal_dir(broker_deal(tmp_path), assist=FakeAssist(summary=bad))
    assert exc.value.missing == ["arv"]
    assert "not a single line of the document" in exc.value.refused["arv"]


def test_a_total_that_the_document_does_not_support_leaves_the_tables_missing(tmp_path):
    bad = RawReading(fields=GOOD_SUMMARY.fields, sources=GOOD_SUMMARY.sources,
                     uses=GOOD_SUMMARY.uses, total_sources=GOOD_SUMMARY.total_sources,
                     total_uses=RawRow("Total uses", "$4,999,999", "Total uses | $4,999,999"))
    with pytest.raises(MissingRequiredFieldError) as exc:
        parse_deal_dir(broker_deal(tmp_path), assist=FakeAssist(summary=bad))
    assert {"uses_table", "stated_total_uses"} <= set(exc.value.missing)


def test_the_model_is_not_called_when_the_deterministic_parse_works():
    class Boom:
        def read_document(self, *a):
            raise AssertionError("the model must not be asked")

        def map_columns(self, *a):
            raise AssertionError("the model must not be asked")

    deal = parse_deal_dir(DEALS_DIR / "bronx_mf", assist=Boom())
    assert deal.flags == [] and deal.loan_request.loan_commitment.confidence == 0.98


# ---- table columns
def renamed_rent_roll(tmp_path, headers):
    folder = tmp_path / "renamed"
    shutil.copytree(DEALS_DIR / "bronx_mf", folder,
                    ignore=shutil.ignore_patterns("cached", "expected.json", "README.md"))
    with (folder / "rent_roll.csv").open(newline="") as fh:
        rows = list(csv.reader(fh))
    rows[0] = headers
    with (folder / "rent_roll.csv").open("w", newline="") as fh:
        csv.writer(fh).writerows(rows)
    return folder


ODD = ["Apt #", "Layout", "Sq Ft", "Occupancy", "Resident", "Move In", "Lease Exp", "Rent"]
MAPPING = {"Apt #": "unit", "Layout": "unit_type", "Sq Ft": "sqft", "Occupancy": "status",
           "Resident": "tenant", "Move In": "lease_start", "Lease Exp": "lease_end",
           "Rent": "monthly_rent"}


def test_unfamiliar_column_headings_are_mapped_but_the_numbers_come_from_the_table(tmp_path):
    folder = renamed_rent_roll(tmp_path, ODD)
    with pytest.raises(MissingRequiredFieldError):
        parse_deal_dir(folder)
    assist = FakeAssist(mapping=MAPPING)
    deal = parse_deal_dir(folder, assist=assist)
    original = parse_deal_dir(DEALS_DIR / "bronx_mf")
    assert deal.rent_roll.units == original.rent_roll.units
    assert len(assist.maps) == 1
    flag = next(f for f in deal.flags if f.code == "MODEL_ASSISTED_EXTRACTION")
    assert "rent_roll.csv" in flag.message and "monthly_rent" in flag.message


def test_a_bad_column_mapping_is_ignored(tmp_path):
    folder = renamed_rent_roll(tmp_path, ODD)
    bad = {"Apt #": "unit", "Rent": "monthly_rent", "Resident": "monthly_rent",   # claimed twice
           "Layout": "not_a_column", "Made Up": "unit_type"}                        # unknown names
    with pytest.raises(MissingRequiredFieldError) as exc:
        parse_deal_dir(folder, assist=FakeAssist(mapping=bad))
    assert set(exc.value.missing) == {"rent_roll.unit_type", "rent_roll.status"}


def test_month_headings_like_nov_25_are_understood_without_a_model(tmp_path):
    folder = tmp_path / "t12"
    shutil.copytree(DEALS_DIR / "bronx_mf", folder,
                    ignore=shutil.ignore_patterns("cached", "expected.json", "README.md"))
    with (folder / "t12.csv").open(newline="") as fh:
        rows = list(csv.reader(fh))
    names = ["Nov-25", "Dec-25", "Jan-26", "Feb-26", "Mar-26", "Apr-26", "May-26", "Jun-26",
             "Jul-26", "Aug-26", "Sep-26", "Oct-26"]
    rows[0] = ["Line Item", "Category", *names, "Total"]
    with (folder / "t12.csv").open("w", newline="") as fh:
        csv.writer(fh).writerows(rows)
    deal = parse_deal_dir(folder)
    assert deal.t12.lines == parse_deal_dir(DEALS_DIR / "bronx_mf").t12.lines
    assert not [f for f in deal.flags if f.code == "T12_ROW_TOTAL_MISMATCH"]


# ---- through the chief and the independent checker
def run_through_chief(tmp_path, runner, folder):
    from bridge.agents.chief import Chief
    from bridge.core import completeness
    from bridge.store.db import Store
    chief = Chief(Store(tmp_path / "t.db"), runner, tmp_path / "out", tmp_path / "up")
    deal_id = chief.create_deal()
    for stem in ("deal_summary", "purchase_contract", "rent_roll", "t12", "renovation_budget"):
        path = next(folder.glob(f"{stem}.*"))
        chief.register_file(deal_id, path.name, path.read_bytes(), stem)
    facts = {"property_address": "55 Maple Court, Yonkers, NY 10701", "asset_type": "multifamily",
             "unit_count": "24", "loan_amount_requested": "3000000", "purchase_price": "3900000",
             "renovation_budget": "550000", "sponsor_name": "Maple Court Holdings LLC"}
    for key, value in facts.items():
        chief.record_fact(deal_id, key, value)
    assert completeness.status(["deal_summary", "purchase_contract", "rent_roll", "t12",
                                "renovation_budget"], facts).ready
    chief.process(deal_id)
    return chief, deal_id


def test_a_model_read_deal_reaches_review_with_an_honest_check(tmp_path):
    from bridge.agents.runner import CachedRunner
    from bridge.store import projections

    class Offline(CachedRunner):
        """Extraction through the assist, everything else offline (no model needed)."""
        def extract_deal(self, deal_dir):
            return parse_deal_dir(deal_dir, assist=FakeAssist())

    chief, deal_id = run_through_chief(tmp_path, Offline(), broker_deal(tmp_path))
    status = projections.status(chief.store, deal_id)
    assert status.state == "NEEDS_REVIEW", status
    _, result, check = chief.latest(deal_id)
    assert result.call == "watch"
    by_name = {c.name: c for c in check.checks}
    assert by_name["extraction_match"].status == "warn"
    assert by_name["extraction_match"].detail["independently_reparsed"] is False
    assert by_name["rules_recheck"].status == "pass"      # LOW_CONFIDENCE_FIELD is not its concern
    # the part that does not depend on the second parse still holds, on the PDF's own text
    assert by_name["source_trace"].status == "pass", by_name["source_trace"].detail
    assert by_name["recompute_metrics"].status == "pass"
    assert check.status == "warn"


def test_a_deterministic_deal_still_gets_a_full_independent_parse(tmp_path):
    from bridge.agents.chief import Chief
    from bridge.agents.runner import CachedRunner
    from bridge.store.db import Store
    chief = Chief(Store(tmp_path / "t.db"), CachedRunner(), tmp_path / "out", tmp_path / "up")
    deal_id = chief.create_deal()
    chief.ingest_directory(deal_id, DEALS_DIR / "bronx_mf")
    chief.process(deal_id)
    _, _, check = chief.latest(deal_id)
    match = next(c for c in check.checks if c.name == "extraction_match")
    assert match.status == "pass" and match.detail["independently_reparsed"] is True


def test_the_checker_does_not_hide_a_real_parse_failure_on_a_deterministic_deal(tmp_path):
    """The fallback exists only for deals the model read; any other parse failure still fails."""
    import shutil

    from bridge.agents.checker import run_checker
    from bridge.agents.recorder import Recorder
    from bridge.agents.runner import CachedRunner
    from bridge.core.builders.memo import render_memo
    from bridge.core.builders.workbook import build_workbook
    from bridge.core.rules import load_rules
    from bridge.store.db import Store
    folder = tmp_path / "deal"
    shutil.copytree(DEALS_DIR / "bronx_mf", folder, ignore=shutil.ignore_patterns("cached"))
    deal = parse_deal_dir(folder)
    result = underwrite(deal)
    result.artifacts = {"memo_pdf": str(tmp_path / "memo.pdf"),
                        "workbook": str(tmp_path / "w.xlsx")}
    build_workbook(deal, result, load_rules(), tmp_path / "w.xlsx")
    render_memo(deal, result, tmp_path / "memo.pdf")
    summary = folder / "deal_summary.md"                    # the checker's regexes now fail
    summary.write_text(summary.read_text().replace("Loan commitment requested", "Requested"))
    store = Store(tmp_path / "t.db")
    store.create_deal("D-1")
    with pytest.raises(ValueError):
        run_checker(deal, result, folder, Recorder(store, "D-1"), CachedRunner())


def test_a_failed_refusal_detail_is_logged_when_the_model_answer_is_not_accepted(tmp_path):
    from bridge.agents.runner import CachedRunner

    bad = RawReading(fields=[q("arv", "$9,000,000", "After-repair value: $9,000,000")])

    class Offline(CachedRunner):
        def extract_deal(self, deal_dir):
            return parse_deal_dir(deal_dir, assist=FakeAssist(summary=bad))

    chief, deal_id = run_through_chief(tmp_path, Offline(), broker_deal(tmp_path))
    assert chief.state(deal_id) == "NEEDS_INPUT"
    tool = next(e for e in chief.store.events(deal_id)
                if e.type == "tool.called" and e.payload["tool"] == "extract.documents")
    assert "arv" in tool.payload["output"]["refused_model_answers"]


def test_the_memo_of_a_model_read_deal_still_fits_one_page_and_lists_what_to_confirm(tmp_path):
    import re

    from bridge.core.builders.memo import render_memo
    deal = parse_deal_dir(broker_deal(tmp_path), assist=FakeAssist())
    result = underwrite(deal)
    assert len([r for r in result.reasons if r.code == "LOW_CONFIDENCE_FIELD"]) == 9
    path = render_memo(deal, result, tmp_path / "memo.pdf")
    data = path.read_bytes()
    assert len(re.findall(rb"/Type\s*/Page(?![s\w])", data)) == 1
    confirm = [q for q in result.open_questions if q.startswith("Confirm against")]
    assert len(confirm) == 1 and "loan_commitment" in confirm[0]      # one question, not nine
