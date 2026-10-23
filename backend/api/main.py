"""RootLens API. Serves precomputed artifacts and light per-request scoring.

Run: uvicorn backend.api.main:app --host 0.0.0.0 --port 8000   (docs at /docs)
"""
import os

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.api.state import ArtifactMissing, state
from backend.config import DISCLAIMER
from backend.ml import cost, pilot
from backend.ml.pipeline import clean

app = FastAPI(title="RootLens API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ArtifactMissing)
def _missing(_, exc: ArtifactMissing):
    return JSONResponse(status_code=503, content={
        "detail": f"artifact '{exc}' not found; run `make train` first"})


def _artifact(name: str):
    return clean(state.json(name))


@app.get("/api/health")
def health():
    ready = (state.dir / "model.pkl").exists()
    return {"status": "ok", "artifacts_ready": ready}


@app.get("/api/overview")
def overview():
    """Headline numbers for the landing view."""
    m = state.json("metrics.json")
    r = state.json("ranking.json")
    w = state.json("safe_windows.json")
    p = state.json("planted_benchmark.json")
    return clean({
        "data": m["data_profile"],
        "split": m["split"],
        "test_pr_auc": {"lightgbm": m["lightgbm"]["test"]["pr_auc"],
                        "logistic_baseline": m["logistic_baseline"]["test"]["pr_auc"]},
        "random_split_pr_auc": m["leakage_contrast"]["random_split_pr_auc"],
        "n_stable_parameters": r["n_stable"],
        "stable_parameters": [f["feature"] for f in r["features"] if f["stable"]],
        "recommended_windows": [x["feature"] for x in w["windows"] if x.get("status", "").startswith("recommended")],
        "planted_benchmark": p["summary"],
        "disclaimer": DISCLAIMER,
    })


# precomputed artifacts
for _path, _name in [
    ("/api/metrics", "metrics.json"),
    ("/api/ranking", "ranking.json"),
    ("/api/safe-windows", "safe_windows.json"),
    ("/api/pilots", "pilots.json"),
    ("/api/timeline", "timeline.json"),
    ("/api/validation/planted", "planted_benchmark.json"),
    ("/api/validation/ai4i", "ai4i_check.json"),
    ("/api/stations", "bosch.json"),
    ("/api/operating-ranges", "operating_ranges.json"),
    ("/api/savings/default", "savings_default.json"),
]:
    app.add_api_route(_path, (lambda n: lambda: _artifact(n))(_name), methods=["GET"],
                      name=_name.removesuffix(".json"))


class SavingsRequest(BaseModel):
    volume_per_day: float = cost.DEFAULTS["volume_per_day"]
    scrap_cost_per_part: float = cost.DEFAULTS["scrap_cost_per_part"]
    false_alarm_cost: float = cost.DEFAULTS["false_alarm_cost"]
    days_per_month: float = cost.DEFAULTS["days_per_month"]
    feature: str | None = Field(None, description="safe-window feature to price; default = best recommended")
    false_alarms_per_day: float = 0.0


@app.post("/api/savings")
def savings(req: SavingsRequest):
    w = state.json("safe_windows.json")
    pool = [x for x in w["windows"] if "fit" in x]
    if req.feature:
        pool = [x for x in pool if x["feature"] == req.feature]
        if not pool:
            raise HTTPException(404, f"no safe window for {req.feature}")
    else:
        pool = [x for x in pool if x.get("status", "").startswith("recommended")]
        if not pool:
            raise HTTPException(404, "no stable recommendation to price")
    best = max(pool, key=lambda x: x["reduction_if_in_window"]["mid"])
    red = best["reduction_if_in_window"]
    try:
        out = cost.monthly_savings(cost.CostInputs(
            volume_per_day=req.volume_per_day, scrap_cost_per_part=req.scrap_cost_per_part,
            false_alarm_cost=req.false_alarm_cost, days_per_month=req.days_per_month,
            baseline_fail_rate=w["baseline_fail_rate"], false_alarms_per_day=req.false_alarms_per_day,
            reduction_low=red["low"], reduction_mid=red["mid"], reduction_high=red["high"]))
    except ValueError as e:
        raise HTTPException(422, str(e))
    out["based_on"] = best["feature"]
    out["stable"] = best["stable"]
    return clean(out)


class PilotRequest(BaseModel):
    feature: str
    volume_per_day: float = pilot.DEFAULTS["volume_per_day"]
    pilot_share: float = Field(pilot.DEFAULTS["pilot_share"], gt=0, le=1)
    cost_per_pilot_part: float = Field(pilot.DEFAULTS["cost_per_pilot_part"], ge=0)
    scrap_cost_per_part: float = Field(pilot.DEFAULTS["scrap_cost_per_part"], ge=0)
    power: float = Field(pilot.DEFAULTS["power"], gt=0.5, lt=1)
    alpha: float = Field(pilot.DEFAULTS["alpha"], gt=0, lt=0.5)


@app.post("/api/pilot")
def pilot_plan(req: PilotRequest):
    w = state.json("safe_windows.json")
    entry = next((x for x in w["windows"] if x["feature"] == req.feature and "fit" in x), None)
    if entry is None:
        raise HTTPException(404, f"no safe window for {req.feature}")
    kw = req.model_dump(exclude={"feature"})
    return clean(pilot.plan_for_window(req.feature, entry, **kw))


@app.get("/api/runs")
def runs(split: str = Query("test", pattern="^(train|val|test)$"), fails_only: bool = False,
         limit: int = Query(200, le=2000)):
    X, y, ts, s = state.data
    Xs = {"train": s.X_train, "val": s.X_val, "test": s.X_test}[split]
    idx = Xs.index
    p = state.predict(Xs)
    thr = state.json("metrics.json")["lightgbm"]["test"]["threshold"]
    df = pd.DataFrame({"index": idx, "timestamp": ts.loc[idx].astype(str).values,
                       "fail": y.loc[idx].values, "fail_prob": p,
                       "risk_band": [_band(v, thr) for v in p]})
    if fails_only:
        df = df[df["fail"] == 1]
    return clean({"split": split, "runs": df.head(limit).to_dict(orient="records"),
                  "label": "fail_prob is model-estimated"})


def _band(prob: float, thr: float) -> str:
    return "high" if prob >= max(thr * 2, 0.3) else "elevated" if prob >= thr else "low"


def _explain_row(row: pd.Series, exclude_index=None) -> dict:
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
        top.append(entry)
    thr = state.json("metrics.json")["lightgbm"]["test"]["threshold"]
    band = _band(prob, thr)
    cf = state.neighbours.explain(row, weights=pd.Series(state.bundle["importance"]),
                                  model_fn=state.predict, exclude_index=exclude_index)
    return {"fail_probability": prob, "risk_band": band, "threshold": thr,
            "top_contributors": top, "counterfactual": cf,
            "label": "model-estimated", "disclaimer": DISCLAIMER}


@app.get("/api/runs/{index}")
def run_detail(index: int):
    X, y, ts, _ = state.data
    if index not in X.index:
        raise HTTPException(404, "run not found")
    out = _explain_row(X.loc[index], exclude_index=index)
    out.update({"index": index, "timestamp": str(ts.loc[index]), "fail": int(y.loc[index])})
    return clean(out)


class ScoreRequest(BaseModel):
    values: dict[str, float] = Field(..., description="parameter -> value; missing ones are left NaN")


@app.post("/api/score")
def score(req: ScoreRequest):
    """Score a new run (e.g. typed in or read from a sheet). Flags unknown and out-of-range values."""
    cols = state.bundle["feature_columns"]
    ranges = state.json("operating_ranges.json")
    unknown = [k for k in req.values if k not in cols]
    row = pd.Series(np.nan, index=cols, dtype=float)
    needs_review = []
    for k, v in req.values.items():
        if k in unknown:
            continue
        r = ranges.get(k)
        if r is not None and r["min"] is not None:
            span = (r["max"] - r["min"]) or 1.0
            if not (r["min"] - span <= v <= r["max"] + span):
                needs_review.append(k)
        row[k] = v
    out = _explain_row(row)
    out.update({"unknown_parameters": unknown, "needs_review": needs_review,
                "provided": len(req.values) - len(unknown)})
    return clean(out)
