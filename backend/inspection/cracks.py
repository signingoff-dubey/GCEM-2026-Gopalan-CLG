"""Crack candidates in the colour texture, mapped back to mesh faces through UVs.

Cracks are thin, dark, elongated lines. A black-hat filter picks out thin dark structure,
a ridge filter confirms line shape, and connected components are kept only if long and thin.
"""
import cv2
import numpy as np
import trimesh
from PIL import Image
from skimage import measure, morphology

from backend.inspection.load import texture_image


def crack_mask(img: Image.Image, min_length_frac=0.06, min_elongation=5.0, min_contrast=35) -> tuple[np.ndarray, list[dict]]:
    gray = np.asarray(img.convert("L"))
    h, w = gray.shape
    scale = 2048 / max(h, w) if max(h, w) > 2048 else 1.0
    if scale != 1.0:
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    k = max(9, int(min(gray.shape) * 0.012) | 1)
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    blackhat = cv2.GaussianBlur(blackhat, (3, 3), 0)
    thr, _ = cv2.threshold(blackhat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mask = blackhat > max(thr, min_contrast)
    mask = morphology.remove_small_objects(mask, max(20, int(mask.size * 2e-5)))

    labels = measure.label(mask, connectivity=2)
    keep = np.zeros_like(mask)
    regions = []
    min_len = min_length_frac * max(gray.shape)
    for r in measure.regionprops(labels):
        major = r.axis_major_length
        minor = max(r.axis_minor_length, 1.0)
        if major >= min_len and major / minor >= min_elongation:
            keep[labels == r.label] = True
            regions.append({"length_px": round(float(major / scale), 1),
                            "elongation": round(float(major / minor), 1),
                            "bbox": [int(v / scale) for v in r.bbox]})
    if scale != 1.0:
        keep = cv2.resize(keep.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST).astype(bool)
    return keep, regions


def faces_on_mask(mesh: trimesh.Trimesh, mask: np.ndarray) -> np.ndarray:
    """Faces whose UV footprint touches the mask (centroid + vertices sampled)."""
    uv = mesh.visual.uv
    h, w = mask.shape
    fat = cv2.dilate(mask.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    tri_uv = uv[mesh.faces]                       # (F, 3, 2)
    pts = np.concatenate([tri_uv, tri_uv.mean(axis=1, keepdims=True)], axis=1)  # (F, 4, 2)
    u = np.clip((pts[..., 0] % 1.0) * (w - 1), 0, w - 1).astype(int)
    v = np.clip((1 - (pts[..., 1] % 1.0)) * (h - 1), 0, h - 1).astype(int)
    return fat[v, u].any(axis=1)


def detect(mesh: trimesh.Trimesh) -> dict:
    img = texture_image(mesh)
    if img is None:
        return {"enabled": False, "reason": "no colour texture with UVs; cracks are only searched in texture"}
    mask, regions = crack_mask(img)
    flagged = faces_on_mask(mesh, mask) if regions else np.zeros(len(mesh.faces), bool)
    area = mesh.area_faces
    return {
        "enabled": True,
        "regions": len(regions),
        "region_details": regions[:20],
        "faces_flagged": int(flagged.sum()),
        "area_frac": float(area[flagged].sum() / area.sum()) if area.sum() > 0 else 0.0,
        "texture_px_frac": float(mask.mean()),
        "method": "black-hat + elongation filter on the texture, mapped to faces via UV",
        "_faces": flagged, "_mask": mask,
    }
