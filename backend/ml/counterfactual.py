"""Data-grounded counterfactuals: for a failing run, find the most similar real passing runs.

Every suggested value comes from a run the line actually produced, so nothing is
extrapolated and correlated parameters move together the way they did in reality.
"""
import numpy as np
import pandas as pd

from backend.config import DISCLAIMER


class NeighbourIndex:
    def __init__(self, X_ref: pd.DataFrame, y_ref: pd.Series, features: list[str],
                 timestamps: pd.Series | None = None, risk: np.ndarray | None = None):
        self.features = [f for f in features if f in X_ref]
        ref = X_ref[self.features]
        self.median = ref.median()
        self.scale = (ref.quantile(0.75) - ref.quantile(0.25)).replace(0, np.nan).fillna(ref.std()).replace(0, 1.0)
        self.Z = ((ref.fillna(self.median) - self.median) / self.scale).to_numpy()
        self.y = y_ref.to_numpy()
        self.index = X_ref.index
        self.raw = ref
        self.ts = timestamps
        self.X_full = X_ref
        # only learn from passing runs the model also considers low-risk (not lucky passes)
        ok = self.y == 0
        if risk is not None:
            risk = np.asarray(risk)
            ok &= risk <= np.median(risk[self.y == 0])
        self.reference_ok = ok

    def _z(self, row: pd.Series) -> np.ndarray:
        r = row.reindex(self.features)
        return ((r.fillna(self.median) - self.median) / self.scale).to_numpy(dtype=float)

    def typical_distance(self) -> float:
        """Median nearest-pass distance among passing runs, as a yardstick for 'close'."""
        passing = np.where(self.y == 0)[0]
        sample = passing[:: max(1, len(passing) // 200)]
        dists = []
        for i in sample:
            d = np.sqrt(((self.Z[passing] - self.Z[i]) ** 2).mean(axis=1))
            d = d[d > 0]
            if len(d):
                dists.append(d.min())
        return float(np.median(dists)) if dists else float("nan")

    def explain(self, row: pd.Series, k=5, weights: pd.Series | None = None,
                model_fn=None, exclude_index=None) -> dict:
        z = self._z(row)
        w = np.ones(len(self.features)) if weights is None else \
            weights.reindex(self.features).fillna(0).to_numpy() + 1e-6
        w = w / w.sum()
        mask = self.reference_ok.copy()
        if exclude_index is not None:
            mask &= self.index != exclude_index
        cand = np.where(mask)[0]
        d = np.sqrt((((self.Z[cand] - z) ** 2) * w).sum(axis=1))
        best = cand[np.argsort(d)[:k]]
        nd = np.sort(d)[:k]

        neigh_vals = self.raw.iloc[best]
        target = neigh_vals.median()
        gap = ((row.reindex(self.features) - target) / self.scale).abs()
        # rank by how far off the run is, weighted by how much the parameter matters
        priority = (gap * pd.Series(w, index=self.features)).fillna(0)
        diffs = []
        for f in priority.sort_values(ascending=False).index[:10]:
            cur = row.get(f)
            diffs.append({
                "feature": f,
                "current": None if pd.isna(cur) else float(cur),
                "neighbour_median": float(target[f]),
                "neighbour_range": [float(neigh_vals[f].min()), float(neigh_vals[f].max())],
                "gap_in_iqr": None if pd.isna(gap[f]) else float(gap[f]),
            })
        out = {
            "neighbours": [
                {"index": int(self.index[i]), "distance": float(dist),
                 "timestamp": str(self.ts.iloc[i]) if self.ts is not None else None}
                for i, dist in zip(best, nd)
            ],
            "biggest_differences": diffs,
            "label": "Nearest real passing runs. " + DISCLAIMER,
        }
        if model_fn is not None:
            # adopt the nearest neighbour's full profile on the ranked parameters, so
            # correlated parameters move together as they did on a real run
            moved = row.copy()
            nearest = self.X_full.iloc[best[0]]
            for f in self.features:
                moved[f] = nearest[f]
            p0 = float(model_fn(pd.DataFrame([row]))[0])
            p1 = float(model_fn(pd.DataFrame([moved]))[0])
            out["model_estimate"] = {
                "fail_prob_now": p0,
                "fail_prob_with_nearest_pass_profile": p1,
                "label": "model-estimated",
            }
        return out
