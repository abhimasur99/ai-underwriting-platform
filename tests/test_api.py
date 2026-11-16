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
    assert "Next I need your deal summary" in out["reply"]
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
    assert events[0]["type"] == "deal.created" and events[-1]["type"] == "review.requested"
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
