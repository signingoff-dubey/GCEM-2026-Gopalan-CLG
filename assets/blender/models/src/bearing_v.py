"""Deep-groove ball bearing with faults: spalled + cracked outer race, cracked ball, missing ball.
Usage: blender -b --python bearing.py -- <out_dir> [preview]
"""
import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa: E402,F401,F403

args = sys.argv[sys.argv.index("--") + 1:]
out = os.path.abspath(args[0])
preview = len(args) > 1
random.seed(7)
reset()
VAR = int(os.environ.get("VARIANT", "1"))
VP = {
    1: dict(N=8, broken=3, missing=None, spall=True, spall_deg=200, crack=False, crack_deg=300),
    2: dict(N=10, broken=None, missing=2, spall=False, spall_deg=130, crack=True, crack_deg=60),
    3: dict(N=7, broken=5, missing=1, spall=True, spall_deg=290, crack=True, crack_deg=20),
}[VAR]

steel = mat("Steel", (0.62, 0.63, 0.66), 1.0, 0.22)
ball_steel = mat("BallSteel", (0.78, 0.79, 0.82), 1.0, 0.1)
pitted = mat("PittedSteel", (0.05, 0.035, 0.03), 0.7, 0.7)
fracture = mat("FractureFace", (0.3, 0.1, 0.04), 0.6, 0.45)
crack_m = mat("Crack", (0.01, 0.005, 0.005), 0.2, 0.8)
ghost = mat("MissingBall", (1, 0.1, 0.05), 0.0, 0.3, emit=RED, estr=1.5, alpha=0.2)
debris_m = mat("Debris", (0.5, 0.45, 0.42), 1.0, 0.4)

RB = 12.5       # pitch radius of ball centres
RR = 2.5        # ball radius
GR = 2.65       # groove radius
N = VP["N"]
pitch = 360 / N

# ---------------- outer race (groove on inside)
prof = [(14.2, -3.5), (18.6, -3.5), (19.0, -3.1), (19.0, 3.1), (18.6, 3.5), (14.2, 3.5)]
for a in range(50, -51, -5):
    prof.append((RB + GR * math.cos(math.radians(a)), GR * math.sin(math.radians(a))))
bm = lathe_bm(prof, 240)

th_s = math.radians(VP["spall_deg"])                      # spall location on raceway
P = Vector(((RB + GR) * math.cos(th_s), (RB + GR) * math.sin(th_s), 0))
for v in bm.verts:
    d = (v.co - P).length
    if VP["spall"] and d < 1.7:
        radial = Vector((v.co.x, v.co.y, 0)).normalized()
        v.co += radial * 0.55 * (1 - (d / 1.7) ** 2) * (0.6 + 0.8 * random.random())
for f in bm.faces:
    if VP["spall"] and (f.calc_center_median() - P).length < 2.0:
        f.material_index = 1
outer = to_obj("OuterRace", bm, [steel, pitted], "FAULT" if (VP["spall"] or VP["crack"]) else "OK", smooth_angle=30)
outer["fault"] = "spall on raceway + radial crack on outer diameter"

# radial crack on outer diameter
th_c = math.radians(VP["crack_deg"])
pts = []
for k in range(17):
    z = -3.4 + k * 0.425
    t = th_c + math.radians(2.2 * math.sin(k * 1.7) + 1.1 * random.random())
    pts.append((19.03 * math.cos(t), 19.03 * math.sin(t), z))
if VP["crack"]:
    poly_curve("OuterRace_Crack", pts, 0.07, crack_m, "FAULT")

# ---------------- inner race (healthy)
prof = [(7.2, -3.5), (10.8, -3.5), (10.8, -GR * math.sin(math.radians(50)))]
for a in range(230, 129, -5):
    prof.append((RB + GR * math.cos(math.radians(a)), GR * math.sin(math.radians(a))))
prof += [(10.8, 3.5), (7.2, 3.5), (7.0, 3.3), (7.0, -3.3)]
bm = lathe_bm(prof, 160)
inner = to_obj("InnerRace", bm, steel, "OK", smooth_angle=30)

# ---------------- balls
broken_i, missing_i = VP["broken"], VP["missing"]
for i in range(N):
    th = math.radians(i * pitch)
    c = Vector((RB * math.cos(th), RB * math.sin(th), 0))
    if i == missing_i:
        sphere("MissingBall_Ghost", RR, c, ghost, 32, "FAULT")
        continue
    if i != broken_i:
        sphere(f"Ball_{i}", RR, c, ball_steel, 64, "OK")
        continue
    n = Vector((0.35, 0.25, 0.9)).normalized()
    for side, clear in ((1, "clear_outer"), (-1, "clear_inner")):
        bm = sphere_bm(RR, 64)
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-4,
                               plane_co=(0, 0, 0), plane_no=n, **{clear: True})
        bnd = [e for e in bm.edges if e.is_boundary]
        r = bmesh.ops.edgeloop_fill(bm, edges=bnd)
        for f in r["faces"]:
            f.material_index = 1
        bmesh.ops.translate(bm, vec=n * 0.22 * side + c, verts=bm.verts[:])
        o = to_obj(f"Ball_{i}_half{'A' if side > 0 else 'B'}", bm, [ball_steel, fracture], "FAULT")
        o["fault"] = "ball fractured in two"

# loose metal debris near the fault
for k in range(6 if broken_i is not None else 0):
    t = math.radians(broken_i * pitch + random.uniform(-25, 25))
    r = RB + random.uniform(-1.5, 1.5)
    box(f"Debris_{k}", (random.uniform(.15, .45), random.uniform(.15, .4), random.uniform(.05, .15)),
        (r * math.cos(t), r * math.sin(t), -3.6 - 0.0), debris_m, 0.03, "FAULT",
        rot=Matrix.Rotation(random.uniform(0, 6), 3, "Z"))

CAM = Vector((46, -64, 50))
stage(CAM, (0, -4, 2), 31, -3.6, exposure=0.3)
G = collect([("Balls", lambda n: n.startswith(("Ball_", "MissingBall", "Debris_"))),
             ("OuterRace", lambda n: n.startswith("OuterRace")),
             ("InnerRace", lambda n: n.startswith("InnerRace"))],
            {"CRACKED_BALL": "Balls", "MISSING_BALL": "Balls", "RACE_SPALL": "OuterRace",
             "OUTER_CRACK": "OuterRace", "INNER_RACE_OK": "InnerRace", "BALL_OK": "Balls"})
peak = explode(G, {"InnerRace": (0, 0, 0), "Balls": (0, 0, 13), "OuterRace": (0, 0, 28)},
               target=(0, 0, 10), zoom=1.85, lift=14)
os.makedirs(out, exist_ok=True)
sc = bpy.context.scene
base = os.path.join(out, "bearing_v%d" % VAR)
tag_rootlens("bearing", VAR, base + ".json")
sc.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=base + ".blend")
export_glb(base + ".glb")
print("DONE")
