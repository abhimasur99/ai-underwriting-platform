"""SQLite store: versioned deal record, append-only event log, files, facts, patches.

The event log is append-only (triggers reject UPDATE and DELETE). A deal's state and the queue are
projections over the events, never separate mutable columns.
"""
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from bridge.core.schema import Deal, Event, Patch

SCHEMA = """
CREATE TABLE IF NOT EXISTS deals(
    deal_id TEXT PRIMARY KEY, name TEXT, created_at TEXT, owner TEXT);
CREATE TABLE IF NOT EXISTS events(
    event_id INTEGER PRIMARY KEY AUTOINCREMENT, deal_id TEXT NOT NULL, ts TEXT NOT NULL,
    actor TEXT NOT NULL, type TEXT NOT NULL, summary TEXT NOT NULL,
    deal_version INTEGER NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_events_deal ON events(deal_id, event_id);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
    BEGIN SELECT RAISE(ABORT, 'event log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
    BEGIN SELECT RAISE(ABORT, 'event log is append-only'); END;
CREATE TABLE IF NOT EXISTS deal_versions(
    deal_id TEXT, version INTEGER, deal_json TEXT, created_at TEXT,
    PRIMARY KEY(deal_id, version));
CREATE TABLE IF NOT EXISTS results(
    deal_id TEXT, version INTEGER, attempt INTEGER, result_json TEXT, check_json TEXT,
    PRIMARY KEY(deal_id, version, attempt));
CREATE TABLE IF NOT EXISTS files(
    file_id TEXT PRIMARY KEY, deal_id TEXT, filename TEXT, label TEXT, path TEXT, size INTEGER,
    uploaded_at TEXT);
CREATE TABLE IF NOT EXISTS facts(
    deal_id TEXT, key TEXT, value TEXT, PRIMARY KEY(deal_id, key));
CREATE TABLE IF NOT EXISTS patches(
    patch_id TEXT PRIMARY KEY, deal_id TEXT, kind TEXT, path TEXT, old_json TEXT, new_json TEXT,
    reason TEXT, status TEXT, created_at TEXT);
"""


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._memory = sqlite3.connect(":memory:", check_same_thread=False) \
            if self.path == ":memory:" else None
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        with self._lock:
            conn = self._memory or sqlite3.connect(self.path, timeout=10)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                if self._memory is None:
                    conn.close()

    # ---- deals
    def create_deal(self, deal_id: str, name: str = "", owner: str = "unassigned") -> None:
        with self._conn() as c:
            c.execute("INSERT INTO deals VALUES (?,?,?,?)", (deal_id, name, now(), owner))

    def next_deal_id(self) -> str:
        with self._conn() as c:
            n = c.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
        return f"D-{n + 1:04d}"

    def deal_exists(self, deal_id: str) -> bool:
        with self._conn() as c:
            row = c.execute("SELECT 1 FROM deals WHERE deal_id=?", (deal_id,)).fetchone()
        return row is not None

    def deal_ids(self) -> list[str]:
        with self._conn() as c:
            return [r[0] for r in c.execute("SELECT deal_id FROM deals ORDER BY created_at")]

    def deal_meta(self, deal_id: str) -> dict:
        with self._conn() as c:
            row = c.execute("SELECT * FROM deals WHERE deal_id=?", (deal_id,)).fetchone()
        return dict(row) if row else {}

    def set_name(self, deal_id: str, name: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE deals SET name=? WHERE deal_id=?", (name, deal_id))

    # ---- event log (append-only)
    def append_event(self, deal_id: str, actor: str, type_: str, summary: str,
                     deal_version: int = 1, payload: dict | None = None) -> Event:
        ts, body = now(), json.dumps(payload or {}, default=str)
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO events(deal_id, ts, actor, type, summary, deal_version, payload) "
                "VALUES (?,?,?,?,?,?,?)", (deal_id, ts, actor, type_, summary, deal_version, body))
            event_id = cur.lastrowid
        return Event(event_id=event_id, deal_id=deal_id, ts=ts, actor=actor, type=type_,
                     summary=summary, deal_version=deal_version, payload=payload or {})

    def events(self, deal_id: str | None = None, after_id: int = 0) -> list[Event]:
        sql, args = "SELECT * FROM events WHERE event_id > ?", [after_id]
        if deal_id:
            sql += " AND deal_id = ?"
            args.append(deal_id)
        with self._conn() as c:
            rows = c.execute(sql + " ORDER BY event_id", args).fetchall()
        return [Event(event_id=r["event_id"], deal_id=r["deal_id"], ts=r["ts"], actor=r["actor"],
                      type=r["type"], summary=r["summary"], deal_version=r["deal_version"],
                      payload=json.loads(r["payload"])) for r in rows]

    # ---- versioned deal record
    def save_deal(self, deal: Deal) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO deal_versions VALUES (?,?,?,?)",
                      (deal.deal_id, deal.version, deal.model_dump_json(), now()))

    def get_deal(self, deal_id: str, version: int | None = None) -> Deal | None:
        with self._conn() as c:
            if version is None:
                row = c.execute("SELECT deal_json FROM deal_versions WHERE deal_id=? "
                                "ORDER BY version DESC LIMIT 1", (deal_id,)).fetchone()
            else:
                row = c.execute("SELECT deal_json FROM deal_versions WHERE deal_id=? AND "
                                "version=?", (deal_id, version)).fetchone()
        return Deal.model_validate_json(row[0]) if row else None

    def versions(self, deal_id: str) -> list[int]:
        with self._conn() as c:
            return [r[0] for r in c.execute(
                "SELECT version FROM deal_versions WHERE deal_id=? ORDER BY version", (deal_id,))]

    # ---- results and check reports (latest attempt per version)
    def save_result(self, deal_id: str, version: int, attempt: int, result_json: str,
                    check_json: str | None = None) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO results VALUES (?,?,?,?,?)",
                      (deal_id, version, attempt, result_json, check_json))

    def set_check(self, deal_id: str, version: int, attempt: int, check_json: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE results SET check_json=? WHERE deal_id=? AND version=? AND "
                      "attempt=?", (check_json, deal_id, version, attempt))

    def latest_result(self, deal_id: str, version: int | None = None) -> dict | None:
        with self._conn() as c:
            if version is None:
                row = c.execute("SELECT * FROM results WHERE deal_id=? ORDER BY version DESC, "
                                "attempt DESC LIMIT 1", (deal_id,)).fetchone()
            else:
                row = c.execute("SELECT * FROM results WHERE deal_id=? AND version=? "
                                "ORDER BY attempt DESC LIMIT 1", (deal_id, version)).fetchone()
        if not row:
            return None
        return {"version": row["version"], "attempt": row["attempt"],
                "result": json.loads(row["result_json"]),
                "check": json.loads(row["check_json"]) if row["check_json"] else None}

    # ---- files and facts
    def add_file(self, file_id: str, deal_id: str, filename: str, label: str | None, path: str,
                 size: int) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO files VALUES (?,?,?,?,?,?,?)",
                      (file_id, deal_id, filename, label, path, size, now()))

    def set_file_label(self, file_id: str, label: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE files SET label=? WHERE file_id=?", (label, file_id))

    def files(self, deal_id: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM files WHERE deal_id=? ORDER BY uploaded_at, file_id", (deal_id,))]

    def record_fact(self, deal_id: str, key: str, value: str) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO facts VALUES (?,?,?)", (deal_id, key, value))

    def facts(self, deal_id: str) -> dict[str, str]:
        with self._conn() as c:
            return {r["key"]: r["value"] for r in c.execute(
                "SELECT key, value FROM facts WHERE deal_id=?", (deal_id,))}

    # ---- patches
    def add_patch(self, patch: Patch) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO patches VALUES (?,?,?,?,?,?,?,?,?)", (
                patch.patch_id, patch.deal_id, patch.kind, patch.path,
                json.dumps(patch.old, default=str), json.dumps(patch.new, default=str),
                patch.reason, patch.status, now()))

    def get_patch(self, patch_id: str) -> Patch | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM patches WHERE patch_id=?", (patch_id,)).fetchone()
        if not r:
            return None
        return Patch(patch_id=r["patch_id"], deal_id=r["deal_id"], kind=r["kind"], path=r["path"],
                     old=json.loads(r["old_json"]), new=json.loads(r["new_json"]),
                     reason=r["reason"], status=r["status"])

    def patches(self, deal_id: str, kind: str | None = None, status: str | None = None
                ) -> list[Patch]:
        with self._conn() as c:
            ids = [r[0] for r in c.execute(
                "SELECT patch_id FROM patches WHERE deal_id=? ORDER BY patch_id", (deal_id,))]
        got = [self.get_patch(i) for i in ids]
        return [p for p in got if (kind is None or p.kind == kind)
                and (status is None or p.status == status)]

    def set_patch_status(self, patch_id: str, status: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE patches SET status=? WHERE patch_id=?", (status, patch_id))

    def next_patch_id(self) -> str:
        with self._conn() as c:
            n = c.execute("SELECT COUNT(*) FROM patches").fetchone()[0]
        return f"p-{n + 1:04d}"
