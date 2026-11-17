"""Every sample deal, through the real upload path in its own file formats (PDF, Word, Excel,
CSV, markdown): intake, extraction, underwriting, the independent check, and the expected call."""
import json

import pytest
from bridge.api.app import create_app
from bridge.core import completeness
from bridge.core.parsers import parse_deal_dir
from bridge.settings import Settings
from fastapi.testclient import TestClient

from tests.conftest import DEAL_NAMES, DEALS_DIR, NEEDS_INPUT_DEAL

DOC_STEMS = ["deal_summary", "purchase_contract", "rent_roll", "t12", "renovation_budget"]


def make_client(tmp_path):
    return TestClient(create_app(Settings(None, "unused", tmp_path / "t.db", tmp_path)))


def document(folder, stem):
    return next(p for p in sorted(folder.glob(f"{stem}.*")))


def facts_message(facts: dict) -> str:
    """What a sponsor would type, built from the facts the documents contain."""
    kind = "mixed use" if facts["asset_type"] == "mixed_use" else "multifamily"
    return (f"Sponsor is {facts['sponsor_name']}. Address: {facts['property_address']}. "
            f"{facts['unit_count']} units, {kind}. Purchase price ${facts['purchase_price']:,.0f}, "
            f"reno budget ${facts['renovation_budget']:,.0f}, "
            f"loan amount ${facts['loan_amount_requested']:,.0f}")


def submit(client, folder, facts, stems=DOC_STEMS):
    deal_id = client.post("/api/deals").json()["deal_id"]
    for stem in stems:
        path = document(folder, stem)
        out = client.post(f"/api/deals/{deal_id}/files",
                          files={"file": (path.name, path.read_bytes())})
        assert out.status_code == 200, (path.name, out.text)
        assert stem in out.json()["checklist"]["received"], (path.name, out.json()["reply"])
    client.post(f"/api/deals/{deal_id}/chat", json={"message": facts_message(facts)})
    return deal_id


@pytest.mark.parametrize("name", DEAL_NAMES)
def test_each_deal_uploads_and_runs_to_its_expected_call(tmp_path, name):
    folder = DEALS_DIR / name
    expected = json.loads((folder / "expected.json").read_text())
    facts = completeness.facts_from_deal(parse_deal_dir(folder))
    client = make_client(tmp_path)
    deal_id = submit(client, folder, facts)
    detail = client.get(f"/api/deals/{deal_id}").json()
    assert detail["status"]["state"] == "NEEDS_REVIEW", detail["status"]
    assert detail["result"]["call"] == expected["expected_call"]
    assert [r["code"] for r in detail["result"]["reasons"]] == expected["expected_reason_codes"]
    assert detail["check"]["status"] in ("pass", "warn"), detail["check"]["summary"]
    assert detail["status"]["escalation"] is False


@pytest.mark.parametrize("name", [n for n in DEAL_NAMES if n not in
                                  ("bronx_mf", "queens_mixed_use", "overleveraged_bk")])
def test_the_new_deals_come_in_realistic_formats(name):
    suffixes = {document(DEALS_DIR / name, stem).suffix for stem in DOC_STEMS}
    assert suffixes & {".pdf", ".xlsx"} and ".md" not in suffixes


def test_a_missing_arv_stops_and_asks_then_runs_after_the_corrected_file(tmp_path):
    folder = DEALS_DIR / NEEDS_INPUT_DEAL
    expected = json.loads((folder / "expected.json").read_text())
    assert expected["initial_state"] == "needs_input"
    facts = {"sponsor_name": "Cypress Hills Capital LLC",
             "property_address": "60-14 Sample Avenue, Queens, NY 11385", "unit_count": 16,
             "asset_type": "multifamily", "purchase_price": 3_300_000,
             "renovation_budget": 500_000, "loan_amount_requested": 2_600_000}
    client = make_client(tmp_path)
    deal_id = submit(client, folder, facts)
    status = client.get(f"/api/deals/{deal_id}").json()["status"]
    assert status["state"] == "NEEDS_INPUT"
    events = client.get(f"/api/deals/{deal_id}/events").json()
    tool = next(e for e in events if e["type"] == "tool.called"
                and e["payload"]["tool"] == "extract.documents")
    assert tool["payload"]["output"] == {"missing": ["arv"]}      # asks; never guesses a value
    assert client.get(f"/api/deals/{deal_id}").json()["result"] is None

    corrected = folder / expected["followup_file"]
    out = client.post(f"/api/deals/{deal_id}/files",
                      files={"file": ("deal_summary.pdf", corrected.read_bytes())})
    assert out.json()["submitted"] is True
    detail = client.get(f"/api/deals/{deal_id}").json()
    assert detail["status"]["state"] == "NEEDS_REVIEW"
    assert detail["result"]["call"] == expected["expected_call"] == "screen"
    assert detail["check"]["status"] in ("pass", "warn")


def test_the_catalog_lists_every_sample_deal():
    text = (DEALS_DIR.parents[1] / "docs" / "deals-catalog.md").read_text()
    for name in (*DEAL_NAMES, NEEDS_INPUT_DEAL):
        expected = json.loads((DEALS_DIR / name / "expected.json").read_text())
        assert expected["deal_id"] in text
