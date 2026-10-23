"""Defect alerts: watch new scan inspections, model uploads and captures, and as soon as one shows a
crack (or another enabled trigger) phone, WhatsApp and email the plant contact.

Settings and the delivery log live in data/alerts/. A background thread polls every POLL_S seconds;
items that existed before the first start are marked seen, so turning alerts on never floods anyone.
Findings are batched: nothing is sent while an upload or inspection is still running, and once the
system has been quiet for QUIET_S seconds every pending finding goes out as one call / message.
"""
import json
import os
import threading
import time
from datetime import datetime

from backend.alerts import channels
from backend.assembly import service as assembly
from backend.capture import store as captures
from backend.config import ALERTS_DIR
from backend.inspection import service as inspection

POLL_S = 3.0
QUIET_S = 8.0          # no running jobs and no new findings for this long = batch is done
LOG_KEEP = 300
CHANNELS = ("call", "whatsapp", "email")
TRIGGERS = {
    "scan_crack": "Crack found by a surface scan inspection",
    "scan_dent": "Dent or deformation beyond tolerance in a scan inspection",
    "model_damage": "A 3D model with a tagged damaged part is loaded",
    "capture_high_risk": "A captured run scores high risk",
}
_lock = threading.Lock()
_thread: threading.Thread | None = None
_stop = threading.Event()
_jobs = {"running": 0, "last": 0.0}


def job_started() -> None:
    with _lock:
        _jobs["running"] += 1
        _jobs["last"] = time.time()


def job_finished() -> None:
    with _lock:
        _jobs["running"] = max(0, _jobs["running"] - 1)
        _jobs["last"] = time.time()


def _defaults() -> dict:
    phone = os.getenv("ALERT_PHONE", "")
    team = os.getenv("ALERT_TEAM") or os.getenv("ALERT_WHATSAPP_TO") or phone
    return {"enabled": True,
            "channels": {c: True for c in CHANNELS},
            "recipients": {"phone": phone, "whatsapp": team,
                           "email": os.getenv("ALERT_EMAIL_TO", "")},
            "triggers": {"scan_crack": True, "scan_dent": True, "model_damage": True, "capture_high_risk": False},
            "call_min_gap_min": 5, "calls_per_day": 10}


def _path(name: str):
    ALERTS_DIR.mkdir(parents=True, exist_ok=True)
    return ALERTS_DIR / name


def _read(name: str, default):
    p = _path(name)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default
    except (OSError, ValueError):
        return default


def _write(name: str, data) -> None:
    p = _path(name)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.replace(p)


def settings() -> dict:
    s, saved = _defaults(), _read("settings.json", {})
    for k, v in saved.items():
        s[k] = {**s[k], **v} if isinstance(s.get(k), dict) and isinstance(v, dict) else v
    return s


def update_settings(patch: dict) -> dict:
    with _lock:
        s = settings()
        for k, v in patch.items():
            if k not in s:
                continue
            if isinstance(s[k], dict) and isinstance(v, dict):
                s[k] = {**s[k], **{kk: vv for kk, vv in v.items() if kk in s[k]}}
            else:
                s[k] = v
        _write("settings.json", s)
    return s


def log(limit: int = 50) -> list[dict]:
    p = _path("log.jsonl")
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(x) for x in reversed(lines) if x.strip()]


def _record(entry: dict) -> None:
    p = _path("log.jsonl")
    lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    lines.append(json.dumps(entry))
    p.write_text("\n".join(lines[-LOG_KEEP:]) + "\n", encoding="utf-8")


# ---------- what counts as an alert ----------
def detect() -> list[dict]:
    """Every current item that matches a trigger, newest first. Ids are stable, so each alerts once."""
    out = []
    for i in inspection.listing():
        tag = " (artificial defect)" if i.get("artificial") else ""
        mesh = (i.get("inputs") or {}).get("mesh", "scan")
        cracks = i.get("cracks_found") or 0
        dev = i.get("max_deviation_mm") or 0
        dented = (i.get("dent_faces") or 0) > 0
        if cracks:
            out.append({"key": f"{i['id']}:crack", "trigger": "scan_crack", "at": i["created"], "where": f"{mesh}{tag}",
                        "link": f"#/inspection/{i['id']}",
                        "subject": f"RootLens: crack detected on {mesh}{tag}",
                        "text": f"Crack detected on {mesh}{tag}. {cracks} crack region{'s' if cracks != 1 else ''} found "
                                f"by the surface scan inspection {i['id']}. Open RootLens, Inspection, to see where it lies."})
        pdmg = sorted(i.get("part_damage") or [], key=lambda d: -(d.get("severity") or 0))
        if pdmg and not cracks:
            names = "; ".join(f"{d.get('display_name')}: {d.get('type')}" + (", internal" if d.get("internal") else "")
                              + (f", severity {d['severity']}" if d.get("severity") is not None else "") for d in pdmg[:4])
            out.append({"key": f"{i['id']}:parts", "trigger": "scan_crack", "at": i["created"],
                        "where": f"the {pdmg[0].get('display_name', 'part').lower()} of {mesh}{tag}",
                        "link": f"#/inspection/{i['id']}",
                        "subject": f"RootLens: damage found in {mesh}{tag}",
                        "text": f"{len(pdmg)} damaged part{'s' if len(pdmg) != 1 else ''} in {mesh}{tag}: {names}. "
                                f"Open RootLens, Inspection, to see it in 3D."})
        if dented:
            out.append({"key": f"{i['id']}:dent", "trigger": "scan_dent", "at": i["created"], "where": f"{mesh}{tag}",
                        "link": f"#/inspection/{i['id']}",
                        "subject": f"RootLens: deformation on {mesh}{tag}",
                        "text": f"Deformation found on {mesh}{tag}: up to {dev:.2f} mm from the reference shape, "
                                f"beyond the {i.get('dent_threshold_mm')} mm tolerance, "
                                f"in scan inspection {i['id']}. Open RootLens, Inspection, to see where it lies."})
    for a in assembly.listing():
        n = (a.get("counts") or {}).get("damaged_parts", 0)
        if n:
            m = assembly.get(a["id"]) or {}
            dmg = sorted(m.get("damage", []), key=lambda d: -(d.get("severity") or 0))
            names = "; ".join(
                f"{d.get('display_name')}: {d.get('type')}"
                + (", internal" if d.get("internal") else "")
                + (f", severity {d['severity']}" if d.get("severity") is not None else "")
                + (f". {d['description']}" if d.get("description") else "")
                for d in dmg[:4]) + (f"; and {len(dmg) - 4} more" if len(dmg) > 4 else "")
            out.append({"key": f"{a['id']}:damage", "trigger": "model_damage", "at": a["created"],
                        "where": (f"the {dmg[0]['display_name'].lower()} of the {a['label'].lower()} model" if dmg
                                  else f"the {a['label'].lower()} model"),
                        "link": f"#/inspection/{a['id']}",
                        "subject": f"RootLens: damaged part in {a['label']}",
                        "text": f"{n} damaged part{'s' if n != 1 else ''} in {a['label']}: {names or f'{n} part'}. "
                                f"Open RootLens, Inspection, View damage, to see the part in 3D."})
    for c in captures.listing(200):
        if c.get("risk_band") == "high":
            p = c.get("fail_probability")
            out.append({"key": f"{c['id']}:risk", "trigger": "capture_high_risk", "at": c["created"], "where": f"capture {c['id']}",
                        "link": f"#/captures/{c['id']}",
                        "subject": "RootLens: high-risk run captured",
                        "text": f"A captured run scored high risk"
                                + (f", model-estimated failure probability {p:.0%}" if p is not None else "")
                                + f". Capture {c['id']}. Open RootLens, Captures, for the suspected parameters."})
    return sorted(out, key=lambda e: e["at"], reverse=True)


# ---------- delivery ----------
def _calls_allowed(s: dict, manual: bool = False) -> str | None:
    today = datetime.now().date().isoformat()
    calls = [e for e in log(LOG_KEEP) if e.get("channel") == "call" and e.get("ok")]
    if sum(e["at"][:10] == today for e in calls) >= s["calls_per_day"]:
        return f"daily call limit ({s['calls_per_day']}) reached"
    if calls and not manual:                         # a call placed by hand skips the spacing, not the daily cap
        gap = (datetime.now() - datetime.fromisoformat(calls[0]["at"])).total_seconds() / 60
        if gap < s["call_min_gap_min"]:
            return f"last call {gap:.0f} min ago (minimum gap {s['call_min_gap_min']} min)"
    return None


def dispatch(alert: dict, s: dict | None = None, only: str | None = None, manual: bool = False) -> list[dict]:
    """Send one alert on every enabled channel (or just `only`). Returns one log entry per channel."""
    s = s or settings()
    ready = channels.configured()
    results = []
    for ch in CHANNELS:
        if only and ch != only:
            continue
        if not only and not s["channels"].get(ch):
            continue
        entry = {"at": datetime.now().isoformat(timespec="seconds"), "channel": ch, "key": alert["key"],
                 "trigger": alert["trigger"], "subject": alert["subject"], "link": alert.get("link"),
                 "ok": False, "result": ""}
        try:
            if not ready[ch]:
                raise channels.ChannelError("not configured: add the credentials to .env")
            if ch == "call":
                blocked = _calls_allowed(s, manual)
                if blocked:
                    raise channels.ChannelError(f"skipped: {blocked}")
                entry["result"] = channels.send_call(s["recipients"]["phone"], alert.get("opening") or alert["text"],
                                                     {"fault_details": alert["text"]})
            elif ch == "whatsapp":
                numbers = [n for n in str(s["recipients"]["whatsapp"]).split(",") if channels.digits(n)]
                if not numbers:
                    raise channels.ChannelError("no WhatsApp number set")
                done = [channels.send_whatsapp(n, f"*{alert['subject']}*\n{alert['text']}") for n in numbers]
                entry["result"] = "; ".join(done)
            else:
                entry["result"] = channels.send_email(s["recipients"]["email"], alert["subject"], alert["text"])
            entry["ok"] = True
        except channels.ChannelError as e:
            entry["result"] = str(e)
        _record(entry)
        results.append(entry)
    return results


def test_alert(channel: str | None = None) -> list[dict]:
    alert = {"key": f"test:{int(time.time())}", "trigger": "test", "link": None,
             "subject": "RootLens: test alert",
             "opening": "Hi boss, this is RootLens with a test call. Ask me anything about the last inspection.",
             "text": "This is a RootLens test alert. Defect alerts will reach you on this channel."}
    return dispatch(alert, only=channel)


def combine(alerts: list[dict]) -> dict:
    """One message for a whole batch: 'Hi boss, a fault was found in X' (or N faults in X and Y)."""
    where = list(dict.fromkeys(a["where"] for a in alerts))
    places = where[0] if len(where) == 1 else ", ".join(where[:-1]) + " and " + where[-1]
    n = len(alerts)
    opening = (f"Hi boss, this is RootLens. A fault was found in {places}." if n == 1 else
               f"Hi boss, this is RootLens. {n} faults were found, in {places}.")
    return {"key": "batch:" + ",".join(a["key"] for a in alerts)[:300], "trigger": "batch",
            "link": alerts[0].get("link"), "opening": opening,
            "subject": alerts[0]["subject"] if n == 1 else f"RootLens: {n} faults found in {places}",
            "text": " ".join(f"{k + 1}. {a['text']}" if n > 1 else a["text"] for k, a in enumerate(alerts))}


def flush(force: bool = False) -> list[dict]:
    """Send every pending finding as one alert once no job is running and the line has been quiet."""
    with _lock:
        pending = _read("pending.json", [])
        if not pending:
            return []
        quiet = time.time() - max(_jobs["last"], _read("last_new.json", 0.0))
        if not force and (_jobs["running"] or quiet < QUIET_S):
            return []
        _write("pending.json", [])
    return dispatch(combine(pending))


def report_call(item_id: str) -> dict:
    """'Place call' on the Inspection page: phone the report of one scan or model right now."""
    if item_id.startswith("i_"):
        r = inspection.get(item_id)
        label = ((r or {}).get("inputs") or {}).get("mesh", item_id) if r else None
    else:
        m = assembly.get(item_id)
        label = m and m.get("label")
    if not label:
        raise LookupError(f"no inspection or model with id {item_id}")
    found = [a for a in detect() if a["key"].split(":")[0] == item_id]
    if found:
        alert = combine(found)
        alert["key"] = f"manual:{alert['key']}"
    else:
        alert = {"key": f"manual:{item_id}", "trigger": "manual", "link": f"#/inspection/{item_id}",
                 "subject": f"RootLens: report for {label}",
                 "opening": f"Hi boss, this is RootLens with the report on {label}. No faults were found.",
                 "text": f"Inspection report for {label}: no cracks, dents beyond tolerance or tagged damage were found."}
    return {"findings": len(found), "results": dispatch(alert, only="call", manual=True)}


def check_once() -> list[dict]:
    """Queue every new matching item, then send the batch if the system is idle.
    The first run only records what already exists."""
    with _lock:
        seen = _read("seen.json", None)
        current = detect()
        if seen is None:
            _write("seen.json", [a["key"] for a in current])
            return []
        seen_set = set(seen)
        fresh = [a for a in current if a["key"] not in seen_set]
        if fresh:
            _write("seen.json", (seen + [a["key"] for a in fresh])[-5000:])
            s = settings()
            keep = [a for a in reversed(fresh) if s["enabled"] and s["triggers"].get(a["trigger"])]
            if keep:
                _write("pending.json", _read("pending.json", []) + keep)
                _write("last_new.json", time.time())
    return flush()


def status() -> dict:
    return {"watching": bool(_thread and _thread.is_alive()), "poll_s": POLL_S, "quiet_s": QUIET_S,
            "jobs_running": _jobs["running"], "pending": len(_read("pending.json", [])),
            "configured": channels.configured(), "triggers": TRIGGERS, "settings": settings(), "log": log(30)}


def _loop():
    while not _stop.wait(POLL_S):
        try:
            check_once()
        except Exception as e:  # keep watching; a bad item must not stop alerts
            _record({"at": datetime.now().isoformat(timespec="seconds"), "channel": "watcher", "ok": False,
                     "key": "error", "trigger": "error", "subject": "watcher error", "result": str(e)[:200]})


def start() -> None:
    global _thread
    if os.getenv("ROOTLENS_ALERTS", "1") == "0" or (_thread and _thread.is_alive()):
        return
    check_once()
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="rootlens-alerts", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
