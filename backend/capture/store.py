"""Captures: SQLite with images beside it locally, Firestore `captures` + Storage `captures/` when deployed."""
import json
import sqlite3
import uuid
from datetime import datetime

from backend import cloud
from backend.config import CAPTURES_DIR

SUMMARY = ("source", "status", "run_id", "fail_probability", "risk_band")

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


def put_image(cid: str, data: bytes) -> str:
    """Store the photo; returns the URL the dashboard loads it from."""
    if cloud.CLOUD:
        return cloud.blob_put(f"captures/{cid}.jpg", data, "image/jpeg")
    image_path(cid).parent.mkdir(parents=True, exist_ok=True)
    image_path(cid).write_bytes(data)
    return f"/api/captures/{cid}/image"


def save(record: dict) -> None:
    res = record.get("result") or {}
    if cloud.CLOUD:
        cloud.record_put("captures", record["id"], record, {
            "source": record["source"], "status": record["status"],
            "run_id": (record.get("extracted") or {}).get("run_id"),
            "fail_probability": res.get("fail_probability"), "risk_band": res.get("risk_band")})
        return
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO captures VALUES (?,?,?,?,?,?,?,?)", (
            record["id"], record["created"], record["source"], record["status"],
            (record.get("extracted") or {}).get("run_id"), res.get("fail_probability"),
            res.get("risk_band"), json.dumps(record, default=str)))


def get(cid: str) -> dict | None:
    if cloud.CLOUD:
        return cloud.record_get("captures", cid)
    with _conn() as c:
        row = c.execute("SELECT payload FROM captures WHERE id=?", (cid,)).fetchone()
    return json.loads(row[0]) if row else None


def latest() -> dict | None:
    if cloud.CLOUD:
        rows = cloud.record_list("captures", 1)
        return get(rows[0]["id"]) if rows else None
    with _conn() as c:
        row = c.execute("SELECT payload FROM captures ORDER BY created DESC LIMIT 1").fetchone()
    return json.loads(row[0]) if row else None


def listing(limit=50) -> list[dict]:
    if cloud.CLOUD:
        return [{k: r.get(k) for k in ("id", "created", *SUMMARY)} for r in cloud.record_list("captures", limit)]
    with _conn() as c:
        rows = c.execute("SELECT id, created, source, status, run_id, fail_probability, risk_band "
                         "FROM captures ORDER BY created DESC LIMIT ?", (limit,)).fetchall()
    keys = ("id", "created", "source", "status", "run_id", "fail_probability", "risk_band")
    return [dict(zip(keys, r)) for r in rows]


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def delete(cid: str) -> None:
    """Remove one local capture and its photo."""
    with _conn() as c:
        c.execute("DELETE FROM captures WHERE id = ?", (cid,))
    image_path(cid).unlink(missing_ok=True)
