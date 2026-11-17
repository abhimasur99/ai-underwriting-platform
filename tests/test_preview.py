"""Reading the deal's basic details from documents as they arrive."""
import shutil

import pytest
from bridge.core.parsers.preview import read_facts

from scripts.sample_docs import markdown_to_docx, markdown_to_pdf
from tests.conftest import DEAL_NAMES, DEALS_DIR


@pytest.mark.parametrize("name", DEAL_NAMES)
def test_every_sample_deal_yields_all_seven_details_that_match_the_answer_key(name):
    import json
    facts = {f.key: f for f in read_facts(DEALS_DIR / name)}
    key = json.loads((DEALS_DIR / name / "expected.json").read_text())["answer_key"]
    assert set(facts) == {"property_address", "asset_type", "unit_count", "loan_amount_requested",
                          "purchase_price", "renovation_budget", "sponsor_name"}
    assert float(facts["loan_amount_requested"].value) == key["loan_commitment"]
    assert float(facts["purchase_price"].value) == key["purchase_price"]
    assert float(facts["renovation_budget"].value) == key["renovation_budget"]
    assert int(facts["unit_count"].value) == key["unit_count"]
    assert facts["asset_type"].value == key["asset_type"]


def test_each_detail_cites_its_document_and_line(tmp_path):
    facts = {f.key: f for f in read_facts(DEALS_DIR / "bronx_mf")}
    price = facts["purchase_price"]
    assert price.doc == "purchase_contract.md" and price.locator.startswith("line ")
    line = int(price.locator.removeprefix("line "))
    text = (DEALS_DIR / "bronx_mf" / "purchase_contract.md").read_text().splitlines()
    assert price.quote in text[line - 1]


@pytest.mark.parametrize("fmt", ["pdf", "docx"])
def test_pdf_and_word_documents_are_read_too(tmp_path, fmt):
    src = DEALS_DIR / "bronx_mf"
    for stem in ("deal_summary", "purchase_contract"):
        writer = markdown_to_pdf if fmt == "pdf" else markdown_to_docx
        writer((src / f"{stem}.md").read_text(), tmp_path / f"{stem}.{fmt}")
    facts = {f.key: f.value for f in read_facts(tmp_path)}
    assert facts["unit_count"] == "40" and facts["loan_amount_requested"] == "6500000"
    assert facts["sponsor_name"].startswith("Harborline")


def test_a_missing_or_unreadable_document_gives_fewer_details_not_an_error(tmp_path):
    shutil.copy(DEALS_DIR / "bronx_mf" / "deal_summary.md", tmp_path / "deal_summary.md")
    facts = {f.key for f in read_facts(tmp_path)}
    assert "purchase_price" not in facts and "property_address" in facts
    (tmp_path / "purchase_contract.pdf").write_bytes(b"not a pdf")
    assert "purchase_price" not in {f.key for f in read_facts(tmp_path)}
    assert read_facts(tmp_path / "nothing-here") == []


def test_unfamiliar_wording_is_not_guessed(tmp_path):
    text = "# Offering\n- Maple Court Apartments\n- 24 apartments\n"
    (tmp_path / "deal_summary.md").write_text(text)
    assert read_facts(tmp_path) == []
