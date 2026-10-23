"""Populated PCB with faults: bulged/leaking capacitor, burnt resistor, lifted IC pin, broken trace.
Usage: blender -b --python pcb.py -- <out_dir> [preview]
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
random.seed(11)
reset()
VAR = int(os.environ.get("VARIANT", "1"))
VP = {
    1: dict(bulged=True, burnt=False, lift=True, lift_side=2, lift_i=5, trace=False),
    2: dict(bulged=False, burnt=True, lift=False, lift_side=3, lift_i=2, trace=True),
    3: dict(bulged=True, burnt=True, lift=True, lift_side=0, lift_i=6, trace=True),
}[VAR]

M_BOARD = mat("SolderMask", (0.015, 0.2, 0.08), 0.0, 0.35)
M_COPPER = mat("Copper", (0.8, 0.45, 0.18), 1.0, 0.3)
M_GOLD = mat("Gold", (0.95, 0.7, 0.25), 1.0, 0.22)
M_SILVER = mat("Tin", (0.8, 0.8, 0.82), 1.0, 0.25)
M_IC = mat("ICBody", (0.02, 0.02, 0.025), 0.0, 0.45)
M_DOT = mat("ICDot", (0.7, 0.7, 0.7), 0.0, 0.4)
M_SMD = mat("SMDBody", (0.03, 0.03, 0.03), 0.0, 0.6)
M_CER = mat("Ceramic", (0.35, 0.2, 0.08), 0.0, 0.5)
M_CAPS = mat("CapSleeve", (0.02, 0.05, 0.25), 0.1, 0.35)
M_ALU = mat("CapTop", (0.7, 0.7, 0.72), 1.0, 0.3)
M_VENT = mat("Vent", (0.12, 0.12, 0.12), 0.5, 0.5)
M_RES = mat("ResistorBody", (0.75, 0.6, 0.35), 0.0, 0.5)
M_CHAR = mat("Charred", (0.008, 0.006, 0.005), 0.0, 0.92)
M_SCORCH = mat("Scorch", (0.02, 0.012, 0.008), 0.0, 0.95)
M_SOOT = mat("Soot", (0.0, 0.0, 0.0), 0.0, 1.0, alpha=0.45)
M_LEAK = mat("Electrolyte", (0.28, 0.12, 0.03), 0.0, 0.12)
M_HOLE = mat("Hole", (0.01, 0.01, 0.01), 0.0, 0.8)
M_BAND = [mat(f"Band{i}", c, 0.0, 0.5) for i, c in enumerate(
    [(0.45, 0.05, 0.02), (0.02, 0.02, 0.02), (0.55, 0.3, 0.02), (0.8, 0.65, 0.2)])]
M_HDR = mat("HeaderBase", (0.015, 0.015, 0.015), 0.0, 0.5)
M_BURN = mat("BurntTrace", (0.04, 0.02, 0.01), 0.3, 0.7)

BW, BH, BT = 70.0, 46.0, 1.6
box("Board", (BW, BH, BT), (0, 0, -BT / 2), M_BOARD, 0.3, "OK")
for sx in (-1, 1):
    for sy in (-1, 1):
        p = (sx * (BW / 2 - 4), sy * (BH / 2 - 4))
        cyl(f"MountRing_{sx}{sy}", 2.6, 0.06, (*p, 0.03), M_GOLD, 32, status="OK")
        cyl(f"MountHole_{sx}{sy}", 1.5, 0.08, (*p, 0.04), M_HOLE, 32, status="OK")

# ---------------- main IC (QFP, healthy except one lifted pin)
U = Vector((-14, 4, 0))
box("U1_MCU", (12, 12, 1.6), (U.x, U.y, 0.8), M_IC, 0.25, "OK")
cyl("U1_Pin1Dot", 0.45, 0.05, (U.x - 4.2, U.y + 4.2, 1.62), M_DOT, 16, status="OK")
cyl("U1_Logo", 1.6, 0.04, (U.x + 0.5, U.y - 0.5, 1.62), mat("Marking", (0.12, 0.12, 0.13), 0, 0.3), 24, status="OK")
LIFTED = ("S", 2)
for side, (dx, dy) in enumerate([(1, 0), (0, 1), (-1, 0), (0, -1)]):
    tag = "ESWN"[side]
    for i in range(8):
        t = (i - 3.5) * 1.4
        cx = U.x + dx * 6.7 + (t if dy else 0)
        cy = U.y + dy * 6.7 + (t if dx else 0)
        if dx:
            size, pad = (1.6, 0.35, 0.2), (1.3, 0.55, 0.05)
        else:
            size, pad = (0.35, 1.6, 0.2), (0.55, 1.3, 0.05)
        pad_pos = (cx + dx * 0.9, cy + dy * 0.9, 0.025)
        lifted = VP["lift"] and side == VP["lift_side"] and i == VP["lift_i"]
        box(f"U1_Pad_{tag}{i}", pad, pad_pos, M_GOLD, 0, "OK")
        if lifted:
            box("U1_Pin_LIFTED", size, (cx + dx * 0.1, cy + dy * 0.1, 1.15), M_SILVER, 0.04, "FAULT",
                rot=Matrix.Rotation(math.radians(-24) * (1 if dy else 0), 3, "X"))
            # crack in the solder fillet
            box("U1_SolderCrack", (0.7, 0.5, 0.35), (cx + dx * 0.9, cy + dy * 0.9, 0.2), M_BURN, 0.05, "FAULT")
        else:
            box(f"U1_Pin_{tag}{i}", size, (cx, cy, 0.28), M_SILVER, 0.04, "OK")

# ---------------- SOIC-8
V = Vector((14, 12, 0))
box("U2_SOIC", (5, 4, 1.4), (V.x, V.y, 0.7), M_IC, 0.15, "OK")
for s in (-1, 1):
    for i in range(4):
        x = V.x + (i - 1.5) * 1.27
        y = V.y + s * 2.6
        box(f"U2_Pin_{s}{i}", (0.4, 1.0, 0.2), (x, y, 0.2), M_SILVER, 0.03, "OK")
        box(f"U2_Pad_{s}{i}", (0.6, 1.4, 0.05), (x, y + s * 0.1, 0.025), M_GOLD, 0, "OK")

# ---------------- traces (one broken)
def trace(name, a, b, w=0.45, status="OK", m=M_COPPER):
    a, b = Vector(a), Vector(b)
    mid, d = (a + b) / 2, b - a
    if abs(d.x) >= abs(d.y):
        box(name, (abs(d.x) + w, w, 0.07), (mid.x, mid.y, 0.035), m, 0, status)
    else:
        box(name, (w, abs(d.y) + w, 0.07), (mid.x, mid.y, 0.035), m, 0, status)


GAP = 0.9 if VP["trace"] else 0.0
trace("Trace_Net1_L", (-6.6, 4.3, 0), (-GAP, 4.3, 0))
trace("Trace_Net1_R", (GAP, 4.3, 0), (6.0, 4.3, 0))
trace("Trace_Net1_Up", (6.0, 4.3, 0), (6.0, 12.0, 0))
trace("Trace_Net1_End", (6.0, 12.0, 0), (11.3, 12.0, 0))
if VP["trace"]:
    box("Trace_Break", (1.7, 0.9, 0.09), (0, 4.3, 0.06), M_BURN, 0.1, "FAULT")
    for k, (dz, dy) in enumerate([(-0.3, 0.6), (0.4, -0.5), (0.1, 0.3)]):
        box(f"Trace_Whisker_{k}", (0.5, 0.12, 0.05), (dz * 1.2, 4.3 + dy, 0.1), M_COPPER, 0, "FAULT",
            rot=Matrix.Rotation(random.uniform(-0.6, 0.6), 3, "Z"))

trace("Trace_Net2", (-14, -4.4, 0), (-14, -9.5, 0))
trace("Trace_Net2b", (-14, -9.5, 0), (8, -9.5, 0))
trace("Trace_Net3", (-6.6, 6.0, 0), (-2, 6.0, 0))
trace("Trace_Net3b", (-2, 6.0, 0), (-2, 16, 0))
trace("Trace_Net3c", (-2, 16, 0), (10.8, 16, 0))
trace("Trace_Net4", (18, 12, 0), (26, 12, 0))
trace("Trace_Net5", (-20, 10.7, 0), (-20, 19, 0))

# ---------------- SMD resistors / ceramic caps (healthy)
for i in range(6):
    x = -30 + i * 3.4
    y = 16
    box(f"R_SMD_{i}", (1.4, 1.2, 0.5), (x, y, 0.3), M_SMD, 0.05, "OK")
    for s in (-1, 1):
        box(f"R_SMD_{i}_cap{s}", (0.35, 1.25, 0.55), (x + s * 0.8, y, 0.3), M_SILVER, 0.04, "OK")
for i in range(3):
    x, y = -26 + i * 3.2, 9
    box(f"C_Ceramic_{i}", (1.6, 1.0, 0.9), (x, y, 0.5), M_CER, 0.05, "OK")
    for s in (-1, 1):
        box(f"C_Ceramic_{i}_cap{s}", (0.3, 1.05, 0.95), (x + s * 0.85, y, 0.5), M_SILVER, 0.04, "OK")


# ---------------- electrolytic capacitors
def elec_cap(name, c, healthy):
    r, h = 3.2, 6.0
    if healthy:
        prof = [(0, 0), (r, 0), (r, h - 0.4), (r - 0.4, h), (0, h)]
    else:   # bulged barrel, domed top, torn vent
        prof = [(0, 0), (r, 0), (r + 0.1, 2.0), (r + 0.45, 4.2), (r + 0.55, 5.6), (r - 0.4, 6.9),
                (r - 1.6, 7.7), (r - 2.7, 7.95), (0, 8.1)]
    bm = lathe_bm(prof, 48)
    if not healthy:                # lumpy burst top
        for v in bm.verts:
            if v.co.z > 6.5:
                v.co.z += 0.25 * math.sin(v.co.x * 2.1) * math.cos(v.co.y * 1.7)
    ob = to_obj(name, bm, M_CAPS if healthy else mat("CapSleeveBulged", (0.025, 0.045, 0.2), 0.1, 0.3),
                "OK" if healthy else "FAULT", smooth_angle=45)
    ob.location = c
    # aluminium top + vent
    top_z = h if healthy else 7.9
    cyl(name + "_Top", r - 0.45 if healthy else r - 1.3, 0.06, (c[0], c[1], c[2] + top_z + (0.01 if healthy else 0.12)),
        M_ALU, 32, status="OK" if healthy else "FAULT")
    if healthy:
        for ang in (0, math.pi / 2):
            box(name + f"_Vent{int(ang)}", (4.0, 0.14, 0.06), (c[0], c[1], c[2] + top_z + 0.07), M_VENT, 0, "OK",
                rot=Matrix.Rotation(ang, 3, "Z"))
        # negative stripe
        box(name + "_Stripe", (0.9, 0.1, 4.2), (c[0] - r - 0.01, c[1], c[2] + 3.0), M_ALU, 0, "OK")
    else:
        for k in range(5):         # burst vent, flaps
            a = k * 2 * math.pi / 5 + 0.3
            box(name + f"_Flap{k}", (1.8, 0.35, 0.12),
                (c[0] + math.cos(a) * 0.9, c[1] + math.sin(a) * 0.9, c[2] + 8.35), M_VENT, 0.03, "FAULT",
                rot=Matrix.Rotation(a, 3, "Z") @ Matrix.Rotation(math.radians(-22), 3, "Y"))
    # leads
    for s in (-1, 1):
        cyl(name + f"_Lead{s}", 0.25, 1.2, (c[0] + s * 1.3, c[1], -0.1), M_SILVER, 12, status="OK")


for i, c in enumerate([(8, -9, 0), (18, -9, 0)]):
    elec_cap(f"C{i + 1}_OK", c, True)
elec_cap("C3_BULGED" if VP["bulged"] else "C3_OK", (28, -9, 0), not VP["bulged"])
if VP["bulged"]:
    # electrolyte leak around base and down the side
    bm = sphere_bm(1.0, 24)
    bmesh.ops.scale(bm, vec=(6.3, 5.2, 0.22), verts=bm.verts[:])
    bmesh.ops.translate(bm, vec=(28.8, -9.8, 0.18), verts=bm.verts[:])
    to_obj("C3_Leak_Puddle", bm, M_LEAK, "FAULT")
    for k, (dx, dy, rr) in enumerate([(3.4, -2.3, 0.9), (-2.8, -3.2, 0.7), (4.4, 1.0, 0.6)]):
        sphere(f"C3_Leak_Drop{k}", rr, (28 + dx, -9 + dy, 0.4), M_LEAK, 16, "FAULT")
    for k in range(3):                 # crusty residue ring at the vent
        sphere(f"C3_Residue{k}", 0.9, (28 + math.cos(k * 2.1) * 1.8, -9 + math.sin(k * 2.1) * 1.8, 8.3), M_LEAK, 12, "FAULT")

# ---------------- axial resistors: R8 healthy, R7 burnt
def axial(name, c, healthy):
    L, r = 6.2, 1.5
    body = cyl(name + "_Body", r, L, c, M_RES if healthy else M_CHAR, 24, axis="X",
               status="OK" if healthy else "FAULT")
    if healthy:
        for k, m in enumerate(M_BAND):
            cyl(name + f"_Band{k}", r + 0.04, 0.45, (c[0] - 2.2 + k * 1.15, c[1], c[2]), m, 24, axis="X", status="OK")
    else:
        for k, (dx, dz, rr) in enumerate([(-1.4, 1.2, 0.5), (0.8, 1.3, 0.6), (1.9, 0.8, 0.35)]):
            sphere(name + f"_Blister{k}", rr, (c[0] + dx, c[1] + 0.2, c[2] + dz), M_CHAR, 16, "FAULT")
        box(name + "_Split", (0.3, 0.1, 0.1), (c[0] + 0.2, c[1] - 1.4, c[2] + 0.6), M_BURN, 0, "FAULT")
    for s in (-1, 1):
        cyl(name + f"_Lead{s}", 0.28, 5.0, (c[0] + s * (L / 2 + 2.2), c[1], c[2]), M_SILVER, 12, axis="X",
            status="OK")
        cyl(name + f"_Leg{s}", 0.28, c[2] + 1.0, (c[0] + s * (L / 2 + 4.4), c[1], c[2] / 2 - 0.5), M_SILVER, 12,
            status="OK")


axial("R8_OK", (-20, -20, 2.0), True)
axial("R7_BURNT" if VP["burnt"] else "R7_OK2", (-20, -13, 2.0), not VP["burnt"])
if VP["burnt"]:
    bm = sphere_bm(1.0, 32)
    bmesh.ops.scale(bm, vec=(8.5, 6.2, 0.04), verts=bm.verts[:])
    bmesh.ops.translate(bm, vec=(-20, -13, 0.05), verts=bm.verts[:])
    to_obj("R7_Soot", bm, M_SOOT, "FAULT")
    bm = sphere_bm(1.0, 32)
    bmesh.ops.scale(bm, vec=(5.6, 3.9, 0.06), verts=bm.verts[:])
    bmesh.ops.translate(bm, vec=(-20, -13, 0.07), verts=bm.verts[:])
    to_obj("R7_Scorch", bm, M_SCORCH, "FAULT")

# ---------------- connector header (healthy)
box("J1_Base", (20.4, 2.6, 2.5), (-4, 19.5, 1.25), M_HDR, 0.1, "OK")
for i in range(8):
    box(f"J1_Pin{i}", (0.64, 0.64, 7.0), (-4 + (i - 3.5) * 2.54, 19.5, 3.5), M_GOLD, 0.03, "OK")

CAM = Vector((56, -78, 62))
stage(CAM, (2, -2, 2), 31, -1.65, exposure=0.2)
sw = lambda *p: (lambda n: n.startswith(p))
G = collect([("Header", sw("J1_")),
             ("SMD", sw("R_SMD", "C_Ceramic")),
             ("U1", lambda n: n.startswith("U1_") and not n.startswith(("U1_Pad", "U1_SolderCrack"))),
             ("U2", lambda n: n.startswith("U2_") and not n.startswith("U2_Pad")),
             ("Axial", lambda n: n.startswith(("R7_", "R8_")) and n not in ("R7_Soot", "R7_Scorch")),
             ("CapsOK", sw("C1_OK", "C2_OK")),
             ("Bulged", lambda n: n.startswith("C3_") and n != "C3_Leak_Puddle")],
            {"BULGED_CAPACITOR": "Bulged", "BURNT_RESISTOR": "Axial", "LIFTED_PIN": "U1", "MCU_OK": "U1",
             "CAPACITOR_OK": "CapsOK", "HEADER_OK": "Header"})
peak = explode(G, {"SMD": (0, 0, 7), "Axial": (0, 0, 13), "Header": (0, 0, 10), "U2": (0, 0, 18),
                   "U1": (0, 0, 22), "CapsOK": (0, 0, 27), "Bulged": (0, 0, 34)}, target=(2, -2, 14), zoom=2.0, lift=14)
os.makedirs(out, exist_ok=True)
sc = bpy.context.scene
base = os.path.join(out, "pcb_v%d" % VAR)
tag_rootlens("pcb", VAR, base + ".json")
sc.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=base + ".blend")
export_glb(base + ".glb")
print("DONE")
