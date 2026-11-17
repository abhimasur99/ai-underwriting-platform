"""API routes: intake chat, queue, deal view, SSE, artifacts, chief chat, patches, decision."""
import json

import pytest
from bridge.agents.underwriter import FaultPlan
from bridge.api.app import create_app
from bridge.settings import Settings
from fastapi.testclient import TestClient

from tests.conftest import DEALS_DIR

SRC = DEALS_DIR / "bronx_mf"
DOCS = ["deal_summary.md", "purchase_contract.md", "rent_roll.csv", "t12.csv",
        "renovation_budget.csv"]
FACTS = ("Sponsor is Harborline Residential LLC. Address: 1200 Sample Avenue. 40 units, "
         "multifamily. Purchase price $8,000,000, reno budget $1.2 million, "
         "loan amount $6.5 million")


def make_client(tmp_path, faults=None):
    settings = Settings(None, "unused", tmp_path / "t.db", tmp_path)
    return TestClient(create_app(settings, faults=faults))


def upload(client, deal_id, name):
    return client.post(f"/api/deals/{deal_id}/files",
                       files={"file": (name, (SRC / name).read_bytes())})


def submitted_deal(client):
    deal_id = client.post("/api/deals").json()["deal_id"]
    for name in DOCS:
        upload(client, deal_id, name)
    out = client.post(f"/api/deals/{deal_id}/chat", json={"message": FACTS}).json()
    assert out["checklist"]["ready"] is True
    return deal_id


@pytest.fixture
def client(tmp_path):
    return make_client(tmp_path)


def test_health_reports_the_mode(client):
    assert client.get("/api/health").json() == {"status": "ok", "mode": "cached"}


def test_create_deal_and_walk_the_checklist_through_uploads(client):
    created = client.post("/api/deals").json()
    assert created["deal_id"] == "D-0001" and created["checklist"]["ready"] is False
    out = upload(client, created["deal_id"], "rent_roll.csv").json()
    assert out["checklist"]["received"] == ["rent_roll"]
    assert "please send your deal summary" in out["reply"]
    assert out["submitted"] is False


def test_full_flow_from_chat_to_review(client):
    deal_id = submitted_deal(client)            # background processing runs before the reply
    detail = client.get(f"/api/deals/{deal_id}").json()
    assert detail["status"]["state"] == "NEEDS_REVIEW"
    assert detail["result"]["call"] == "screen" and detail["check"]["status"] == "pass"
    assert detail["versions"] == [1] and len(detail["files"]) == 5
    rows = client.get("/api/deals").json()
    assert rows[0]["deal_id"] == deal_id and rows[0]["stage"] == "Review"
    assert rows[0]["call"] == "screen"


def test_external_chat_never_exposes_underwriting(client):
    deal_id = submitted_deal(client)
    reply = client.post(f"/api/deals/{deal_id}/chat",
                        json={"message": "Is it approved? what is the LTC?"}).json()["reply"]
    assert "team will follow up" in reply
    assert "70.65" not in reply and "screen" not in reply.lower()


def test_events_history_and_sse_once(client):
    deal_id = submitted_deal(client)
    events = client.get(f"/api/deals/{deal_id}/events").json()
    types = [e["type"] for e in events]
    assert types[0] == "deal.created" and "review.requested" in types
    assert "chat.sponsor" in types and types[-1] == "chat.assistant"   # the chat is in the log
    after = events[3]["event_id"]
    assert all(e["event_id"] > after for e in
               client.get(f"/api/deals/{deal_id}/events", params={"after": after}).json())
    text = client.get(f"/api/deals/{deal_id}/stream", params={"once": True}).text
    frames = [f for f in text.split("\n\n") if f.startswith("id:")]
    assert len(frames) == len(events)
    payload = json.loads(frames[0].split("data: ")[1])
    assert set(payload) == {"event_id", "deal_id", "ts", "type", "actor", "summary",
                            "deal_version"}
    resumed = client.get(f"/api/deals/{deal_id}/stream",
                         params={"once": True}, headers={"Last-Event-ID": str(after)}).text
    assert resumed.count("\nid:") + resumed.startswith("id:") == len(events) - 4


def test_queue_stream_covers_all_deals(client):
    a, b = submitted_deal(client), client.post("/api/deals").json()["deal_id"]
    text = client.get("/api/stream", params={"once": True}).text
    assert f'"deal_id": "{a}"' in text and f'"deal_id": "{b}"' in text


def test_artifacts_download(client):
    deal_id = submitted_deal(client)
    memo = client.get(f"/api/deals/{deal_id}/artifacts/memo.pdf")
    assert memo.status_code == 200 and memo.content.startswith(b"%PDF")
    wb = client.get(f"/api/deals/{deal_id}/artifacts/workbook.xlsx")
    assert wb.status_code == 200 and wb.content[:2] == b"PK"
    assert client.get(f"/api/deals/{deal_id}/artifacts/secret.txt").status_code == 404


def test_artifact_before_underwriting_is_404(client):
    deal_id = client.post("/api/deals").json()["deal_id"]
    assert client.get(f"/api/deals/{deal_id}/artifacts/memo.pdf").status_code == 404


def test_unknown_deal_is_404(client):
    assert client.get("/api/deals/D-9999").status_code == 404
    assert client.post("/api/deals/D-9999/chat", json={"message": "hi"}).status_code == 404


def test_chief_chat_question_and_patch_confirm_flow(client):
    deal_id = submitted_deal(client)
    q = client.post(f"/api/deals/{deal_id}/chief-chat",
                    json={"message": "what is the loan to cost?"}).json()
    assert "70.65%" in q["reply"] and q["patch"] is None
    edit = client.post(f"/api/deals/{deal_id}/chief-chat",
                       json={"message": "change the ARV to 9,000,000 because broker cut it"}).json()
    assert edit["intent"] == "data_edit" and edit["patch"]["status"] == "proposed"
    detail = client.get(f"/api/deals/{deal_id}").json()
    assert detail["versions"] == [1] and len(detail["pending_patches"]) == 1
    done = client.post(f"/api/deals/{deal_id}/patches/{edit['patch']['patch_id']}/confirm")
    assert done.json() == {"state": "NEEDS_REVIEW"}
    after = client.get(f"/api/deals/{deal_id}").json()
    assert after["versions"] == [1, 2] and after["result"]["call"] == "decline"
    assert after["pending_patches"] == []


def test_chief_chat_before_underwriting_is_refused(client):
    deal_id = client.post("/api/deals").json()["deal_id"]
    assert client.post(f"/api/deals/{deal_id}/chief-chat",
                       json={"message": "hi"}).status_code == 409


def test_cancel_patch(client):
    deal_id = submitted_deal(client)
    edit = client.post(f"/api/deals/{deal_id}/chief-chat",
                       json={"message": "change the ARV to 9,000,000 because x"}).json()
    pid = edit["patch"]["patch_id"]
    assert client.post(f"/api/deals/{deal_id}/patches/{pid}/cancel").status_code == 200
    assert client.post(f"/api/deals/{deal_id}/patches/{pid}/confirm").status_code == 422


def test_decision_approve_then_conflict(client):
    deal_id = submitted_deal(client)
    ok = client.post(f"/api/deals/{deal_id}/decision",
                     json={"decision": "approve", "rationale": "fine"})
    assert ok.json() == {"state": "RELEASED"}
    assert client.post(f"/api/deals/{deal_id}/decision",
                       json={"decision": "approve"}).status_code == 409
    assert client.post(f"/api/deals/{deal_id}/decision",
                       json={"decision": "maybe"}).status_code == 422


def test_send_back_reruns_to_review(client):
    deal_id = submitted_deal(client)
    out = client.post(f"/api/deals/{deal_id}/decision", json={"decision": "send_back"})
    assert out.json() == {"state": "NEEDS_REVIEW"}


def test_escalation_shows_in_the_queue(tmp_path):
    client = make_client(tmp_path, faults=FaultPlan("ltc", 0.01, frozenset({1, 2, 3})))
    deal_id = submitted_deal(client)
    row = client.get("/api/deals").json()[0]
    assert row["escalation"] is True and row["retry_count"] == 2 and row["flags"] >= 1
    assert client.get(f"/api/deals/{deal_id}").json()["check"]["status"] == "fail"


def test_openapi_lists_every_route_from_the_spec(client):
    paths = client.get("/openapi.json").json()["paths"]
    for p in ["/api/deals", "/api/deals/{deal_id}", "/api/deals/{deal_id}/chat",
              "/api/deals/{deal_id}/files", "/api/deals/{deal_id}/events",
              "/api/deals/{deal_id}/stream", "/api/stream",
              "/api/deals/{deal_id}/artifacts/{name}", "/api/deals/{deal_id}/chief-chat",
              "/api/deals/{deal_id}/patches/{patch_id}/confirm", "/api/deals/{deal_id}/decision"]:
        assert p in paths, p


def test_workbook_route_returns_cells_with_formulas_and_values(client):
    deal_id = submitted_deal(client)
    wb = client.get(f"/api/deals/{deal_id}/workbook").json()
    names = [s["name"] for s in wb["sheets"]]
    assert {"Summary", "Inputs", "Metrics", "Exit & Stress", "Exceptions"} <= set(names)
    metrics = next(s for s in wb["sheets"] if s["name"] == "Metrics")
    formulas = [c for c in metrics["cells"] if c["formula"]]
    assert formulas and all(c["value"] is not None and c["error"] is None for c in formulas)
    ltc = next(c for c in formulas if c["ref"] == "B3")
    assert ltc["value"] == pytest.approx(0.7065217391)


def test_workbook_route_before_underwriting_is_404(client):
    deal_id = client.post("/api/deals").json()["deal_id"]
    assert client.get(f"/api/deals/{deal_id}/workbook").status_code == 404


def test_intake_status_is_plain_words_only(client):
    deal_id = submitted_deal(client)
    out = client.get(f"/api/deals/{deal_id}/intake-status").json()
    assert out["message"] == "Under review." or "review" in out["message"].lower()
    text = json.dumps(out)
    for word in ("ltc", "dscr", "screen", "watch", "decline"):
        assert word not in text.lower().replace("checklist", "")


def test_pacing_and_forced_mismatch_come_from_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("BRIDGE_STEP_DELAY", "0.25")
    monkeypatch.setenv("BRIDGE_FORCE_MISMATCH", "persist")
    from bridge.settings import get_settings
    s = get_settings()
    assert s.step_delay == 0.25 and s.force_mismatch == "persist"


def test_memo_opens_inline_and_workbook_downloads(client):
    deal_id = submitted_deal(client)
    memo = client.get(f"/api/deals/{deal_id}/artifacts/memo.pdf")
    assert memo.headers["content-disposition"].startswith("inline")
    book = client.get(f"/api/deals/{deal_id}/artifacts/workbook.xlsx")
    assert book.headers["content-disposition"].startswith("attachment")


def test_live_mode_needs_a_key_and_unknown_modes_are_rejected(tmp_path):
    no_key = Settings(None, "m", tmp_path / "a.db", tmp_path, mode="live")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        create_app(no_key)
    with pytest.raises(RuntimeError, match="cached"):
        create_app(Settings(None, "m", tmp_path / "b.db", tmp_path, mode="turbo"))


def test_live_mode_health_reports_live(tmp_path):
    settings = Settings("test-key-not-real", "m", tmp_path / "c.db", tmp_path, mode="live")
    health = TestClient(create_app(settings)).get("/api/health").json()
    assert health == {"status": "ok", "mode": "live"}


def test_archive_restore_and_queue_filter(client):
    deal_id = submitted_deal(client)
    kept = client.post("/api/deals").json()["deal_id"]
    out = client.delete(f"/api/deals/{deal_id}")
    assert out.status_code == 200 and out.json()["archived"] is True
    assert [r["deal_id"] for r in client.get("/api/deals").json()] == [kept]
    everything = client.get("/api/deals?include_archived=true").json()
    assert {r["deal_id"] for r in everything} == {deal_id, kept}
    assert next(r for r in everything if r["deal_id"] == deal_id)["archived"] is True
    assert client.get(f"/api/deals/{deal_id}").status_code == 200          # still readable
    assert client.post(f"/api/deals/{deal_id}/restore").json()["archived"] is False
    assert {r["deal_id"] for r in client.get("/api/deals").json()} == {deal_id, kept}
    types = [e["type"] for e in client.get(f"/api/deals/{deal_id}/events").json()]
    assert "deal.archived" in types and "deal.restored" in types


def test_archive_is_refused_while_a_deal_is_processing(client):
    deal_id = client.post("/api/deals").json()["deal_id"]
    client.app.state.store.append_event(deal_id, "chief", "state.changed", "x",
                                        payload={"to": "UNDERWRITING"})
    assert client.delete(f"/api/deals/{deal_id}").status_code == 409


def test_archive_unknown_deal_is_404(client):
    assert client.delete("/api/deals/D-9999").status_code == 404
    assert client.post("/api/deals/D-9999/restore").status_code == 404


def test_rename_a_deal(client):
    deal_id = client.post("/api/deals").json()["deal_id"]
    out = client.patch(f"/api/deals/{deal_id}", json={"name": "  Harbor Street bridge  "})
    assert out.status_code == 200 and out.json()["name"] == "Harbor Street bridge"
    assert client.get("/api/deals").json()[0]["name"] == "Harbor Street bridge"
    assert client.patch(f"/api/deals/{deal_id}", json={"name": "   "}).status_code == 422
    assert client.patch("/api/deals/D-9999", json={"name": "x"}).status_code == 404


def test_request_info_round_trip_over_the_api(client):
    deal_id = submitted_deal(client)
    assert client.post(f"/api/deals/{deal_id}/decision",
                       json={"decision": "request_info", "rationale": " "}).status_code == 409
    out = client.post(f"/api/deals/{deal_id}/decision", json={
        "decision": "request_info", "rationale": "Please send the 2025 tax bill."})
    assert out.json() == {"state": "NEEDS_INPUT"}
    row = client.get("/api/deals").json()[0]
    assert row["next_action"].startswith("Waiting on sponsor: Please send") and not row["needs_you"]
    status = client.get(f"/api/deals/{deal_id}/intake-status").json()
    assert "Please send the 2025 tax bill." in status["message"]
    reply = client.post(f"/api/deals/{deal_id}/chat", json={"message": "Attached next week."})
    assert "passed that to the team" in reply.json()["reply"]
    row = client.get("/api/deals").json()[0]
    assert row["next_action"] == "Your review" and row["needs_you"] is True
    events = [e["type"] for e in client.get(f"/api/deals/{deal_id}/events").json()]
    assert "info.requested" in events and "info.replied" in events


def test_the_queue_puts_what_needs_the_reviewer_first(client):
    waiting = client.post("/api/deals").json()["deal_id"]
    ready = submitted_deal(client)
    assert [r["deal_id"] for r in client.get("/api/deals").json()] == [ready, waiting]


def test_a_documents_text_matches_the_line_a_source_points_to(client):
    deal_id = submitted_deal(client)
    detail = client.get(f"/api/deals/{deal_id}").json()
    loan = detail["deal"]["loan_request"]["loan_commitment"]["source"]
    summary = next(f for f in detail["files"] if f["label"] == "deal_summary")
    out = client.get(f"/api/deals/{deal_id}/files/{summary['file_id']}/text").json()
    line = int(loan["locator"].removeprefix("line "))
    assert out["kind"] == "text" and out["filename"] == "deal_summary.md"
    assert loan["quote"] in out["lines"][line - 1]          # the Files tab can highlight it


def test_a_table_is_shown_as_numbered_rows_with_the_header_first(client):
    deal_id = submitted_deal(client)
    files = client.get(f"/api/deals/{deal_id}").json()["files"]
    rent_roll = next(f for f in files if f["label"] == "rent_roll")
    out = client.get(f"/api/deals/{deal_id}/files/{rent_roll['file_id']}/text").json()
    assert out["kind"] == "table"
    assert out["lines"][0].startswith("unit | unit_type | sqft") and "101" in out["lines"][1]


def test_an_unknown_file_is_404_and_a_replaced_file_is_listed_once(client):
    deal_id = submitted_deal(client)
    assert client.get(f"/api/deals/{deal_id}/files/f-nope/text").status_code == 404
    again = (SRC / "t12.csv").read_bytes() + b"\n"                # a corrected copy, new size
    client.post(f"/api/deals/{deal_id}/files", files={"file": ("t12.csv", again)})
    labels = [f["label"] for f in client.get(f"/api/deals/{deal_id}").json()["files"]]
    assert labels.count("t12") == 1 and len(labels) == 5


def test_the_sponsor_page_gets_the_details_read_and_the_files_received(client):
    deal_id = client.post("/api/deals").json()["deal_id"]
    upload(client, deal_id, "deal_summary.md")
    status = client.get(f"/api/deals/{deal_id}/intake-status").json()
    facts = {f["key"]: f for f in status["facts"]}
    assert facts["unit_count"]["value"] == "40"
    assert facts["property_address"]["label"] == "Property address"
    assert facts["unit_count"]["source"].startswith("deal_summary.md, line ")
    assert status["files"] == {"deal_summary": "deal_summary.md"}


def test_the_transcript_is_the_conversation_only_and_survives_a_reload(client):
    deal_id = submitted_deal(client)
    client.post(f"/api/deals/{deal_id}/chat", json={"message": "thanks"})
    transcript = client.get(f"/api/deals/{deal_id}/transcript").json()
    roles = [m["from"] for m in transcript]
    assert "you" in roles and "agent" in roles and "file" in roles
    assert transcript[0]["from"] == "file" and transcript[0]["text"] == "deal_summary.md"
    everything = " ".join(m["text"] for m in transcript)
    for internal in ("70.65", "NEEDS_REVIEW", "tool"):
        assert internal not in everything
    assert client.get("/api/deals/D-9999/transcript").status_code == 404


def test_changes_route_reports_what_an_edit_moved(client):
    deal_id = submitted_deal(client)
    first = client.get(f"/api/deals/{deal_id}/changes").json()
    assert first["from_version"] == first["to_version"] == 1 and first["metrics"] == []
    reply = client.post(f"/api/deals/{deal_id}/chief-chat",
                        json={"message": "change the ARV to 11,000,000 because it came in lower"})
    patch = reply.json()["patch"]
    client.post(f"/api/deals/{deal_id}/patches/{patch['patch_id']}/confirm")
    diff = client.get(f"/api/deals/{deal_id}/changes").json()
    assert (diff["from_version"], diff["to_version"]) == (1, 2)
    assert diff["inputs"][0]["path"] == "valuation.arv"
    assert "loan_to_arv" in [m["key"] for m in diff["metrics"]]
    assert client.get("/api/deals/D-9999/changes").status_code == 404


def test_the_reviewers_conversation_is_kept_apart_from_the_sponsors(client):
    deal_id = submitted_deal(client)
    client.post(f"/api/deals/{deal_id}/chief-chat", json={"message": "hello"})
    mine = client.get(f"/api/deals/{deal_id}/chief-transcript").json()
    assert [m["from"] for m in mine] == ["you", "agent"] and mine[0]["text"] == "hello"
    sponsors = " ".join(m["text"] for m in client.get(f"/api/deals/{deal_id}/transcript").json())
    assert "How can I help with this deal" not in sponsors


def test_what_if_route_answers_and_changes_nothing(client):
    deal_id = submitted_deal(client)
    events_before = client.get(f"/api/deals/{deal_id}/events").json()
    out = client.post(f"/api/deals/{deal_id}/what-if",
                      json={"params": {"takeout_rate": 0.065}})
    assert out.status_code == 200
    body = out.json()
    assert body["call_before"] == body["call_after"] == "screen"
    assert body["assumptions"][0]["key"] == "takeout_rate"
    assert body["diff"]["metrics"] and body["diff"]["from_version"] == body["diff"]["to_version"]
    assert client.get(f"/api/deals/{deal_id}/events").json() == events_before   # nothing logged
    assert client.get(f"/api/deals/{deal_id}").json()["versions"] == [1]


def test_what_if_route_refuses_unreasonable_or_empty_assumptions(client):
    deal_id = submitted_deal(client)
    assert client.post(f"/api/deals/{deal_id}/what-if", json={"params": {}}).status_code == 422
    bad = client.post(f"/api/deals/{deal_id}/what-if", json={"params": {"takeout_rate": 0.9}})
    assert bad.status_code == 422 and "take-out rate" in bad.json()["detail"]
    missing = client.post("/api/deals/D-9999/what-if", json={"params": {"arv": 1e7}})
    assert missing.status_code == 404
    fresh = client.post("/api/deals").json()["deal_id"]
    assert client.post(f"/api/deals/{fresh}/what-if",
                       json={"params": {"arv": 1e7}}).status_code == 409


def test_max_loan_route_gives_the_exact_limit(client):
    deal_id = submitted_deal(client)
    body = client.get(f"/api/deals/{deal_id}/max-loan").json()
    assert body["target"] == "screen" and body["current_call"] == "screen"
    assert body["max_loan"] > body["current_loan"]
    looser = client.get(f"/api/deals/{deal_id}/max-loan", params={"target": "watch"})
    assert looser.status_code == 200
    assert client.get(f"/api/deals/{deal_id}/max-loan", params={"target": "x"}).status_code == 422
    assert client.get("/api/deals/D-9999/max-loan").status_code == 404
