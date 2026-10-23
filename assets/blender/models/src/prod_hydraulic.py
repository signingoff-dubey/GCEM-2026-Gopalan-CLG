"""Hydraulic cylinder (vertical): bulged barrel, scored piston rod, torn rod seal leaking oil, cracked weld."""
import math
import os
import sys

from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prod_common import *  # noqa: E402,F401,F403

out, preview = args()
reset()

paint = mat("HydraulicYellow", (0.9, 0.65, 0.05), 0.4, 0.45)
chrome = mat("ChromeRod", (0.88, 0.89, 0.93), 1.0, 0.1)
steel = mat("SteelDark", (0.2, 0.21, 0.24), 0.9, 0.4)
rubber = mat("SealRubber", (0.03, 0.03, 0.03), 0.0, 0.6)
torn = mat("TornRubber", (0.15, 0.05, 0.02), 0.0, 0.7)
oil = mat("HydraulicOil", (0.25, 0.14, 0.03), 0.0, 0.1)
dark = mat("CrackDark", (0.01, 0.01, 0.01), 0.0, 1.0)
bolt_m = mat("BoltSteel", (0.35, 0.35, 0.38), 1.0, 0.4)

# barrel (hollow tube, bulged mid-section)
prof = [(15, 0), (19, 0)]
for k in range(1, 12):
    z = 80 * k / 12
    prof.append((19 + 2.4 * math.sin(math.pi * k / 12) ** 2 * (1 if abs(k - 6) < 3 else 0), z))
prof += [(19, 80), (15, 80)]
to_obj("Barrel_Bulged", lathe_bm(prof, 64), paint, "FAULT").location = (0, 0, 8)
for k, (a, z) in enumerate([(-0.6, 40), (-0.5, 46)]):
    box(f"Barrel_Crack{k}", (0.6, 0.5, 9), (21.3 * math.cos(a), 21.3 * math.sin(a), 8 + z), dark, 0.0, "FAULT",
        rot=Matrix.Rotation(a, 3, "Z"))
cyl("Base_Cap", 21, 8, (0, 0, 4), paint, 48, status="OK")
cyl("Base_Eye", 9, 8, (0, 0, -3), steel, 32, status="OK")
for i in range(4):
    a = i * math.pi / 2 + math.pi / 4
    cyl(f"Bolt_Head_{i}", 1.8, 2.4, (math.cos(a) * 17, math.sin(a) * 17, 10.3), bolt_m, 6, status="OK")
    cyl(f"Bolt_Rod_{i}", 0.9, 90, (math.cos(a) * 17, math.sin(a) * 17, 55), bolt_m, 10, status="OK")
# piston + rod
cyl("Piston_Head", 14.8, 10, (0, 0, 35), steel, 48, status="OK")
for z in (31, 39):
    cyl(f"Piston_Ring_{int(z)}", 15.1, 1.6, (0, 0, z), rubber, 48, status="OK")
cyl("Rod", 6, 110, (0, 0, 78), chrome, 32, status="OK")
for k, z in enumerate((100, 104, 109)):
    cyl(f"Rod_ScoredRing{k}", 6.25, 1.0, (0, 0, z), dark, 24, status="FAULT")
cyl("Rod_Clevis", 8, 12, (0, 0, 138), steel, 24, status="OK")
# gland + rod seal
to_obj("Gland_Cap", lathe_bm([(6.6, 0), (21, 0), (21, 6), (11, 6), (11, 10), (6.6, 10)], 64), paint, "OK").location = (0, 0, 88)
to_obj("Seal_Torn", lathe_bm([(6.1, -2), (10.5, -2), (10.5, 2), (6.1, 2)], 48), torn, "FAULT").location = (0, 0, 94)
for k in range(3):
    a = 1.0 + k * 0.14
    box(f"Seal_Tear{k}", (0.5, 3.0, 3.0), (math.cos(a) * 10.5, math.sin(a) * 10.5, 94), mat("TearGap", (0, 0, 0), 0, 1),
        0.02, "FAULT", rot=Matrix.Rotation(a, 3, "Z"))
bm = sphere_bm(1.0, 24)
bmesh.ops.scale(bm, vec=(11, 8, 0.25), verts=bm.verts[:])
to_obj("Gland_LeakPuddle", bm, oil, "FAULT").location = (6, 8, 98.3)
for k, (x, y) in enumerate([(-8, 6), (12, -4), (2, 15)]):
    sphere(f"Gland_LeakDrop{k}", 1.0, (x, y, 98.6), oil, 12, "FAULT")

finish_product("hydraulic", out, preview, cam=(170, -210, 120), target=(0, 0, 95), lens=34, floor_z=-8,
               rules=[("Bolts", sw("Bolt_")), ("Gland", sw("Gland", "Seal")), ("RodGroup", sw("Rod")),
                      ("Piston", sw("Piston")), ("BaseGroup", sw("Base"))],
               offsets={"BaseGroup": (0, 0, -28), "Piston": (0, 0, 40), "RodGroup": (0, 0, 76), "Gland": (0, 0, 112),
                        "Bolts": (0, 0, 150)},
               ex_target=(0, 0, 95), zoom=2.3, lift=0)
