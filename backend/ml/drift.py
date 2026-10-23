"""Drift: how far the later runs moved from the training runs, and whether a drift-aware training variant helps.

Report: the data's real date range, train-vs-test separability (adversarial AUC), and the sensors whose
distribution moved most (KS statistic, population stability index).

Experiment, each variant scored on the real validation window (used to choose) and the real later test window:
- baseline: the model as trained by the pipeline;
- interpolation: extra synthetic training runs, each interpolated between two real training runs of the same
  class that are next to each other in time. Synthetic rows are training-only; they are never scored;
- recency: newer training runs weighted more (linear 0.5 -> 1.5), so the model leans toward the recent process.
The variant with the best mean validation PR-AUC over several seeds is recommended; the test score is reported,
not used to choose. Real dates are never extended: SECOM ends in October 2008.
"""
import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

from backend.config import SEED
from backend.ml.features import Preprocessor
from backend.ml.metrics import pr_auc
from backend.ml.train import LGB_PARAMS, adversarial_drift, scale_pos_weight

SEEDS = (11, 22, 33, 44, 55)


def _psi(a: np.ndarray, b: np.ndarray, bins: int = 10) -> float:
    a, b = a[~np.isnan(a)], b[~np.isnan(b)]
    if len(a) < 20 or len(b) < 20:
        return float("nan")
    edges = np.unique(np.quantile(a, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0
    pa = np.histogram(a, edges)[0] / len(a) + 1e-4
    pb = np.histogram(np.clip(b, edges[0], edges[-1]), edges)[0] / len(b) + 1e-4
    return float(np.sum((pa - pb) * np.log(pa / pb)))


def report(s, ts: pd.Series) -> dict:
    pre = Preprocessor(impute=False).fit(s.X_train)
    rows = []
    for f in pre.kept_:
        a, b = s.X_train[f].to_numpy(float), s.X_test[f].to_numpy(float)
        aa, bb = a[~np.isnan(a)], b[~np.isnan(b)]
        if len(aa) < 20 or len(bb) < 20:
            continue
        rows.append({"feature": f, "ks": float(ks_2samp(aa, bb).statistic), "psi": _psi(a, b),
                     "train_mean": float(aa.mean()), "test_mean": float(bb.mean())})
    rows.sort(key=lambda r: -r["ks"])
    psi = np.array([r["psi"] for r in rows if r["psi"] == r["psi"]])
    adv = adversarial_drift(pd.concat([s.X_train, s.X_val]), s.X_test)
    return {
        "data_period": {"first_run": str(ts.min()), "last_run": str(ts.max()),
                        "train": [str(s.t_train.min()), str(s.t_train.max())],
                        "val": [str(s.t_val.min()), str(s.t_val.max())],
                        "test": [str(s.t_test.min()), str(s.t_test.max())]},
        "adversarial": adv,
        "sensors_checked": len(rows),
        "sensors_shifted_psi_gt_0_25": int((psi > 0.25).sum()),
        "most_shifted": [{k: round(v, 4) if isinstance(v, float) else v for k, v in r.items()} for r in rows[:12]],
    }


def _interpolate(X: pd.DataFrame, y: pd.Series, rng, per_row: float = 1.0) -> tuple[pd.DataFrame, pd.Series]:
    """Synthetic runs between consecutive (in time) training runs of the same class. NaN stays NaN."""
    new_x, new_y = [], []
    for cls in (0, 1):
        idx = np.where(y.to_numpy() == cls)[0]
        if len(idx) < 2:
            continue
        a = X.iloc[idx[:-1]].to_numpy(float)
        b = X.iloc[idx[1:]].to_numpy(float)
        n = int(len(a) * per_row)
        pick = rng.integers(0, len(a), n)
        u = rng.random((n, 1))
        new_x.append(a[pick] + u * (b[pick] - a[pick]))
        new_y.append(np.full(n, cls))
    Xs = pd.DataFrame(np.vstack(new_x), columns=X.columns)
    return pd.concat([X, Xs], ignore_index=True), pd.concat([y.reset_index(drop=True), pd.Series(np.concatenate(new_y))], ignore_index=True)


def _fit_score(X_tr, y_tr, s, n_estimators, impute, seed, weight=None) -> tuple[float, float]:
    pre = Preprocessor(impute=impute).fit(X_tr)
    params = dict(LGB_PARAMS, random_state=seed, scale_pos_weight=scale_pos_weight(y_tr), n_estimators=n_estimators, n_jobs=4)
    m = lgb.LGBMClassifier(**params).fit(pre.transform(X_tr), y_tr, sample_weight=weight)
    return (pr_auc(s.y_val, m.predict_proba(pre.transform(s.X_val))[:, 1]),
            pr_auc(s.y_test, m.predict_proba(pre.transform(s.X_test))[:, 1]))


def experiment(s, n_estimators: int, impute: bool) -> dict:
    variants = {}
    for name in ("baseline", "interpolation", "recency"):
        val, test = [], []
        for seed in SEEDS:
            rng = np.random.default_rng(seed)
            X_tr, y_tr, w = s.X_train, s.y_train, None
            if name == "interpolation":
                X_tr, y_tr = _interpolate(s.X_train, s.y_train, rng)
            if name == "recency":
                w = np.linspace(0.5, 1.5, len(s.X_train))
            v, t = _fit_score(X_tr, y_tr, s, n_estimators, impute, seed, w)
            val.append(v)
            test.append(t)
        variants[name] = {"val_pr_auc": round(float(np.mean(val)), 4), "val_sd": round(float(np.std(val)), 4),
                          "test_pr_auc": round(float(np.mean(test)), 4), "test_sd": round(float(np.std(test)), 4)}
    best = max(variants, key=lambda k: variants[k]["val_pr_auc"])
    base = variants["baseline"]
    gain = variants[best]["val_pr_auc"] - base["val_pr_auc"]
    keep = best != "baseline" and gain > base["val_sd"]
    return {
        "variants": variants,
        "chosen_on": "mean validation PR-AUC over 5 seeds (the test window is reported, not used to choose)",
        "best_on_validation": best,
        "decision": (f"Use {best}: validation PR-AUC {variants[best]['val_pr_auc']} vs {base['val_pr_auc']} for the baseline."
                     if keep else
                     f"Keep the baseline: {best if best != 'baseline' else 'no variant'} did not beat it on validation by more than "
                     f"the seed-to-seed spread ({base['val_sd']})."),
        "keep_variant": keep,
        "note": "Interpolated runs are synthetic and used for training only. Scores are on real held-out runs.",
    }


def build(s, ts: pd.Series, n_estimators: int, impute: bool) -> dict:
    return {"report": report(s, ts), "experiment": experiment(s, n_estimators, impute), "seed": SEED}
