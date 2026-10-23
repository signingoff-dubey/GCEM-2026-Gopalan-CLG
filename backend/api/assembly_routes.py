"""Assembly endpoints for the "View damage" demo: upload a Blender export (or .blend when Blender
is installed on the server), inspect parts / damage / thermal / animations, map parts to stations."""
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.assembly import service
from backend.assembly.convert import ACCEPTED, ConvertError, blender_path

router = APIRouter(prefix="/api/assembly", tags=["assembly"])
MAX_BYTES = 300 * 1024 * 1024
MEDIA = {".glb": "model/gltf-binary", ".gltf": "model/gltf+json", ".bin": "application/octet-stream",
         ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
         ".ktx2": "image/ktx2"}


@router.get("/capabilities")
def capabilities():
    return {"accepted": sorted(ACCEPTED), "blend_conversion": blender_path() is not None,
            "preferred": ".glb with Custom Properties and Animation exported",
            "contract": {"extras_prefix": "rootlens_", "thermal_attribute": "COLOR_0",
                         "animations": ["disassembly", "damage_reveal (optional)"]}}


@router.post("")
async def upload(file: UploadFile = File(...), label: str | None = Form(None)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ACCEPTED:
        raise HTTPException(422, f"unsupported file type {ext or '(none)'}; accepted: {sorted(ACCEPTED)}")
    data = await file.read()
    if not data:
        raise HTTPException(422, "empty file")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "file too large (max 300 MB)")
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / ("upload" + ext)
        p.write_bytes(data)
        named = p.with_name(Path(file.filename).stem[:60] + ext)
        p.rename(named)
        try:
            return await run_in_threadpool(service.register, named, label)
        except ConvertError as e:
            raise HTTPException(422, str(e))


@router.get("/samples")
def samples():
    return service.samples()


class SampleRequest(BaseModel):
    name: str
    label: str | None = None


@router.post("/samples/load")
async def load_sample(req: SampleRequest):
    try:
        if req.name.startswith("builtin:"):
            return await run_in_threadpool(service.load_builtin, req.name)
        return await run_in_threadpool(service.register, service.sample_path(req.name), req.label)
    except ConvertError as e:
        raise HTTPException(422, str(e))


@router.get("/demo")
async def demo():
    """Shortcut for the "View damage" button: the built-in sample, created on first use."""
    return await run_in_threadpool(service.load_builtin, "builtin:power_bank")


@router.get("")
def listing():
    return {"assemblies": service.listing()}


@router.get("/{aid}")
def get_one(aid: str):
    m = service.get(aid)
    if m is None:
        raise HTTPException(404, "assembly not found")
    return m


@router.get("/{aid}/model.glb")
def model(aid: str):
    p = service.model_file(aid)
    if p is None:
        raise HTTPException(404, "model not found")
    return FileResponse(p, media_type="model/gltf-binary")


@router.get("/{aid}/files/{rel:path}")
def model_files(aid: str, rel: str):
    p = service.model_file(aid, rel)
    if p is None:
        raise HTTPException(404, "file not found")
    return FileResponse(p, media_type=MEDIA.get(p.suffix.lower(), "application/octet-stream"))


class MappingRequest(BaseModel):
    mapping: dict[str, str | None]


@router.put("/{aid}/mapping")
def put_mapping(aid: str, req: MappingRequest):
    try:
        return {"mapping": service.set_mapping(aid, req.mapping),
                "label": "Illustrative, user-defined part-to-station mapping."}
    except LookupError:
        raise HTTPException(404, "assembly not found")
    except ConvertError as e:
        raise HTTPException(422, str(e))


@router.get("/{aid}/overlay")
def get_overlay(aid: str):
    try:
        return service.overlay(aid)
    except LookupError:
        raise HTTPException(404, "assembly not found")
