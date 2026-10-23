"""Replay of the SECOM runs onto a recent calendar window, so the dashboard calendar and the assistant can talk
about "a day", "last month" or "this month versus last month" the way a plant would.

Every SECOM run keeps its own measurements, pass/fail label and model risk; only its time stamp is moved: the
2008 recording period (19 Jul to 17 Oct 2008) is stretched linearly onto REPLAY_START .. REPLAY_END, keeping the
order and the gaps between runs. Each replayed run carries its original index and 2008 time stamp, and every
screen and answer says "replayed from SECOM 2008 runs". Nothing outside the replay window exists: a question about
2025 gets "no data".
"""
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

REPLAY_START = datetime(2026, 9, 1, 6, 0)
REPLAY_END = datetime(2026, 10, 23, 18, 0)
LABEL = ("Replayed from SECOM 2008 runs onto Sep-Oct 2026 for the demo; measurements and outcomes are the real SECOM "
         "ones. Model risk is model-estimated (in-sample for runs the model was trained on).")


def build(X: pd.DataFrame, y: pd.Series, ts: pd.Series, risk: np.ndarray, threshold: float, windows: list[dict]) -> dict:
    t0, t1 = ts.min(), ts.max()
    span = (t1 - t0).total_seconds() or 1.0
    target = (REPLAY_END - REPLAY_START).total_seconds()
    rec = [w for w in windows if w.get("recommended")]
    rows = []
    for k in range(len(X)):
        frac = (ts.iloc[k] - t0).total_seconds() / span
        at = REPLAY_START + timedelta(seconds=frac * target)
        inside = {w["feature"]: (None if pd.isna(X[w["feature"]].iloc[k]) else
                                 bool(w["window"][0] <= X[w["feature"]].iloc[k] <= w["window"][1])) for w in rec}
        rows.append({"at": at.isoformat(timespec="minutes"), "run": int(k), "recorded": str(ts.iloc[k]),
                     "fail": int(y.iloc[k]), "risk": round(float(risk[k]), 4),
                     "high_risk": bool(risk[k] >= max(2 * threshold, 0.3)), "in_window": inside})
    return {"label": LABEL, "start": REPLAY_START.isoformat(), "end": REPLAY_END.isoformat(),
            "source_period": [str(t0), str(t1)], "threshold": threshold,
            "recommended_windows": [{"feature": w["feature"], "window": w["window"]} for w in rec], "runs": rows}


# ---------- questions over the replay ----------
def _frame(replay: dict) -> pd.DataFrame:
    df = pd.DataFrame(replay["runs"])
    df["at"] = pd.to_datetime(df["at"])
    df["day"] = df["at"].dt.date.astype(str)
    df["month"] = df["at"].dt.strftime("%Y-%m")
    for f in [w["feature"] for w in replay["recommended_windows"]]:
        df[f"in_{f}"] = df["in_window"].map(lambda d, f=f: d.get(f))
    return df


def _stats(df: pd.DataFrame, replay: dict) -> dict:
    if df.empty:
        return {"runs": 0, "note": "no runs in this period (the replay covers 1 Sep to 23 Oct 2026)"}
    out = {"runs": int(len(df)), "fails": int(df["fail"].sum()), "passes": int((1 - df["fail"]).sum()),
           "fail_rate": round(float(df["fail"].mean()), 4), "mean_model_risk": round(float(df["risk"].mean()), 4),
           "high_risk_runs": int(df["high_risk"].sum()),
           "first_run": df["at"].min().isoformat(timespec="minutes"), "last_run": df["at"].max().isoformat(timespec="minutes")}
    for w in replay["recommended_windows"]:
        col = df[f"in_{w['feature']}"].dropna()
        if len(col):
            inside = df.loc[col.index][col.astype(bool)]
            outside = df.loc[col.index][~col.astype(bool)]
            out[f"{w['feature']}_window"] = {
                "window": w["window"], "runs_inside": int(len(inside)), "runs_outside": int(len(outside)),
                "fail_rate_inside": round(float(inside["fail"].mean()), 4) if len(inside) else None,
                "fail_rate_outside": round(float(outside["fail"].mean()), 4) if len(outside) else None}
    return out


def calendar(replay: dict) -> list[dict]:
    df = _frame(replay)
    return [{"date": d, "runs": int(len(g)), "fails": int(g["fail"].sum()), "high_risk": int(g["high_risk"].sum())}
            for d, g in df.groupby("day")]


def period(replay: dict, start: str, end: str | None = None) -> dict:
    """Stats for one day (YYYY-MM-DD), a month (YYYY-MM) or a range start..end (inclusive dates)."""
    df = _frame(replay)
    if end is None and len(start) == 7:
        sel, name = df[df["month"] == start], start
    else:
        e = end or start
        sel, name = df[(df["day"] >= start) & (df["day"] <= e)], start if e == start else f"{start} to {e}"
    s = _stats(sel, replay)
    s["period"] = name
    if len(sel):
        worst = sel.sort_values("risk", ascending=False).head(3)
        s["highest_risk_runs"] = [{"at": r.at.isoformat(timespec="minutes"), "run": int(r.run), "risk": float(r.risk),
                                   "failed": bool(r.fail), "recorded_2008": r.recorded} for r in worst.itertuples()]
        s["failed_runs"] = [{"at": r.at.isoformat(timespec="minutes"), "run": int(r.run)} for r in sel[sel["fail"] == 1].head(10).itertuples()]
    s["label"] = replay["label"]
    return s


def compare(replay: dict, a: str, b: str) -> dict:
    pa, pb = period(replay, a), period(replay, b)
    diff = {}
    if pa.get("runs") and pb.get("runs"):
        diff = {"fail_rate_change": round(pb["fail_rate"] - pa["fail_rate"], 4),
                "runs_change": pb["runs"] - pa["runs"], "fails_change": pb["fails"] - pa["fails"]}
    return {"a": pa, "b": pb, "b_minus_a": diff, "label": replay["label"]}


def resolve(replay: dict, phrase: str, today: date | None = None) -> tuple[str, str | None]:
    """'today', 'yesterday', 'this month', 'last month', 'this week', 'last week', 'last year' -> (start, end)."""
    t = today or min(date.today(), datetime.fromisoformat(replay["end"]).date())
    p = phrase.strip().lower()
    if p in ("today",):
        return t.isoformat(), None
    if p == "yesterday":
        return (t - timedelta(days=1)).isoformat(), None
    if p in ("this month", "current month"):
        return t.strftime("%Y-%m"), None
    if p in ("last month", "previous month"):
        return (t.replace(day=1) - timedelta(days=1)).strftime("%Y-%m"), None
    if p in ("this week",):
        return (t - timedelta(days=t.weekday())).isoformat(), t.isoformat()
    if p in ("last week", "previous week"):
        s = t - timedelta(days=t.weekday() + 7)
        return s.isoformat(), (s + timedelta(days=6)).isoformat()
    if p in ("last year", "previous year"):
        return f"{t.year - 1}-01-01", f"{t.year - 1}-12-31"
    return phrase, None
