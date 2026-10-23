"""Dents: align the sample scan to a good reference (ICP) and measure signed surface deviation."""
import numpy as np
import trimesh
from scipy.spatial import cKDTree

from backend.inspection.load import unit_scale_to_mm

REF_SAMPLES = 200_000
ICP_POINTS = 5_000


def _pca_frame(points):
    c = points.mean(axis=0)
    _, _, vt = np.linalg.svd(points - c, full_matrices=False)
    return c, vt


def align(sample: trimesh.Trimesh, reference: trimesh.Trimesh, seed=0) -> tuple[np.ndarray, float]:
    """Coarse PCA alignment (tries the 4 proper axis flips) followed by ICP. Returns (4x4, rms)."""
    rng = np.random.default_rng(seed)
    src = sample.vertices[rng.choice(len(sample.vertices), min(ICP_POINTS, len(sample.vertices)), replace=False)]
    cs, vs = _pca_frame(sample.vertices)
    cr, vr = _pca_frame(reference.vertices)
    # ICP against sampled surface points (KD-tree) rather than the mesh, which would need rtree
    target = trimesh.sample.sample_surface(reference, 30_000, seed=seed)[0]
    best = (None, np.inf)
    for signs in ([1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]):
        R = vr.T @ np.diag(signs) @ vs
        init = np.eye(4)
        init[:3, :3] = R
        init[:3, 3] = cr - R @ cs
        try:
            matrix, _, cost = trimesh.registration.icp(src, target, initial=init, max_iterations=40,
                                                       threshold=1e-6, reflection=False, scale=False)
        except Exception:  # noqa: BLE001 - ICP can fail on degenerate scans; try next flip
            continue
        if cost < best[1]:
            best = (matrix, cost)
    if best[0] is None:
        raise ValueError("could not align the scans")
    return best[0], float(np.sqrt(best[1]))


def deviation(sample: trimesh.Trimesh, reference: trimesh.Trimesh) -> np.ndarray:
    """Signed distance (sample units) from each sample vertex to the reference surface;
    positive = outward bump, negative = inward dent."""
    pts, face_idx = trimesh.sample.sample_surface(reference, REF_SAMPLES, seed=1)
    normals = reference.face_normals[face_idx]
    d, i = cKDTree(pts).query(sample.vertices)
    sign = np.sign(np.einsum("ij,ij->i", sample.vertices - pts[i], normals[i]))
    return d * np.where(sign == 0, 1, sign)


def detect(sample: trimesh.Trimesh, reference: trimesh.Trimesh | None, threshold_mm: float) -> dict:
    if reference is None:
        return {"enabled": False, "threshold_mm": threshold_mm,
                "reason": "dent detection needs a reference scan of a good part"}
    scale, unit = unit_scale_to_mm(reference)
    matrix, rms = align(sample, reference)
    moved = sample.copy()
    moved.apply_transform(matrix)
    dev_mm = deviation(moved, reference) * scale
    face_dev = dev_mm[sample.faces].mean(axis=1)
    above = np.abs(face_dev) > threshold_mm
    area_mm2 = moved.area_faces * scale ** 2
    return {
        "enabled": True,
        "threshold_mm": threshold_mm,
        "units": unit,
        "alignment_rms_mm": round(rms * scale, 2),
        "max_deviation_mm": round(float(np.abs(dev_mm).max()), 2),
        "p95_deviation_mm": round(float(np.percentile(np.abs(dev_mm), 95)), 2),
        "max_inward_mm": round(float(-dev_mm.min()), 2),
        "max_outward_mm": round(float(dev_mm.max()), 2),
        "area_above_threshold_cm2": round(float(area_mm2[above].sum() / 100), 2),
        "faces_above_threshold": int(above.sum()),
        "method": "PCA + ICP alignment to reference, signed point-to-surface distance",
        "_vertex_dev_mm": dev_mm, "_faces": above,
    }
