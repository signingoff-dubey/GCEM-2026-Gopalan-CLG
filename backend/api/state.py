"""Loads artifacts once and keeps them in memory for the API. Never retrains."""
import json
import pickle
from functools import cached_property

import numpy as np
import pandas as pd

from backend.config import ARTIFACTS_DIR
from backend.ml.counterfactual import NeighbourIndex
from backend.ml.load import load_secom, time_split
from backend.ml.train import predict


class ArtifactMissing(Exception):
    pass


class State:
    def __init__(self, artifacts_dir=ARTIFACTS_DIR):
        self.dir = artifacts_dir

    def json(self, name: str) -> dict:
        path = self.dir / name
        if not path.exists():
            raise ArtifactMissing(name)
        return json.loads(path.read_text())

    @cached_property
    def bundle(self) -> dict:
        path = self.dir / "model.pkl"
        if not path.exists():
            raise ArtifactMissing("model.pkl")
        with open(path, "rb") as f:
            return pickle.load(f)

    @cached_property
    def data(self):
        X, y, ts = load_secom()
        return X, y, ts, time_split(X, y, ts)

    @cached_property
    def neighbours(self) -> NeighbourIndex:
        X, y, ts, _ = self.data
        idx = self.bundle["train_index"]
        Xr, yr = X.loc[idx], y.loc[idx]
        return NeighbourIndex(Xr, yr, self.bundle["neighbour_features"], ts.loc[idx],
                              risk=self.predict(Xr))

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        X = X.reindex(columns=self.bundle["feature_columns"])
        return predict(self.bundle["model"], X)

    def shap_row(self, X: pd.DataFrame) -> pd.Series:
        import shap

        from backend.ml.features import base_feature
        trained = self.bundle["model"]
        A = trained.pre.transform(X.reindex(columns=self.bundle["feature_columns"]))
        sv = shap.TreeExplainer(trained.model).shap_values(A)
        sv = sv[1] if isinstance(sv, list) else sv
        return pd.Series(sv[0], index=A.columns).groupby(base_feature).sum()


state = State()
