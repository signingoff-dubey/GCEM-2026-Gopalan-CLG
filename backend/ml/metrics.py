"""Imbalance-aware metrics with bootstrap CIs. Accuracy is never reported."""
import numpy as np
from scipy.stats import norm
from sklearn.metrics import average_precision_score, confusion_matrix, matthews_corrcoef

from backend.config import SEED


def pr_auc(y, p) -> float:
    return float(average_precision_score(y, p)) if np.sum(y) > 0 else float("nan")


def mcc(y, p, threshold) -> float:
    return float(matthews_corrcoef(y, (np.asarray(p) >= threshold).astype(int)))


def recall_at_precision(y, p, min_precision=0.3) -> float:
    y, p = np.asarray(y), np.asarray(p)
    order = np.argsort(-p)
    tp = np.cumsum(y[order])
    precision = tp / np.arange(1, len(y) + 1)
    recall = tp / max(y.sum(), 1)
    ok = precision >= min_precision
    return float(recall[ok].max()) if ok.any() else 0.0


def cost_threshold(y, p, cost_fn: float, cost_fp: float) -> float:
    """Threshold minimising cost_fn * FN + cost_fp * FP on the given (validation) data."""
    y, p = np.asarray(y), np.asarray(p)
    candidates = np.unique(np.concatenate([p, [0.5]]))
    best_t, best_c = 0.5, np.inf
    for t in candidates:
        pred = p >= t
        c = cost_fn * np.sum(~pred & (y == 1)) + cost_fp * np.sum(pred & (y == 0))
        if c < best_c:
            best_t, best_c = float(t), c
    return best_t


def bootstrap_ci(y, p, fn, n=1000, alpha=0.05, seed=SEED) -> dict:
    rng = np.random.default_rng(seed)
    y, p = np.asarray(y), np.asarray(p)
    vals = []
    for _ in range(n):
        idx = rng.integers(0, len(y), len(y))
        if y[idx].sum() == 0:
            continue
        vals.append(fn(y[idx], p[idx]))
    vals = np.array(vals)
    return {
        "point": float(fn(y, p)),
        "low": float(np.nanpercentile(vals, 100 * alpha / 2)),
        "high": float(np.nanpercentile(vals, 100 * (1 - alpha / 2))),
    }


def evaluate(y, p, threshold) -> dict:
    y, p = np.asarray(y), np.asarray(p)
    tn, fp, fn, tp = confusion_matrix(y, (p >= threshold).astype(int), labels=[0, 1]).ravel()
    return {
        "n": int(len(y)),
        "positives": int(y.sum()),
        "prevalence": float(y.mean()),
        "pr_auc": bootstrap_ci(y, p, pr_auc),
        "mcc": bootstrap_ci(y, p, lambda a, b: mcc(a, b, threshold)),
        "pr_auc_lift_over_random": float(pr_auc(y, p) / y.mean()) if y.mean() > 0 else None,
        "recall_at_precision_0.3": recall_at_precision(y, p, 0.3),
        "capture_curve": capture_curve(y, p),
        "threshold": float(threshold),
        "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def wilson_ci(k: int, n: int, alpha=0.05) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    z = norm.ppf(1 - alpha / 2)
    phat = k / n
    denom = 1 + z**2 / n
    centre = (phat + z**2 / (2 * n)) / denom
    half = z * np.sqrt(phat * (1 - phat) / n + z**2 / (4 * n**2)) / denom
    return (float(max(0.0, centre - half)), float(min(1.0, centre + half)))


def capture_curve(y, p, fractions=(0.05, 0.10, 0.20, 0.30)) -> list[dict]:
    """'Inspect the top x% riskiest runs and catch y% of failures.' Random catches x%."""
    y, p = np.asarray(y), np.asarray(p)
    order = np.argsort(-p)
    total = max(y.sum(), 1)
    out = []
    for f in fractions:
        k = max(1, int(round(len(y) * f)))
        caught = int(y[order[:k]].sum())
        out.append({"inspect_frac": f, "inspected": k, "fails_caught": caught,
                    "capture_rate": caught / total, "random_capture_rate": f})
    return out
