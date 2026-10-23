"""Tools the LLM can call. Each returns compact JSON taken straight from the analysis,
so every number the model may quote has a source."""
import json

from backend.api import service
from backend.api.state import ArtifactMissing, state


def _art(name):
    try:
        return state.json(name)
    except ArtifactMissing:
        return None


def get_overview() -> dict:
    m, r = _art("metrics.json"), _art("ranking.json")
    if not m or not r:
        return {"error": "analysis not generated yet"}
    return {
        "rows": m["data_profile"]["rows"], "fails": m["data_profile"]["fails"],
        "fail_rate": m["data_profile"]["fail_rate"],
        "period": [m["data_profile"]["time_start"], m["data_profile"]["time_end"]],
        "stable_parameters": [f["feature"] for f in r["features"] if f["stable"]],
        "n_stable": r["n_stable"],
    }


def get_model_quality() -> dict:
    m = _art("metrics.json")
    if not m:
        return {"error": "analysis not generated yet"}
    t = m["lightgbm"]["test"]
    return {
        "test_window": m["split"]["test"],
        "lightgbm_test_pr_auc": t["pr_auc"], "logistic_test_pr_auc": m["logistic_baseline"]["test"]["pr_auc"],
        "test_prevalence": t["prevalence"], "lightgbm_lift_over_random": t.get("pr_auc_lift_over_random"),
        "lightgbm_test_mcc": t["mcc"], "capture_curve": t.get("capture_curve"),
        "verdict": m["verdict"],
        "random_split_pr_auc_leaky": m["leakage_contrast"]["random_split_pr_auc"],
        "drift": {k: m["drift"][k] for k in ("auc", "badge")} if "drift" in m else None,
    }


def get_ranking(top_n: int = 10) -> dict:
    r = _art("ranking.json")
    if not r:
        return {"error": "analysis not generated yet"}
    keep = ("feature", "mean_rank", "top_k_freq", "stable", "beats_null", "l1_selection_freq", "group")
    return {"method": r["method"], "n_stable": r["n_stable"],
            "features": [{k: f.get(k) for k in keep} for f in r["features"][: max(1, min(int(top_n), 25))]],
            "l1_overlap": r["l1_overlap"]["overlap"]}


def get_safe_windows(only_recommended: bool = False) -> dict:
    w = _art("safe_windows.json")
    if not w:
        return {"error": "analysis not generated yet"}
    out = []
    for x in w["windows"]:
        if "fit" not in x or (only_recommended and not x.get("recommended")):
            continue
        out.append({
            "feature": x["feature"], "status": x["status"], "recommended": x.get("recommended"),
            "window": x["window"], "operating_range": x["operating_range"],
            "current_median": x["current_median"],
            "fail_rate_in_window": x["fit"]["rate_in"], "fail_rate_in_window_ci": x["fit"]["rate_in_ci"],
            "fail_rate_outside": x["fit"]["rate_out"], "n_in_window": x["fit"]["n_in"],
            "test_check": {k: x["test_window_check"].get(k) for k in ("verdict", "rate_in", "rate_out", "n_in")},
            "relative_reduction_if_in_window": x["reduction_if_in_window"],
        })
    return {"baseline_fail_rate": w["baseline_fail_rate"], "windows": out, "caveat": w["caveat"]}


def get_timeline() -> dict:
    t = _art("timeline.json")
    if not t:
        return {"error": "analysis not generated yet"}
    return {"story": t["story"], "drift_between_windows": [
        {k: d[k] for k in ("from", "to", "top5_overlap", "entered_top5", "left_top5")} for d in t["drift"]]}


def get_validation() -> dict:
    p, a = _art("planted_benchmark.json"), _art("ai4i_check.json")
    out = {}
    if p:
        out["planted_fault_benchmark"] = {"summary": p["summary"], "n_scenarios": p["n_scenarios"],
                                          "causes_per_scenario": p["causes_per_scenario"]}
    if a:
        out["ai4i_rule_recovery"] = {m: {k: v[k] for k in ("recovered", "known_inputs", "n_failures")}
                                     for m, v in a["per_failure_mode"].items()}
    return out or {"error": "validation not generated yet"}


def get_stations(top_n: int = 8) -> dict:
    b = _art("bosch.json")
    if not b:
        return {"error": "Bosch analysis not generated yet"}
    top_n = max(1, min(int(top_n), 20))
    rates = sorted(b["station_rates"], key=lambda r: -r["fail_rate"])[:top_n]
    return {"line_fail_rate": b["sample_info"]["true_fail_rate"],
            "highest_fail_rate_stations": [{k: r[k] for k in ("station", "fail_rate", "parts_est")} for r in rates],
            "stability_ranking": [{k: s[k] for k in ("station", "mean_rank", "top_k_freq", "stable")}
                                  for s in b["station_ranking"]["stations"][:top_n]],
            "holdout": b["station_ranking"]["holdout"]}


def plan_pilot(feature: str, volume_per_day: float = 1000, pilot_share: float = 0.2) -> dict:
    try:
        p = service.plan_pilot(feature, volume_per_day=volume_per_day, pilot_share=pilot_share)
    except service.NotFound as e:
        return {"error": str(e)}
    return {"feature": feature, "summary": p["summary"], "scenarios": p["scenarios"]}


def estimate_savings(volume_per_day: float = 1000, scrap_cost_per_part: float = 500,
                     days_per_month: float = 26, feature: str | None = None) -> dict:
    try:
        s = service.price_savings(volume_per_day=volume_per_day, scrap_cost_per_part=scrap_cost_per_part,
                                  days_per_month=days_per_month, feature=feature)
    except (service.NotFound, ValueError) as e:
        return {"error": str(e)}
    return {k: s[k] for k in ("low", "mid", "high", "currency", "label", "based_on", "window_status")}


def list_failed_runs(limit: int = 10) -> dict:
    r = service.list_runs("test", fails_only=True, limit=max(1, min(int(limit), 50)))
    return {"runs": r["runs"], "label": r["label"]}


def explain_run(index: int) -> dict:
    try:
        d = service.run_detail(int(index))
    except service.NotFound as e:
        return {"error": str(e)}
    cf = d["counterfactual"]
    return {"index": d["index"], "timestamp": d["timestamp"], "actually_failed": d["fail"],
            "fail_probability": d["fail_probability"], "risk_band": d["risk_band"],
            "top_contributors": d["top_contributors"][:5],
            "nearest_passing_runs": cf["neighbours"][:3], "biggest_differences": cf["biggest_differences"][:5],
            "model_estimate": cf.get("model_estimate"), "label": d["label"]}


def get_solutions() -> dict:
    from backend.api.solutions import solutions
    return solutions()


def get_data_quality() -> dict:
    d = _art("data_quality.json") or {}
    return {k: d.get(k) for k in ("steps", "splits", "shape_check", "imbalance")}


def _replay():
    from backend.ml import replay
    return replay, state.json("replay.json")


def get_period(start: str, end: str | None = None) -> dict:
    """Runs, failures, fail rate and model risk for a day, month, range or phrase like 'last month'."""
    rp, r = _replay()
    s, e = rp.resolve(r, start)
    return rp.period(r, s, end or e)


def compare_periods(a: str, b: str) -> dict:
    rp, r = _replay()
    sa, ea = rp.resolve(r, a)
    sb, eb = rp.resolve(r, b)
    pa, pb = rp.period(r, sa, ea), rp.period(r, sb, eb)
    diff = {}
    if pa.get("runs") and pb.get("runs"):
        diff = {"fail_rate_change": round(pb["fail_rate"] - pa["fail_rate"], 4), "runs_change": pb["runs"] - pa["runs"],
                "fails_change": pb["fails"] - pa["fails"]}
    return {"a": pa, "b": pb, "b_minus_a": diff, "label": r["label"]}


def get_drift() -> dict:
    d = _art("drift.json") or {}
    r = d.get("report", {})
    return {"data_period": r.get("data_period"), "train_vs_test_auc": (r.get("adversarial") or {}).get("auc"),
            "sensors_shifted": r.get("sensors_shifted_psi_gt_0_25"), "sensors_checked": r.get("sensors_checked"),
            "most_shifted": (r.get("most_shifted") or [])[:5], "experiment": d.get("experiment")}


def get_latest_inspection() -> dict:
    """The newest 3D model or multi-part scan with its damaged parts and the suggested fix for each."""
    from backend.assembly import service as asm
    from backend.inspection import service as insp
    rows = [("model", a["id"], a["created"]) for a in asm.listing()] +            [("scan", i["id"], i["created"]) for i in insp.listing() if i.get("part_damage") or i.get("cracks_found")]
    if not rows:
        return {"none": "no model or scan has been inspected yet"}
    kind, rid, _ = max(rows, key=lambda r: r[2])
    if kind == "model":
        m = asm.get(rid) or {}
        label, dmg = m.get("label"), m.get("damage", [])
    else:
        r = insp.get(rid) or {}
        label, dmg = (r.get("inputs") or {}).get("mesh"), (r.get("parts") or {}).get("damage", [])
    return {"id": rid, "label": label, "damage": [
        {k: d.get(k) for k in ("display_name", "type", "severity", "internal", "description", "source")} |
        {"fix": (d.get("remedy") or {}).get("actions", [])[:2], "stage": (d.get("remedy") or {}).get("stage")}
        for d in sorted(dmg, key=lambda d: -(d.get("severity") or 0))[:8]],
        "fix_source": "engineering reference for the defect type, not derived from the line data"}


REGISTRY = {
    "get_overview": (get_overview, "Dataset size, failure rate, period and the stable suspected parameters.", {}),
    "get_model_quality": (get_model_quality, "Held-out test-window quality (PR-AUC with CI, lift, capture curve), "
                          "the leaky random-split number for contrast, and train-vs-test drift.", {}),
    "get_ranking": (get_ranking, "Ranked suspected parameters with bootstrap stability and null test.",
                    {"top_n": {"type": "integer", "description": "how many (max 25)"}}),
    "get_safe_windows": (get_safe_windows, "Suggested operating windows, historical fail rates inside/outside, "
                         "held-out test verdict and whether each is recommended.",
                         {"only_recommended": {"type": "boolean"}}),
    "get_timeline": (get_timeline, "Which parameter led attribution in each time period, and drift between periods.", {}),
    "get_validation": (get_validation, "Planted-fault benchmark and AI4I rule-recovery results: proof the method works.", {}),
    "get_stations": (get_stations, "Bosch line: station fail rates and station stability ranking.",
                     {"top_n": {"type": "integer"}}),
    "plan_pilot": (plan_pilot, "Size a pilot trial (parts, days, cost) to confirm a safe window for one parameter.",
                   {"feature": {"type": "string"}, "volume_per_day": {"type": "number"},
                    "pilot_share": {"type": "number", "description": "fraction of daily output, 0-1"}}),
    "estimate_savings": (estimate_savings, "Monthly savings range (model estimate) if production runs inside a "
                         "safe window. Defaults to the best recommended window.",
                         {"volume_per_day": {"type": "number"}, "scrap_cost_per_part": {"type": "number"},
                          "days_per_month": {"type": "number"}, "feature": {"type": "string"}}),
    "list_failed_runs": (list_failed_runs, "Failed runs in the held-out test window with model risk.",
                         {"limit": {"type": "integer"}}),
    "get_solutions": (get_solutions, "What to change: corrective windows (with why and the test verdict), stations "
                      "to start with and their top parameters, and the data cleaning summary. Use it for any 'what should we do' question.", {}),
    "get_data_quality": (get_data_quality, "How missing values and outliers were handled (train-only), per split, and the "
                         "check that cleaning kept the training data's shape.", {}),
    "get_period": (get_period, "Production history (replayed SECOM runs, 1 Sep - 23 Oct 2026): runs, failures, passes, fail rate, "
                   "model risk, high-risk runs, the F33 window split and the riskiest runs for a day (YYYY-MM-DD), a month (YYYY-MM), "
                   "a range (start + end), or a phrase: today, yesterday, this week, last week, this month, last month, last year.",
                   {"start": {"type": "string"}, "end": {"type": "string"}}),
    "compare_periods": (compare_periods, "Compare two periods (each a date, month or phrase such as 'last month' and 'this month'): "
                        "both periods' stats and the change in fail rate, runs and failures.",
                        {"a": {"type": "string"}, "b": {"type": "string"}}),
    "get_drift": (get_drift, "When the data was recorded, how much the later runs drifted from training, and whether "
                  "interpolation or recency weighting helped (chosen on validation).", {}),
    "get_latest_inspection": (get_latest_inspection, "The newest inspected 3D model or scan: damaged parts, severity and the "
                              "suggested fix for each defect type.", {}),
    "explain_run": (explain_run, "Why one run is risky: top contributors and nearest real passing runs.",
                    {"index": {"type": "integer"}}),
}
REQUIRED = {"plan_pilot": ["feature"], "explain_run": ["index"], "get_period": ["start"], "compare_periods": ["a", "b"]}


def schemas() -> list[dict]:
    return [{"name": n, "description": d,
             "parameters": {"type": "object", "properties": props, **({"required": REQUIRED[n]} if n in REQUIRED else {})}}
            for n, (_, d, props) in REGISTRY.items()]


def tidy(obj):
    """Round floats to what a person would quote: whole numbers from 1000 up, else 4 significant
    figures. The model then repeats clean figures and the guard checks against the same values."""
    if isinstance(obj, bool) or obj is None:
        return obj
    if isinstance(obj, float):
        if obj != obj:
            return None
        return round(obj) if abs(obj) >= 1000 else float(f"{obj:.4g}")
    if isinstance(obj, dict):
        return {k: tidy(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [tidy(v) for v in obj]
    return obj


def call(name: str, args: dict) -> dict:
    if name not in REGISTRY:
        return {"error": f"unknown tool {name}"}
    fn = REGISTRY[name][0]
    allowed = REGISTRY[name][2].keys()
    try:
        return tidy(fn(**{k: v for k, v in (args or {}).items() if k in allowed}))
    except Exception as e:  # noqa: BLE001 - tool errors go back to the model, not the user
        return {"error": f"{type(e).__name__}: {e}"}


def dumps(obj) -> str:
    return json.dumps(obj, default=str)
