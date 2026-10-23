"""Write a highlighted GLB: cracks in red over the texture, dents as a blue-to-red heat map."""
import numpy as np
import trimesh
from PIL import Image

from backend.inspection.load import texture_image

CRACK_RGB = np.array([230, 30, 30], np.uint8)


def _heat(dev_mm: np.ndarray, threshold_mm: float) -> np.ndarray:
    """Grey below the threshold; blue (inward) / red (outward) above it, saturating at 3x."""
    t = np.clip((np.abs(dev_mm) - threshold_mm) / (2 * threshold_mm), 0, 1)
    grey = np.array([190, 190, 190], float)
    hot = np.where((dev_mm < 0)[:, None], np.array([40, 90, 255], float), np.array([255, 70, 40], float))
    out = np.where((np.abs(dev_mm) > threshold_mm)[:, None], grey * (1 - (0.4 + 0.6 * t))[:, None]
                   + hot * (0.4 + 0.6 * t)[:, None], grey)
    return np.c_[out.astype(np.uint8), np.full(len(out), 255, np.uint8)]


def export(mesh: trimesh.Trimesh, cracks: dict, dents: dict, path) -> None:
    out = mesh.copy()
    img = texture_image(mesh)
    crack_faces = cracks.get("_faces") if cracks.get("enabled") else None
    if dents.get("enabled"):
        colors = _heat(dents["_vertex_dev_mm"], dents["threshold_mm"])
        if crack_faces is not None and crack_faces.any():
            colors[np.unique(mesh.faces[crack_faces])] = np.r_[CRACK_RGB, 255]
        out.visual = trimesh.visual.ColorVisuals(out, vertex_colors=colors)
    elif img is not None and cracks.get("enabled"):
        arr = np.array(img)
        mask = cracks["_mask"]
        if mask.shape != arr.shape[:2]:
            mask = np.array(Image.fromarray(mask.astype(np.uint8) * 255).resize(img.size)) > 0
        arr[mask] = CRACK_RGB
        out.visual = trimesh.visual.TextureVisuals(
            uv=mesh.visual.uv, material=trimesh.visual.material.SimpleMaterial(image=Image.fromarray(arr)))
    elif mesh.visual.kind != "vertex" or img is not None:
        out.visual = trimesh.visual.ColorVisuals(out, vertex_colors=np.tile([190, 190, 190, 255], (len(out.vertices), 1)))
    out.export(path, file_type="glb")


def public(d: dict) -> dict:
    """Drop the private arrays before returning JSON."""
    return {k: v for k, v in d.items() if not k.startswith("_")}
