"""Investigation orchestrator: a fixed RCA plan executed in parallel, follow-ups chosen from the
evidence, then one LLM call writes a structured brief that must pass the grounding check.

Plan: evidence (quality, drift, ranking, windows, timeline, validation, stations) ->
follow-ups (pilot + savings per recommended window, explain the riskiest failed run) -> brief.
"""
import json
import time
from concurrent.futures import ThreadPoolExecutor

from backend.ai import guard, llm, tools
from backend.ai.agent import SYSTEM

EVIDENCE_STEPS = ["get_overview", "get_model_quality", "get_ranking", "get_safe_windows",
                  "get_timeline", "get_validation", "get_stations"]

BRIEF_SPEC = """Write the investigation brief as JSON with exactly these keys:
{
 "headline": one sentence,
 "where": [ {"item": parameter or station id, "evidence": short text with numbers} ],
 "what_to_change": [ {"parameter": id, "action": text, "status": recommended / not recommended + why} ],
 "how_much": {"text": savings range sentence labelled model estimate, or why nothing is priced},
 "reliability": [ short bullets: model quality vs random, drift, validation results ],
 "next_actions": [ short bullets, include pilot sizes when available ]
}
Use only numbers that appear in EVIDENCE. JSON only."""


def _step(name, args=None):
    t0 = time.time()
    res = tools.call(name, args or {})
    return {"step": name, "args": args or {}, "ms": round((time.time() - t0) * 1000), "result": res}


def investigate(provider: str | None = None, volume_per_day: float = 1000,
                scrap_cost_per_part: float = 500) -> dict:
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=len(EVIDENCE_STEPS)) as ex:
        steps = list(ex.map(_step, EVIDENCE_STEPS))
    ev = {s["step"]: s["result"] for s in steps}

    follow = []
    windows = ev.get("get_safe_windows", {}).get("windows", [])
    targets = [w["feature"] for w in windows if w.get("recommended")]
    if not targets:  # nothing passed every check: still size a pilot for the most stable candidate
        stable = [f["feature"] for f in ev.get("get_ranking", {}).get("features", []) if f.get("stable")]
        targets = [f for f in stable if any(w["feature"] == f for w in windows)][:1]
    for f in targets[:3]:
        follow.append(("plan_pilot", {"feature": f, "volume_per_day": volume_per_day}))
        follow.append(("estimate_savings", {"feature": f, "volume_per_day": volume_per_day,
                                            "scrap_cost_per_part": scrap_cost_per_part}))
    runs = tools.call("list_failed_runs", {"limit": 50}).get("runs", [])
    if runs:
        riskiest = max(runs, key=lambda r: r.get("fail_prob") or 0)
        follow.append(("explain_run", {"index": riskiest["index"]}))
    with ThreadPoolExecutor(max_workers=max(1, len(follow))) as ex:
        steps += list(ex.map(lambda a: _step(*a), follow))
    for s in steps[len(EVIDENCE_STEPS):]:
        key = s["step"] + (f":{s['args'].get('feature') or s['args'].get('index')}")
        ev[key] = s["result"]
    t_tools = time.time() - t0

    evidence_json = json.dumps(ev, default=str)
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"EVIDENCE:\n{evidence_json}\n\n{BRIEF_SPEC}"}]
    order = (provider,) if provider else None
    reply = llm.chat_with_fallback(messages, None, order=order, json_mode=True, max_tokens=3000)
    numbers = guard.evidence_numbers(evidence_json)
    brief, check, revised = _parse_and_check(reply.content, numbers)
    if not check["ok"]:
        messages += [reply.as_message(), {"role": "user", "content":
                     f"Fix these problems and return the full JSON again. Unverified numbers: "
                     f"{check['unverified_numbers']}. Violations: {check['violations']}."}]
        reply = llm.chat_with_fallback(messages, None, pinned=(reply.provider, reply.model),
                                       json_mode=True, max_tokens=3000)
        brief, check, _ = _parse_and_check(reply.content, numbers)
        revised = True

    return {
        "brief": brief,
        "grounded": check["ok"],
        "unverified_numbers": check["unverified_numbers"],
        "violations": check["violations"],
        "revised_once": revised,
        "steps": [{"step": s["step"], "args": s["args"], "ms": s["ms"],
                   "ok": "error" not in (s["result"] or {})} for s in steps],
        "provider": reply.provider, "model": reply.model,
        "seconds": {"tools": round(t_tools, 2), "total": round(time.time() - t0, 2)},
        "label": "AI-written brief over RootLens results; every number is checked against the evidence.",
    }


def _parse_and_check(content: str, numbers):
    try:
        brief = json.loads(content)
    except json.JSONDecodeError:
        return None, {"ok": False, "unverified_numbers": [], "violations": ["brief was not valid JSON"]}, False
    text = json.dumps(brief, ensure_ascii=False)
    return brief, guard.check(text, numbers), False
