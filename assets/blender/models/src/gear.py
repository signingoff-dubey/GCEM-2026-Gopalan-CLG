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
CD = 32.4
P1, P2 = Vector((-CD / 2, 0, 0)), Vector((CD / 2, 0, 0))

# housing base
box("Housing_Base", (84, 50, 6), (0, 0, 3), cast, 0.8, "OK")
for i, P in enumerate((P1, P2)):
    cyl(f"Housing_BossLow{i}", 9, 3, (P.x, P.y, 7.5), cast, 48, status="OK")
# gears
gear("PinionGear", 12, 8.0, 10.6, 3.2, W, steel, P1.x, P1.y, Z_G)
bro = 7
gear("OutputGear_BROKEN", 30, 20.9, 25.4, 4.2, W, dark, P2.x, P2.y, Z_G, broken=bro, status="FAULT")
# fracture stump marks + pits on neighbouring teeth
tp = 2 * math.pi / 30
ab = bro * tp
cyl("OutputGear_Stump", 1.6, W * 0.9, (P2.x + 23.4 * math.cos(ab), P2.y + 23.4 * math.sin(ab), Z_G + W / 2), frac, 8,
    status="FAULT", r2=1.0)
for k, off in enumerate((-2, -1, 1, 2, 3)):
    a = (bro + off) * tp
    for j in range(3):
        rr = 24.6 - j * 1.3
        sphere(f"OutputGear_Pit{k}{j}", 0.38, (P2.x + rr * math.cos(a + 0.03 * j), P2.y + rr * math.sin(a + 0.03 * j),
                                               Z_G + 1.3 + 1.6 * j), pit, 10, "FAULT")
for k in range(4):   # broken chunks on housing
    box(f"Debris_{k}", (1.4, 1.0, 0.8), (P2.x + 20 + random.uniform(-4, 4), random.uniform(-14, -6), 6.5),
        frac, 0.1, "FAULT", rot=Matrix.Rotation(random.uniform(0, 6), 3, "Z"))
# shafts
cyl("PinionShaft", 3.2, 36, (P1.x, P1.y, 17), steel, 32, status="OK")
sh = cyl("OutputShaft_SCORED", 4.2, 36, (P2.x, P2.y, 17), steel, 40, status="FAULT")
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
brg("BearingLow_Out_OVERHEATED", P2, 9.0, tempered, "FAULT")
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
SZ = 3.0


def lab(text, a, off, kind, grp=None):
    label(text, a, off, kind, CAM, SZ)


lab("BROKEN TOOTH", (P2.x + 24 * math.cos(ab), P2.y + 24 * math.sin(ab), Z_G + W), (22, -6, 10), "FAULT")
lab("PITTED TEETH", (P2.x + 25 * math.cos(3 * tp), P2.y + 25 * math.sin(3 * tp), Z_G + W), (20, 14, 12), "FAULT")
lab("SCORED SHAFT", (P2.x, P2.y - 4.3, 24.2), (14, -14, 12), "FAULT")
lab("OVERHEATED BEARING", (P2.x + 5, P2.y - 5, 9), (8, -22, 0), "FAULT")
lab("PINION OK", (P1.x, P1.y + 10.6, Z_G + W), (-16, 16, 10), "OK")
lab("HOUSING OK", (-40, 0, 6), (-18, 8, 6), "OK")

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
if preview:
    sc.cycles.samples = 24
    sc.render.resolution_percentage = 50
    sc.frame_set(peak)
    render(os.path.join(out, "gear_preview.png"))
else:
    sc.cycles.samples = 128
    render(os.path.join(out, "gear_fault.png"))
    sc.frame_set(peak)
    render(os.path.join(out, "gear_fault_exploded.png"))
    sc.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "gear_fault.blend"))
    export_glb(os.path.join(out, "gear_fault.glb"))
print("DONE")
