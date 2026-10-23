import json
import socket
import threading

import pytest
from fastapi.testclient import TestClient

from backend.alerts import channels, service
from backend.api.main import app
from backend.integrations import blender_mcp

SCAN = {"id": "i_1", "created": "2026-10-23T10:00:00", "inputs": {"mesh": "bracket.ply"}, "artificial": True,
        "cracks_found": 2, "max_deviation_mm": 0.3, "dent_faces": 0, "dent_threshold_mm": 0.5}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "ALERTS_DIR", tmp_path / "alerts")
    scans = []
    monkeypatch.setattr(service.inspection, "listing", lambda: list(scans))
    monkeypatch.setattr(service.assembly, "listing", lambda: [])
    monkeypatch.setattr(service.captures, "listing", lambda limit=50: [])
    sent = []
    monkeypatch.setattr(channels, "configured", lambda: {"call": "sarvam", "whatsapp": "twilio", "email": None})
    monkeypatch.setattr(channels, "send_call", lambda to, msg, v=None: sent.append(("call", to, msg, v)) or "calling")
    monkeypatch.setattr(service, "QUIET_S", 0.0)
    monkeypatch.setattr(channels, "send_whatsapp", lambda to, msg: sent.append(("whatsapp", to, msg)) or "sent")
    service.update_settings({"recipients": {"phone": "919800000000", "whatsapp": "919800000000", "email": ""}})
    return scans, sent


def test_first_run_marks_existing_then_alerts_new_crack(env):
    scans, sent = env
    scans.append({**SCAN, "id": "i_old"})
    assert service.check_once() == []          # existing items never alert
    scans.append(SCAN)
    out = service.check_once()
    assert {e["channel"] for e in out} == {"call", "whatsapp", "email"}
    assert [e["ok"] for e in out if e["channel"] == "email"] == [False]     # not configured: nothing sent
    assert sent[0][2] == "Hi boss, this is RootLens. A fault was found in bracket.ply (artificial defect)."
    assert "2 crack regions" in sent[0][3]["fault_details"]
    assert service.check_once() == []          # alerts once per item
    assert len(service.log()) == 3


def test_batch_waits_until_jobs_finish(env):
    scans, sent = env
    service.check_once()
    service.job_started()
    scans.append(SCAN)
    scans.append({**SCAN, "id": "i_2", "inputs": {"mesh": "housing.ply"}, "artificial": False})
    assert service.check_once() == [] and sent == []      # still running: hold the alert
    service.job_finished()
    out = service.check_once()
    calls = [s for s in sent if s[0] == "call"]
    assert len(calls) == 1 and "2 faults were found" in calls[0][2] and "housing.ply" in calls[0][2]
    assert len([e for e in out if e["channel"] == "call"]) == 1


def test_whatsapp_goes_to_every_team_number(env):
    _, sent = env
    service.update_settings({"recipients": {"whatsapp": "919800000001,919800000002"}})
    service.test_alert("whatsapp")
    assert [s[1] for s in sent if s[0] == "whatsapp"] == ["919800000001", "919800000002"]


def test_call_gap_and_disabled_trigger(env):
    scans, sent = env
    service.check_once()
    service.update_settings({"triggers": {"scan_crack": False}})
    scans.append(SCAN)
    assert service.check_once() == []
    service.update_settings({"triggers": {"scan_crack": True}})
    service.test_alert("call")
    second = service.test_alert("call")
    assert second[0]["ok"] is False and "minimum gap" in second[0]["result"]


def test_dent_needs_faces_beyond_tolerance(env):
    scans, _ = env
    scans.append({**SCAN, "cracks_found": 0, "dent_faces": 0})
    assert service.detect() == []
    scans[0]["dent_faces"] = 12
    assert [a["trigger"] for a in service.detect()] == ["scan_dent"]


def test_alert_routes(env):
    c = TestClient(app)
    s = c.get("/api/alerts").json()
    assert s["configured"]["call"] == "sarvam" and "scan_crack" in s["triggers"]
    assert c.put("/api/alerts/settings", json={"channels": {"email": False}}).json()["channels"]["email"] is False
    assert c.post("/api/alerts/test", json={"channel": "fax"}).status_code == 400
    assert c.post("/api/alerts/test", json={"channel": "whatsapp"}).json()["results"][0]["ok"] is True


def _fake_blender(reply: dict):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)

    def serve():
        conn, _ = srv.accept()
        with conn:
            req = json.loads(conn.recv(65536))
            assert req["type"] == "execute_code"
            conn.sendall(json.dumps(reply).encode())
        srv.close()
    threading.Thread(target=serve, daemon=True).start()
    return srv.getsockname()[1]


def test_blender_status_reads_defects(tmp_path, monkeypatch):
    monkeypatch.setattr(blender_mcp, "SETTINGS", tmp_path / "integrations.json")
    scene = {"file": "chip.blend", "scene": "Scene", "objects": 5, "meshes": 4,
             "defects": [{"name": "DieCrack", "type": "crack", "center": [0, 0, 1], "size": [1, 1, 0]}]}
    port = _fake_blender({"status": "success", "result": {"executed": True, "result": "ROOTLENS_JSON" + json.dumps(scene)}})
    monkeypatch.setenv("BLENDER_MCP_PORT", str(port))
    s = blender_mcp.status()
    assert s["connected"] and s["defects"][0]["name"] == "DieCrack"
    blender_mcp.set_enabled(False)
    assert blender_mcp.status()["state"] == "off"


def test_blender_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(blender_mcp, "SETTINGS", tmp_path / "integrations.json")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free = s.getsockname()[1]
    monkeypatch.setenv("BLENDER_MCP_PORT", str(free))
    st = blender_mcp.status()
    assert st["connected"] and st["defects"][0]["type"] == "die crack"
    assert blender_mcp.focus("DieCrack") == {"ok": True}


def test_place_call_reports_one_item_and_skips_the_gap(env, monkeypatch):
    scans, sent = env
    scans.append(SCAN)
    monkeypatch.setattr(service.inspection, "get", lambda iid: SCAN if iid == "i_1" else None)
    service.test_alert("call")                       # a call just went out
    out = service.report_call("i_1")
    assert out["findings"] == 1 and out["results"][0]["ok"]
    assert "bracket.ply" in sent[-1][2] and "2 crack regions" in sent[-1][3]["fault_details"]
    with pytest.raises(LookupError):
        service.report_call("i_missing")
