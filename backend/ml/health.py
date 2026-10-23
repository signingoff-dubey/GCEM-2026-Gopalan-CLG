"""Sensor health: is each sensor still giving usable readings?

A sensor's recent readings are compared with how it behaved on the training window. Five checks, all on the
sensor's own values, so they work on anonymised data:

- silent: (almost) no readings recently although it reported during training
- stuck: the same value repeated for a long run while it varied during training
- spikes: jumps between consecutive readings far larger than its normal spread
- out of range: many readings outside the training 1st..99th percentile (2% expected)
- drift: the distribution moved (population stability index) or the median shifted by several spreads

Each check gives ok / watch / bad, and the sensor takes its worst. Nothing is dropped automatically: a bad
sensor is flagged so a person checks it, and a capture that uses it says so.
"""
import numpy as np
import pandas as pd

# thresholds (spread = training interquartile range, or sd when that is 0)
STUCK_RUN = 30             # identical consecutive readings
SPIKE_IQR = 10.0           # one step bigger than 10 spreads
OUT_OF_RANGE = (0.10, 0.25)    # share outside training p1..p99: watch / bad (2% expected)
MISSING_JUMP = (0.20, 0.50)    # rise in missing share: watch / bad
MEDIAN_SHIFT = (1.5, 3.0)      # |recent median - training median| / spread: watch / bad
PSI_LIMITS = (0.10, 0.25)      # population stability index: watch / drift
RANK = {"ok": 0, "watch": 1, "bad": 2}


def psi(ref: np.ndarray, new: np.ndarray, bins: int = 10) -> float:
    """sum (p_ref - p_new) * ln(p_ref / p_new) over the reference's quantile bins."""
    if len(ref) < 20 or len(new) < 20:
        return float("nan")
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0
    pa = np.histogram(ref, edges)[0] / len(ref) + 1e-4
    pb = np.histogram(np.clip(new, edges[0], edges[-1]), edges)[0] / len(new) + 1e-4
    return float(np.sum((pa - pb) * np.log(pa / pb)))


def longest_repeat(values: np.ndarray) -> tuple[int, float | None]:
    """Longest run of identical consecutive readings, and the repeated value."""
    if len(values) == 0:
        return 0, None
    best, best_v, cur = 1, values[0], 1
    for i in range(1, len(values)):
        cur = cur + 1 if values[i] == values[i - 1] else 1
        if cur > best:
            best, best_v = cur, values[i]
    return best, float(best_v)


def _grade(value: float, limits: tuple[float, float]) -> str:
    if value is None or np.isnan(value):
        return "ok"
    return "bad" if value >= limits[1] else "watch" if value >= limits[0] else "ok"


def check_sensor(ref: pd.Series, recent: pd.Series) -> dict:
    """Health of one sensor: its training readings vs its recent readings (both in time order)."""
    r = ref.dropna().to_numpy(float)
    x = recent.dropna().to_numpy(float)
    out = {"recent_runs": int(len(recent)), "recent_readings": int(len(x)),
           "missing_train": round(float(ref.isna().mean()), 4), "missing_recent": round(float(recent.isna().mean()), 4)}
    if len(r) < 20 or np.unique(r).size <= 1:
        return {**out, "status": "no signal", "checks": {}, "reasons": ["constant or almost never reported in training"]}
    q1, q25, q50, q75, q99 = np.quantile(r, [0.01, 0.25, 0.5, 0.75, 0.99])
    spread = float(q75 - q25) or float(np.std(r)) or 1.0
    checks, reasons = {}, []

    rise = out["missing_recent"] - out["missing_train"]
    silent = len(x) == 0
    checks["silent"] = "bad" if silent else _grade(rise, MISSING_JUMP)
    if silent:
        reasons.append("no readings in the recent runs")
    elif checks["silent"] != "ok":
        reasons.append(f"missing in {out['missing_recent']:.0%} of recent runs (training {out['missing_train']:.0%})")
    if silent:
        return {**out, "status": "bad", "checks": checks, "reasons": reasons}

    run, value = longest_repeat(x)
    checks["stuck"] = "bad" if run >= STUCK_RUN else "watch" if run >= STUCK_RUN // 2 else "ok"
    if checks["stuck"] != "ok":
        reasons.append(f"stuck at {value:.4g} for {run} readings in a row")

    step = float(np.max(np.abs(np.diff(x))) / spread) if len(x) > 1 else 0.0
    checks["spikes"] = "watch" if step >= SPIKE_IQR else "ok"
    if checks["spikes"] != "ok":
        reasons.append(f"a jump of {step:.0f} spreads between two readings")

    oor = float(np.mean((x < q1) | (x > q99)))
    checks["out_of_range"] = _grade(oor, OUT_OF_RANGE)
    if checks["out_of_range"] != "ok":
        reasons.append(f"{oor:.0%} of readings outside the training range (2% expected)")

    shift = abs(float(np.median(x)) - float(q50)) / spread
    p = psi(r, x)
    # drift alone is a process change, not a broken sensor: it can only reach "watch"
    checks["drift"] = "watch" if _grade(shift, MEDIAN_SHIFT) != "ok" or (not np.isnan(p) and p >= PSI_LIMITS[1]) else "ok"
    if checks["drift"] != "ok":
        reasons.append(f"distribution moved (PSI {p:.2f}, median shifted {shift:.1f} spreads)")

    status = max(checks.values(), key=RANK.get)
    return {**out, "status": status, "checks": checks, "reasons": reasons,
            "psi": None if np.isnan(p) else round(p, 3), "median_shift_spreads": round(shift, 2),
            "out_of_range_share": round(oor, 3), "longest_repeat": run,
            "train_range": [round(float(q1), 6), round(float(q99), 6)],
            "recent_median": round(float(np.median(x)), 6), "train_median": round(float(q50), 6)}


def report(X: pd.DataFrame, n_train: int, recent: int = 200, windows: int = 12) -> dict:
    """Every sensor: training rows [0, n_train) vs the last `recent` runs. Rows must be in time order.
    Also a small per-window trace (missing share, median in spreads) for sparklines."""
    ref = X.iloc[:n_train]
    tail = X.iloc[-recent:]
    edges = np.linspace(0, len(X), windows + 1).astype(int)
    sensors = []
    for c in X.columns:
        h = check_sensor(ref[c], tail[c])
        r = ref[c].dropna()
        med = float(r.median()) if len(r) else 0.0
        q = r.quantile([0.25, 0.75]) if len(r) else pd.Series([0.0, 0.0])
        spread = float(q.iloc[1] - q.iloc[0]) or float(r.std() or 1.0)
        trace = []
        for a, b in zip(edges[:-1], edges[1:]):
            w = X[c].iloc[a:b]
            obs = w.dropna()
            trace.append({"missing": round(float(w.isna().mean()), 3),
                          "median_z": None if obs.empty else round((float(obs.median()) - med) / spread, 3)})
        sensors.append({"sensor": c, **h, "trace": trace})
    counts = {s: sum(1 for x in sensors if x["status"] == s) for s in ("ok", "watch", "bad", "no signal")}
    order = {"bad": 0, "watch": 1, "ok": 2, "no signal": 3}
    sensors.sort(key=lambda s: (order[s["status"]], -len(s.get("reasons", []))))
    return {
        "counts": counts,
        "compared": f"last {recent} runs vs the training window ({n_train} runs)",
        "thresholds": {"stuck_run": STUCK_RUN, "spike_spreads": SPIKE_IQR, "out_of_range_watch_bad": OUT_OF_RANGE,
                       "missing_rise_watch_bad": MISSING_JUMP, "median_shift_watch_bad": MEDIAN_SHIFT,
                       "psi_watch_drift": PSI_LIMITS},
        "rule": "A bad sensor is flagged for a person to check; RootLens never drops it on its own. "
                "Drift alone is shown as 'watch': the process moved, the sensor may be fine.",
        "sensors": sensors,
    }
