"""Synthetic fixtures with known defects: a bump of known height and a drawn crack line."""
import numpy as np
import pytest
import trimesh
from PIL import Image, ImageDraw

from backend.inspection import cracks, dents, service
from backend.inspection.load import ScanError, load_mesh


def grid_plane(n=80, size=0.3, bump_mm=0.0):
    """size in metres (like a scanner export); optional gaussian bump in the centre."""
    xs = np.linspace(-size / 2, size / 2, n)
    X, Y = np.meshgrid(xs, xs)
    Z = (bump_mm / 1000) * np.exp(-((X ** 2 + Y ** 2) / (2 * 0.02 ** 2)))
    verts = np.c_[X.ravel(), Y.ravel(), Z.ravel()]
    faces = []
    for i in range(n - 1):
        for j in range(n - 1):
            a = i * n + j
            faces += [[a, a + 1, a + n], [a + 1, a + n + 1, a + n]]
    uv = np.c_[(X.ravel() + size / 2) / size, (Y.ravel() + size / 2) / size]
    return trimesh.Trimesh(verts, np.array(faces), process=False), uv


def textured_plane_with_line():
    mesh, uv = grid_plane()
    img = Image.new("RGB", (1024, 1024), (200, 200, 200))
    rng = np.random.default_rng(0)
    arr = np.clip(np.asarray(img, float) + rng.normal(0, 6, (1024, 1024, 3)), 0, 255).astype(np.uint8)
    img = Image.fromarray(arr)
    ImageDraw.Draw(img).line([(200, 300), (820, 700)], fill=(40, 40, 40), width=4)
    mesh.visual = trimesh.visual.TextureVisuals(uv=uv, material=trimesh.visual.material.SimpleMaterial(image=img))
    return mesh


def test_crack_line_is_found_and_mapped_to_faces():
    mesh = textured_plane_with_line()
    res = cracks.detect(mesh)
    assert res["enabled"] and res["regions"] >= 1
    assert 0 < res["area_frac"] < 0.2


def test_clean_texture_has_no_cracks():
    mesh, uv = grid_plane()
    rng = np.random.default_rng(1)
    img = Image.fromarray(np.clip(200 + rng.normal(0, 6, (512, 512, 3)), 0, 255).astype(np.uint8))
    mesh.visual = trimesh.visual.TextureVisuals(uv=uv, material=trimesh.visual.material.SimpleMaterial(image=img))
    assert cracks.detect(mesh)["regions"] == 0


def test_cracks_disabled_without_texture():
    mesh, _ = grid_plane()
    assert cracks.detect(mesh)["enabled"] is False


def test_known_bump_is_measured():
    ref, _ = grid_plane(bump_mm=0)
    sample, _ = grid_plane(bump_mm=25)
    sample.apply_translation([0.01, -0.005, 0.002])  # misplaced scan; ICP must undo it
    res = dents.detect(sample, ref, threshold_mm=10)
    assert res["enabled"]
    assert 18 <= res["max_deviation_mm"] <= 30
    assert res["area_above_threshold_cm2"] > 0


def test_identical_scans_have_no_dent():
    ref, _ = grid_plane()
    res = dents.detect(ref.copy(), ref, threshold_mm=10)
    assert res["max_deviation_mm"] < 3 and res["faces_above_threshold"] == 0


def test_dents_need_reference():
    mesh, _ = grid_plane()
    assert dents.detect(mesh, None, 15)["enabled"] is False


def test_end_to_end_writes_glb(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "INSPECTION_DIR", tmp_path / "out")
    mesh = textured_plane_with_line()
    p = tmp_path / "scan.glb"
    mesh.export(p)
    res = service.analyze(p, artificial=True)
    assert res["label"] == "analyzed after upload" and res["artificial_note"] == "artificial defect"
    assert (tmp_path / "out" / res["id"] / "model.glb").stat().st_size > 0
    assert "_faces" not in res["cracks"]


def test_bad_file_rejected(tmp_path):
    p = tmp_path / "x.obj"
    p.write_text("not a mesh")
    with pytest.raises(ScanError):
        load_mesh(p)


def test_sample_path_blocks_traversal():
    with pytest.raises(ScanError):
        service.sample_path("../../.env")
