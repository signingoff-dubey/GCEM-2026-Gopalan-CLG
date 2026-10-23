"""Slower checks that exercise model code on synthetic data with known causes."""
import numpy as np
import pandas as pd

from backend.ml.bosch import route_links, station_of, stations, visited_matrix
from backend.ml.counterfactual import NeighbourIndex
from backend.ml.planted import plant_labels
from backend.ml.rank import build_ranking
from backend.ml.timeline import build_timeline, rolling_windows


def synth(n=800, p=40, seed=0):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(rng.normal(size=(n, p)), columns=[f"F{i}" for i in range(p)])
    logit = -3.2 + 2.0 * X["F3"] + 1.5 * (X["F7"] > 1)
    y = pd.Series(rng.binomial(1, 1 / (1 + np.exp(-logit))), name="fail")
    return X, y


def test_ranking_recovers_planted_signal():
    X, y = synth()
    r = build_ranking(X, y, n_estimators=100, impute=False, B=8)
    t = r["_table"]
    assert set(t.sort_values("mean_rank").index[:3]) >= {"F3"}
    assert t.loc["F3", "stable"]
    stable = set(t.index[t["stable"]])
    assert stable <= {"F3", "F7"} | set(t.index[:4])  # few false stable flags


def test_null_labels_give_no_stable_features():
    X, _ = synth()
    y = pd.Series(np.random.default_rng(5).binomial(1, 0.07, len(X)))
    r = build_ranking(X, y, n_estimators=100, impute=False, B=8, top_k=3)
    assert r["n_stable"] == 0


def test_plant_labels_hits_prevalence():
    X, _ = synth(n=2000)
    out = plant_labels(X, n_causes=3, seed=3)
    assert len(out["causes"]) == 3
    assert 0.03 < out["y"].mean() < 0.12


def test_rolling_windows_cover_end():
    w = rolling_windows(1000, 400, 150)
    assert w[0] == (0, 400) and w[-1][1] == 1000


def test_timeline_shapes():
    X, y = synth(n=900)
    ts = pd.Series(pd.date_range("2024-01-01", periods=len(X), freq="h"))
    tl = build_timeline(X, y, ts, size=400, step=250, n_estimators=50)
    assert len(tl["matrix"]) == len(tl["windows"])
    assert tl["features"]


def test_counterfactual_neighbours_are_real_passing_runs():
    X, y = synth()
    ni = NeighbourIndex(X, y, ["F3", "F7", "F1"])
    fail_row = X[y == 1].iloc[0]
    out = ni.explain(fail_row, k=3)
    for nb in out["neighbours"]:
        assert y.loc[nb["index"]] == 0
    for d in out["biggest_differences"]:
        lo, hi = d["neighbour_range"]
        assert X[d["feature"]].min() <= lo <= hi <= X[d["feature"]].max()


def test_bosch_station_parsing_and_routes():
    assert station_of("L3_S29_F3407") == "L3_S29"
    assert station_of("L0_S0_D1") == "L0_S0"
    assert station_of("Response") is None
    df = pd.DataFrame({
        "L0_S0_F0": [1.0, np.nan, 2.0], "L0_S1_F2": [1.0, 1.0, np.nan],
        "L1_S24_F5": [np.nan, 3.0, 1.0], "Response": [0, 1, 0],
    })
    sts = stations(df)
    assert sts == ["L0_S0", "L0_S1", "L1_S24"]
    V = visited_matrix(df, sts)
    assert V.sum().tolist() == [2, 2, 2]
    links = route_links(df, df["Response"], sts, {"negative_weight": 1.0})
    pairs = {(l["source"], l["target"]) for l in links["links"]}
    assert ("L0_S0", "L0_S1") in pairs and ("L0_S1", "L1_S24") in pairs
