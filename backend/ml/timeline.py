"""Root-cause timeline: refit the model on rolling time windows and track which parameters
drive failures in each period. Answers *when* a driver took over, and flags drift."""
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from backend.ml.rank import shap_importance
from backend.ml.train import fit_lgbm


def rolling_windows(n: int, size: int, step: int) -> list[tuple[int, int]]:
    starts = range(0, max(n - size, 0) + 1, step)
    wins = [(s, s + size) for s in starts]
    if wins and wins[-1][1] < n:
        wins.append((n - size, n))
    return wins


def build_timeline(X: pd.DataFrame, y: pd.Series, ts: pd.Series, size=400, step=150,
                   n_estimators=100, impute=False, top_n=8, min_fails=8) -> dict:
    windows, imps = [], []
    for a, b in rolling_windows(len(X), size, step):
        Xw, yw = X.iloc[a:b], y.iloc[a:b]
        info = {"start": str(ts.iloc[a]), "end": str(ts.iloc[b - 1]), "n": int(b - a),
                "fails": int(yw.sum()), "fail_rate": float(yw.mean())}
        if yw.sum() < min_fails:
            info["status"] = "too few failures"
            windows.append(info)
            imps.append(None)
            continue
        t = fit_lgbm(Xw, yw, Xw, yw, impute=impute, n_estimators=n_estimators)
        imp = shap_importance(t, Xw)
        imp = imp / imp.sum() if imp.sum() > 0 else imp
        info["status"] = "ok"
        info["top"] = [{"feature": f, "share": float(v)} for f, v in imp.head(5).items()]
        windows.append(info)
        imps.append(imp)

    valid = [i for i in imps if i is not None]
    if not valid:
        return {"windows": windows, "features": [], "matrix": [], "drift": []}
    M = pd.concat(valid, axis=1).fillna(0.0)
    overall = M.mean(axis=1).sort_values(ascending=False)
    feats = list(overall.head(top_n).index)

    # rank agreement between consecutive valid windows; low = drivers changed
    drift = []
    valid_idx = [i for i, v in enumerate(imps) if v is not None]
    for i, j in zip(valid_idx, valid_idx[1:]):
        common = M.index
        rho = spearmanr(imps[i].reindex(common).fillna(0), imps[j].reindex(common).fillna(0)).statistic
        top_i = set(imps[i].head(5).index)
        top_j = set(imps[j].head(5).index)
        drift.append({"from": windows[i]["end"], "to": windows[j]["end"],
                      "rank_agreement": float(rho), "top5_overlap": len(top_i & top_j),
                      "entered_top5": sorted(top_j - top_i), "left_top5": sorted(top_i - top_j)})

    # dominant driver per window, for a one-line story
    story = []
    for w in windows:
        if w.get("status") == "ok":
            lead = w["top"][0]
            story.append(f"{w['start'][:10]} to {w['end'][:10]}: {lead['feature']} leads "
                         f"({lead['share']:.0%} of attribution), fail rate {w['fail_rate']:.1%}")

    matrix = []
    for k, w in enumerate(windows):
        row = {"window": k, "start": w["start"], "end": w["end"]}
        imp = imps[k]
        for f in feats:
            row[f] = None if imp is None else float(imp.get(f, 0.0))
        matrix.append(row)

    return {
        "window_size": size, "step": step,
        "windows": windows, "features": feats, "matrix": matrix,
        "drift": drift, "story": story,
        "label": "Per-window attribution share. Association, not proven cause.",
    }


def parameter_drift(X: pd.DataFrame, ts: pd.Series, features: list[str], freq="W") -> dict:
    """Weekly median of each parameter, to show whether a driver's operating point moved."""
    df = X[features].copy()
    df["period"] = ts.dt.to_period(freq).astype(str).values
    med = df.groupby("period")[features].median()
    return {"period": list(med.index),
            "series": {f: [None if np.isnan(v) else float(v) for v in med[f]] for f in features}}
