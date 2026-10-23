"""RootLens on Firebase: the FastAPI app as one HTTP Cloud Function, plus a 1-minute alert tick.

scripts/build_functions.py copies backend/, config/, the analysis results and the sample files next to
this file before `firebase deploy`. Rows live in Firestore and files in Cloud Storage (backend/cloud.py).
"""
import os

os.environ.setdefault("ROOTLENS_STORE", "firebase")
os.environ.setdefault("ROOTLENS_DATA_DIR", "/tmp/rootlens")
os.environ.setdefault("ROOTLENS_ALERTS", "0")        # no background thread; alerts_tick sends the batches
os.environ.setdefault("ROOTLENS_JOBS", "1")
os.environ.setdefault("TZ", "Asia/Kolkata")        # timestamps match the plant's day on the calendar
if hasattr(__import__("time"), "tzset"):
    __import__("time").tzset()

from firebase_functions import https_fn, options, scheduler_fn  # noqa: E402

options.set_global_options(region="us-central1", memory=options.MemoryOption.GB_2, timeout_sec=300, max_instances=3)
_wsgi = None


def _app():
    """Import the API on first use: keeps deploy-time discovery fast and seeds Firebase once per start."""
    global _wsgi
    if _wsgi is None:
        from a2wsgi import ASGIMiddleware

        from backend import seed
        from backend.api.main import app
        seed.ensure()
        _wsgi = ASGIMiddleware(app)
    return _wsgi


@https_fn.on_request(concurrency=8, cpu=2)
def api(req: https_fn.Request) -> https_fn.Response:
    return https_fn.Response.from_app(_app(), req.environ)


@scheduler_fn.on_schedule(schedule="every 1 minutes", memory=options.MemoryOption.GB_1)
def alerts_tick(event: scheduler_fn.ScheduledEvent) -> None:
    """Sends one alert per finished batch: findings wait until nothing new arrived for QUIET_S seconds."""
    from backend import seed
    from backend.alerts import service
    seed.ensure()
    service.check_once()
    # keep the API instance warm so the phone agent's data tool answers within its ~10 s limit
    import urllib.request
    try:
        urllib.request.urlopen(os.getenv("ROOTLENS_API_URL", "https://us-central1-rootlens-hb.cloudfunctions.net/api") + "/api/health", timeout=50)
    except OSError:
        pass
