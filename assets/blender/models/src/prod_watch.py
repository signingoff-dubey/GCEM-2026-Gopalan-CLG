"""Wristwatch movement (face up): cracked crystal, broken minute hand with fragment, dial residue (moisture), pitted gear."""
import math
import os
import random
import sys

from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prod_common import *  # noqa: E402,F401,F403

out, preview = args()
random.seed(11)
reset()

case_m = mat("CaseSteel", (0.7, 0.72, 0.76), 1.0, 0.2)
glass = mat("SapphireCrystal", (0.9, 0.95, 1.0), 0.0, 0.05, alpha=0.35)
dial_m = mat("DialNavy", (0.03, 0.07, 0.2), 0.2, 0.4)
index_m = mat("IndexSilver", (0.9, 0.9, 0.92), 1.0, 0.2)
hand_m = mat("HandSilver", (0.85, 0.85, 0.88), 1.0, 0.2)
sec_m = mat("SecondHandRed", (0.8, 0.05, 0.04), 0.3, 0.4)
plate_m = mat("MovementPlate", (0.72, 0.62, 0.35), 1.0, 0.3)
gold = mat("GearBrass", (0.85, 0.65, 0.2), 1.0, 0.25)
ruby = mat("Ruby", (0.7, 0.02, 0.08), 0.0, 0.1)
frac = mat("FractureFace", (0.55, 0.3, 0.12), 0.8, 0.45)
dark = mat("CrackDark", (0.01, 0.01, 0.01), 0.0, 1.0)
pit_m = mat("PitDark", (0.04, 0.03, 0.02), 0.4, 0.8)
moist = mat("MoistureStain", (0.55, 0.6, 0.65), 0.0, 0.1, alpha=0.6)
strap = mat("StrapLeather", (0.25, 0.12, 0.06), 0.0, 0.7)

# case ring + back
to_obj("Case_Ring", lathe_bm([(19, 0), (23, 0), (23, 9), (19, 9)], 96), case_m, "OK")
cyl("Case_Back", 23, 1.6, (0, 0, -0.8), case_m, 96, status="OK")
for i, a in enumerate((math.pi / 2, -math.pi / 2)):
    for s in (-1, 1):
        box(f"Case_Lug_{i}_{s}", (5, 12, 4), (s * 9, math.sin(a) * 27, 4), case_m, 0.6, "OK")
cyl("Case_Crown", 2.6, 5, (24.5, 0, 4.5), case_m, 24, axis="X", status="OK")
# movement: plate, gear train, balance, mainspring barrel
cyl("Movement_Plate", 18.5, 1.6, (0, 0, 2), plate_m, 96, status="OK")
gears = [(-9, 3, 7.5, 18, 0.0), (6, 7, 5.5, 14, 0.2), (-2, -9, 5.0, 12, 0.0)]
for k, (x, y, r, n, skip) in enumerate(gears):
    if k == 1:
        to_obj(f"Gear_Pitted_{k}", gear_bm(n, r - 0.8, r, 1.2, skip=None), gold, "FAULT").location = (x, y, 3.8)
        for j in range(5):
            aa = j * 1.3
            sphere(f"Gear_Pit{j}", 0.45, (x + (r - 1.4) * math.cos(aa), y + (r - 1.4) * math.sin(aa), 4.5), pit_m, 8, "FAULT")
    else:
        to_obj(f"Gear_{k}", gear_bm(n, r - 0.8, r, 1.2), gold, "OK").location = (x, y, 3.8)
    cyl(f"Gear_Pivot_{k}", 0.5, 4, (x, y, 4.2), ruby, 12, status="OK")
to_obj("Balance_Wheel", lathe_bm([(5.2, 0), (6, 0), (6, 1), (5.2, 1)], 64), gold, "OK").location = (9, -6, 5)
for i in range(3):
    a = i * 2 * math.pi / 3
    box(f"Balance_Spoke_{i}", (5.2, 0.5, 0.6), (9 + math.cos(a) * 2.6, -6 + math.sin(a) * 2.6, 5.4), gold, 0.0, "OK",
        rot=Matrix.Rotation(a, 3, "Z"))
poly_curve("Balance_Hairspring", helix(1.8, 5.8, 5.8, 5.0, 60), 0.12, hand_m, "OK").location = (9, -6, 0)
cyl("Mainspring_Barrel", 6.5, 2.4, (-8, 8, 4.5), gold, 48, status="OK")
# dial + indices
cyl("Dial_Face", 19, 0.8, (0, 0, 10), dial_m, 96, status="OK")
for h in range(12):
    a = h * math.pi / 6
    big = h % 3 == 0
    box(f"Index_{h}", (2.6 if big else 1.6, 0.8 if big else 0.5, 0.5),
        (math.cos(a) * 16.5, math.sin(a) * 16.5, 10.6), index_m, 0.0, "OK", rot=Matrix.Rotation(a, 3, "Z"))
bm = sphere_bm(1.0, 24)
bmesh.ops.scale(bm, vec=(6, 3.5, 0.12), verts=bm.verts[:])
to_obj("Dial_Residue", bm, moist, "FAULT").location = (-6, -8, 10.6)
bm = sphere_bm(1.0, 24)
bmesh.ops.scale(bm, vec=(3, 2, 0.12), verts=bm.verts[:])
to_obj("Dial_ResidueB", bm, moist, "FAULT").location = (7, -11, 10.6)
# hands
cyl("Hand_Pinion", 1.2, 4, (0, 0, 12), hand_m, 16, status="OK")
box("Hand_Hour", (9, 1.6, 0.5), (4.5 * math.cos(0.9), 4.5 * math.sin(0.9), 12.4), hand_m, 0.1, "OK",
    rot=Matrix.Rotation(0.9, 3, "Z"))
ang = 2.2
box("Hand_Minute_Broken", (7, 1.1, 0.5), (3.5 * math.cos(ang), 3.5 * math.sin(ang), 13), hand_m, 0.05, "FAULT",
    rot=Matrix.Rotation(ang, 3, "Z"))
box("Hand_MinuteBreak", (0.3, 1.2, 0.6), (7.1 * math.cos(ang), 7.1 * math.sin(ang), 13), frac, 0.0, "FAULT",
    rot=Matrix.Rotation(ang, 3, "Z"))
box("Hand_MinuteFragment", (9, 1.0, 0.45), (-9, -3, 10.9), hand_m, 0.05, "FAULT", rot=Matrix.Rotation(0.5, 3, "Z"))
box("Hand_Second", (15, 0.4, 0.3), (-1, 3, 13.8), sec_m, 0.0, "OK", rot=Matrix.Rotation(1.57, 3, "Z"))
# crystal with cracks + bezel
to_obj("Crystal_Dome", lathe_bm([(0, 0), (19.5, 0), (19.5, 1.5), (0, 3)], 96), glass, "OK").location = (0, 0, 14)
for k, (a, r0, ln) in enumerate([(0.5, 4, 16), (0.9, 9, 9), (-0.3, 6, 7)]):
    box(f"Crystal_Crack{k}", (ln, 0.22, 0.3), (math.cos(a) * (r0 + ln / 2), math.sin(a) * (r0 + ln / 2), 16.6), dark, 0.0,
        "FAULT", rot=Matrix.Rotation(a, 3, "Z"))
to_obj("Bezel_Ring", lathe_bm([(19.4, 0), (22.8, 0), (22.8, 2), (19.4, 2)], 96), case_m, "OK").location = (0, 0, 13.5)
# strap pieces
for s in (-1, 1):
    box(f"Strap_{'Top' if s > 0 else 'Bottom'}", (18, 26, 2), (0, s * 41, 2), strap, 0.6, "OK")

finish_product("watch", out, preview, cam=(70, -95, 85), target=(0, 0, 8), lens=38, floor_z=-4,
               rules=[("Crystalg", sw("Crystal", "Bezel")), ("Hands", sw("Hand_")), ("Dialg", sw("Dial", "Index")),
                      ("Train", sw("Gear", "Balance", "Mainspring")), ("Plate", sw("Movement")),
                      ("Strapg", sw("Strap"))],
               offsets={"Plate": (0, 0, -8), "Train": (0, 0, 10), "Dialg": (0, 0, 24), "Hands": (0, 0, 40),
                        "Crystalg": (0, 0, 60), "Strapg": (0, 0, -6)},
               ex_target=(0, 0, 25), zoom=1.7, lift=0)
