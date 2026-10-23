"""End-to-end batch run: train, rank, windows, pilots, timeline, validation; write artifacts/.

    python -m backend.ml.pipeline            # full run
    python -m backend.ml.pipeline --quick    # fewer bootstraps, for smoke tests
"""
import argparse
import json
import math
import pickle
import time

import numpy as np
import pandas as pd

from backend.config import ARTIFACTS_DIR, BOSCH_DIR, DATA_DIR, N_BOOTSTRAP, TOP_K
from backend.ml import cost, drift, pilot
from backend.ml.bosch import run_bosch
from backend.ml.features import data_quality
from backend.ml.load import load_secom, profile, time_split
from backend.ml.planted import run_ai4i_check, run_planted_benchmark
from backend.ml.rank import build_ranking
from backend.ml.safe_window import build_safe_windows, operating_range
from backend.ml.timeline import build_timeline, parameter_drift
from backend.ml.train import predict, rolling_origin, train_all

N_NEIGHBOUR_FEATURES = 30


def clean(obj):
    """Make an object JSON-safe: numpy scalars to Python, NaN/inf to None."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        v = float(obj)
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def write_json(name: str, obj) -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS_DIR / name).write_text(json.dumps(clean(obj), indent=2))


def log(msg: str, t0: float) -> None:
    print(f"[{time.time() - t0:6.1f}s] {msg}", flush=True)


def run(quick: bool = False) -> dict:
    t0 = time.time()
    B = 10 if quick else N_BOOTSTRAP
    X, y, ts = load_secom()
    s = time_split(X, y, ts)
    X_tv, y_tv = pd.concat([s.X_train, s.X_val]), pd.concat([s.y_train, s.y_val])
    ts_tv = pd.concat([s.t_train, s.t_val])
    log(f"loaded SECOM {X.shape}, fails={int(y.sum())}", t0)

    trained = train_all(s)
    model, report = trained["model"], trained["report"]
    report["rolling_origin"] = rolling_origin(X, y)
    report["data_profile"] = profile(X, y, ts)
    write_json("metrics.json", report)
    write_json("data_quality.json", data_quality(s))
    write_json("drift.json", drift.build(s, ts, report["model_selection"]["n_estimators"],
                                         report["model_selection"]["chosen_imputation"] != "native_nan"))
    log("drift report and drift-aware variants written", t0)
    log(f"trained: test PR-AUC lgbm={report['lightgbm']['test']['pr_auc']['point']:.3f} "
        f"logit={report['logistic_baseline']['test']['pr_auc']['point']:.3f}", t0)

    ranking = build_ranking(X_tv, y_tv, report["model_selection"]["n_estimators"],
                            impute=not report["model_selection"]["chosen_imputation"] == "native_nan", B=B)
    table = ranking.pop("_table")
    write_json("ranking.json", ranking)
    log(f"ranking: {ranking['n_stable']} stable of top-{TOP_K}", t0)

    windows = build_safe_windows(table, X_tv, y_tv, s.X_test, s.y_test, model, predict, TOP_K)
    write_json("safe_windows.json", windows)
    pilots = [pilot.plan_for_window(w["feature"], w) for w in windows["windows"] if "fit" in w]
    write_json("pilots.json", {"defaults": pilot.DEFAULTS, "plans": pilots})

    ranked = list(table.sort_values("mean_rank").index)
    write_json("operating_ranges.json", {
        f: {"p5_p95": list(operating_range(X_tv[f])), "min": float(X_tv[f].min()),
            "max": float(X_tv[f].max()), "median": float(X_tv[f].median())}
        for f in model.pre.kept_
    })

    recommended = [w for w in windows["windows"] if w.get("status", "").startswith("recommended")]
    best = max(recommended, key=lambda w: w["reduction_if_in_window"]["mid"], default=None)
    if best:
        red = best["reduction_if_in_window"]
        savings = cost.monthly_savings(cost.CostInputs(
            baseline_fail_rate=windows["baseline_fail_rate"],
            reduction_low=red["low"], reduction_mid=red["mid"], reduction_high=red["high"]))
        savings["based_on"] = best["feature"]
    else:
        savings = {"label": "model estimate", "note": "no stable recommendation to price"}
    write_json("savings_default.json", savings)
    log("safe windows, pilots, savings written", t0)

    timeline = build_timeline(X, y, ts, n_estimators=report["model_selection"]["n_estimators"])
    timeline["parameter_drift"] = parameter_drift(X, ts, ranked[:5])
    write_json("timeline.json", timeline)
    log("timeline written", t0)

    planted = run_planted_benchmark(X, n_scenarios=2 if quick else 5, B=10 if quick else 30)
    write_json("planted_benchmark.json", planted)
    log(f"planted benchmark: {planted['summary']}", t0)

    ai4i_path = DATA_DIR / "ai4i" / "ai4i2020.csv"
    if ai4i_path.exists():
        write_json("ai4i_check.json", run_ai4i_check(ai4i_path, B=10 if quick else 30))
        log("AI4I check written", t0)

    if (BOSCH_DIR / "numeric_sample.parquet").exists():
        write_json("bosch.json", run_bosch(B=3 if quick else 20))
        log("Bosch station analysis written", t0)
    else:
        log("Bosch sample missing; run `python -m backend.ml.bosch` to build it", t0)

    with open(ARTIFACTS_DIR / "model.pkl", "wb") as f:
        pickle.dump({
            "model": model,
            "baseline": trained["baseline"],
            "train_index": list(X_tv.index),
            "neighbour_features": ranked[:N_NEIGHBOUR_FEATURES],
            "importance": table["mean_abs_shap"].to_dict(),
            "feature_columns": list(X.columns),
        }, f)
    from backend.ml import replay
    write_json("replay.json", replay.build(X, y, ts, predict(model, X.reindex(columns=list(X.columns))),
                                           report["lightgbm"]["test"]["threshold"], windows["windows"]))
    write_json("config.json", {
        "quick": quick, "n_bootstrap": B, "top_k": TOP_K,
        "created": pd.Timestamp.now().isoformat(), "seconds": time.time() - t0,
        "train_end": str(ts_tv.max()),
    })
    log(f"done -> {ARTIFACTS_DIR}", t0)
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    run(quick=ap.parse_args().quick)
