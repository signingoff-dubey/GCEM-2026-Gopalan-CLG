"""Run an inspection on files and persist the result under data/inspection/<id>/."""
import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from backend.assembly.gltf import GltfError, read_glb
from backend.assembly.inspect import summarize
from backend.config import INSPECTION_DIR, ROOT, SCANS_DIR
from backend.inspection import SENSOR_NOTE, cracks, dents, export
from backend.inspection.load import IMAGE_EXT, MESH_EXT, ScanError, describe, load_mesh


BLENDER_DIR = ROOT / "assets" / "blender"     # the Blender team's exported models, offered as samples too
PART_KEYS = ("counts", "bounds", "animations", "damage", "thermal", "view_damage", "warnings", "note")


def _parts(mesh_path: Path, out_dir: Path, iid: str) -> dict | None:
    """A multi-part .glb keeps its parts: damage per part, simulated heat, animation and explode in the viewer."""
    if mesh_path.suffix.lower() != ".glb":
        return None
    try:
        doc, binary = read_glb(mesh_path.read_bytes())
        s = summarize(doc, binary)
    except (GltfError, ValueError, KeyError):
        return None
    if s["counts"]["parts"] < 2:
        return None
    shutil.copyfile(mesh_path, out_dir / "parts.glb")
    return {"id": iid, "model_url": f"/api/inspection/{iid}/parts.glb", **{k: s[k] for k in PART_KEYS},
            "parts": [{k: p[k] for k in ("node", "name", "display_name", "role", "damage", "temp_c", "bbox")} for p in s["parts"]]}


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
        parts = _parts(mesh_path, out_dir, iid)
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
    if parts:
        result["parts"] = parts
    if artificial:
        result["artificial_note"] = "artificial defect"
    (out_dir / "result.json").write_text(json.dumps(result, indent=2))
    return result


def get(iid: str) -> dict | None:
    p = INSPECTION_DIR / Path(iid).name / "result.json"
    return json.loads(p.read_text()) if p.exists() else None


def model_path(iid: str, name: str = "model.glb") -> Path | None:
    p = INSPECTION_DIR / Path(iid).name / name
    return p if p.exists() else None


def listing() -> list[dict]:
    if not INSPECTION_DIR.exists():
        return []
    out = []
    for p in INSPECTION_DIR.glob("*/result.json"):
        r = json.loads(p.read_text())
        out.append({k: r.get(k) for k in ("id", "created", "status", "inputs", "artificial")} | {
            "cracks_found": r["cracks"].get("regions"), "max_deviation_mm": r["dents"].get("max_deviation_mm"),
            "dent_faces": r["dents"].get("faces_above_threshold") or 0, "dent_threshold_mm": r["dents"].get("threshold_mm"),
            "part_damage": (r.get("parts") or {}).get("damage", [])})
    return sorted(out, key=lambda r: r["created"], reverse=True)


def samples() -> dict:
    SCANS_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for p in sorted(SCANS_DIR.rglob("*")):
        ext = p.suffix.lower()
        if p.is_file() and (ext in MESH_EXT or ext in IMAGE_EXT):
            files.append({"name": str(p.relative_to(SCANS_DIR)).replace("\\", "/"),
                          "kind": "mesh" if ext in MESH_EXT else "texture", "size": p.stat().st_size})
    if BLENDER_DIR.exists():
        for p in sorted(BLENDER_DIR.rglob("*.glb")):
            files.append({"name": "blender/" + p.relative_to(BLENDER_DIR).as_posix(), "kind": "mesh",
                          "size": p.stat().st_size, "group": "Blender models"})
    return {"folder": str(SCANS_DIR), "files": files}


def sample_path(name: str | None) -> Path | None:
    """Resolve a name from the samples folder, refusing anything outside it."""
    if not name:
        return None
    root, rel = (BLENDER_DIR, name[len("blender/"):]) if name.startswith("blender/") else (SCANS_DIR, name)
    p = (root / rel).resolve()
    if root.resolve() not in p.parents or not p.is_file():
        raise ScanError(f"sample not found: {name}")
    return p
