"""Capture endpoints: photo or webcam frame -> vision transcription -> range check -> score."""
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, RedirectResponse, Response

from backend import cloud
from pydantic import BaseModel, Field

from backend.api import service
from backend.capture import run_sheet, store, vision
from backend.ml.pipeline import clean

router = APIRouter(prefix="/api", tags=["capture"])
MAX_IMAGE_BYTES = 12 * 1024 * 1024
LABEL = ("Values transcribed from the photo by a vision model (digits only). "
         "Risk is model-estimated. Staged demo sheet, not a live factory integration.")


def _score(record: dict, values: dict) -> dict:
    result = service.score_values(values)
    record["result"] = result
    unreadable = (record.get("extracted") or {}).get("unreadable") or []
    record["status"] = "needs_review" if (result["needs_review"] or unreadable or
                                          result["unknown_parameters"]) else "ok"
    return record


def _process(raw: bytes, source: str) -> dict:
    cid = store.new_id()
    image_url = store.put_image(cid, vision.prepare(raw))
    out = vision.extract(raw, run_sheet.fields())
    record = {"id": cid, "created": store.now(), "source": source,
              "provider": out["provider"], "model": out["model"], "chain_log": out["chain_log"],
              "extracted": out["extracted"], "result": None, "image_url": image_url,
              "label": LABEL}
    if out["extracted"] and out["extracted"]["values"]:
        _score(record, out["extracted"]["values"])
    else:
        record["status"] = "failed"
        record["message"] = "Could not read the sheet. Retake the photo or use manual entry."
    record = clean(record)
    store.save(record)
    return record


@router.post("/captures")
async def create_capture(file: UploadFile = File(...), source: str = Form("upload")):
    if source not in ("upload", "webcam", "phone"):
        raise HTTPException(422, "source must be upload, webcam or phone")
    raw = await file.read()
    if not raw:
        raise HTTPException(422, "empty file")
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "image too large (max 12 MB)")
    try:
        return await run_in_threadpool(_process, raw, source)
    except OSError:
        raise HTTPException(422, "not a readable image")


class ManualCapture(BaseModel):
    values: dict[str, float] = Field(..., min_length=1)
    run_id: str | None = None


@router.post("/captures/manual")
def manual_capture(req: ManualCapture):
    record = {"id": store.new_id(), "created": store.now(), "source": "manual", "provider": "manual",
              "model": None, "chain_log": [], "extracted": {"run_id": req.run_id, "values": req.values,
                                                            "unreadable": []},
              "result": None, "image_url": None, "label": "Values entered by hand. Risk is model-estimated."}
    record = clean(_score(record, req.values))
    store.save(record)
    return record


@router.get("/captures")
def list_captures(limit: int = Query(50, le=500)):
    return {"captures": store.listing(limit)}


@router.get("/captures/latest")
def latest_capture():
    rec = store.latest()
    if rec is None:
        raise HTTPException(404, "no captures yet")
    return rec


@router.get("/captures/{cid}")
def get_capture(cid: str):
    rec = store.get(cid)
    if rec is None:
        raise HTTPException(404, "capture not found")
    return rec


@router.get("/captures/{cid}/image")
def capture_image(cid: str):
    if cloud.CLOUD:
        return RedirectResponse(cloud.blob_url(f"captures/{cid}.jpg"))
    p = store.image_path(cid)
    if not cid.startswith("c_") or not p.exists():
        raise HTTPException(404, "image not found")
    return FileResponse(p, media_type="image/jpeg")


@router.get("/run-sheet/fields")
def sheet_fields():
    return {"fields": run_sheet.fields()}


@router.get("/run-sheet")
def sheet(index: int | None = None, format: str = Query("png", pattern="^(png|json)$")):
    X, y, _, s = run_sheet.state.data
    if index is None:  # default: first failed run in the held-out test window
        fails = s.y_test[s.y_test == 1]
        index = int(fails.index[0])
    if index not in X.index:
        raise HTTPException(404, "run not found")
    if format == "json":
        return clean(run_sheet.sheet_values(index))
    return Response(run_sheet.render(index), media_type="image/png",
                    headers={"Content-Disposition": f'inline; filename="run_sheet_R-{index:04d}.png"'})
