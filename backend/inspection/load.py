"""Load a scanned mesh (OBJ/PLY/GLB/GLTF/STL) and an optional texture image."""
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image

MESH_EXT = {".obj", ".ply", ".glb", ".gltf", ".stl"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


class ScanError(ValueError):
    pass


def load_mesh(path: Path, texture: Path | None = None) -> trimesh.Trimesh:
    if path.suffix.lower() not in MESH_EXT:
        raise ScanError(f"unsupported mesh format {path.suffix}")
    try:
        loaded = trimesh.load(path, force="mesh", process=False)
    except Exception as e:  # noqa: BLE001 - trimesh raises many types on bad files
        raise ScanError(f"could not read mesh: {e}") from e
    if not isinstance(loaded, trimesh.Trimesh) or len(loaded.faces) == 0:
        raise ScanError("file contains no triangle mesh")
    mesh = loaded
    if texture is not None:
        uv = getattr(mesh.visual, "uv", None)
        if uv is None or len(uv) != len(mesh.vertices):
            raise ScanError("texture given but the mesh has no UV coordinates")
        img = Image.open(texture).convert("RGB")
        mesh.visual = trimesh.visual.TextureVisuals(
            uv=uv, material=trimesh.visual.material.SimpleMaterial(image=img))
    return mesh


def texture_image(mesh: trimesh.Trimesh) -> Image.Image | None:
    vis = mesh.visual
    if not isinstance(vis, trimesh.visual.TextureVisuals) or vis.uv is None:
        return None
    mat = vis.material
    img = getattr(mat, "image", None) or getattr(mat, "baseColorTexture", None)
    return img.convert("RGB") if img is not None else None


def unit_scale_to_mm(mesh: trimesh.Trimesh) -> tuple[float, str]:
    """Scanner apps export metres; CAD/STL is usually mm. Guess from the object size."""
    size = float(np.max(mesh.extents))
    if size < 10:        # under 10 units across: metres
        return 1000.0, "m (assumed)"
    if size < 100:       # 10-100: centimetres
        return 10.0, "cm (assumed)"
    return 1.0, "mm (assumed)"


def describe(mesh: trimesh.Trimesh, fmt: str) -> dict:
    scale, unit = unit_scale_to_mm(mesh)
    vc = getattr(mesh.visual, "vertex_colors", None) if mesh.visual.kind == "vertex" else None
    return {
        "vertices": int(len(mesh.vertices)), "faces": int(len(mesh.faces)),
        "extent_mm": [round(float(e) * scale, 1) for e in mesh.extents],
        "units": unit, "format": fmt,
        "has_texture": texture_image(mesh) is not None,
        "has_colors": vc is not None and len(vc) == len(mesh.vertices),
        "watertight": bool(mesh.is_watertight),
    }
