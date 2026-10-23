"""Centrifugal pump: broken impeller blade, torn/leaking mechanical seal. Rest is healthy.
Usage: blender -b --python pump.py -- <out_dir> [preview]
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
random.seed(9)
reset()
VAR = int(os.environ.get("VARIANT", "1"))
VP = {
    1: dict(blades=5, broken=1, torn=False, pitting=True),
    2: dict(blades=7, broken=None, torn=True, pitting=False),
    3: dict(blades=8, broken=5, torn=True, pitting=True),
}[VAR]

casing_m = mat("PumpCasting", (0.05, 0.22, 0.42), 0.6, 0.4)
bronze = mat("Bronze", (0.72, 0.45, 0.18), 1.0, 0.3)
steel = mat("ShaftSteel", (0.7, 0.71, 0.75), 1.0, 0.2)
rubber = mat("SealRubber", (0.03, 0.03, 0.03), 0.0, 0.6)
torn = mat("TornRubber", (0.12, 0.04, 0.02), 0.0, 0.7)
oil = mat("LeakedFluid", (0.2, 0.1, 0.03), 0.0, 0.1)
frac = mat("FractureFace", (0.55, 0.3, 0.12), 0.8, 0.45)
bolt_m = mat("BoltSteel", (0.35, 0.35, 0.38), 1.0, 0.4)
cast = mat("CastIron", (0.14, 0.16, 0.2), 0.5, 0.6)

# bracket / bearing housing (static)
cyl("Bracket", 13, 20, (0, 0, -10), cast, 48, status="OK")
cyl("BracketFoot", 20, 3, (0, 0, -19), cast, 48, status="OK")
# casing: cup + discharge nozzle
ob = to_obj("Casing", lathe_bm([(0, 0), (32, 0), (32, 16), (28.5, 16), (28.5, 3), (0, 3)], 96), casing_m, "OK")
cyl("Casing_Nozzle", 7.5, 22, (41, 0, 9), casing_m, 32, axis="X", status="OK")
cyl("Casing_NozzleFlange", 11.5, 2.4, (52, 0, 9), casing_m, 32, axis="X", status="OK")
pit_m = mat("CavitationPits", (0.02, 0.03, 0.04), 0.5, 0.8)
if VP["pitting"]:
    for k in range(16):
        ang = random.uniform(0, 2 * math.pi)
        rad = random.uniform(27.2, 28.3)
        sphere(f"Casing_Pit{k}", 0.55, (rad * math.cos(ang), rad * math.sin(ang), random.uniform(5, 14)), pit_m, 10, "FAULT")
# shaft
cyl("Shaft", 4, 54, (0, 0, 4), steel, 32, status="OK")
# seal
seal = to_obj("Seal_TORN" if VP["torn"] else "Seal", lathe_bm([(4.6, -1.5), (8.8, -1.5), (8.8, 1.5), (4.6, 1.5)], 48), torn if VP["torn"] else rubber, "FAULT" if VP["torn"] else "OK")
seal.location = (0, 0, 4.5)
if VP["torn"]:
    for k in range(3):
        ang = 2.2 + k * 0.12
        box(f"Seal_Tear{k}", (0.5, 3.4, 3.2), (math.cos(ang) * 8.8, math.sin(ang) * 8.8, 4.5), mat("TearGap", (0, 0, 0), 0, 1),
            0.03, "FAULT", rot=Matrix.Rotation(ang, 3, "Z"))
    bm = sphere_bm(1.0, 32)
    bmesh.ops.scale(bm, vec=(13, 10, 0.18), verts=bm.verts[:])
    bmesh.ops.translate(bm, vec=(-6, 6, 3.1), verts=bm.verts[:])
    to_obj("Seal_Leak", bm, oil, "FAULT")
    for k, (x, y, r) in enumerate([(-15, 12, 1.2), (-9, -1, 0.9), (5, 12, 0.8)]):
        sphere(f"Seal_LeakDrop{k}", r, (x, y, 3.4), oil, 14, "FAULT")

# impeller
bronze_obj = cyl("Impeller_Backplate", 23, 2, (0, 0, 5), bronze, 64, status="OK")
cyl("Impeller_Hub", 7, 10, (0, 0, 9), bronze, 32, status="OK")
BR = VP["broken"]
for i in range(VP["blades"]):
    a = i * 2 * math.pi / VP["blades"]
    if i == BR:
        # stump (short) + fractured face + fragment lying on the casing floor
        L = 6.0
        box("Impeller_Blade_BROKEN", (L, 1.4, 7), (math.cos(a) * (7 + L / 2), math.sin(a) * (7 + L / 2), 9.5), bronze, 0.08,
            "FAULT", rot=Matrix.Rotation(a, 3, "Z"))
        box("Impeller_BladeBreak", (0.5, 1.5, 7.1), (math.cos(a) * (7 + L), math.sin(a) * (7 + L), 9.5), frac, 0.05, "FAULT",
            rot=Matrix.Rotation(a, 3, "Z"))
        box("Impeller_BladeFragment", (9, 1.4, 3.6), (-14, -16, 4.2), bronze, 0.08, "FAULT",
            rot=Matrix.Rotation(0.9, 3, "Z") @ Matrix.Rotation(0.5, 3, "X"))
    else:
        L = 16.0
        box(f"Impeller_Blade_{i}", (L, 1.4, 7), (math.cos(a) * (7 + L / 2), math.sin(a) * (7 + L / 2), 9.5), bronze, 0.08,
            "OK", rot=Matrix.Rotation(a + 0.0, 3, "Z"))
# cover
to_obj("Cover", lathe_bm([(8.5, 0), (33, 0), (33, 3), (12, 3), (12, 20), (8.5, 20)], 96), casing_m, "OK").location = (0, 0, 16)
for i in range(8):
    a = i * math.pi / 4 + math.pi / 8
    x, y = 30.2 * math.cos(a), 30.2 * math.sin(a)
    cyl(f"Bolt_Head_{i}", 2.4, 2.2, (x, y, 20.2), bolt_m, 6, status="OK")
    cyl(f"Bolt_Shank_{i}", 1.2, 12, (x, y, 14), bolt_m, 12, status="OK")

CAM = Vector((105, -135, 85))
stage(CAM, (0, 0, 10), 40, -20.0, exposure=0.5)
sw = lambda *p: (lambda n: n.startswith(p))
G = collect([("Bolts", sw("Bolt_")), ("Cover", sw("Cover")), ("Impeller", sw("Impeller", "Shaft")),
             ("Seal", sw("Seal_"))],
            {"BROKEN_BLADE": "Impeller", "TORN_SEAL": "Seal", "BLADE_OK": "Impeller", "CASING_OK": None, "COVER_OK": "Cover"})
peak = explode(G, {"Seal": (0, 0, 8), "Impeller": (0, 0, 22), "Cover": (0, 0, 42), "Bolts": (0, 0, 58)},
               target=(0, 0, 30), zoom=1.9, lift=26)
G.get("Seal")

os.makedirs(out, exist_ok=True)
sc = bpy.context.scene
base = os.path.join(out, "pump_v%d" % VAR)
tag_rootlens("pump", VAR, base + ".json")
sc.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=base + ".blend")
export_glb(base + ".glb")
print("DONE")
