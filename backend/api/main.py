"""RootLens API. Serves precomputed artifacts and light per-request scoring.

Run: uvicorn backend.api.main:app --host 0.0.0.0 --port 8000   (docs at /docs)
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.alerts import service as alerts
from backend.api import service
from backend.api.activity import router as activity_router
from backend.api.ai_routes import router as ai_router
from backend.api.alert_routes import router as alert_router
from backend.api.assembly_routes import router as assembly_router
from backend.api.capture_routes import router as capture_router
from backend.api.compare import router as compare_router
from backend.api.inspection_routes import router as inspection_router
from backend.api.state import ArtifactMissing, state
from backend.config import DISCLAIMER
from backend.ml import cost, pilot
from backend.ml.pipeline import clean



@asynccontextmanager
async def lifespan(_):
    alerts.start()      # defect alerts: call / WhatsApp / email on a new crack
    yield
    alerts.stop()


app = FastAPI(title="RootLens API", version="0.1.0", lifespan=lifespan)
JOB_PATHS = ("/api/inspection", "/api/assembly", "/api/captures")


@app.middleware("http")
async def _track_jobs(request, call_next):
    """Uploads and inspections in flight hold back defect alerts until the whole batch is done."""
    if request.method in ("POST", "PUT") and request.url.path.startswith(JOB_PATHS):
        alerts.job_started()
        try:
            return await call_next(request)
        finally:
            alerts.job_finished()
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ArtifactMissing)
def _missing(_, exc: ArtifactMissing):
    return JSONResponse(status_code=503, content={
        "detail": f"artifact '{exc}' not found; run `make train` first"})


def _artifact(name: str):
    return clean(state.json(name))


@app.get("/api/health")
def health():
    ready = (state.dir / "model.pkl").exists()
    return {"status": "ok", "artifacts_ready": ready}


@app.get("/api/overview")
def overview():
    """Headline numbers for the landing view."""
    m = state.json("metrics.json")
    r = state.json("ranking.json")
    w = state.json("safe_windows.json")
    p = state.json("planted_benchmark.json")
    return clean({
        "data": m["data_profile"],
        "split": m["split"],
        "test_pr_auc": {"lightgbm": m["lightgbm"]["test"]["pr_auc"],
                        "logistic_baseline": m["logistic_baseline"]["test"]["pr_auc"]},
        "random_split_pr_auc": m["leakage_contrast"]["random_split_pr_auc"],
        "n_stable_parameters": r["n_stable"],
        "stable_parameters": [f["feature"] for f in r["features"] if f["stable"]],
        "recommended_windows": [x["feature"] for x in w["windows"] if x.get("status", "").startswith("recommended")],
        "planted_benchmark": p["summary"],
        "disclaimer": DISCLAIMER,
    })


# precomputed artifacts
for _path, _name in [
    ("/api/metrics", "metrics.json"),
    ("/api/ranking", "ranking.json"),
    ("/api/safe-windows", "safe_windows.json"),
    ("/api/pilots", "pilots.json"),
    ("/api/timeline", "timeline.json"),
    ("/api/validation/planted", "planted_benchmark.json"),
    ("/api/validation/ai4i", "ai4i_check.json"),
    ("/api/stations", "bosch.json"),
    ("/api/operating-ranges", "operating_ranges.json"),
    ("/api/savings/default", "savings_default.json"),
]:
    app.add_api_route(_path, (lambda n: lambda: _artifact(n))(_name), methods=["GET"],
                      name=_name.removesuffix(".json"))


class SavingsRequest(BaseModel):
    volume_per_day: float = cost.DEFAULTS["volume_per_day"]
    scrap_cost_per_part: float = cost.DEFAULTS["scrap_cost_per_part"]
    false_alarm_cost: float = cost.DEFAULTS["false_alarm_cost"]
    days_per_month: float = cost.DEFAULTS["days_per_month"]
    feature: str | None = Field(None, description="safe-window feature to price; default = best recommended")
    false_alarms_per_day: float = 0.0


@app.post("/api/savings")
def savings(req: SavingsRequest):
    try:
        return service.price_savings(**req.model_dump())
    except service.NotFound as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


class PilotRequest(BaseModel):
    feature: str
    volume_per_day: float = pilot.DEFAULTS["volume_per_day"]
    pilot_share: float = Field(pilot.DEFAULTS["pilot_share"], gt=0, le=1)
    cost_per_pilot_part: float = Field(pilot.DEFAULTS["cost_per_pilot_part"], ge=0)
    scrap_cost_per_part: float = Field(pilot.DEFAULTS["scrap_cost_per_part"], ge=0)
    power: float = Field(pilot.DEFAULTS["power"], gt=0.5, lt=1)
    alpha: float = Field(pilot.DEFAULTS["alpha"], gt=0, lt=0.5)


@app.post("/api/pilot")
def pilot_plan(req: PilotRequest):
    try:
        return service.plan_pilot(req.feature, **req.model_dump(exclude={"feature"}))
    except service.NotFound as e:
        raise HTTPException(404, str(e))


@app.get("/api/runs")
def runs(split: str = Query("test", pattern="^(train|val|test)$"), fails_only: bool = False,
         limit: int = Query(200, le=2000)):
    return service.list_runs(split, fails_only, limit)


@app.get("/api/runs/{index}")
def run_detail(index: int):
    try:
        return service.run_detail(index)
    except service.NotFound as e:
        raise HTTPException(404, str(e))


class ScoreRequest(BaseModel):
    values: dict[str, float] = Field(..., description="parameter -> value; missing ones are left NaN")


@app.post("/api/score")
def score(req: ScoreRequest):
    """Score a new run (e.g. typed in or read from a sheet). Flags unknown and out-of-range values."""
    return service.score_values(req.values)


app.include_router(ai_router)
app.include_router(capture_router)
app.include_router(inspection_router)
app.include_router(compare_router)
app.include_router(assembly_router)
app.include_router(activity_router)
app.include_router(alert_router)
