"""Live activity for the dashboard calendar: captures, scan inspections and model uploads, grouped
by day, plus a server-sent-events stream that pushes whenever something new lands."""
import asyncio
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from backend.assembly import service as assembly
from backend.capture import store as captures
from backend.inspection import service as inspection

router = APIRouter(prefix="/api/activity", tags=["activity"])
POLL_S = 2.0
HEARTBEAT_S = 15.0


def _events(limit=500) -> list[dict]:
    ev = []
    for c in captures.listing(limit):
        bad = c["status"] in ("failed", "needs_review") or c["risk_band"] == "high"
        ev.append({"id": c["id"], "kind": "capture", "at": c["created"],
                   "title": f"Capture ({c['source']}): {c['status'].replace('_', ' ')}"
                            + (f", {c['risk_band']} risk" if c["risk_band"] else ""),
                   "tone": "rose" if bad else "good", "link": f"#/captures/{c['id']}"})
    for i in inspection.listing()[:limit]:
        found = ((i.get("cracks_found") or 0) > 0 or (i.get("dent_faces") or 0) > 0
                 or bool(i.get("part_damage")))
        ev.append({"id": i["id"], "kind": "inspection", "at": i["created"],
                   "title": f"Scan inspection: {i['inputs']['mesh']}" + (" (artificial defect)" if i.get("artificial") else ""),
                   "tone": "rose" if found else "info", "link": f"#/inspection/{i['id']}"})
    for a in assembly.listing()[:limit]:
        dmg = (a.get("counts") or {}).get("damaged_parts", 0)
        ev.append({"id": a["id"], "kind": "assembly", "at": a["created"],
                   "title": f"Model uploaded: {a['label']}" + (f" ({dmg} damaged part)" if dmg else ""),
                   "tone": "rose" if dmg else "info", "link": f"#/inspection/{a['id']}"})
    return sorted(ev, key=lambda e: e["at"], reverse=True)


def snapshot(days: int = 62) -> dict:
    now = datetime.now()
    since = (now - timedelta(days=days)).date().isoformat()
    ev = [e for e in _events() if e["at"][:10] >= since]
    by_day = defaultdict(lambda: {"capture": 0, "inspection": 0, "assembly": 0, "alerts": 0, "events": []})
    for e in ev:
        d = by_day[e["at"][:10]]
        d[e["kind"]] += 1
        d["alerts"] += e["tone"] == "rose"
        if len(d["events"]) < 20:
            d["events"].append(e)
    version = hashlib.sha1(json.dumps([(e["id"], e["at"], e["title"]) for e in ev]).encode()).hexdigest()[:12]
    return {"now": now.isoformat(timespec="seconds"), "today": now.date().isoformat(), "version": version,
            "days": [{"date": k, **v} for k, v in sorted(by_day.items())], "recent": ev[:10]}


@router.get("")
def activity(days: int = Query(62, ge=1, le=400)):
    return snapshot(days)


@router.get("/stream")
async def stream(request: Request, days: int = Query(62, ge=1, le=400)):
    """SSE: an `activity` event on connect and on every change, a `tick` heartbeat with server time."""
    async def gen():
        sent = {"version": None, "today": None}
        last_beat = 0.0
        loop = asyncio.get_running_loop()
        yield "retry: 3000\n\n"
        while not await request.is_disconnected():
            snap = await loop.run_in_executor(None, snapshot, days)
            if (snap["version"], snap["today"]) != (sent["version"], sent["today"]):
                sent.update(version=snap["version"], today=snap["today"])
                yield f"event: activity\ndata: {json.dumps(snap)}\n\n"
                last_beat = loop.time()
            elif loop.time() - last_beat > HEARTBEAT_S:
                yield f"event: tick\ndata: {json.dumps({'now': snap['now'], 'today': snap['today']})}\n\n"
                last_beat = loop.time()
            await asyncio.sleep(POLL_S)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
