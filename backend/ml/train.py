"""Train LightGBM + logistic baseline on a time split and report imbalance-aware metrics."""
from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from backend.config import SEED
from backend.ml import cost
from backend.ml.features import Preprocessor
from backend.ml.load import Split
from backend.ml.metrics import cost_threshold, evaluate, pr_auc

LGB_PARAMS = dict(
    n_estimators=1000,
    learning_rate=0.03,
    num_leaves=7,
    max_depth=3,
    min_child_samples=15,
    colsample_bytree=0.5,
    subsample=0.8,
    subsample_freq=1,
    reg_lambda=1.0,
    verbose=-1,
)


@dataclass
class Trained:
    model: object
    pre: Preprocessor
    threshold: float
    best_iter: int


def scale_pos_weight(y) -> float:
    y = np.asarray(y)
    return float((y == 0).sum() / max((y == 1).sum(), 1))


def fit_lgbm(X_tr, y_tr, X_va, y_va, impute=True, n_estimators=None, seed=SEED,
             n_jobs=None) -> Trained:
    pre = Preprocessor(impute=impute).fit(X_tr)
    A, B = pre.transform(X_tr), pre.transform(X_va)
    params = dict(LGB_PARAMS, random_state=seed, scale_pos_weight=scale_pos_weight(y_tr))
    if n_jobs is not None:
        params["n_jobs"] = n_jobs
    if n_estimators is not None:
        params["n_estimators"] = n_estimators
        model = lgb.LGBMClassifier(**params).fit(A, y_tr)
        best = n_estimators
    else:
        model = lgb.LGBMClassifier(**params).fit(
            A, y_tr, eval_set=[(B, y_va)], eval_metric="average_precision",
            callbacks=[lgb.early_stopping(100, verbose=False)],
        )
        best = int(model.best_iteration_ or params["n_estimators"])
    p_va = model.predict_proba(B)[:, 1]
    thr = cost_threshold(y_va, p_va, cost.COST_FN, cost.COST_FP)
    return Trained(model, pre, thr, best)


def fit_logistic(X_tr, y_tr, X_va, y_va) -> Trained:
    pre = Preprocessor(impute=True).fit(X_tr)
    A, B = pre.transform(X_tr), pre.transform(X_va)
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(C=0.05, penalty="l2", class_weight="balanced", max_iter=5000),
    ).fit(A, y_tr)
    p_va = model.predict_proba(B)[:, 1]
    thr = cost_threshold(y_va, p_va, cost.COST_FN, cost.COST_FP)
    return Trained(model, pre, thr, 0)


def predict(t: Trained, X: pd.DataFrame) -> np.ndarray:
    return t.model.predict_proba(t.pre.transform(X))[:, 1]


def rolling_origin(X, y, n_folds=4, min_train_frac=0.4) -> dict:
    """Expanding-window backtest: train on [0, k), test on the next block.
    Steadier than a single 9-positive test window. Last 15 % of each train block is
    used for early stopping and threshold selection."""
    n = len(X)
    edges = np.linspace(int(n * min_train_frac), n, n_folds + 1).astype(int)
    folds = []
    for i in range(n_folds):
        tr_end, te_end = edges[i], edges[i + 1]
        va_start = int(tr_end * 0.85)
        Xtr, ytr = X.iloc[:va_start], y.iloc[:va_start]
        Xva, yva = X.iloc[va_start:tr_end], y.iloc[va_start:tr_end]
        Xte, yte = X.iloc[tr_end:te_end], y.iloc[tr_end:te_end]
        row = {"train_end": int(tr_end), "test_n": int(len(yte)), "test_pos": int(yte.sum())}
        for name, fit in (("lightgbm", fit_lgbm), ("logistic", fit_logistic)):
            t = fit(Xtr, ytr, Xva, yva)
            row[f"{name}_pr_auc"] = pr_auc(yte, predict(t, Xte))
        row["prevalence"] = float(yte.mean())
        folds.append(row)
    df = pd.DataFrame(folds)
    return {
        "folds": folds,
        "mean": {c: float(df[c].mean()) for c in ("lightgbm_pr_auc", "logistic_pr_auc", "prevalence")},
    }


N_ESTIMATOR_GRID = (100, 300, 500)


def select_n_estimators(X, y, impute=True, n_folds=3) -> dict:
    """Pick tree count by expanding-window PR-AUC inside the given (train+val) data only.
    Early stopping on a ~17-positive validation window stops at iteration 1, so it is not used."""
    n = len(X)
    edges = np.linspace(int(n * 0.5), n, n_folds + 1).astype(int)
    scores = {}
    for k in N_ESTIMATOR_GRID:
        fold_scores = []
        for i in range(n_folds):
            a, b = edges[i], edges[i + 1]
            t = fit_lgbm(X.iloc[:a], y.iloc[:a], X.iloc[a:b], y.iloc[a:b], impute=impute, n_estimators=k)
            fold_scores.append(pr_auc(y.iloc[a:b], predict(t, X.iloc[a:b])))
        scores[k] = float(np.mean(fold_scores))
    return {"scores": scores, "best": max(scores, key=scores.get)}


def random_split_inflation(X, y, n_estimators, seed=SEED) -> float:
    """Shuffled 5-fold PR-AUC — the leaky number a random split would report. Shown for contrast only."""
    from sklearn.model_selection import StratifiedKFold
    scores = []
    for tr, te in StratifiedKFold(5, shuffle=True, random_state=seed).split(X, y):
        t = fit_lgbm(X.iloc[tr], y.iloc[tr], X.iloc[te], y.iloc[te], n_estimators=n_estimators)
        scores.append(pr_auc(y.iloc[te], predict(t, X.iloc[te])))
    return float(np.mean(scores))


def adversarial_drift(X_past, X_future, seed=SEED) -> dict:
    """Can a classifier tell earlier runs from later ones? AUC ~0.5 = same process, ~1 = drifted."""
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedKFold
    X = pd.concat([X_past, X_future])
    y = np.r_[np.zeros(len(X_past)), np.ones(len(X_future))]
    pre = Preprocessor(impute=False).fit(X)
    A = pre.transform(X)
    p = np.zeros(len(y))
    for tr, te in StratifiedKFold(5, shuffle=True, random_state=seed).split(A, y):
        m = lgb.LGBMClassifier(n_estimators=100, num_leaves=15, verbose=-1, random_state=seed)
        m.fit(A.iloc[tr], y[tr])
        p[te] = m.predict_proba(A.iloc[te])[:, 1]
    m = lgb.LGBMClassifier(n_estimators=100, num_leaves=15, verbose=-1, random_state=seed).fit(A, y)
    top = pd.Series(m.feature_importances_, index=A.columns).sort_values(ascending=False).head(10)
    auc = float(roc_auc_score(y, p))
    return {"auc": auc, "drifting_parameters": list(top.index),
            "badge": "strong drift" if auc > 0.8 else "moderate drift" if auc > 0.65 else "stable",
            "note": "Train+val vs test window. High AUC explains why later-window performance drops."}


def train_all(s: Split) -> dict:
    """Select settings on train+val only, refit on train+val, report on the later test window."""
    X_tv = pd.concat([s.X_train, s.X_val])
    y_tv = pd.concat([s.y_train, s.y_val])

    sel_imp = select_n_estimators(X_tv, y_tv, impute=True)
    sel_nan = select_n_estimators(X_tv, y_tv, impute=False)
    # keep the simpler (median impute, shared with baseline) unless native NaN is clearly better
    use_nan = sel_nan["scores"][sel_nan["best"]] > sel_imp["scores"][sel_imp["best"]] + 0.02
    impute = not use_nan
    n_est = (sel_nan if use_nan else sel_imp)["best"]

    # threshold: fit on train only, choose cost-optimal cut on val
    thr_model = fit_lgbm(s.X_train, s.y_train, s.X_val, s.y_val, impute=impute, n_estimators=n_est)
    chosen = fit_lgbm(X_tv, y_tv, s.X_val, s.y_val, impute=impute, n_estimators=n_est)
    chosen.threshold = thr_model.threshold

    logit_thr = fit_logistic(s.X_train, s.y_train, s.X_val, s.y_val)
    logit = fit_logistic(X_tv, y_tv, s.X_val, s.y_val)
    logit.threshold = logit_thr.threshold

    report = {
        "split": s.boundaries(),
        "preprocessing": chosen.pre.summary(),
        "model_selection": {
            "method": "expanding-window PR-AUC on train+val; test untouched",
            "median_impute": sel_imp,
            "native_nan": sel_nan,
            "chosen_imputation": "native_nan" if use_nan else "median_impute",
            "n_estimators": n_est,
        },
        "lightgbm": {
            "val_from_train_only": evaluate(s.y_val, predict(thr_model, s.X_val), chosen.threshold),
            "test": evaluate(s.y_test, predict(chosen, s.X_test), chosen.threshold),
        },
        "logistic_baseline": {
            "val_from_train_only": evaluate(s.y_val, predict(logit_thr, s.X_val), logit.threshold),
            "test": evaluate(s.y_test, predict(logit, s.X_test), logit.threshold),
        },
        "drift": adversarial_drift(X_tv, s.X_test),
        "leakage_contrast": {
            "random_split_pr_auc": random_split_inflation(X_tv, y_tv, n_est),
            "note": "Shuffled CV mixes future rows into training; not a valid estimate on drifting process data.",
        },
    }
    lg, lr = report["lightgbm"]["test"]["pr_auc"]["point"], report["logistic_baseline"]["test"]["pr_auc"]["point"]
    report["verdict"] = (
        "LightGBM beats logistic baseline on test PR-AUC" if lg > lr
        else "LightGBM does NOT beat logistic baseline on test PR-AUC"
    )
    return {"report": report, "model": chosen, "baseline": logit}
