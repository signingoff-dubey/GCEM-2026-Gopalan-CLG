import io
import json
import zipfile

import pytest
import trimesh
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.assembly import convert, demo, service
from backend.assembly.gltf import read_glb, write_glb
from backend.assembly.inspect import summarize


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "ASSEMBLY_DIR", tmp_path / "assemblies")
    monkeypatch.setattr(service, "MODELS_DIRS", [tmp_path / "models"])
    (tmp_path / "models").mkdir()
    return TestClient(app)


def test_demo_follows_contract():
    s = summarize(*read_glb(demo.build()))
    assert s["counts"]["parts"] >= 10 and s["counts"]["animations"] == 2
    assert [a["name"] for a in s["animations"]] == ["disassembly", "damage_reveal"]
    d = s["damage"][0]
    assert d["part"] == "battery_cell_2" and d["type"] == "crack" and d["internal"] is True
    assert s["thermal"]["attribute"] == "COLOR_0" and s["thermal"]["max_c"] >= 75
    assert s["view_damage"]["focus_part"] == "battery_cell_2"
    assert s["view_damage"]["animation"] == "disassembly"
    assert not s["warnings"]


def test_glb_roundtrip_keeps_extras():
    doc, binary = read_glb(demo.build())
    doc2, binary2 = read_glb(write_glb(doc, binary))
    assert doc2["nodes"][1]["extras"] == doc["nodes"][1]["extras"] and binary2[:len(binary)] == binary


def test_demo_endpoint_and_model(client):
    m = client.get("/api/assembly/demo").json()
    assert m["id"] == "demo_power_bank" and m["view_damage"]["isolate"]
    r = client.get(m["model_url"])
    assert r.status_code == 200 and r.content[:4] == b"glTF"
    assert client.get("/api/assembly/demo").json()["created"] == m["created"]  # cached


def test_upload_glb_and_mapping_overlay(client):
    r = client.post("/api/assembly", files={"file": ("sample.glb", demo.build(), "model/gltf-binary")},
                    data={"label": "test"})
    m = r.json()
    assert r.status_code == 200 and m["label"] == "test"
    ok = client.put(f"/api/assembly/{m['id']}/mapping", json={"mapping": {"pcb_main": "L1_S24"}})
    assert ok.status_code == 200
    bad = client.put(f"/api/assembly/{m['id']}/mapping", json={"mapping": {"pcb_main": "station 4"}})
    assert bad.status_code == 422
    unknown = client.put(f"/api/assembly/{m['id']}/mapping", json={"mapping": {"nope": "L1_S24"}})
    assert unknown.status_code == 422
    ov = client.get(f"/api/assembly/{m['id']}/overlay").json()
    row = next(p for p in ov["parts"] if p["part"] == "pcb_main")
    assert row["station"] == "L1_S24" and "Illustrative" in ov["mapping_label"]


def test_single_mesh_warns(client):
    glb = trimesh.Scene(trimesh.creation.box()).export(file_type="glb")
    m = client.post("/api/assembly", files={"file": ("scan.glb", glb, "model/gltf-binary")}).json()
    assert any("single mesh" in w for w in m["warnings"]) and m["view_damage"] is None


def test_obj_groups_become_parts(client, tmp_path):
    scene = trimesh.Scene()
    scene.add_geometry(trimesh.creation.box(), node_name="lid", geom_name="lid")
    scene.add_geometry(trimesh.creation.icosphere().apply_translation([3, 0, 0]), node_name="core", geom_name="core")
    obj = scene.export(file_type="obj")
    m = client.post("/api/assembly", files={"file": ("thing.obj", obj, "text/plain")}).json()
    assert m["counts"]["parts"] == 2


def test_gltf_zip_with_traversal_rejected(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("model.gltf", json.dumps({"asset": {"version": "2.0"}}))
        z.writestr("../evil.txt", "x")
    r = client.post("/api/assembly", files={"file": ("m.zip", buf.getvalue(), "application/zip")})
    assert r.status_code == 422 and "unsafe" in r.json()["detail"]


def test_gltf_external_uri_rejected(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("model.gltf", json.dumps({"asset": {"version": "2.0"},
                                             "buffers": [{"uri": "https://example.com/x.bin", "byteLength": 4}]}))
    r = client.post("/api/assembly", files={"file": ("m.zip", buf.getvalue(), "application/zip")})
    assert r.status_code == 422 and "external" in r.json()["detail"]


def test_blend_without_blender_explains(client, monkeypatch):
    monkeypatch.setattr(convert, "blender_path", lambda: None)
    r = client.post("/api/assembly", files={"file": ("dev.blend", b"BLENDER-v300", "application/octet-stream")})
    assert r.status_code == 422 and "Export" in r.json()["detail"]


def test_bad_inputs(client):
    assert client.post("/api/assembly", files={"file": ("x.fbx", b"abc", "x")}).status_code == 422
    assert client.post("/api/assembly", files={"file": ("x.glb", b"not a glb at all!!!!", "x")}).status_code == 422
    assert client.get("/api/assembly/missing/model.glb").status_code == 404
    assert client.get("/api/assembly/demo_power_bank/files/../../manifest.json").status_code == 404


def test_activity_lists_new_events(client):
    before = client.get("/api/activity").json()
    client.get("/api/assembly/demo")
    after = client.get("/api/activity").json()
    assert after["version"] != before["version"]
    today = next(d for d in after["days"] if d["date"] == after["today"])
    assert today["assembly"] >= 1 and after["recent"][0]["kind"] == "assembly"


def test_damage_inferred_from_object_names():
    from backend.config import ROOT
    glb = ROOT / "assets" / "blender" / "semiconductor" / "semiconductor_internal_fault.glb"
    if not glb.exists():
        pytest.skip("Blender team asset not present")
    s = summarize(*read_glb(glb.read_bytes()))
    assert s["view_damage"]["focus_part"] == "Die"
    die = next(d for d in s["damage"] if d["part"] == "Die")
    assert die["type"] == "crack" and die["internal"] and die["inferred"]
    assert {"WireStub0_4", "WireLift2_3"} <= {d["part"] for d in s["damage"]}
    assert "DieCrack" in s["view_damage"]["isolate"] and s["thermal"]["available"]
    assert any("inferred from object names" in w for w in s["warnings"])


def test_own_tags_skip_inference():
    s = summarize(*read_glb(demo.build()))
    assert not any("inferred" in w for w in s["warnings"])
