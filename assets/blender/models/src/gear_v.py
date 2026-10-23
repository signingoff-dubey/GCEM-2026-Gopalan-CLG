"""Two-stage-free spur gear reducer: broken tooth, pitted teeth, scored shaft journal, overheated bearing.
Usage: blender -b --python gear.py -- <out_dir> [preview]
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
random.seed(5)
reset()
VAR = int(os.environ.get("VARIANT", "1"))
VP = {
    1: dict(n_big=28, broken=3, pits=False, pit_at=0, scored=True, hot=False),
    2: dict(n_big=24, broken=None, pits=True, pit_at=5, scored=False, hot=True),
    3: dict(n_big=26, broken=11, pits=True, pit_at=14, scored=False, hot=True),
}[VAR]

steel = mat("GearSteel", (0.55, 0.56, 0.6), 1.0, 0.3)
dark = mat("Hardened", (0.2, 0.21, 0.24), 1.0, 0.35)
cast = mat("CastIron", (0.16, 0.2, 0.26), 0.5, 0.55)
pit = mat("Pitting", (0.03, 0.025, 0.02), 0.6, 0.8)
frac = mat("FractureFace", (0.45, 0.2, 0.08), 0.7, 0.5)
scored = mat("ScoredShaft", (0.1, 0.07, 0.05), 0.9, 0.45)
tempered = mat("OverheatedBearing", (0.12, 0.14, 0.5), 1.0, 0.25)
bearing_m = mat("BearingSteel", (0.7, 0.71, 0.74), 1.0, 0.2)
bolt_m = mat("BoltSteel", (0.35, 0.35, 0.38), 1.0, 0.4)


def gear(name, n, r_root, r_tip, bore, width, m, cx, cy, z0, broken=None, status="OK", twist=0.0):
    bm = bmesh.new()
    p = 2 * math.pi / n
    outer, inner = [], []
    for i in range(n):
        a0 = i * p + twist
        tip = r_tip if i != broken else r_root * 1.1
        for da, r in ((-0.36, r_root), (-0.16, tip if i != broken else r_root * 1.05),
                      (0.16, tip if i != broken else r_root * 1.14), (0.36, r_root)):
            outer.append(bm.verts.new((r * math.cos(a0 + da * p), r * math.sin(a0 + da * p), 0)))
    for k in range(len(outer)):
        a = twist + k * 2 * math.pi / len(outer)
        inner.append(bm.verts.new((bore * math.cos(a), bore * math.sin(a), 0)))
    es = [bm.edges.new((v[i], v[(i + 1) % len(v)])) for v in (outer, inner) for i in range(len(v))]
    r = bmesh.ops.bridge_loops(bm, edges=es)
    ext = bmesh.ops.extrude_face_region(bm, geom=r["faces"])
    vs = [g for g in ext["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, 0, width), verts=vs)
    bmesh.ops.translate(bm, vec=(cx, cy, z0), verts=bm.verts[:])
    return to_obj(name, bm, m, status, smooth_angle=40)


Z_G = 11.0     # gear bottom
W = 6.0
CD = 9.25 + 0.77 * VP["n_big"]
P1, P2 = Vector((-CD / 2, 0, 0)), Vector((CD / 2, 0, 0))

# housing base
box("Housing_Base", (84, 50, 6), (0, 0, 3), cast, 0.8, "OK")
for i, P in enumerate((P1, P2)):
    cyl(f"Housing_BossLow{i}", 9, 3, (P.x, P.y, 7.5), cast, 48, status="OK")
# gears
gear("PinionGear", 12, 8.0, 10.6, 3.2, W, steel, P1.x, P1.y, Z_G)
bro = VP["pit_at"] if VP["broken"] is None else VP["broken"]
gear("OutputGear_BROKEN" if VP["broken"] is not None else "OutputGear", VP["n_big"], 0.77 * VP["n_big"] - 2.2, 0.77 * VP["n_big"] + 2.3, 4.2, W, dark, P2.x, P2.y, Z_G, broken=VP["broken"], status="FAULT" if VP["broken"] is not None else "OK")
# fracture stump marks + pits on neighbouring teeth
tp = 2 * math.pi / VP["n_big"]
ab = bro * tp
if VP["broken"] is not None:
    cyl("OutputGear_Stump", 1.6, W * 0.9, (P2.x + (0.77 * VP["n_big"] + 0.3) * math.cos(ab), P2.y + (0.77 * VP["n_big"] + 0.3) * math.sin(ab), Z_G + W / 2), frac, 8,
        status="FAULT", r2=1.0)

if VP["pits"]:
    for k, off in enumerate((-2, -1, 1, 2, 3)):
        a = (bro + off) * tp
        for j in range(3):
            rr = (0.77 * VP["n_big"] + 1.6) - j * 1.3
            sphere(f"OutputGear_Pit{k}{j}", 0.38, (P2.x + rr * math.cos(a + 0.03 * j), P2.y + rr * math.sin(a + 0.03 * j),
                                                   Z_G + 1.3 + 1.6 * j), pit, 10, "FAULT")

if VP["broken"] is not None:
    for k in range(4):   # broken chunks on housing
        box(f"Debris_{k}", (1.4, 1.0, 0.8), (P2.x + 20 + random.uniform(-4, 4), random.uniform(-14, -6), 6.5),
            frac, 0.1, "FAULT", rot=Matrix.Rotation(random.uniform(0, 6), 3, "Z"))

# shafts
cyl("PinionShaft", 3.2, 36, (P1.x, P1.y, 17), steel, 32, status="OK")
sh = cyl("OutputShaft_SCORED" if VP["scored"] else "OutputShaft", 4.2, 36, (P2.x, P2.y, 17), steel, 40, status="FAULT" if VP["scored"] else "OK")
if VP["scored"]:
    cyl("OutputShaft_ScoredBand", 4.28, 4.0, (P2.x, P2.y, 24.2), scored, 40, status="FAULT")
for i, P in enumerate((P1, P2)):   # keys
    box(f"Key{i}", (1.6, 1.6, 5), (P.x + 3.6 - (0.8 if i == 0 else -0.2), P.y, Z_G + W / 2), bolt_m, 0.05, "OK")
# bearings (lathe rings)
def brg(name, P, z, m, status):
    r_o, r_i = 7.0, 4.3 if "Out" in name else 3.3
    prof = [(r_i, -2), (r_o, -2), (r_o, 2), (r_i, 2)]
    ob = to_obj(name, lathe_bm(prof, 48), m, status)
    ob.location = (P.x, P.y, z)


brg("BearingLow_Pin", P1, 9.0, bearing_m, "OK")
brg("BearingLow_Out_OVERHEATED" if VP["hot"] else "BearingLow_Out", P2, 9.0, tempered if VP["hot"] else bearing_m, "FAULT" if VP["hot"] else "OK")
brg("BearingUp_Pin", P1, 19.0, bearing_m, "OK")
brg("BearingUp_Out", P2, 19.0, bearing_m, "OK")
# cover
box("Cover_Plate", (84, 50, 6), (0, 0, 25), cast, 0.8, "OK")
for i, P in enumerate((P1, P2)):
    cyl(f"Cover_Boss{i}", 9, 3, (P.x, P.y, 21.5), cast, 48, status="OK")
for sx in (-1, 1):
    for sy in (-1, 1):
        x, y = sx * 38, sy * 20
        cyl(f"Bolt_Head_{sx}{sy}", 2.6, 2.4, (x, y, 29.2), bolt_m, 6, status="OK")
        cyl(f"Bolt_Shank_{sx}{sy}", 1.3, 14, (x, y, 21), bolt_m, 12, status="OK")

CAM = Vector((95, -125, 90))
stage(CAM, (0, 0, 14), 40, 0.0, exposure=0.6)
sw = lambda *p: (lambda n: n.startswith(p))
G = collect([("Bolts", sw("Bolt_")), ("Cover", sw("Cover_")), ("UpBearings", sw("BearingUp")),
             ("LowBearings", sw("BearingLow")),
             ("GearsShafts", sw("PinionGear", "OutputGear", "PinionShaft", "OutputShaft", "Key", "Debris")),
             ("Base", lambda n: False)],
            {"BROKEN_TOOTH": "GearsShafts", "PITTED_TEETH": "GearsShafts", "SCORED_SHAFT": "GearsShafts",
             "OVERHEATED_BEARING": "LowBearings", "PINION_OK": "GearsShafts"})
peak = explode(G, {"LowBearings": (0, 0, 5), "GearsShafts": (0, 0, 16), "UpBearings": (0, 0, 28),
                   "Cover": (0, 0, 40), "Bolts": (0, 0, 54)}, target=(0, 0, 25), zoom=1.9, lift=22)

os.makedirs(out, exist_ok=True)
sc = bpy.context.scene
base = os.path.join(out, "gear_v%d" % VAR)
tag_rootlens("gear", VAR, base + ".json")
sc.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=base + ".blend")
export_glb(base + ".glb")
print("DONE")
