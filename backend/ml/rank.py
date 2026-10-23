"""Root-cause ranking: SHAP importance repeated over bootstrap refits, plus L1 stability selection."""
import time

import numpy as np
import pandas as pd
import shap
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from backend.config import CORR_GROUP_THRESHOLD, N_BOOTSTRAP, SEED, STABLE_FREQ, TOP_K
from backend.ml.features import Preprocessor, base_feature, correlation_groups
from backend.ml.train import fit_lgbm


def shap_importance(trained, X: pd.DataFrame) -> pd.Series:
    """Mean |SHAP| per raw parameter (missingness flags folded into their parameter)."""
    A = trained.pre.transform(X)
    values = shap.TreeExplainer(trained.model).shap_values(A)
    if isinstance(values, list):
        values = values[1]
    imp = pd.Series(np.abs(values).mean(axis=0), index=A.columns)
    return imp.groupby(base_feature).sum().sort_values(ascending=False)


def bootstrap_ranks(X, y, n_estimators, impute, B=N_BOOTSTRAP, seed=SEED, progress=None) -> dict:
    rng = np.random.default_rng(seed)
    ranks, imps, times = [], [], []
    for b in range(B):
        t0 = time.time()
        idx = rng.integers(0, len(X), len(X))
        Xb, yb = X.iloc[idx], y.iloc[idx]
        t = fit_lgbm(Xb, yb, Xb, yb, impute=impute, n_estimators=n_estimators, seed=seed + b)
        imp = shap_importance(t, X)
        imps.append(imp)
        ranks.append(imp.rank(ascending=False, method="min"))
        times.append(time.time() - t0)
        if progress:
            progress(b + 1, B)
    R = pd.concat(ranks, axis=1).fillna(len(X.columns))
    I = pd.concat(imps, axis=1).fillna(0.0)
    return {"ranks": R, "importance": I, "sec_per_bootstrap": float(np.mean(times))}


def l1_stability(X, y, n_runs=N_BOOTSTRAP, frac=0.5, C=0.05, seed=SEED) -> pd.Series:
    """Fraction of half-subsamples in which L1 logistic keeps a non-zero coefficient."""
    rng = np.random.default_rng(seed)
    pre = Preprocessor(impute=True).fit(X)
    A = pre.transform(X)
    A = pd.DataFrame(StandardScaler().fit_transform(A), columns=A.columns, index=A.index)
    counts = pd.Series(0.0, index=A.columns)
    for _ in range(n_runs):
        idx = rng.choice(len(A), int(len(A) * frac), replace=False)
        m = LogisticRegression(penalty="l1", C=C, solver="liblinear", class_weight="balanced")
        m.fit(A.iloc[idx], y.iloc[idx])
        counts += (m.coef_[0] != 0).astype(float)
    freq = (counts / n_runs).groupby(base_feature).max()
    return freq.sort_values(ascending=False)


def build_ranking(X, y, n_estimators, impute, B=N_BOOTSTRAP, top_k=TOP_K,
                  stable_freq=STABLE_FREQ, progress=None) -> dict:
    boot = bootstrap_ranks(X, y, n_estimators, impute, B=B, progress=progress)
    R, I = boot["ranks"], boot["importance"]
    in_top = (R <= top_k).mean(axis=1)
    l1 = l1_stability(X, y)

    table = pd.DataFrame({
        "mean_rank": R.mean(axis=1),
        "rank_std": R.std(axis=1),
        "rank_p10": R.quantile(0.10, axis=1),
        "rank_p90": R.quantile(0.90, axis=1),
        "mean_abs_shap": I.mean(axis=1),
        "top_k_freq": in_top,
        "l1_selection_freq": l1.reindex(R.index).fillna(0.0),
    }).sort_values(["top_k_freq", "mean_rank"], ascending=[False, True])
    table["stable"] = table["top_k_freq"] >= stable_freq

    # feature groups: correlation clusters on the kept parameters (never called stations)
    pre = Preprocessor(impute=True).fit(X)
    groups = correlation_groups(pre.transform(X)[pre.kept_], CORR_GROUP_THRESHOLD)
    table["group"] = [groups.get(f, f) for f in table.index]
    grp = (
        table.groupby("group")
        .agg(group_shap=("mean_abs_shap", "sum"), members=("mean_abs_shap", "size"),
             best_member_rank=("mean_rank", "min"))
        .sort_values("group_shap", ascending=False)
    )
    member_lists = table.reset_index(names="feature").groupby("group")["feature"].apply(list)

    shap_top = table.sort_values("mean_rank").head(top_k).index
    l1_top = l1.head(top_k).index
    features = [
        {"feature": f, **{k: (bool(v) if k == "stable" else v if k == "group" else float(v))
                           for k, v in row.items()}}
        for f, row in table.head(50).iterrows()
    ]
    return {
        "method": f"LightGBM mean |SHAP| over {B} bootstrap refits; stable if in top-{top_k} "
                  f"in >= {int(stable_freq * 100)}% of refits",
        "n_bootstrap": B,
        "sec_per_bootstrap": boot["sec_per_bootstrap"],
        "top_k": top_k,
        "n_stable": int(table["stable"].sum()),
        "features": features,
        "groups": [
            {"group": g, "group_shap": float(r.group_shap), "members": int(r.members),
             "best_member_rank": float(r.best_member_rank), "features": member_lists[g]}
            for g, r in grp.head(20).iterrows()
        ],
        "l1_overlap": {
            "shap_top": list(shap_top), "l1_top": list(l1_top),
            "overlap": sorted(set(shap_top) & set(l1_top)),
        },
        "label": "Statistically suspected, stability-checked. Association, not proven cause.",
        "_table": table,
    }
