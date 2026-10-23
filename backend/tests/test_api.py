"""API tests. Skipped when artifacts have not been generated (run `make train`)."""
import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.config import ARTIFACTS_DIR

client = TestClient(app)
needs_artifacts = pytest.mark.skipif(not (ARTIFACTS_DIR / "model.pkl").exists(),
                                     reason="artifacts not built")


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


@needs_artifacts
def test_overview_never_reports_accuracy():
    body = client.get("/api/overview").json()
    assert "accuracy" not in str(body).lower()
    assert "pr_auc" in str(body)


@needs_artifacts
def test_savings_is_a_range():
    r = client.post("/api/savings", json={"volume_per_day": 1500})
    if r.status_code == 404:
        pytest.skip("no recommended window in current artifacts")
    body = r.json()
    assert {"low", "mid", "high"} <= body.keys() and body["label"] == "model estimate"


@needs_artifacts
def test_savings_rejects_bad_input():
    assert client.post("/api/savings", json={"volume_per_day": -5}).status_code in (404, 422)


@needs_artifacts
def test_score_flags_unknown_and_out_of_range():
    r = client.post("/api/score", json={"values": {"NOT_A_PARAM": 1.0, "F59": 1e9}})
    body = r.json()
    assert r.status_code == 200
    assert "NOT_A_PARAM" in body["unknown_parameters"]
    assert "F59" in body["needs_review"]
    assert 0 <= body["fail_probability"] <= 1


@needs_artifacts
def test_run_detail_counterfactual():
    runs = client.get("/api/runs", params={"split": "test", "fails_only": True}).json()["runs"]
    r = client.get(f"/api/runs/{runs[0]['index']}").json()
    assert r["counterfactual"]["neighbours"]
    assert r["label"] == "model-estimated"


def test_unknown_run_404():
    if not (ARTIFACTS_DIR / "model.pkl").exists():
        pytest.skip("artifacts not built")
    assert client.get("/api/runs/999999").status_code == 404
