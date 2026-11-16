"""Completeness against config/checklist.yaml. Code decides, never a model."""
from bridge.core.completeness import facts_from_deal, load_checklist, status
from bridge.core.parsers import parse_deal_dir

from tests.conftest import DEALS_DIR

ALL_DOCS = ["deal_summary", "purchase_contract", "rent_roll", "t12", "renovation_budget"]
ALL_FACTS = {
    "property_address": "1 Main St", "asset_type": "multifamily", "unit_count": 40,
    "loan_amount_requested": 6_500_000, "purchase_price": 8_000_000,
    "renovation_budget": 1_200_000, "sponsor_name": "Sample LLC",
}


def test_checklist_loads_required_documents():
    cl = load_checklist()
    assert cl.required_documents == ALL_DOCS
    assert "sponsor_name" in cl.required_facts


def test_nothing_received():
    s = status([], {})
    assert s.ready is False
    assert s.missing == ALL_DOCS
    assert s.received == []
    assert len(s.facts_missing) == 7


def test_partial_matches_contract_example():
    s = status(["rent_roll", "t12"], {k: v for k, v in ALL_FACTS.items() if k != "sponsor_name"})
    assert s.received == ["rent_roll", "t12"]
    assert s.missing == ["deal_summary", "purchase_contract", "renovation_budget"]
    assert s.facts_missing == ["sponsor_name"]
    assert s.ready is False


def test_ready_only_when_documents_and_facts_complete():
    assert status(ALL_DOCS, ALL_FACTS).ready is True
    assert status(ALL_DOCS[:-1], ALL_FACTS).ready is False
    assert status(ALL_DOCS, {**ALL_FACTS, "sponsor_name": ""}).ready is False


def test_duplicate_and_unknown_labels_are_harmless():
    s = status(["rent_roll", "rent_roll", "photos"], {})
    assert s.received == ["rent_roll"]


def test_extraction_provides_facts():
    facts = facts_from_deal(parse_deal_dir(DEALS_DIR / "bronx_mf"))
    assert set(facts) == set(ALL_FACTS)
    assert status(ALL_DOCS, facts).ready is True
