"""Ground-truth validation.

Real process data has no known causes, so a ranking cannot be checked on it directly.
Here the real SECOM inputs are kept (missingness, correlations, drift all intact) but the
labels are regenerated from a known rule on a few planted parameters. RootLens should
recover the planted ones and flag little else; a single naive SHAP fit always returns a
full top-10, mostly noise. A null scenario (labels unrelated to any input) checks that
RootLens reports nothing stable when there is nothing to find.
"""
import numpy as np
import pandas as pd

from backend.config import CORR_GROUP_THRESHOLD, SEED, STABLE_FREQ, TOP_K
from backend.ml.features import Preprocessor, correlation_groups
from backend.ml.rank import build_ranking, shap_importance
from backend.ml.train import fit_lgbm

TARGET_PREVALENCE = 0.066


def _calibrate_intercept(score: np.ndarray, prevalence: float) -> float:
    lo, hi = -20.0, 20.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if (1 / (1 + np.exp(-(score + mid)))).mean() > prevalence:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def plant_labels(X: pd.DataFrame, n_causes=3, strength=1.6, seed=SEED,
                 prevalence=TARGET_PREVALENCE) -> dict:
    """Pick n_causes low-missing parameters from different correlation groups and
    generate fail labels from a mix of threshold and linear effects on them."""
    rng = np.random.default_rng(seed)
    pre = Preprocessor(impute=True).fit(X)
    A = pre.transform(X)[pre.kept_]
    groups = correlation_groups(A, CORR_GROUP_THRESHOLD)
    low_missing = [c for c in pre.kept_ if X[c].isna().mean() < 0.02 and A[c].std() > 0]
    rng.shuffle(low_missing)
    causes, used_groups = [], set()
    for c in low_missing:
        if groups[c] not in used_groups:
            causes.append(c)
            used_groups.add(groups[c])
        if len(causes) == n_causes:
            break

    z = (A[causes] - A[causes].mean()) / A[causes].std()
    effects = []
    score = np.zeros(len(X))
    for i, c in enumerate(causes):
        sign = rng.choice([-1, 1])
        if i % 2 == 0:  # threshold effect: failures rise when parameter drifts past ~1 sd
            contrib = strength * 1.5 * (sign * z[c] > 1.0).astype(float)
            effects.append({"feature": c, "type": "threshold", "direction": "high" if sign > 0 else "low"})
        else:
            contrib = strength * sign * z[c]
            effects.append({"feature": c, "type": "linear", "direction": "high" if sign > 0 else "low"})
        score += contrib.to_numpy()
    b0 = _calibrate_intercept(score, prevalence)
    p = 1 / (1 + np.exp(-(score + b0)))
    y = pd.Series(rng.binomial(1, p), index=X.index, name="fail")
    proxies = {c: sorted(f for f, g in groups.items() if g == groups[c]) for c in causes}
    return {"y": y, "causes": causes, "effects": effects, "proxies": proxies}


def null_labels(X: pd.DataFrame, seed=SEED, prevalence=TARGET_PREVALENCE) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(rng.binomial(1, prevalence, len(X)), index=X.index, name="fail")


def _hits(features, causes, proxies) -> set:
    """A ranked feature counts as a hit if it is a planted cause or a near-duplicate (|corr|>0.8) of one."""
    hit = set()
    for c in causes:
        if any(f in proxies[c] for f in features):
            hit.add(c)
    return hit


def _is_true(f, proxies) -> bool:
    return any(f in members for members in proxies.values())


def evaluate_scenario(X, y, causes, proxies, n_estimators=100, B=30, top_k=TOP_K) -> dict:
    naive = fit_lgbm(X, y, X, y, impute=False, n_estimators=n_estimators)
    naive_top = list(shap_importance(naive, X).head(top_k).index)
    r = build_ranking(X, y, n_estimators, impute=False, B=B, top_k=top_k)
    t = r["_table"]
    stable = list(t.index[t["stable"]])
    naive_false = [f for f in naive_top if not _is_true(f, proxies)]
    stable_false = [f for f in stable if not _is_true(f, proxies)]
    return {
        "planted": causes,
        "naive_shap": {
            "top_k": naive_top,
            "recovered": len(_hits(naive_top, causes, proxies)),
            "false_flags": len(naive_false),
        },
        "rootlens": {
            "stable": stable,
            "recovered": len(_hits(stable, causes, proxies)),
            "false_flags": len(stable_false),
            "planted_top_k_freq": {c: float(t.loc[t.index.isin(proxies[c]), "top_k_freq"].max())
                                   if t.index.isin(proxies[c]).any() else 0.0 for c in causes},
        },
    }


def run_planted_benchmark(X: pd.DataFrame, n_scenarios=5, n_causes=3, B=30, progress=None) -> dict:
    scenarios = []
    for i in range(n_scenarios):
        planted = plant_labels(X, n_causes=n_causes, seed=SEED + 100 + i)
        res = evaluate_scenario(X, planted["y"], planted["causes"], planted["proxies"], B=B)
        res["effects"] = planted["effects"]
        res["prevalence"] = float(planted["y"].mean())
        scenarios.append(res)
        if progress:
            progress(i + 1, n_scenarios + 1)

    y0 = null_labels(X, seed=SEED + 999)
    null_res = evaluate_scenario(X, y0, [], {}, B=B)
    if progress:
        progress(n_scenarios + 1, n_scenarios + 1)

    total = n_scenarios * n_causes
    def agg(key, field):
        return int(sum(s[key][field] for s in scenarios))
    return {
        "description": "Real SECOM inputs, labels regenerated from known planted causes.",
        "n_scenarios": n_scenarios,
        "causes_per_scenario": n_causes,
        "summary": {
            "naive_shap_recall": agg("naive_shap", "recovered") / total,
            "naive_shap_false_flags_per_scenario": agg("naive_shap", "false_flags") / n_scenarios,
            "rootlens_recall": agg("rootlens", "recovered") / total,
            "rootlens_false_flags_per_scenario": agg("rootlens", "false_flags") / n_scenarios,
            "null_naive_flags": len(null_res["naive_shap"]["top_k"]),
            "null_rootlens_stable": len(null_res["rootlens"]["stable"]),
        },
        "scenarios": scenarios,
        "null_scenario": {
            "naive_shap_top_k": null_res["naive_shap"]["top_k"],
            "rootlens_stable": null_res["rootlens"]["stable"],
            "note": "Labels are pure noise: anything flagged here is a false discovery.",
        },
        "stable_threshold": STABLE_FREQ,
    }


AI4I_COLUMNS = {
    "Air temperature [K]": "air_temp_K",
    "Process temperature [K]": "process_temp_K",
    "Rotational speed [rpm]": "rotational_speed_rpm",
    "Torque [Nm]": "torque_Nm",
    "Tool wear [min]": "tool_wear_min",
}
AI4I_FEATURES = list(AI4I_COLUMNS.values()) + ["Type_L", "Type_M", "Type_H"]
# from the dataset's published failure rules (Matzka 2020)
AI4I_KNOWN = {
    "TWF": ["tool_wear_min"],
    "HDF": ["air_temp_K", "process_temp_K", "rotational_speed_rpm"],
    "PWF": ["torque_Nm", "rotational_speed_rpm"],
    "OSF": ["tool_wear_min", "torque_Nm", "Type_L", "Type_M", "Type_H"],
    "RNF": [],
}


def load_ai4i(path) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    df = pd.read_csv(path, encoding="utf-8-sig").sort_values("UDI").reset_index(drop=True)
    df = df.rename(columns=AI4I_COLUMNS)
    for t in ("L", "M", "H"):
        df[f"Type_{t}"] = (df["Type"] == t).astype(int)
    modes = df[list(AI4I_KNOWN)]
    return df[AI4I_FEATURES], df["Machine failure"].astype(int), modes


def run_ai4i_check(path, B=30) -> dict:
    """Synthetic dataset with rule-defined failure modes: does the ranking surface the rule inputs?"""
    X, y, modes = load_ai4i(path)
    r = build_ranking(X, y, n_estimators=200, impute=False, B=B, top_k=3)
    t = r["_table"]
    per_mode = {}
    for mode, causes in AI4I_KNOWN.items():
        if not causes or modes[mode].sum() < 10:
            continue
        rm = build_ranking(X, modes[mode], n_estimators=200, impute=False, B=10, top_k=len(causes))
        top = list(rm["_table"].sort_values("mean_rank").head(len(causes)).index)
        per_mode[mode] = {"known_inputs": causes, "ranked_top": top,
                          "recovered": len(set(top) & set(causes)), "n_failures": int(modes[mode].sum())}
    return {
        "description": "AI4I 2020: synthetic, failure modes defined by explicit rules, so true inputs are known.",
        "overall_ranking": [{"feature": f, "mean_rank": float(row.mean_rank), "top_k_freq": float(row.top_k_freq)}
                            for f, row in t.sort_values("mean_rank").iterrows()],
        "per_failure_mode": per_mode,
    }
