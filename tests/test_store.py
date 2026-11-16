"""Store: append-only event log, versioned records, projections."""
import sqlite3

import pytest
from bridge.core.parsers import parse_deal_dir
from bridge.core.schema import Patch
from bridge.store import projections
from bridge.store.db import Store

from tests.conftest import DEALS_DIR


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    s.create_deal("D-0001", "Test deal")
    return s


def test_events_are_ordered_and_carry_payload(store):
    store.append_event("D-0001", "chief", "deal.created", "created")
    e = store.append_event("D-0001", "chief", "state.changed", "to READY",
                           payload={"to": "READY"})
    got = store.events("D-0001")
    assert [x.type for x in got] == ["deal.created", "state.changed"]
    assert got[1].event_id == e.event_id > got[0].event_id
    assert got[1].payload == {"to": "READY"}


def test_events_after_id_supports_streaming(store):
    first = store.append_event("D-0001", "chief", "deal.created", "a")
    store.append_event("D-0001", "chief", "state.changed", "b", payload={"to": "READY"})
    assert [e.summary for e in store.events("D-0001", after_id=first.event_id)] == ["b"]


def test_event_log_rejects_update_and_delete(store, tmp_path):
    store.append_event("D-0001", "chief", "deal.created", "a")
    conn = sqlite3.connect(tmp_path / "t.db")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("UPDATE events SET summary='tampered'")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("DELETE FROM events")


def test_deal_versions_stay_readable(store):
    deal = parse_deal_dir(DEALS_DIR / "bronx_mf")
    store.save_deal(deal)
    v2 = deal.model_copy(deep=True)
    v2.version = 2
    v2.valuation.arv.value = 11_000_000
    store.save_deal(v2)
    assert store.versions(deal.deal_id) == [1, 2]
    assert store.get_deal(deal.deal_id, 1).valuation.arv.value == 12_500_000
    assert store.get_deal(deal.deal_id).valuation.arv.value == 11_000_000


def test_latest_result_and_check_per_version(store):
    store.save_result("D-0001", 1, 1, '{"call": "screen"}')
    store.save_result("D-0001", 1, 2, '{"call": "watch"}')
    store.set_check("D-0001", 1, 2, '{"status": "pass"}')
    latest = store.latest_result("D-0001")
    assert latest["attempt"] == 2 and latest["result"]["call"] == "watch"
    assert latest["check"]["status"] == "pass"


def test_files_and_facts(store):
    store.add_file("f-1", "D-0001", "rent_roll.csv", "rent_roll", "/x/rent_roll.csv", 10)
    store.record_fact("D-0001", "sponsor_name", "Sample LLC")
    assert store.files("D-0001")[0]["label"] == "rent_roll"
    assert store.facts("D-0001") == {"sponsor_name": "Sample LLC"}


def test_patches_roundtrip(store):
    p = Patch(patch_id="p-0001", deal_id="D-0001", kind="data", path="valuation.arv",
              old=12_500_000, new=11_000_000, reason="reviewer")
    store.add_patch(p)
    store.set_patch_status("p-0001", "confirmed")
    got = store.get_patch("p-0001")
    assert (got.old, got.new, got.status) == (12_500_000, 11_000_000, "confirmed")


def test_status_is_a_projection_of_events(store):
    assert projections.status(store, "D-0001").state == "CREATED"
    store.append_event("D-0001", "chief", "state.changed", "x", payload={"to": "UNDERWRITING"})
    store.append_event("D-0001", "underwriter", "underwriting.completed", "x",
                       payload={"call": "watch", "flags": 2})
    store.append_event("D-0001", "chief", "state.changed", "x", payload={"to": "CHECKING"})
    s = projections.status(store, "D-0001")
    assert (s.state, s.stage, s.call, s.flags) == ("CHECKING", "Checker", "watch", 2)


def test_queue_lists_deals_newest_activity_first(store):
    store.create_deal("D-0002", "Other")
    store.append_event("D-0002", "chief", "state.changed", "x", payload={"to": "NEEDS_REVIEW"})
    rows = projections.queue(store)
    assert [r.deal_id for r in rows][0] == "D-0002"
    assert rows[0].stage == "Review"


def test_next_deal_id(store):
    assert store.next_deal_id() == "D-0002"
