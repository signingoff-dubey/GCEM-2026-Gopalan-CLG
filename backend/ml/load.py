"""Load SECOM, sort by time, and produce a time-based split."""
import zipfile
from dataclasses import dataclass

import numpy as np
import pandas as pd

from backend.config import SECOM_DIR, SECOM_ZIP, SPLIT_FRACTIONS


@dataclass
class Split:
    X_train: pd.DataFrame
    y_train: pd.Series
    X_val: pd.DataFrame
    y_val: pd.Series
    X_test: pd.DataFrame
    y_test: pd.Series
    t_train: pd.Series
    t_val: pd.Series
    t_test: pd.Series

    def boundaries(self) -> dict:
        def span(t, y):
            return {
                "start": str(t.min()), "end": str(t.max()),
                "n": int(len(y)), "fails": int(y.sum()),
            }
        return {
            "train": span(self.t_train, self.y_train),
            "val": span(self.t_val, self.y_val),
            "test": span(self.t_test, self.y_test),
        }


def _ensure_extracted() -> None:
    if (SECOM_DIR / "secom.data").exists():
        return
    if not SECOM_ZIP.exists():
        raise FileNotFoundError(f"SECOM not found in {SECOM_DIR} or {SECOM_ZIP}")
    SECOM_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(SECOM_ZIP) as zf:
        zf.extractall(SECOM_DIR)


def load_secom() -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Return (X, y, timestamp), sorted by timestamp. y: 1 = fail, 0 = pass."""
    _ensure_extracted()
    X = pd.read_csv(SECOM_DIR / "secom.data", sep=" ", header=None, na_values="NaN")
    X.columns = [f"F{i}" for i in range(X.shape[1])]
    labels = pd.read_csv(
        SECOM_DIR / "secom_labels.data", sep=" ", header=None, names=["label", "ts"]
    )
    y = (labels["label"] == 1).astype(int).rename("fail")
    ts = pd.to_datetime(labels["ts"], format="%d/%m/%Y %H:%M:%S").rename("timestamp")

    order = np.argsort(ts.values, kind="stable")
    X = X.iloc[order].reset_index(drop=True)
    y = y.iloc[order].reset_index(drop=True)
    ts = ts.iloc[order].reset_index(drop=True)
    return X, y, ts


def time_split(X: pd.DataFrame, y: pd.Series, ts: pd.Series,
               fractions=SPLIT_FRACTIONS) -> Split:
    """Chronological split; rows must already be sorted by time."""
    if not ts.is_monotonic_increasing:
        raise ValueError("rows must be sorted by timestamp before splitting")
    n = len(X)
    a = int(n * fractions[0])
    b = int(n * (fractions[0] + fractions[1]))
    return Split(
        X.iloc[:a], y.iloc[:a], X.iloc[a:b], y.iloc[a:b], X.iloc[b:], y.iloc[b:],
        ts.iloc[:a], ts.iloc[a:b], ts.iloc[b:],
    )


def profile(X: pd.DataFrame, y: pd.Series, ts: pd.Series) -> dict:
    miss = X.isna().mean()
    return {
        "rows": int(X.shape[0]),
        "features": int(X.shape[1]),
        "fails": int(y.sum()),
        "fail_rate": float(y.mean()),
        "time_start": str(ts.min()),
        "time_end": str(ts.max()),
        "missing_cells_frac": float(X.isna().values.mean()),
        "cols_no_missing": int((miss == 0).sum()),
        "cols_missing_gt_60pct": int((miss > 0.6).sum()),
        "cols_missing_5_60pct": int(((miss >= 0.05) & (miss <= 0.6)).sum()),
        "cols_constant": int((X.nunique(dropna=True) <= 1).sum()),
    }
