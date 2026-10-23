"""Sensor health and labelled exports of the SECOM data.

SECOM is published anonymised: 590 numbered columns, a pass/fail label and a time stamp, no sensor names,
units or product. These exports add everything RootLens knows about each column (position, what cleaning did,
correlation group, ranking, safe window, health) and everything about each run (split, outcome, model risk,
replayed date). Units and descriptions are left as "not published": they are not invented.
"""
import csv
import io
from functools import lru_cache

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from backend.api.state import ArtifactMissing, state
from backend.config import CORR_GROUP_THRESHOLD
from backend.ml import health
from backend.ml.features import Preprocessor, correlation_groups

router = APIRouter(prefix="/api", tags=["export"])

NOT_PUBLISHED = "not published (SECOM is anonymised)"
RECENT_RUNS = 200


@lru_cache(maxsize=1)
def health_report() -> dict:
    X, _, _, s = state.data
    return health.report(X, n_train=len(s.X_train), recent=RECENT_RUNS)


def health_of(sensor: str) -> dict | None:
    return next((h for h in health_report()["sensors"] if h["sensor"] == sensor), None)


@lru_cache(maxsize=1)
def _sensor_table() -> list[dict]:
    X, _, _, s = state.data
    pre = Preprocessor(impute=True).fit(s.X_train)
    groups = correlation_groups(pre.transform(s.X_train)[pre.kept_], CORR_GROUP_THRESHOLD)
    dropped = {c: "dropped: constant" for c in pre.dropped_["constant"]}
    dropped.update({c: "dropped: missing in >60% of training runs" for c in pre.dropped_["too_missing"]})
    try:
        ranked = {f["feature"]: f for f in state.json("ranking.json")["features"]}
    except ArtifactMissing:
        ranked = {}
    try:
        windows = {w["feature"]: w for w in state.json("safe_windows.json")["windows"]}
    except ArtifactMissing:
        windows = {}
    hmap = {h["sensor"]: h for h in health_report()["sensors"]}
    tr = s.X_train
    rows = []
    for pos, c in enumerate(X.columns):
        col = tr[c].dropna()
        r, w, h = ranked.get(c, {}), windows.get(c, {}), hmap.get(c, {})
        q = col.quantile([0.01, 0.99]) if len(col) else None
        rows.append({
            "sensor": c,
            "column_position": pos,
            "unit": NOT_PUBLISHED,
            "description": NOT_PUBLISHED,
            "in_model": dropped.get(c, "kept" + (" + was-missing flag" if c in pre.flagged_ else "")),
            "missing_share_train": round(float(tr[c].isna().mean()), 4),
            "train_min": _r(col.min()) if len(col) else None,
            "train_p1": _r(q.iloc[0]) if q is not None else None,
            "train_mean": _r(col.mean()) if len(col) else None,
            "train_p99": _r(q.iloc[1]) if q is not None else None,
            "train_max": _r(col.max()) if len(col) else None,
            "correlation_group": groups.get(c, ""),
            "mean_rank": _r(r.get("mean_rank")),
            "rank_sd": _r(r.get("rank_std")),
            "top10_share": _r(r.get("top_k_freq")),
            "stable_driver": "yes" if r.get("stable") else ("no" if r else ""),
            "safe_window_low": _r((w.get("window") or [None, None])[0]),
            "safe_window_high": _r((w.get("window") or [None, None])[1]),
            "window_status": w.get("status", ""),
            "health": h.get("status", ""),
            "health_reasons": "; ".join(h.get("reasons", [])),
        })
    return rows


def _r(v, n=6):
    try:
        return None if v is None else round(float(v), n)
    except (TypeError, ValueError):
        return None


def _csv(rows: list[list]) -> str:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue()


@router.get("/sensors/health")
def sensors_health(status: str | None = None, limit: int = 600):
    """Every sensor's health, worst first. status: ok | watch | bad | no signal."""
    rep = health_report()
    sensors = [s for s in rep["sensors"] if status is None or s["status"] == status][:limit]
    return {**rep, "sensors": sensors}


@router.get("/sensors/health/{sensor}")
def sensor_health(sensor: str):
    h = health_of(sensor)
    if h is None:
        raise HTTPException(404, f"no sensor {sensor}")
    return h


@router.get("/export/sensors.csv")
def export_sensors():
    """Data dictionary: one row per SECOM column with everything RootLens knows about it."""
    rows = _sensor_table()
    head = list(rows[0].keys())
    body = _csv([head] + [[r[k] for k in head] for r in rows])
    return Response(body, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=rootlens_secom_sensors.csv"})


@router.get("/export/runs.csv")
def export_runs():
    """The SECOM data, labelled. Top rows describe each sensor column (group, stable, health ...); then one row per
    run with its id, original and replayed time, split, pass/fail and model risk, followed by the readings."""
    X, y, ts, s = state.data
    table = {r["sensor"]: r for r in _sensor_table()}
    try:
        replay = {r["run"]: r for r in state.json("replay.json")["runs"]}
    except ArtifactMissing:
        replay = {}
    n_tr, n_va = len(s.X_train), len(s.X_val)
    lead = ["row_type", "run_id", "run_index", "recorded_2008", "replayed_at_2026", "split", "result", "model_risk", "high_risk"]
    sensors = list(X.columns)
    meta_fields = [("unit", "unit"), ("in_model", "in_model"), ("correlation_group", "correlation_group"),
                   ("stable_driver", "stable_driver"), ("safe_window", None), ("health", "health")]
    out = [lead + sensors]
    for label, key in meta_fields:
        cells = []
        for c in sensors:
            t = table[c]
            if key is None:
                lo, hi = t["safe_window_low"], t["safe_window_high"]
                cells.append(f"{lo}..{hi}" if lo is not None else "")
            else:
                cells.append(t[key])
        out.append(["sensor_info", label, "", "", "", "", "", "", ""] + cells)
    for i in range(len(X)):
        rp = replay.get(i, {})
        split = "train" if i < n_tr else "validation" if i < n_tr + n_va else "test"
        vals = ["" if v != v else _r(v) for v in X.iloc[i].to_numpy()]
        out.append(["run", f"R-{i:04d}", i, str(ts.iloc[i]), rp.get("at", ""), split, "fail" if y.iloc[i] else "pass",
                    rp.get("risk", ""), "yes" if rp.get("high_risk") else "no"] + vals)
    return Response(_csv(out), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=rootlens_secom_labelled.csv"})
