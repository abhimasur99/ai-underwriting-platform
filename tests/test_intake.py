"""Intake chat: classification, limits, facts, guardrails, checklist progress."""
import re

import pytest
from bridge.agents.chief import Chief
from bridge.agents.intake import IncomingFile, IntakeAgent
from bridge.agents.runner import CachedRunner
from bridge.core.parsers.classify import classify
from bridge.store.db import Store

from tests.conftest import DEALS_DIR

SRC = DEALS_DIR / "bronx_mf"


def f(name, content=None):
    return IncomingFile(name, content if content is not None else (SRC / name).read_bytes())


@pytest.fixture
def agent(tmp_path):
    chief = Chief(Store(tmp_path / "t.db"), CachedRunner(), tmp_path / "out", tmp_path / "up")
    return IntakeAgent(chief, CachedRunner()), chief.create_deal()


# ---- classification (filename hints, then header hints)
@pytest.mark.parametrize("name,label", [
    ("rent_roll.csv", "rent_roll"), ("t12.csv", "t12"),
    ("renovation_budget.csv", "renovation_budget"),
    ("purchase_contract.md", "purchase_contract"), ("deal_summary.md", "deal_summary")])
def test_classifies_the_sample_documents(name, label):
    c = classify(name, (SRC / name).read_bytes())
    assert (c.label, c.status) == (label, "ok")


def test_header_hints_classify_a_generic_filename():
    c = classify("export_final.csv", (SRC / "rent_roll.csv").read_bytes())
    assert (c.label, c.status) == ("rent_roll", "ok")
    c = classify("scan1.csv", (SRC / "t12.csv").read_bytes())
    assert c.label == "t12"


def test_conflicting_filename_and_columns_ask_for_confirmation():
    c = classify("rent_roll.csv", (SRC / "t12.csv").read_bytes())
    assert c.status == "ambiguous" and set(c.candidates) == {"rent_roll", "t12"}


def test_unknown_files_are_not_guessed():
    c = classify("notes.txt", b"hello")
    assert (c.label, c.status) == (None, "unknown")


# ---- upload rules
def test_disallowed_type_and_oversize_are_rejected(agent):
    a, deal_id = agent
    out = a.handle(deal_id, files=[f("virus.exe", b"x")])
    assert "can't accept" in out["reply"] and out["checklist"]["received"] == []
    big = IncomingFile("rent_roll.csv", b"x" * (26 * 1024 * 1024))
    assert "larger than" in a.handle(deal_id, files=[big])["reply"]


def test_duplicate_upload_is_noticed(agent):
    a, deal_id = agent
    a.handle(deal_id, files=[f("rent_roll.csv")])
    assert "already have" in a.handle(deal_id, files=[f("rent_roll.csv")])["reply"]


def test_a_confusing_file_is_not_registered_until_confirmed(agent):
    a, deal_id = agent
    out = a.handle(deal_id, files=[IncomingFile("rent_roll.csv", (SRC / "t12.csv").read_bytes())])
    assert "not sure" in out["reply"] and out["checklist"]["received"] == []
    confirmed = IncomingFile("rent_roll.csv", (SRC / "t12.csv").read_bytes(), label="t12")
    assert a.handle(deal_id, files=[confirmed])["checklist"]["received"] == ["t12"]


def test_file_type_must_suit_the_document(agent):
    a, deal_id = agent
    out = a.handle(deal_id, files=[IncomingFile("rent_roll.md", b"x", label="rent_roll")])
    assert "I can accept" in out["reply"]


# ---- chat flow
def test_chat_walks_the_checklist_one_ask_at_a_time(agent):
    a, deal_id = agent
    out = a.handle(deal_id, files=[f("rent_roll.csv"), f("deal_summary.md")])
    assert out["checklist"]["received"] == ["deal_summary", "rent_roll"]
    assert "Next I need your purchase contract" in out["reply"]
    for name in ("purchase_contract.md", "t12.csv", "renovation_budget.csv"):
        out = a.handle(deal_id, files=[f(name)])
    assert out["checklist"]["missing"] == [] and not out["checklist"]["ready"]
    assert "sponsor's name" in out["reply"] or "address" in out["reply"]


def test_facts_are_recorded_from_free_text_and_complete_the_deal(agent):
    a, deal_id = agent
    for name in ("deal_summary.md", "purchase_contract.md", "rent_roll.csv", "t12.csv",
                 "renovation_budget.csv"):
        a.handle(deal_id, files=[f(name)])
    out = a.handle(deal_id, "Sponsor is Harborline Residential LLC. Address: 1200 Sample Avenue. "
                            "40 units, multifamily. Purchase price $8,000,000, reno budget "
                            "$1.2 million, loan amount $6.5 million")
    assert out["checklist"]["ready"] is True and out["submitted"] is True
    assert "team will review" in out["reply"]
    assert a.chief.state(deal_id) == "READY"
    assert a.chief.store.facts(deal_id)["sponsor_name"] == "Harborline Residential LLC"
    assert a.chief.store.facts(deal_id)["renovation_budget"] == "1200000"


def test_submit_deal_is_refused_until_ready(agent):
    a, deal_id = agent
    with pytest.raises(RuntimeError):
        a.submit_deal(deal_id)


def test_only_allowlisted_facts_are_recorded(agent):
    a, deal_id = agent

    class Sneaky(CachedRunner):
        def interpret_intake(self, message):
            turn = super().interpret_intake(message)
            turn.facts["admin_password"] = "x"
            return turn

    a.runner = Sneaky()
    a.handle(deal_id, "Sponsor is Sample LLC")
    assert set(a.chief.store.facts(deal_id)) == {"sponsor_name"}


# ---- guardrails
@pytest.mark.parametrize("message", [
    "What rate will you offer?", "What are my approval odds?", "Will you fund this?",
    "What's the LTV?", "Can I get a term sheet"])
def test_asking_for_a_decision_gets_the_team_will_follow_up(agent, message):
    a, deal_id = agent
    out = a.handle(deal_id, message)
    assert "team will follow up" in out["reply"]


def test_external_replies_never_carry_underwriting_numbers(tmp_path):
    chief = Chief(Store(tmp_path / "t.db"), CachedRunner(), tmp_path / "out", tmp_path / "up")
    a, deal_id = IntakeAgent(chief, CachedRunner()), chief.create_deal()
    chief.ingest_directory(deal_id, SRC)
    chief.process(deal_id)
    asked = a.handle(deal_id, "Is it approved? What is the LTC?")["reply"]
    replies = [a.status_message(deal_id), asked]
    for reply in replies:
        assert not re.search(r"\d+\.\d+%|\$\d|\bdecline\b|\bscreen\b|\bwatch\b", reply, re.I), reply


@pytest.mark.parametrize("state_hint,expected", [("AWAITING_DOCS", "Next I need")])
def test_status_message_for_an_incomplete_deal(agent, state_hint, expected):
    a, deal_id = agent
    a.handle(deal_id, files=[f("rent_roll.csv")])
    assert expected in a.status_message(deal_id)


def test_status_message_while_in_review_is_just_under_review(tmp_path):
    chief = Chief(Store(tmp_path / "t.db"), CachedRunner(), tmp_path / "out", tmp_path / "up")
    deal_id = chief.create_deal()
    chief.ingest_directory(deal_id, SRC)
    chief.process(deal_id)
    assert IntakeAgent(chief, CachedRunner()).status_message(deal_id) == "Under review."


# ---- PDF, Word and Excel uploads
def _doc(tmp_path, source, fmt, name):
    from scripts.sample_docs import markdown_to_docx, markdown_to_pdf
    path = tmp_path / name
    md = (SRC / source).read_text()
    (markdown_to_pdf if fmt == "pdf" else markdown_to_docx)(md, path)
    return path.read_bytes()


def test_content_hints_classify_pdf_and_word_with_generic_names(tmp_path):
    c = classify("scan_0042.pdf", _doc(tmp_path, "deal_summary.md", "pdf", "a.pdf"))
    assert (c.label, c.status) == ("deal_summary", "ok")
    c = classify("attachment.docx", _doc(tmp_path, "purchase_contract.md", "docx", "b.docx"))
    assert (c.label, c.status) == ("purchase_contract", "ok")


def test_an_unreadable_document_is_not_guessed(tmp_path):
    c = classify("attachment.pdf", b"not a pdf")
    assert c.status == "unknown"


def test_tables_are_accepted_as_csv_or_xlsx_only(agent):
    a, deal_id = agent
    out = a.handle(deal_id, files=[IncomingFile("rent_roll.pdf", b"%PDF-1.4")])
    assert "csv, xlsx" in out["reply"] and out["checklist"]["received"] == []


def test_uploading_a_replacement_in_another_format_leaves_one_file(agent, tmp_path):
    a, deal_id = agent
    a.handle(deal_id, files=[f("deal_summary.md")])
    pdf = _doc(tmp_path, "deal_summary.md", "pdf", "x.pdf")
    out = a.handle(deal_id, files=[IncomingFile("deal_summary.pdf", pdf)])
    assert "Updated your deal summary" in out["reply"]
    names = sorted(p.name for p in a.chief.deal_dir(deal_id).glob("deal_summary.*"))
    assert names == ["deal_summary.pdf"]
