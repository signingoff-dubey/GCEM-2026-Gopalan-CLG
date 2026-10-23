"""Run an inspection on files and persist the result under data/inspection/<id>/."""
import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from backend.config import INSPECTION_DIR, SCANS_DIR
from backend.inspection import SENSOR_NOTE, cracks, dents, export
from backend.inspection.load import IMAGE_EXT, MESH_EXT, ScanError, describe, load_mesh


def analyze(mesh_path: Path, texture_path: Path | None = None, reference_path: Path | None = None,
            threshold_mm: float = 15.0, artificial: bool = False) -> dict:
    iid = "i_" + uuid.uuid4().hex[:10]
    out_dir = INSPECTION_DIR / iid
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        mesh = load_mesh(mesh_path, texture_path)
        ref = load_mesh(reference_path) if reference_path else None
        c = cracks.detect(mesh)
        d = dents.detect(mesh, ref, threshold_mm)
        export.export(mesh, c, d, out_dir / "model.glb")
    except (ScanError, ValueError) as e:
        shutil.rmtree(out_dir, ignore_errors=True)
        raise ScanError(str(e)) from e
    result = {
        "id": iid, "created": datetime.now().isoformat(timespec="seconds"), "status": "ok",
        "inputs": {"mesh": mesh_path.name, "texture": texture_path.name if texture_path else None,
                   "reference": reference_path.name if reference_path else None},
        "mesh": describe(mesh, mesh_path.suffix.lower().lstrip(".")),
        "cracks": export.public(c), "dents": export.public(d),
        "model_url": f"/api/inspection/{iid}/model.glb",
        "sensor_note": SENSOR_NOTE,
        "label": "analyzed after upload",
        "artificial": bool(artificial),
        "scope": "Separate capability: surface inspection of a scanned part, not root-cause analysis.",
    }
    if artificial:
        result["artificial_note"] = "artificial defect"
    (out_dir / "result.json").write_text(json.dumps(result, indent=2))
    return result


def get(iid: str) -> dict | None:
    p = INSPECTION_DIR / Path(iid).name / "result.json"
    return json.loads(p.read_text()) if p.exists() else None


def model_path(iid: str) -> Path | None:
    p = INSPECTION_DIR / Path(iid).name / "model.glb"
    return p if p.exists() else None


def listing() -> list[dict]:
    if not INSPECTION_DIR.exists():
        return []
    out = []
    for p in INSPECTION_DIR.glob("*/result.json"):
        r = json.loads(p.read_text())
        out.append({k: r.get(k) for k in ("id", "created", "status", "inputs", "artificial")} | {
            "cracks_found": r["cracks"].get("regions"), "max_deviation_mm": r["dents"].get("max_deviation_mm")})
    return sorted(out, key=lambda r: r["created"], reverse=True)


def samples() -> dict:
    SCANS_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for p in sorted(SCANS_DIR.rglob("*")):
        ext = p.suffix.lower()
        if p.is_file() and (ext in MESH_EXT or ext in IMAGE_EXT):
            files.append({"name": str(p.relative_to(SCANS_DIR)).replace("\\", "/"),
                          "kind": "mesh" if ext in MESH_EXT else "texture", "size": p.stat().st_size})
    return {"folder": str(SCANS_DIR), "files": files}


def sample_path(name: str | None) -> Path | None:
    """Resolve a name from the samples folder, refusing anything outside it."""
    if not name:
        return None
    p = (SCANS_DIR / name).resolve()
    if SCANS_DIR.resolve() not in p.parents or not p.is_file():
        raise ScanError(f"sample not found: {name}")
    return p
