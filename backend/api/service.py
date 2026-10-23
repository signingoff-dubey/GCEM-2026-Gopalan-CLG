"""Request logic shared by the REST endpoints and the AI agent's tools."""
import numpy as np
import pandas as pd

from backend.api.state import state
from backend.config import DISCLAIMER
from backend.ml import cost, pilot
from backend.ml.pipeline import clean


class NotFound(LookupError):
    pass


def price_savings(volume_per_day=cost.DEFAULTS["volume_per_day"],
                  scrap_cost_per_part=cost.DEFAULTS["scrap_cost_per_part"],
                  false_alarm_cost=cost.DEFAULTS["false_alarm_cost"],
                  days_per_month=cost.DEFAULTS["days_per_month"],
                  feature=None, false_alarms_per_day=0.0) -> dict:
    """Savings range for one safe window (default: best recommended). Raises NotFound / ValueError."""
    w = state.json("safe_windows.json")
    pool = [x for x in w["windows"] if "fit" in x]
    if feature:
        pool = [x for x in pool if x["feature"] == feature]
        if not pool:
            raise NotFound(f"no safe window for {feature}")
    else:
        pool = [x for x in pool if x.get("recommended")]
        if not pool:
            raise NotFound("no stable recommendation to price")
    best = max(pool, key=lambda x: x["reduction_if_in_window"]["mid"])
    red = best["reduction_if_in_window"]
    out = cost.monthly_savings(cost.CostInputs(
        volume_per_day=volume_per_day, scrap_cost_per_part=scrap_cost_per_part,
        false_alarm_cost=false_alarm_cost, days_per_month=days_per_month,
        baseline_fail_rate=w["baseline_fail_rate"], false_alarms_per_day=false_alarms_per_day,
        reduction_low=red["low"], reduction_mid=red["mid"], reduction_high=red["high"]))
    out["based_on"] = best["feature"]
    out["stable"] = best["stable"]
    out["window_status"] = best["status"]
    return clean(out)


def plan_pilot(feature: str, **kw) -> dict:
    w = state.json("safe_windows.json")
    entry = next((x for x in w["windows"] if x["feature"] == feature and "fit" in x), None)
    if entry is None:
        raise NotFound(f"no safe window for {feature}")
    return clean(pilot.plan_for_window(feature, entry, **kw))


def risk_band(prob: float, thr: float) -> str:
    return "high" if prob >= max(thr * 2, 0.3) else "elevated" if prob >= thr else "low"


def list_runs(split="test", fails_only=False, limit=200) -> dict:
    X, y, ts, s = state.data
    Xs = {"train": s.X_train, "val": s.X_val, "test": s.X_test}[split]
    idx = Xs.index
    p = state.predict(Xs)
    thr = state.json("metrics.json")["lightgbm"]["test"]["threshold"]
    df = pd.DataFrame({"index": idx, "timestamp": ts.loc[idx].astype(str).values,
                       "fail": y.loc[idx].values, "fail_prob": p,
                       "risk_band": [risk_band(v, thr) for v in p]})
    if fails_only:
        df = df[df["fail"] == 1]
    return clean({"split": split, "runs": df.head(limit).to_dict(orient="records"),
                  "label": "fail_prob is model-estimated"})


def explain_row(row: pd.Series, exclude_index=None) -> dict:
    X1 = pd.DataFrame([row])
    prob = float(state.predict(X1)[0])
    sv = state.shap_row(X1)
    w = {x["feature"]: x for x in state.json("safe_windows.json")["windows"] if "fit" in x}
    top = []
    for f, v in sv.reindex(sv.abs().sort_values(ascending=False).index).head(8).items():
        val = row.get(f)
        entry = {"feature": f, "value": None if pd.isna(val) else float(val), "shap": float(v)}
        if f in w:
            a, b = w[f]["window"]
            entry["safe_window"] = [a, b]
            entry["in_safe_window"] = None if pd.isna(val) else bool(a <= val <= b)
            entry["window_status"] = w[f]["status"]
            entry["window_recommended"] = bool(w[f].get("recommended"))
        top.append(entry)
    thr = state.json("metrics.json")["lightgbm"]["test"]["threshold"]
    cf = state.neighbours.explain(row, weights=pd.Series(state.bundle["importance"]),
                                  model_fn=state.predict, exclude_index=exclude_index)
    return {"fail_probability": prob, "risk_band": risk_band(prob, thr), "threshold": thr,
            "top_contributors": top, "counterfactual": cf,
            "label": "model-estimated", "disclaimer": DISCLAIMER}


def run_detail(index: int) -> dict:
    X, y, ts, _ = state.data
    if index not in X.index:
        raise NotFound("run not found")
    out = explain_row(X.loc[index], exclude_index=index)
    out.update({"index": index, "timestamp": str(ts.loc[index]), "fail": int(y.loc[index])})
    return clean(out)


def score_values(values: dict) -> dict:
    cols = state.bundle["feature_columns"]
    ranges = state.json("operating_ranges.json")
    unknown = [k for k in values if k not in cols]
    row = pd.Series(np.nan, index=cols, dtype=float)
    needs_review = []
    for k, v in values.items():
        if k in unknown:
            continue
        r = ranges.get(k)
        if r is not None and r["min"] is not None:
            span = (r["max"] - r["min"]) or 1.0
            if not (r["min"] - span <= v <= r["max"] + span):
                needs_review.append(k)
        row[k] = v
    out = explain_row(row)
    out.update({"unknown_parameters": unknown, "needs_review": needs_review,
                "provided": len(values) - len(unknown)})
    return clean(out)
