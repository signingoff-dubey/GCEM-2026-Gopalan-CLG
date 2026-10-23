"""Assistant conversations, one per topic, shared by the web dashboard and the Android app.

Deployed: Firestore `chats/{topic}/messages`, which both clients listen to, so a question asked on the
phone shows on the dashboard within a second and the other way round. Locally: one JSON file per topic.
"""
import json
import re
import time
import uuid
from datetime import datetime, timezone

from backend import cloud
from backend.config import DATA_DIR

KEEP = 60
DIR = DATA_DIR / "chats"


def _tid(topic: str | None) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", topic or "line")[:40] or "line"


def _file(topic: str):
    return DIR / f"{_tid(topic)}.json"


def _col(topic: str):
    return cloud.db().collection("chats").document(_tid(topic)).collection("messages")


def message(role: str, content: str, client: str, **extra) -> dict:
    now = time.time()
    return {"id": uuid.uuid4().hex[:12], "role": role, "content": content, "client": client,
            "at": int(now * 1000), "created": datetime.fromtimestamp(now, timezone.utc).isoformat(timespec="seconds"),
            **{k: v for k, v in extra.items() if v is not None}}


def history(topic: str | None, limit: int = KEEP) -> list[dict]:
    """Oldest first."""
    if cloud.CLOUD:
        from google.cloud.firestore_v1 import Query
        docs = _col(topic).order_by("at", direction=Query.DESCENDING).limit(limit).stream()
        return sorted((d.to_dict() for d in docs), key=lambda m: m.get("at", 0))
    f = _file(topic)
    return json.loads(f.read_text(encoding="utf-8"))[-limit:] if f.exists() else []


def append(topic: str | None, *msgs: dict) -> None:
    if cloud.CLOUD:
        col = _col(topic)
        for m in msgs:
            col.document(m["id"]).set(m)
        cloud.db().collection("chats").document(_tid(topic)).set({"updated": msgs[-1]["created"]}, merge=True)
        return
    DIR.mkdir(parents=True, exist_ok=True)
    _file(topic).write_text(json.dumps((history(topic, 10_000) + list(msgs))[-KEEP:]), encoding="utf-8")


def clear(topic: str | None) -> int:
    if cloud.CLOUD:
        n = 0
        for d in _col(topic).list_documents():
            d.delete()
            n += 1
        return n
    f = _file(topic)
    n = len(history(topic, 10_000))
    f.unlink(missing_ok=True)
    return n
