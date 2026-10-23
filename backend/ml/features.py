"""Missing-data handling. Every statistic is fitted on TRAIN only."""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from backend.config import FLAG_MISSING_FRAC, MAX_MISSING_FRAC


@dataclass
class Preprocessor:
    impute: bool = True
    max_missing: float = MAX_MISSING_FRAC
    flag_missing: float = FLAG_MISSING_FRAC
    kept_: list = field(default_factory=list)
    flagged_: list = field(default_factory=list)
    medians_: dict = field(default_factory=dict)
    dropped_: dict = field(default_factory=dict)

    def fit(self, X: pd.DataFrame) -> "Preprocessor":
        miss = X.isna().mean()
        nunique = X.nunique(dropna=True)
        constant = nunique[nunique <= 1].index.tolist()
        too_missing = miss[miss > self.max_missing].index.difference(constant).tolist()
        self.dropped_ = {"constant": constant, "too_missing": too_missing}
        self.kept_ = [c for c in X.columns if c not in set(constant) | set(too_missing)]
        kept_miss = miss[self.kept_]
        self.flagged_ = kept_miss[kept_miss >= self.flag_missing].index.tolist()
        self.medians_ = X[self.kept_].median().to_dict()
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        out = X.reindex(columns=self.kept_).copy()
        flags = pd.DataFrame(
            {f"{c}_missing": X[c].isna().astype(int) if c in X else 1 for c in self.flagged_},
            index=X.index,
        )
        if self.impute:
            out = out.fillna(self.medians_)
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
            "imputed_with": "train median" if self.impute else "none (LightGBM native NaN)",
        }


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
