"""The deployed (Firebase) code paths, run against an in-memory stand-in for Firestore and Storage."""
import json

import pytest
from fastapi.testclient import TestClient

from backend import cloud, seed
from backend.alerts import service as alerts
from backend.api.main import app
from backend.assembly import demo
from backend.config import ROOT


class Fake:
    def __init__(self):
        self.docs, self.blobs = {}, {}

    def doc_get(self, col, did):
        d = self.docs.get((col, did))
        return json.loads(json.dumps(d)) if d is not None else None

    def doc_set(self, col, did, data, merge=False):
        self.docs[(col, did)] = {**(self.docs.get((col, did)) or {}), **data} if merge else dict(data)

    def doc_add(self, col, data):
        self.docs[(col, f"auto{len(self.docs)}")] = dict(data)

    def doc_list(self, col, order="created", limit=500, fields=None):
        rows = [d for (c, _), d in self.docs.items() if c == col]
        return sorted(rows, key=lambda d: d.get(order) or "", reverse=True)[:limit]

    def record_list(self, col, limit=500):
        return [{k: v for k, v in d.items() if k != "payload"} for d in self.doc_list(col, limit=limit)]

    def blob_put(self, key, src, content_type="application/octet-stream"):
        self.blobs[key] = src if isinstance(src, bytes) else src.read_bytes()
        return f"https://storage.test/{key}"

    def blob_get(self, key, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self.blobs[key])
        return dest

    def blob_list(self, prefix):
        return [{"key": k, "size": len(v)} for k, v in sorted(self.blobs.items()) if k.startswith(prefix)]

    def blob_exists(self, key):
        return key in self.blobs


@pytest.fixture
def fake(tmp_path, monkeypatch):
    f = Fake()
    monkeypatch.setattr(cloud, "CLOUD", True)
    for name in ("doc_get", "doc_set", "doc_add", "doc_list", "record_list", "blob_put", "blob_get", "blob_list", "blob_exists"):
        monkeypatch.setattr(cloud, name, getattr(f, name))
    monkeypatch.setattr(cloud, "blob_url", lambda key: f"https://storage.test/{key}")
    monkeypatch.setattr(cloud, "put_tree", lambda prefix, folder, types: None)
    from backend.assembly import service as asm
    from backend.inspection import service as insp
    monkeypatch.setattr(asm, "ASSEMBLY_DIR", tmp_path / "asm")
    monkeypatch.setattr(insp, "INSPECTION_DIR", tmp_path / "insp")
    monkeypatch.setattr(insp, "SCANS_DIR", tmp_path / "scans")
    return f


def test_artifacts_and_samples_come_from_firebase(fake):
    for p in (ROOT / "artifacts").glob("*.json"):
        fake.doc_set("artifacts", p.stem, {"json": p.read_text(encoding="utf-8")})
    fake.blobs["samples/models/power_bank.glb"] = demo.build()
    c = TestClient(app)
    assert c.get("/api/overview").status_code == 200
    assert c.get("/api/ranking").json()
    labels = [f["label"] for f in c.get("/api/assembly/samples").json()["files"]]
    assert "Power bank" in labels
    fake.docs.pop(("artifacts", "metrics"))
    assert c.get("/api/metrics").status_code == 503


def test_model_stored_in_firestore_and_storage(fake):
    fake.blobs["samples/models/power_bank.glb"] = demo.build()
    c = TestClient(app)
    m = c.post("/api/assembly/samples/load", json={"name": "models/power_bank.glb"}).json()
    assert m["model_url"] == f"https://storage.test/assemblies/{m['id']}/model.glb"
    assert f"assemblies/{m['id']}/model.glb" in fake.blobs
    assert c.get(f"/api/assembly/{m['id']}").json()["counts"] == m["counts"]
    assert [a["id"] for a in c.get("/api/assembly").json()["assemblies"]] == [m["id"]]
    r = c.get(f"/api/assembly/{m['id']}/model.glb", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"].endswith("model.glb")


def test_scan_stored_and_alert_state_in_firestore(fake, monkeypatch):
    glb = ROOT / "assets" / "blender" / "semiconductor" / "semiconductor_internal_fault.glb"
    if not glb.exists():
        pytest.skip("Blender team asset not present")
    fake.blobs["samples/blender/semiconductor/x.glb"] = glb.read_bytes()
    c = TestClient(app)
    assert any(f["name"] == "blender/semiconductor/x.glb" for f in c.get("/api/inspection/samples").json()["files"])
    alerts.check_once()                                            # first run: remembers what exists
    r = c.post("/api/inspection/samples/analyze", json={"mesh": "blender/semiconductor/x.glb"}).json()
    assert r["parts"]["model_url"].startswith("https://storage.test/inspections/")
    row = fake.docs[("inspections", r["id"])]
    assert row["part_damage"] and "payload" in row
    monkeypatch.setattr(alerts, "QUIET_S", 0.0)
    sent = []
    monkeypatch.setattr(alerts.channels, "configured", lambda: {"call": "sarvam", "whatsapp": None, "email": None})
    monkeypatch.setattr(alerts.channels, "send_call", lambda to, msg, v=None: sent.append(msg) or "calling")
    assert alerts.check_once() == [] and not sent                  # model damage waits for View damage
    out = alerts.view_damage(r["id"])
    assert out["sent"] and "silicon die" in sent[0]
    assert alerts.view_damage(r["id"])["reason"] == "already reported for this model"
    assert alerts.log(5)[0]["channel"] in ("call", "whatsapp", "email")


def test_seed_writes_artifacts(fake, monkeypatch):
    class Bucket:
        cors = None

        def patch(self):
            pass
    monkeypatch.setattr(cloud, "bucket", lambda: Bucket())
    out = seed.run()
    assert out["artifacts"] >= 5 and ("artifacts", "metrics") in fake.docs
    assert fake.docs[("meta", "seed")]["version"] == seed.version()
