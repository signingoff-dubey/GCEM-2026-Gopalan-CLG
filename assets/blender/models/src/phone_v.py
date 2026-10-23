"""Smartphone teardown: cracked display, swollen battery, burnt PMIC. Frame, back glass, SoC, camera healthy.
Usage: blender -b --python phone_teardown.py -- <out_dir> [preview]
"""
import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa: E402,F401,F403

args = sys.argv[sys.argv.index("--") + 1:]
out = os.path.abspath(args[0])
preview = len(args) > 1
random.seed(3)
reset()
VAR = int(os.environ.get("VARIANT", "1"))
VP = {
    1: dict(crack=True, imp=(-18, -30), deadline=False, swell=5.0, burnt=False),
    2: dict(crack=False, imp=(14, 24), deadline=False, swell=4.0, burnt=True),
    3: dict(crack=True, imp=(20, -10), deadline=True, swell=0.0, burnt=True),
}[VAR]

back_m = mat("BackGlass", (0.05, 0.1, 0.26), 0.1, 0.12)
frame_m = mat("Frame", (0.72, 0.72, 0.75), 1.0, 0.25)
screen_m = mat("Screen", (0.01, 0.015, 0.03), 0.0, 0.05)
crack_m = mat("GlassCrack", (0.85, 0.88, 0.95), 0.0, 0.2, emit=(0.6, 0.65, 0.8), estr=0.6)
deadpx = mat("DeadPixels", (0.1, 0.0, 0.1), 0.0, 0.3, emit=(1.0, 0.1, 0.8), estr=3.0)
foil = mat("PouchFoil", (0.7, 0.72, 0.76), 1.0, 0.35)
label_m = mat("BatteryLabel", (0.05, 0.25, 0.7), 0.0, 0.5)
pcb_m = mat("Mainboard", (0.02, 0.18, 0.1), 0.0, 0.35)
chip = mat("Chip", (0.02, 0.02, 0.025), 0.0, 0.4)
chip_hi = mat("ChipMetal", (0.6, 0.6, 0.65), 1.0, 0.3)
char = mat("Charred", (0.008, 0.006, 0.005), 0.0, 0.9)
scorch = mat("Scorch", (0.03, 0.015, 0.008), 0.0, 0.95)
shield = mat("Shield", (0.55, 0.56, 0.6), 1.0, 0.35)
lens_ring = mat("LensRing", (0.8, 0.8, 0.82), 1.0, 0.2)
lens_glass = mat("LensGlass", (0.0, 0.0, 0.015), 0.0, 0.03)
cam_body = mat("CamBody", (0.08, 0.08, 0.09), 0.2, 0.3)
gold = mat("Gold", (0.95, 0.7, 0.25), 1.0, 0.22)

W, H = 72.0, 150.0
box("BackGlass", (W - 1, H - 1, 1.0), (0, 0, 0.5), back_m, 0.8, "OK")
for sx in (-1, 1):
    box(f"Frame_Side{sx}", (2.6, H, 7.8), (sx * (W / 2 - 1.3), 0, 3.9), frame_m, 0.6, "OK")
for sy in (-1, 1):
    box(f"Frame_End{sy}", (W - 5.2, 2.6, 7.8), (0, sy * (H / 2 - 1.3), 3.9), frame_m, 0.6, "OK")
box("Frame_Button", (0.8, 14, 2.6), (W / 2 + 0.3, 25, 4), frame_m, 0.2, "OK")

# swollen battery
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1.0)
bmesh.ops.scale(bm, vec=(58, 84, 4.6), verts=bm.verts[:])
bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=12, use_grid_fill=True)
for v in bm.verts:
    if v.co.z > 0:
        v.co.z += VP["swell"] * math.exp(-((v.co.x / 19) ** 2 + ((v.co.y - 4) / 27) ** 2)) * (0.9 + 0.1 * math.sin(v.co.x))
    else:
        v.co.z -= 0.6 * math.exp(-((v.co.x / 19) ** 2 + (v.co.y / 27) ** 2))
bmesh.ops.translate(bm, vec=(0, -26, 3.8), verts=bm.verts[:])
SW = VP["swell"] > 0
to_obj("Battery_SWOLLEN" if SW else "Battery", bm, foil, "FAULT" if SW else "OK", smooth_angle=60)
box("Battery_Label", (34, 26, 0.12), (0, -26, 6.3 + VP["swell"] * 0.75), label_m, 0.05, "FAULT" if SW else "OK")
if SW:
    for k in range(3):    # wrinkled / split pouch seam
        box(f"Battery_Seam{k}", (58 + k, 0.5, 0.3), (0, -26 + 42.2 + k * 0.1, 4.0 + 0.6 * k), foil, 0.05, "FAULT",
            rot=Matrix.Rotation(0.03 * (k - 1), 3, "Z"))

# mainboard (upper section)
BY = 47.0
box("Board", (58, 50, 1.4), (0, BY, 3.0), pcb_m, 0.2, "OK")
box("SoC", (11, 11, 1.1), (6, BY - 4, 4.25), chip, 0.15, "OK")
box("SoC_Shield", (14, 14, 0.25), (6, BY - 4, 5.0), shield, 0.05, "OK")
box("RAM", (9, 7, 0.9), (-14, BY - 6, 4.15), chip, 0.1, "OK")
box("Modem", (7, 7, 0.8), (-14, BY + 8, 4.1), chip, 0.1, "OK")
box("Flash", (8, 6, 0.8), (14, BY + 10, 4.1), chip, 0.1, "OK")
for i in range(8):
    box(f"Passive_{i}", (1.4, 0.8, 0.5), (-22 + i * 2.6, BY - 20, 3.95), chip_hi, 0.05, "OK")
# burnt PMIC
box("PMIC_BURNT" if VP["burnt"] else "PMIC", (6, 6, 0.9), (22, BY - 14, 4.15), char if VP["burnt"] else chip, 0.2, "FAULT" if VP["burnt"] else "OK")
if VP["burnt"]:
    for k, (dx, dy, r) in enumerate([(-1.2, 1, 0.8), (1.3, -0.9, 0.6)]):
        sphere(f"PMIC_Blister{k}", r, (22 + dx, BY - 14 + dy, 4.7), char, 12, "FAULT")
    bm = sphere_bm(1.0, 24)
    bmesh.ops.scale(bm, vec=(7.5, 6.5, 0.05), verts=bm.verts[:])
    bmesh.ops.translate(bm, vec=(22, BY - 14, 3.72), verts=bm.verts[:])
    to_obj("PMIC_Scorch", bm, scorch, "FAULT")

# camera module
CX, CY = -16, 61
box("Cam_Housing", (24, 26, 4.2), (CX, CY, 7.5), cam_body, 0.8, "OK")
for i, (dx, dy) in enumerate([(-5, 6), (-5, -6), (5, 0)]):
    cyl(f"Cam_Ring{i}", 4.4, 1.2, (CX + dx, CY + dy, 9.8), lens_ring, 40, status="OK")
    cyl(f"Cam_Glass{i}", 3.3, 1.4, (CX + dx, CY + dy, 9.85), lens_glass, 40, status="OK")

# display (cracked)
box("Display_CRACKED" if VP["crack"] or VP["deadline"] else "Display", (W - 1.6, H - 1.6, 0.8), (0, 0, 8.4), screen_m, 0.5, "FAULT" if (VP["crack"] or VP["deadline"]) else "OK")
zc = 8.85
imp = Vector((*VP["imp"], 0))
if VP["crack"]:
    for k in range(9):
        a = k * 2 * math.pi / 9 + random.uniform(-.2, .2)
        pts, p = [], imp.copy()
        for s in range(7):
            pts.append((p.x, p.y, zc))
            a += random.uniform(-0.25, 0.25)
            p = p + Vector((math.cos(a), math.sin(a), 0)) * random.uniform(5, 14)
            p.x = max(-34, min(34, p.x))
            p.y = max(-73, min(73, p.y))
        poly_curve(f"Display_Crack{k}", pts, 0.12, crack_m, "FAULT")
    for ring in (6, 13, 22):
        pts = [(imp.x + ring * math.cos(t) * random.uniform(.85, 1.1), imp.y + ring * math.sin(t) * random.uniform(.85, 1.1), zc)
               for t in [i * 2 * math.pi / 14 for i in range(15)]]
        poly_curve(f"Display_CrackRing{ring}", pts, 0.08, crack_m, "FAULT")

if VP["deadline"]:
    box("Display_DeadLine", (66, 1.3, 0.05), (0, -4, 8.82), deadpx, 0, "FAULT")

CAM = Vector((125, -190, 140))
stage(CAM, (0, 5, 5), 45, -42.0, exposure=0.5)
sw = lambda *p: (lambda n: n.startswith(p))
G = collect([("Display", sw("Display")), ("Camera", sw("Cam_")), ("Board", sw("Board", "SoC", "RAM", "Modem", "Flash", "Passive", "PMIC")),
             ("Battery", sw("Battery")), ("Back", sw("BackGlass"))],
            {"CRACKED_DISPLAY": "Display", "SWOLLEN_BATTERY": "Battery", "BURNT_PMIC": "Board",
             "CAMERA_OK": "Camera", "SOC_OK": "Board"})
peak = explode(G, {"Back": (0, 0, -34), "Battery": (0, 0, -16), "Board": (0, 0, 14), "Camera": (0, 0, 30),
                   "Display": (0, 0, 48)}, target=(0, 5, 10), zoom=1.7, lift=30)

os.makedirs(out, exist_ok=True)
sc = bpy.context.scene
base = os.path.join(out, "phone_teardown_v%d" % VAR)
tag_rootlens("phone_teardown", VAR, base + ".json")
sc.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=base + ".blend")
export_glb(base + ".glb")
print("DONE")
