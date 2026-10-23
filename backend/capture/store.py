"""SQLite store for captures; images live next to the database."""
import json
import sqlite3
import uuid
from datetime import datetime

from backend.config import CAPTURES_DIR

DB = CAPTURES_DIR / "captures.db"


def _conn():
    CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS captures (
        id TEXT PRIMARY KEY, created TEXT, source TEXT, status TEXT,
        run_id TEXT, fail_probability REAL, risk_band TEXT, payload TEXT)""")
    return c


def new_id() -> str:
    return "c_" + uuid.uuid4().hex[:10]


def image_path(cid: str):
    return CAPTURES_DIR / f"{cid}.jpg"


def save(record: dict) -> None:
    res = record.get("result") or {}
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO captures VALUES (?,?,?,?,?,?,?,?)", (
            record["id"], record["created"], record["source"], record["status"],
            (record.get("extracted") or {}).get("run_id"), res.get("fail_probability"),
            res.get("risk_band"), json.dumps(record, default=str)))


def get(cid: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT payload FROM captures WHERE id=?", (cid,)).fetchone()
    return json.loads(row[0]) if row else None


def latest() -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT payload FROM captures ORDER BY created DESC LIMIT 1").fetchone()
    return json.loads(row[0]) if row else None


def listing(limit=50) -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT id, created, source, status, run_id, fail_probability, risk_band "
                         "FROM captures ORDER BY created DESC LIMIT ?", (limit,)).fetchall()
    keys = ("id", "created", "source", "status", "run_id", "fail_probability", "risk_band")
    return [dict(zip(keys, r)) for r in rows]


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")
