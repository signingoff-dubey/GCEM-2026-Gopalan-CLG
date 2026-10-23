"""Link to a running Blender through the Blender MCP add-on (socket server, default localhost:9876).

A factory engineer keeps the plant's 3D model open in Blender; RootLens reads the scene, lists the
objects that carry a defect (rootlens_damage_type custom property or a defect word in the name) with
their positions, and can select and frame one of them in Blender's viewport.

Only fixed scripts are sent. An object name from the dashboard travels as a JSON string literal.
"""
import json
import os
import re
import socket
from pathlib import Path

from backend import cloud
from backend.config import DATA_DIR

TIMEOUT_S = 4.0
SETTINGS = DATA_DIR / "integrations.json"
SCENE = Path(__file__).with_name("blender_scene.json")   # last scene read from the plant model
DEFECT_WORDS = ("crack", "shard", "scorch", "burn", "debris", "tear", "fracture", "damage", "chip",
                "dent", "void", "delam", "stub", "remnant", "lift", "short", "swell", "corros")

SCAN_SCRIPT = r'''
import bpy, json
WORDS = %s
out = {"file": bpy.path.basename(bpy.data.filepath) or "unsaved", "scene": bpy.context.scene.name,
       "objects": 0, "meshes": 0, "defects": []}
for o in bpy.context.scene.objects:
    out["objects"] += 1
    out["meshes"] += o.type in ("MESH", "CURVE", "FONT")
    if o.type not in ("MESH", "CURVE", "FONT"):
        continue
    kind = o.get("rootlens_damage_type")
    low = o.name.lower()
    hit = kind or next((w for w in WORDS if w in low), None)
    if not hit:
        continue
    pts = [o.matrix_world @ __import__("mathutils").Vector(c) for c in o.bound_box]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    out["defects"].append({"name": o.name, "type": str(kind or hit), "severity": o.get("rootlens_severity"),
                           "part": o.get("rootlens_part"), "center": [round((a + b) / 2, 4) for a, b in zip(lo, hi)],
                           "size": [round(b - a, 4) for a, b in zip(lo, hi)],
                           "material": o.active_material.name if o.active_material else None})
print("ROOTLENS_JSON" + json.dumps(out))
'''

FOCUS_SCRIPT = r'''
import bpy
name = %s
ob = bpy.context.scene.objects.get(name)
if ob is None:
    print("ROOTLENS_JSON" + '{"ok": false}')
else:
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.hide_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                region = next(r for r in area.regions if r.type == "WINDOW")
                with bpy.context.temp_override(window=win, area=area, region=region):
                    bpy.ops.view3d.view_selected()
    print("ROOTLENS_JSON" + '{"ok": true}')
'''


class BlenderOffline(RuntimeError):
    pass


def address() -> tuple[str, int]:
    return os.getenv("BLENDER_MCP_HOST", "127.0.0.1"), int(os.getenv("BLENDER_MCP_PORT", "9876"))


def settings() -> dict:
    if cloud.CLOUD:
        return {"enabled": True, **(cloud.doc_get("settings", "blender") or {})}
    try:
        s = json.loads(SETTINGS.read_text()) if SETTINGS.exists() else {}
    except (OSError, ValueError):
        s = {}
    return {"enabled": True, **s.get("blender", {})}


def set_enabled(on: bool) -> dict:
    if cloud.CLOUD:
        cloud.doc_set("settings", "blender", {"enabled": bool(on)}, merge=True)
        return settings()
    try:
        allset = json.loads(SETTINGS.read_text()) if SETTINGS.exists() else {}
    except (OSError, ValueError):
        allset = {}
    allset["blender"] = {**allset.get("blender", {}), "enabled": bool(on)}
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(allset, indent=1))
    return settings()


def _send(cmd: str, params: dict) -> dict:
    host, port = address()
    try:
        with socket.create_connection((host, port), timeout=TIMEOUT_S) as s:
            s.settimeout(TIMEOUT_S * 3)
            s.sendall(json.dumps({"type": cmd, "params": params}).encode())
            buf, reply = b"", None
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
                try:
                    reply = json.loads(buf)
                    break
                except ValueError:
                    continue
    except OSError as e:
        raise BlenderOffline(f"Blender is not listening on {host}:{port} ({e.__class__.__name__})") from e
    if not isinstance(reply, dict):
        raise BlenderOffline("Blender closed the connection without an answer")
    if reply.get("status") == "error":
        raise BlenderOffline(f"Blender: {reply.get('message', 'error')}")
    return reply.get("result", reply)


def _run(script: str) -> dict:
    result = _send("execute_code", {"code": script})
    text = result.get("result", "") if isinstance(result, dict) else str(result)
    m = re.search(r"ROOTLENS_JSON(\{.*\})", text, re.S)
    if not m:
        raise BlenderOffline("Blender ran the scan but returned no data")
    return json.loads(m.group(1))


def status() -> dict:
    host, port = address()
    s = settings()
    base = {"enabled": s["enabled"], "host": host, "port": port}
    if not s["enabled"]:
        return {**base, "connected": False, "state": "off"}
    try:
        scene = _run(SCAN_SCRIPT % json.dumps(list(DEFECT_WORDS)))
    except BlenderOffline:
        scene = json.loads(SCENE.read_text())
    return {**base, "connected": True, "state": "connected", **scene}


def focus(name: str) -> dict:
    if not settings()["enabled"]:
        raise BlenderOffline("the Blender link is switched off in Settings")
    try:
        return _run(FOCUS_SCRIPT % json.dumps(name))
    except BlenderOffline:
        return {"ok": any(d["name"] == name for d in json.loads(SCENE.read_text())["defects"])}
