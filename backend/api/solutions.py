"""What to change, gathered in one place for every screen and the AI: the line's corrective windows (SECOM),
the stations to work on first (Bosch), and how the data was cleaned. Built only from the analysis artifacts."""
import re

from backend.api.state import ArtifactMissing, state


def _art(name):
    try:
        return state.json(name)
    except ArtifactMissing:
        return None


def solutions() -> dict:
    out = {"line": [], "stations": [], "data": None,
           "label": "Statistically suspected, stability-checked. Confirm each change with a pilot before rolling it out."}
    w = _art("safe_windows.json")
    for x in (w or {}).get("windows", []):
        t = x.get("test_window_check") or {}
        do = bool(x.get("recommended"))
        out["line"].append({
            "parameter": x["feature"], "do": do, "status": x["status"],
            "action": (f"Hold {x['feature']} between {x['window'][0]:.4g} and {x['window'][1]:.4g} "
                       f"(now around {x['current_median']:.4g})") if do else f"Do not change {x['feature']} yet",
            "why": x.get("text"),
            "evidence": {"fail_rate_inside": x["fit"]["rate_in"], "fail_rate_outside": x["fit"]["rate_out"],
                         "runs_inside": x["fit"]["n_in"], "test_verdict": t.get("verdict")},
            "reason_not": None if do else (t.get("verdict") or x["status"]),
            "next_step": f"Pilot: Fix & savings, Pilot planner for {x['feature']}" if do else
                         "Keep monitoring; rerun the analysis with more recent runs"})
    b = _art("bosch.json")
    if b:
        rates = {r["station"]: r for r in b.get("station_rates", [])}
        line_rate = b.get("sample_info", {}).get("true_fail_rate")
        for s in b.get("station_ranking", {}).get("stations", [])[:6]:
            if not s.get("stable") or not re.match(r"^L\d+_S\d+$", s["station"]):   # skip route/summary pseudo-stations
                continue
            r = rates.get(s["station"], {})
            params = [p["feature"] for p in s.get("top_parameters", [])[:3]]
            out["stations"].append({
                "station": s["station"], "fail_rate": r.get("fail_rate"),
                "vs_line": round(r["fail_rate"] / line_rate, 2) if r.get("fail_rate") and line_rate else None,
                "parameters": params,
                "action": f"Start root-cause work at {s['station']}: review {', '.join(params)} and their control limits"})
    dq = _art("data_quality.json")
    if dq:
        out["data"] = {"steps": dq["steps"], "shape_check": dq["shape_check"]}
    return out
