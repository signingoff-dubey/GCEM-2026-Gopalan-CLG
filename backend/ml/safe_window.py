"""Corrective ranges ("safe windows") that never leave the observed operating range."""
import numpy as np
import pandas as pd
from scipy.stats import fisher_exact

from backend.config import MIN_BIN_SUPPORT, N_BINS, WINDOW_HIGH_PCT, WINDOW_LOW_PCT
from backend.ml.metrics import wilson_ci


def operating_range(x: pd.Series) -> tuple[float, float]:
    x = x.dropna()
    return float(np.percentile(x, WINDOW_LOW_PCT)), float(np.percentile(x, WINDOW_HIGH_PCT))


def clamp(value: float, bounds: tuple[float, float]) -> float:
    return float(min(max(value, bounds[0]), bounds[1]))


def _bins(x: pd.Series, bounds, n_bins, min_support) -> list[tuple[float, float]]:
    inside = x[(x >= bounds[0]) & (x <= bounds[1])]
    for k in range(n_bins, 1, -1):
        edges = np.unique(np.quantile(inside, np.linspace(0, 1, k + 1)))
        if len(edges) < 3:
            continue
        pairs = list(zip(edges[:-1], edges[1:]))
        counts = [((inside >= a) & (inside <= b)).sum() for a, b in pairs]
        if min(counts) >= min_support:
            return [(float(a), float(b)) for a, b in pairs]
    return []


def _rates(x, y, window):
    a, b = window
    mask_in = (x >= a) & (x <= b)
    k_in, n_in = int(y[mask_in].sum()), int(mask_in.sum())
    k_out, n_out = int(y[~mask_in].sum()), int((~mask_in).sum())
    return {
        "n_in": n_in, "fails_in": k_in,
        "rate_in": k_in / n_in if n_in else float("nan"), "rate_in_ci": wilson_ci(k_in, n_in),
        "n_out": n_out, "fails_out": k_out,
        "rate_out": k_out / n_out if n_out else float("nan"), "rate_out_ci": wilson_ci(k_out, n_out),
        "fisher_p": float(fisher_exact([[k_in, n_in - k_in], [k_out, n_out - k_out]])[1])
        if n_in and n_out else float("nan"),
    }


def safe_window(x: pd.Series, y: pd.Series, n_bins=N_BINS, min_support=MIN_BIN_SUPPORT) -> dict | None:
    """Lowest-failure quantile bin inside [p5, p95]. Returns None when no bin has enough support."""
    ok = x.notna()
    x, y = x[ok], y[ok]
    bounds = operating_range(x)
    bins = _bins(x, bounds, n_bins, min_support)
    if not bins:
        return None
    stats = []
    for a, b in bins:
        m = (x >= a) & (x <= b)
        k, n = int(y[m].sum()), int(m.sum())
        stats.append({"window": [a, b], "n": n, "fails": k, "rate": k / n, "rate_ci": wilson_ci(k, n)})
    best = min(stats, key=lambda s: (s["rate"], -s["n"]))
    return {
        "operating_range": list(bounds),
        "window": best["window"],
        "current_median": float(x.median()),
        "bins": stats,
        "fit": _rates(x, y, best["window"]),
    }


def model_estimated_shift(trained, X: pd.DataFrame, feature: str, window, predict_fn) -> dict:
    """Move `feature` to the window midpoint for rows outside it, others fixed. Circular: model-estimated."""
    mid = (window[0] + window[1]) / 2
    base = predict_fn(trained, X)
    Xs = X.copy()
    outside = ~Xs[feature].between(window[0], window[1])
    Xs.loc[outside, feature] = mid
    shifted = predict_fn(trained, Xs)
    return {
        "mean_fail_prob_before": float(base.mean()),
        "mean_fail_prob_after": float(shifted.mean()),
        "relative_reduction": float(1 - shifted.mean() / base.mean()) if base.mean() > 0 else 0.0,
        "rows_shifted": int(outside.sum()),
        "label": "model-estimated",
    }


def reduction_range(sw: dict, baseline_rate: float) -> dict:
    """Relative fail-rate reduction if all production ran inside the window, from the Wilson CI."""
    lo_rate, hi_rate = sw["fit"]["rate_in_ci"]
    def red(r):
        return float(np.clip(1 - r / baseline_rate, -1, 1)) if baseline_rate > 0 else 0.0
    return {"low": red(hi_rate), "mid": red(sw["fit"]["rate_in"]), "high": red(lo_rate)}


def recommendation_text(feature: str, sw: dict) -> str:
    a, b = sw["window"]
    f = sw["fit"]
    lo, hi = f["rate_in_ci"]
    return (
        f"Move {feature} from current median {sw['current_median']:.4g} to window [{a:.4g}, {b:.4g}]. "
        f"Historical failure rate there: {f['rate_in']:.1%} (95% CI {lo:.1%}-{hi:.1%}, n={f['n_in']}) "
        f"vs {f['rate_out']:.1%} outside. Association, not proof."
    )


def build_safe_windows(ranking_table: pd.DataFrame, X_fit, y_fit, X_test, y_test,
                       trained, predict_fn, top_k: int) -> dict:
    """Windows for the top-k ranked parameters. Only stable ones get a recommendation."""
    baseline = float(y_fit.mean())
    out = []
    for feature, row in ranking_table.sort_values("mean_rank").head(top_k).iterrows():
        if feature not in X_fit:
            continue
        sw = safe_window(X_fit[feature], y_fit)
        if sw is None:
            out.append({"feature": feature, "stable": bool(row["stable"]), "status": "insufficient support"})
            continue
        xt = X_test[feature]
        okt = xt.notna()
        test_check = _rates(xt[okt], y_test[okt], sw["window"])
        if test_check["n_in"] < MIN_BIN_SUPPORT or test_check["fails_in"] + test_check["fails_out"] == 0:
            test_check["verdict"] = "insufficient test data"
        elif test_check["rate_in"] < test_check["rate_out"]:
            test_check["verdict"] = "held on test"
        else:
            test_check["verdict"] = "did not hold on test (possible drift)"
        entry = {
            "feature": feature,
            "stable": bool(row["stable"]),
            "status": "recommended" if row["stable"] else "unstable - not recommended",
            **sw,
            "reduction_if_in_window": reduction_range(sw, baseline),
            "test_window_check": {**test_check, "label": "observed on held-out later window (non-model)"},
            "model_estimate": model_estimated_shift(trained, X_test, feature, sw["window"], predict_fn),
            "text": recommendation_text(feature, sw),
        }
        out.append(entry)
    return {
        "baseline_fail_rate": baseline,
        "windows": out,
        "caveat": "Lowest-rate bin is selected from several, which biases the in-window rate low; "
                  "the held-out test check is the more credible number.",
    }
