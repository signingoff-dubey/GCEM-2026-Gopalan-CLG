"""Turn an upload into something the browser viewer can load: GLB (preferred), a zipped .gltf
folder, OBJ/PLY/STL via trimesh, or .blend via a local headless Blender when one is configured."""
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from urllib.parse import unquote

import numpy as np
import trimesh

from backend.assembly.gltf import GltfError, read_glb, write_glb

ACCEPTED = {".glb", ".zip", ".gltf", ".obj", ".ply", ".stl", ".blend"}
BLEND_TIMEOUT_S = 240
EXPORT_SCRIPT = (
    "import bpy, sys\n"
    "out = sys.argv[sys.argv.index('--') + 1]\n"
    "bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', export_extras=True,\n"
    "    export_animations=True, export_apply=True, export_yup=True)\n"
)


class ConvertError(ValueError):
    pass


def blender_path() -> str | None:
    p = os.getenv("BLENDER_PATH") or shutil.which("blender")
    if p and Path(p).exists():
        return p
    for base in (Path("C:/Program Files/Blender Foundation"), Path("/Applications/Blender.app/Contents/MacOS")):
        if base.exists():
            hits = sorted(base.rglob("blender.exe" if os.name == "nt" else "Blender"))
            if hits:
                return str(hits[-1])
    return None


def _from_blend(src: Path, out: Path) -> None:
    exe = blender_path()
    if not exe:
        raise ConvertError("Blender is not installed on the server. In Blender use File > Export > glTF 2.0 "
                           "(.glb) with Custom Properties and Animation on, then upload the .glb.")
    script = out.with_suffix(".export.py")
    script.write_text(EXPORT_SCRIPT)
    # -Y: never auto-run Python embedded in the uploaded .blend; factory settings, no add-ons
    cmd = [exe, "-b", "--factory-startup", "-Y", str(src), "--python", str(script), "--", str(out)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=BLEND_TIMEOUT_S)
    except subprocess.TimeoutExpired as e:
        raise ConvertError(f"Blender export timed out after {BLEND_TIMEOUT_S} s") from e
    finally:
        script.unlink(missing_ok=True)
    if r.returncode != 0 or not out.exists():
        raise ConvertError("Blender export failed: " + (r.stderr or r.stdout)[-400:])


def _safe_extract(zip_path: Path, dest: Path) -> Path:
    with zipfile.ZipFile(zip_path) as z:
        total = sum(i.file_size for i in z.infolist())
        if total > 500 * 1024 * 1024:
            raise ConvertError("zip expands to more than 500 MB")
        for info in z.infolist():
            target = (dest / info.filename).resolve()
            if dest.resolve() not in target.parents and target != dest.resolve():
                raise ConvertError(f"unsafe path in zip: {info.filename}")
        z.extractall(dest)
    gltfs = [p for p in dest.rglob("*") if p.suffix.lower() in (".gltf", ".glb")]
    if len(gltfs) != 1:
        raise ConvertError(f"zip must contain exactly one .gltf or .glb, found {len(gltfs)}")
    return gltfs[0]


def _check_uris(doc: dict, root: Path) -> None:
    for kind in ("buffers", "images"):
        for item in doc.get(kind, []):
            uri = item.get("uri")
            if not uri or uri.startswith("data:"):
                continue
            if "://" in uri or uri.startswith(("/", "\\")):
                raise ConvertError(f"external or absolute URI not allowed: {uri}")
            p = (root / unquote(uri)).resolve()
            if root.resolve() not in p.parents:
                raise ConvertError(f"URI escapes the model folder: {uri}")
            if not p.exists():
                raise ConvertError(f"missing file referenced by the model: {uri}")


def _obj_parts(path: Path) -> trimesh.Scene:
    """One part per `o` / `g` block (trimesh merges them). Geometry only; prefer GLB for materials."""
    verts, parts, name = [], {}, "part_0"
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        tok = line.split()
        if not tok:
            continue
        if tok[0] == "v":
            verts.append([float(x) for x in tok[1:4]])
        elif tok[0] in ("o", "g") and len(tok) > 1:
            name = "_".join(tok[1:])
        elif tok[0] == "f":
            idx = [int(t.split("/")[0]) for t in tok[1:]]
            idx = [i - 1 if i > 0 else len(verts) + i for i in idx]
            parts.setdefault(name, []).extend([idx[0], idx[k], idx[k + 1]] for k in range(1, len(idx) - 1))
    if not parts:
        raise ConvertError("OBJ has no faces")
    v = np.asarray(verts, float)
    scene = trimesh.Scene()
    for n, faces in parts.items():
        f = np.asarray(faces)
        used, inv = np.unique(f, return_inverse=True)
        scene.add_geometry(trimesh.Trimesh(v[used], inv.reshape(-1, 3), process=False), node_name=n, geom_name=n)
    return scene


def prepare(upload: Path, work: Path) -> dict:
    """Returns {kind: 'glb'|'gltf', path, doc, binary, source_format}. `work` is a scratch folder."""
    ext = upload.suffix.lower()
    if ext not in ACCEPTED:
        raise ConvertError(f"unsupported file type {ext}; use .glb (preferred), a zipped .gltf folder, "
                           ".obj, .ply, .stl or .blend")
    try:
        if ext == ".blend":
            out = work / "model.glb"
            _from_blend(upload, out)
            doc, binary = read_glb(out.read_bytes())
            return {"kind": "glb", "path": out, "doc": doc, "binary": binary, "source_format": "blend"}
        if ext == ".zip":
            folder = work / "gltf"
            folder.mkdir()
            inner = _safe_extract(upload, folder)
            if inner.suffix.lower() == ".glb":
                upload, ext = inner, ".glb"
            else:
                import json
                doc = json.loads(inner.read_text(encoding="utf-8"))
                _check_uris(doc, inner.parent)
                return {"kind": "gltf", "path": inner, "doc": doc, "binary": b"", "source_format": "gltf"}
        if ext == ".gltf":
            raise ConvertError("a .gltf references other files; upload the folder as a .zip, or export .glb")
        if ext == ".glb":
            doc, binary = read_glb(upload.read_bytes())
            return {"kind": "glb", "path": upload, "doc": doc, "binary": binary, "source_format": "glb"}
        scene = _obj_parts(upload) if ext == ".obj" else trimesh.load(upload, force="scene", process=False)
        out = work / "model.glb"
        out.write_bytes(scene.export(file_type="glb"))
        doc, binary = read_glb(out.read_bytes())
        return {"kind": "glb", "path": out, "doc": doc, "binary": binary, "source_format": ext.lstrip(".")}
    except (GltfError, zipfile.BadZipFile, UnicodeDecodeError, ValueError) as e:
        if isinstance(e, ConvertError):
            raise
        raise ConvertError(f"could not read the model: {e}") from e


__all__ = ["prepare", "ConvertError", "ACCEPTED", "blender_path", "write_glb"]
