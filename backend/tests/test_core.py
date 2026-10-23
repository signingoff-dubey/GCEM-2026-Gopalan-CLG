import numpy as np
import pandas as pd
import pytest

from backend.ml import cost, pilot
from backend.ml.features import Preprocessor, correlation_groups
from backend.ml.load import time_split
from backend.ml.metrics import capture_curve, cost_threshold, wilson_ci
from backend.ml.safe_window import clamp, operating_range, safe_window


@pytest.fixture
def toy():
    rng = np.random.default_rng(0)
    n = 600
    X = pd.DataFrame({
        "a": rng.normal(0, 1, n),
        "b": rng.normal(5, 2, n),
        "const": np.ones(n),
        "mostly_nan": np.where(rng.random(n) < 0.8, np.nan, rng.normal(0, 1, n)),
        "some_nan": np.where(rng.random(n) < 0.1, np.nan, rng.normal(0, 1, n)),
    })
    p = 1 / (1 + np.exp(-(2.5 * (X["a"] > 1) - 3)))
    y = pd.Series(rng.binomial(1, p), name="fail")
    ts = pd.Series(pd.date_range("2024-01-01", periods=n, freq="h"))
    return X, y, ts


# ---- split / leakage ----

def test_time_split_is_chronological_and_disjoint(toy):
    X, y, ts = toy
    s = time_split(X, y, ts)
    assert s.t_train.max() < s.t_val.min() <= s.t_val.max() < s.t_test.min()
    assert len(s.y_train) + len(s.y_val) + len(s.y_test) == len(y)
    assert not set(s.X_train.index) & set(s.X_test.index)


def test_time_split_rejects_unsorted(toy):
    X, y, ts = toy
    with pytest.raises(ValueError):
        time_split(X, y, ts[::-1].reset_index(drop=True))


def test_preprocessor_fits_on_train_only(toy):
    X, _, _ = toy
    train, test = X.iloc[:300], X.iloc[300:].copy()
    test["b"] = 1000.0
    pre = Preprocessor().fit(train)
    assert pre.medians_["b"] == pytest.approx(train["b"].median())
    assert "const" in pre.dropped_["constant"]
    assert "mostly_nan" in pre.dropped_["too_missing"]
    assert "some_nan" in pre.flagged_
    out = pre.transform(test)
    assert "some_nan_missing" in out and not out.isna().any().any()


def test_correlation_groups_merges_duplicates():
    rng = np.random.default_rng(1)
    a = rng.normal(size=200)
    X = pd.DataFrame({"a": a, "a2": a * 2 + 0.01 * rng.normal(size=200), "c": rng.normal(size=200)})
    g = correlation_groups(X, 0.8)
    assert g["a"] == g["a2"] != g["c"]


# ---- metrics ----

def test_wilson_ci_bounds():
    lo, hi = wilson_ci(5, 100)
    assert 0 <= lo < 0.05 < hi <= 1
    assert wilson_ci(0, 50)[0] == pytest.approx(0.0, abs=1e-12)


def test_cost_threshold_prefers_catching_fails_when_misses_are_expensive():
    y = np.array([0] * 90 + [1] * 10)
    p = np.r_[np.linspace(0, 0.5, 90), np.linspace(0.3, 0.9, 10)]
    t_cheap_fn = cost_threshold(y, p, cost_fn=1, cost_fp=100)
    t_dear_fn = cost_threshold(y, p, cost_fn=100, cost_fp=1)
    assert t_dear_fn <= t_cheap_fn


def test_capture_curve_perfect_model():
    y = np.array([1] * 10 + [0] * 90)
    p = np.r_[np.ones(10), np.zeros(90)]
    assert capture_curve(y, p, fractions=(0.1,))[0]["capture_rate"] == 1.0


# ---- safe window: never outside observed bounds ----

def test_safe_window_inside_operating_range(toy):
    X, y, _ = toy
    for col in ("a", "b", "some_nan"):
        sw = safe_window(X[col], y)
        assert sw is not None
        lo, hi = sw["operating_range"]
        a, b = sw["window"]
        assert lo <= a <= b <= hi
        for bin_ in sw["bins"]:
            assert lo <= bin_["window"][0] <= bin_["window"][1] <= hi
            assert bin_["n"] >= 30


def test_safe_window_finds_low_risk_side(toy):
    X, y, _ = toy
    sw = safe_window(X["a"], y)
    assert sw["window"][1] <= 1.0 + 1e-9  # failures were planted at a > 1
    assert sw["fit"]["rate_in"] < sw["fit"]["rate_out"]


def test_clamp_and_range():
    x = pd.Series(np.arange(100, dtype=float))
    lo, hi = operating_range(x)
    assert clamp(-50, (lo, hi)) == lo and clamp(500, (lo, hi)) == hi


def test_safe_window_insufficient_support():
    x = pd.Series(np.arange(20, dtype=float))
    y = pd.Series([0] * 19 + [1])
    assert safe_window(x, y) is None


# ---- cost model ----

def test_savings_is_ordered_range_and_labelled():
    out = cost.monthly_savings(cost.CostInputs(baseline_fail_rate=0.07, reduction_low=0.1,
                                               reduction_mid=0.3, reduction_high=0.5))
    assert out["low"]["savings_per_month"] <= out["mid"]["savings_per_month"] <= out["high"]["savings_per_month"]
    assert out["label"] == "model estimate"
    expected = 1000 * 0.07 * 0.3 * 500 * 26
    assert out["mid"]["savings_per_month"] == pytest.approx(expected)


def test_savings_sorts_unordered_reductions():
    out = cost.monthly_savings(cost.CostInputs(reduction_low=0.5, reduction_mid=0.1, reduction_high=0.3))
    assert out["low"]["savings_per_month"] <= out["high"]["savings_per_month"]


def test_savings_subtracts_false_alarms():
    a = cost.monthly_savings(cost.CostInputs(reduction_mid=0.2))
    b = cost.monthly_savings(cost.CostInputs(reduction_mid=0.2, false_alarms_per_day=10))
    assert b["mid"]["savings_per_month"] == pytest.approx(a["mid"]["savings_per_month"] - 10 * 50 * 26)


@pytest.mark.parametrize("field,value", [("volume_per_day", -1), ("days_per_month", 40),
                                         ("baseline_fail_rate", 1.5), ("reduction_mid", 2)])
def test_savings_rejects_bad_inputs(field, value):
    with pytest.raises(ValueError):
        cost.monthly_savings(cost.CostInputs(**{field: value}))


# ---- pilot planner ----

def test_pilot_bigger_effect_needs_fewer_parts():
    big = pilot.parts_per_arm(0.08, 0.02, 0.05, 0.8)
    small = pilot.parts_per_arm(0.08, 0.06, 0.05, 0.8)
    assert big < small


def test_pilot_no_reduction_is_infeasible():
    assert pilot.plan(0.05, 0.06)["feasible"] is False


def test_pilot_days_scale_with_share():
    a = pilot.plan(0.08, 0.03, pilot_share=0.1)
    b = pilot.plan(0.08, 0.03, pilot_share=0.2)
    assert a["parts_per_arm"] == b["parts_per_arm"] and a["days"] > b["days"]


def test_detectable_rate_consistent():
    r = pilot.detectable_rate(0.08, 300)
    assert 0 < r < 0.08
    assert pilot.parts_per_arm(0.08, r, 0.05, 0.8) <= 300
