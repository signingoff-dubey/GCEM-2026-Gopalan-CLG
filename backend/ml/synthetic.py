"""Synthetic SECOM-like process data placed in 2026.

Two generators, both fitted on TRAIN rows only:

* CopulaSynth: rank-based Gaussian copula. Keeps each parameter's marginal (sampled by linear
  interpolation of the empirical quantile function), the cross-parameter correlation, the real
  missing-value pattern, and a shrunk class shift on parameters that separate fails from passes.
  Adds a slow drift on a few parameters and stamps rows across 2026.
* smote_fails: interpolation between pairs of real fail rows (k nearest neighbours).
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.stats import norm

from backend.config import SEED


@dataclass
class CopulaSynth:
    shrink: float = 0.15          # covariance shrinkage towards identity
    shift_t: float = 2.5          # |t| a parameter needs before it gets a fail shift
    shift_scale: float = 0.8
    cols_: list = field(default_factory=list)

    def fit(self, X: pd.DataFrame, y) -> "CopulaSynth":
        y = np.asarray(y)
        self.cols_ = list(X.columns)
        self.sorted_ = [np.sort(X[c].dropna().to_numpy()) for c in self.cols_]
        Z = self._to_z(X)
        Zf = np.nan_to_num(Z)
        cov = np.corrcoef(Zf, rowvar=False)
        cov = np.nan_to_num(cov)
        np.fill_diagonal(cov, 1.0)
        cov = (1 - self.shrink) * cov + self.shrink * np.eye(cov.shape[0])
        self.L_ = np.linalg.cholesky(cov + 1e-6 * np.eye(cov.shape[0]))
        nf = max(int(y.sum()), 1)
        mean_f = np.nanmean(Z[y == 1], axis=0) if y.sum() else np.zeros(Z.shape[1])
        mean_f = np.nan_to_num(mean_f)
        sig = np.abs(mean_f) * np.sqrt(nf) > self.shift_t
        self.shift_ = np.where(sig, mean_f * self.shift_scale, 0.0)
        self.masks_ = X.isna().to_numpy()
        self.rate_ = float(y.mean())
        return self

    def _to_z(self, X: pd.DataFrame) -> np.ndarray:
        Z = np.full(X.shape, np.nan)
        for j, c in enumerate(self.cols_):
            v = X[c].to_numpy(dtype=float)
            ok = ~np.isnan(v)
            if ok.sum() < 2:
                continue
            r = pd.Series(v[ok]).rank(method="average").to_numpy()
            Z[ok, j] = norm.ppf((r - 0.5) / ok.sum())
        return Z

    def sample(self, n: int, start="2026-01-05", end="2026-09-30", fail_rate=None, seed=SEED,
               drift_frac=0.10, drift=0.35) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
        rng = np.random.default_rng(seed)
        p = len(self.cols_)
        rate = self.rate_ if fail_rate is None else fail_rate
        y = (rng.random(n) < rate).astype(int)
        Z = rng.standard_normal((n, p)) @ self.L_.T + y[:, None] * self.shift_
        t = np.linspace(0, 1, n)[:, None]
        idx = rng.choice(p, max(1, int(p * drift_frac)), replace=False)
        Z[:, idx] += drift * rng.choice([-1, 1], len(idx)) * t     # slow 2026 process drift
        U = norm.cdf(Z)
        out = np.empty((n, p))
        for j in range(p):
            s = self.sorted_[j]
            out[:, j] = np.quantile(s, U[:, j]) if len(s) else np.nan  # linear interpolation between order stats
        mask = self.masks_[rng.integers(0, len(self.masks_), n)]
        out[mask] = np.nan
        ts = pd.Series(pd.date_range(start, end, periods=n), name="timestamp")
        return pd.DataFrame(out, columns=self.cols_), pd.Series(y, name="fail"), ts


def smote_fails(X: pd.DataFrame, y, n_new: int, k: int = 5, seed=SEED) -> pd.DataFrame:
    """Interpolate between a real fail row and one of its k nearest fail neighbours."""
    rng = np.random.default_rng(seed)
    F = X[np.asarray(y) == 1]
    if len(F) < 2 or n_new <= 0:
        return X.iloc[:0].copy()
    med = X.median()
    Fi = F.fillna(med)
    A = Fi.to_numpy()
    sd = X.std().replace(0, 1).to_numpy()
    Zs = (A - med.to_numpy()) / sd
    d = ((Zs[:, None, :] - Zs[None, :, :]) ** 2).sum(-1)
    np.fill_diagonal(d, np.inf)
    nn = np.argsort(d, axis=1)[:, : min(k, len(F) - 1)]
    a = rng.integers(0, len(F), n_new)
    b = nn[a, rng.integers(0, nn.shape[1], n_new)]
    lam = rng.random((n_new, 1))
    new = A[a] + lam * (A[b] - A[a])
    return pd.DataFrame(new, columns=X.columns)
