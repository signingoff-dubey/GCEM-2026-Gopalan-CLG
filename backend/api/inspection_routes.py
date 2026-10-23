"""3D-scan inspection endpoints. Separate capability, not root-cause analysis."""
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.inspection import service
from backend.inspection.load import IMAGE_EXT, MESH_EXT, ScanError

router = APIRouter(prefix="/api/inspection", tags=["inspection"])
MAX_BYTES = 300 * 1024 * 1024


async def _save(upload: UploadFile | None, allowed: set, folder: Path) -> Path | None:
    if upload is None or not upload.filename:
        return None
    ext = Path(upload.filename).suffix.lower()
    if ext not in allowed:
        raise HTTPException(422, f"unsupported file type {ext}")
    data = await upload.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "file too large (max 300 MB)")
    p = folder / (Path(upload.filename).stem[:40] + ext)
    p.write_bytes(data)
    return p


@router.post("/scan")
async def scan(mesh: UploadFile = File(...), texture: UploadFile | None = File(None),
               reference: UploadFile | None = File(None), threshold_mm: float = Form(15.0),
               artificial: bool = Form(False)):
    if not 1 <= threshold_mm <= 200:
        raise HTTPException(422, "threshold_mm must be between 1 and 200")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        m = await _save(mesh, MESH_EXT, tmp)
        t = await _save(texture, IMAGE_EXT, tmp)
        ref_dir = tmp / "ref"
        ref_dir.mkdir()
        r = await _save(reference, MESH_EXT, ref_dir)
        try:
            return await run_in_threadpool(service.analyze, m, t, r, threshold_mm, artificial)
        except ScanError as e:
            raise HTTPException(422, str(e))


@router.get("/samples")
def samples():
    return service.samples()


class SampleRequest(BaseModel):
    mesh: str
    texture: str | None = None
    reference: str | None = None
    threshold_mm: float = Field(15.0, ge=1, le=200)
    artificial: bool = False


@router.post("/samples/analyze")
async def analyze_sample(req: SampleRequest):
    try:
        paths = [service.sample_path(n) for n in (req.mesh, req.texture, req.reference)]
        return await run_in_threadpool(service.analyze, *paths, req.threshold_mm, req.artificial)
    except ScanError as e:
        raise HTTPException(422, str(e))


@router.get("")
def listing():
    return {"inspections": service.listing()}


@router.get("/{iid}")
def get_one(iid: str):
    r = service.get(iid)
    if r is None:
        raise HTTPException(404, "inspection not found")
    return r


@router.get("/{iid}/model.glb")
def model(iid: str):
    p = service.model_path(iid)
    if p is None:
        raise HTTPException(404, "model not found")
    return FileResponse(p, media_type="model/gltf-binary")


@router.get("/{iid}/parts.glb")
def parts_model(iid: str):
    """The original multi-part model, so the viewer can play its animation and explode it."""
    p = service.model_path(iid, "parts.glb")
    if p is None:
        raise HTTPException(404, "model not found")
    return FileResponse(p, media_type="model/gltf-binary")
