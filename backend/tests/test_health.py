"""Sensor health checks on hand-made sensors with known faults."""
import numpy as np
import pandas as pd

from backend.ml import health

rng = np.random.default_rng(0)
REF = pd.Series(rng.normal(10, 1, 600))


def test_healthy_sensor_is_ok():
    h = health.check_sensor(REF, pd.Series(rng.normal(10, 1, 200)))
    assert h["status"] == "ok" and h["reasons"] == []


def test_stuck_sensor_is_bad():
    recent = pd.Series(np.r_[rng.normal(10, 1, 50), np.full(60, 10.37), rng.normal(10, 1, 50)])
    h = health.check_sensor(REF, recent)
    assert h["status"] == "bad" and h["checks"]["stuck"] == "bad" and h["longest_repeat"] == 60


def test_silent_sensor_is_bad():
    h = health.check_sensor(REF, pd.Series([np.nan] * 200))
    assert h["status"] == "bad" and h["checks"]["silent"] == "bad"


def test_mostly_out_of_range_is_bad_but_drift_alone_is_only_watch():
    far = health.check_sensor(REF, pd.Series(rng.normal(16, 1, 200)))
    assert far["checks"]["out_of_range"] == "bad" and far["status"] == "bad"
    moved = health.check_sensor(REF, pd.Series(rng.normal(11.6, 0.5, 200)))
    assert moved["checks"]["drift"] == "watch" and moved["checks"]["out_of_range"] != "bad"


def test_constant_in_training_has_no_signal():
    h = health.check_sensor(pd.Series([1.0] * 600), pd.Series([1.0] * 200))
    assert h["status"] == "no signal"


def test_report_counts_and_order():
    X = pd.DataFrame({"good": rng.normal(0, 1, 800), "dead": np.r_[rng.normal(0, 1, 600), [np.nan] * 200]})
    rep = health.report(X, n_train=600, recent=200, windows=4)
    assert rep["counts"]["bad"] == 1 and rep["sensors"][0]["sensor"] == "dead" and len(rep["sensors"][0]["trace"]) == 4


def test_exports_have_no_empty_cells():
    import csv
    import io
    from fastapi.testclient import TestClient
    from backend.api.main import app
    c = TestClient(app)
    for path in ("/api/export/sensors.csv", "/api/export/runs.csv"):
        rows = list(csv.reader(io.StringIO(c.get(path).text)))
        assert rows and len({len(r) for r in rows}) == 1
        assert not [(i, j) for i, r in enumerate(rows) for j, v in enumerate(r) if not v.strip()], path
