"""Missing-data and outlier handling. Every statistic is fitted on TRAIN only, so validation and test
rows never influence how the training data is cleaned.

1. drop constant sensors and sensors missing in more than MAX_MISSING_FRAC of runs;
2. clip each kept sensor to its train 1st..99th percentile (winsorising): a stuck or spiking reading can
   no longer drag the fill value or dominate a split, while an extreme run stays at the edge of the range;
3. fill the gaps with the train mean of the clipped values (mean is safe once outliers are clipped);
4. keep a 0/1 "was missing" flag for sensors missing in at least FLAG_MISSING_FRAC of runs, because
   missingness itself can carry signal.
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from backend.config import CLIP_PCT, FLAG_MISSING_FRAC, MAX_MISSING_FRAC


@dataclass
class Preprocessor:
    impute: bool = True
    max_missing: float = MAX_MISSING_FRAC
    flag_missing: float = FLAG_MISSING_FRAC
    kept_: list = field(default_factory=list)
    flagged_: list = field(default_factory=list)
    clip: bool = True
    means_: dict = field(default_factory=dict)
    lo_: dict = field(default_factory=dict)
    hi_: dict = field(default_factory=dict)
    dropped_: dict = field(default_factory=dict)
    stats_: dict = field(default_factory=dict)

    def fit(self, X: pd.DataFrame) -> "Preprocessor":
        miss = X.isna().mean()
        nunique = X.nunique(dropna=True)
        constant = nunique[nunique <= 1].index.tolist()
        too_missing = miss[miss > self.max_missing].index.difference(constant).tolist()
        self.dropped_ = {"constant": constant, "too_missing": too_missing}
        self.kept_ = [c for c in X.columns if c not in set(constant) | set(too_missing)]
        kept_miss = miss[self.kept_]
        self.flagged_ = kept_miss[kept_miss >= self.flag_missing].index.tolist()
        kept = X[self.kept_]
        if self.clip:
            self.lo_ = kept.quantile(CLIP_PCT / 100).to_dict()
            self.hi_ = kept.quantile(1 - CLIP_PCT / 100).to_dict()
            clipped = kept.clip(lower=pd.Series(self.lo_), upper=pd.Series(self.hi_), axis=1)
        else:
            clipped = kept
        self.means_ = clipped.mean().to_dict()
        n_out = int(((kept < pd.Series(self.lo_)) | (kept > pd.Series(self.hi_))).sum().sum()) if self.clip else 0
        self.stats_ = {"train_rows": int(len(X)), "missing_values": int(kept.isna().sum().sum()),
                       "missing_share": round(float(kept.isna().mean().mean()), 4),
                       "outliers_clipped": n_out, "outlier_share": round(float(n_out / max(1, kept.notna().sum().sum())), 4)}
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        out = X.reindex(columns=self.kept_).copy()
        if getattr(self, "clip", False) and getattr(self, "lo_", None):   # older pickles have no clip bounds
            out = out.clip(lower=pd.Series(self.lo_), upper=pd.Series(self.hi_), axis=1)
        flags = pd.DataFrame(
            {f"{c}_missing": X[c].isna().astype(int) if c in X else 1 for c in self.flagged_},
            index=X.index,
        )
        if self.impute:
            out = out.fillna(getattr(self, "means_", None) or getattr(self, "medians_", {}))
        return pd.concat([out, flags], axis=1)

    def fit_transform(self, X: pd.DataFrame) -> pd.DataFrame:
        return self.fit(X).transform(X)

    @property
    def feature_names(self) -> list:
        return self.kept_ + [f"{c}_missing" for c in self.flagged_]

    def summary(self) -> dict:
        return {
            "dropped_constant": len(self.dropped_["constant"]),
            "dropped_too_missing": len(self.dropped_["too_missing"]),
            "kept": len(self.kept_),
            "missing_flags": len(self.flagged_),
            "imputed_with": "train mean after clipping" if self.impute else "none (LightGBM native NaN)",
            "outliers": f"clipped to the train {_ord(CLIP_PCT)}..{_ord(100 - CLIP_PCT)} percentile" if self.clip else "not clipped",
            "fitted_on": "train window only",
            **self.stats_,
        }


def _ord(x: float) -> str:
    n = int(x)
    return f"{x:g}" + ("th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th"))


def base_feature(name: str) -> str:
    """Map a missingness flag back to its raw parameter."""
    return name[: -len("_missing")] if name.endswith("_missing") else name


def correlation_groups(X: pd.DataFrame, threshold: float) -> dict:
    """Greedy clustering: features with |corr| > threshold share a group.
    Returns {feature: group_id}. Groups are 'feature groups', never 'stations'."""
    corr = X.corr().abs().fillna(0).to_numpy(copy=True)
    np.fill_diagonal(corr, 0)
    cols = list(X.columns)
    group = {}
    gid = 0
    for i, c in enumerate(cols):
        if c in group:
            continue
        stack = [i]
        while stack:
            j = stack.pop()
            if cols[j] in group:
                continue
            group[cols[j]] = f"G{gid}"
            stack.extend(k for k in np.where(corr[j] > threshold)[0] if cols[k] not in group)
        gid += 1
    return group


def data_quality(s) -> dict:
    """What cleaning did to the data, fitted on the train window and applied to every split.

    Shows the missing values filled, the outliers clipped, and that the training data keeps its shape:
    each sensor's mean and spread before cleaning (observed values only) versus after.
    """
    pre = Preprocessor(impute=True).fit(s.X_train)
    lo, hi = pd.Series(pre.lo_), pd.Series(pre.hi_)
    splits = {}
    for name, X, y in (("train", s.X_train, s.y_train), ("val", s.X_val, s.y_val), ("test", s.X_test, s.y_test)):
        kept = X[pre.kept_]
        out = pre.transform(X)[pre.kept_]
        splits[name] = {"rows": int(len(X)), "fails": int(y.sum()), "fail_rate": round(float(y.mean()), 4),
                        "missing_before": int(kept.isna().sum().sum()), "missing_after": int(out.isna().sum().sum()),
                        "outliers_clipped": int(((kept < lo) | (kept > hi)).sum().sum())}
    raw = s.X_train[pre.kept_]
    clean = pre.transform(s.X_train)[pre.kept_]
    scale = raw.std().replace(0, np.nan)
    mean_shift = ((clean.mean() - raw.mean()).abs() / scale).dropna()
    std_ratio = (clean.std() / raw.std()).replace([np.inf, -np.inf], np.nan).dropna()
    miss = s.X_train[pre.kept_].isna().mean().sort_values(ascending=False)
    top = [{"feature": f, "missing_train": round(float(m), 4), "fill_value": round(float(pre.means_[f]), 5),
            "clip_low": round(float(pre.lo_[f]), 5), "clip_high": round(float(pre.hi_[f]), 5),
            "flagged": f in pre.flagged_} for f, m in miss.head(15).items() if m > 0]
    return {
        "method": pre.summary(),
        "steps": [
            f"Dropped {len(pre.dropped_['constant'])} constant sensors and {len(pre.dropped_['too_missing'])} "
            f"missing in more than {MAX_MISSING_FRAC:.0%} of training runs.",
            f"Clipped every remaining sensor to its training {_ord(CLIP_PCT)}..{_ord(100 - CLIP_PCT)} percentile.",
            "Filled the gaps with the training mean of the clipped values.",
            f"Kept a was-missing flag for {len(pre.flagged_)} sensors missing in at least {FLAG_MISSING_FRAC:.0%} of runs.",
            "All of it is fitted on the training window only, then applied unchanged to validation and test.",
        ],
        "splits": splits,
        "shape_check": {
            "features": int(len(pre.kept_)),
            "median_mean_shift_sd": round(float(mean_shift.median()), 4),
            "p95_mean_shift_sd": round(float(mean_shift.quantile(0.95)), 4),
            "median_std_ratio": round(float(std_ratio.median()), 4),
            "note": "Mean shift is in standard deviations of the observed training values; a std ratio near 1 means the spread is kept.",
        },
        "most_missing": top,
        "imbalance": {"fail_rate_train": splits["train"]["fail_rate"], "handled_by": "class weights in LightGBM and the logistic baseline; "
                      "scored with PR-AUC and MCC, never accuracy; decision threshold chosen on validation"},
    }
