"""Cylindrical lithium cell (vertical): swollen can, leaking electrolyte at the cap, scorched jelly roll, torn vent disc."""
import math
import os
import sys

from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prod_common import *  # noqa: E402,F401,F403

out, preview = args()
reset()

can_m = mat("CanSteel", (0.75, 0.77, 0.8), 1.0, 0.3)
wrap = mat("CellWrapBlue", (0.05, 0.3, 0.75), 0.0, 0.4)
cu = mat("CopperFoil", (0.75, 0.38, 0.15), 1.0, 0.3)
al = mat("AluminiumFoil", (0.8, 0.82, 0.85), 1.0, 0.25)
sep = mat("SeparatorWhite", (0.92, 0.92, 0.9), 0.0, 0.7)
cap_m = mat("CapNickel", (0.85, 0.85, 0.88), 1.0, 0.2)
burnt = mat("ScorchedFoil", (0.04, 0.03, 0.02), 0.2, 0.9)
fluid = mat("Electrolyte", (0.85, 0.8, 0.45), 0.0, 0.08)
tear = mat("TearGap", (0.0, 0.0, 0.0), 0.0, 1.0)
ins_m = mat("RedInsulator", (0.7, 0.05, 0.04), 0.0, 0.6)

# can: open-topped shell, 0.8 mm wall, bulged mid-section
prof = [(0, 0), (11, 0)]
for k in range(1, 10):
    prof.append((11 + 1.8 * math.sin(math.pi * k / 10) ** 2, 65 * k / 10))
prof += [(11, 65), (10.2, 65), (10.2, 1), (0, 1)]
to_obj("Can_Swollen", lathe_bm(prof, 64), can_m, "FAULT")
to_obj("Wrap_Sleeve", lathe_bm([(11.2, 3), (11.45, 3), (11.45, 62), (11.2, 62)], 64), wrap, "OK")
# jelly roll: concentric layers, outermost scorched
for k, r in enumerate((9.6, 8.0, 6.4, 4.8, 3.2)):
    m = sep if k % 2 == 0 else (cu if k == 1 else al)
    to_obj(f"Jelly_Layer_{k}", lathe_bm([(r - 0.7, 3), (r, 3), (r, 60), (r - 0.7, 60)], 64), m, "OK")
to_obj("Jelly_Burnt_Layer", lathe_bm([(9.9, 20), (10.1, 20), (10.1, 48), (9.9, 48)], 64), burnt, "FAULT")
for k, (a, z) in enumerate([(0.5, 28), (2.0, 36), (3.6, 42)]):
    sphere(f"Jelly_Scorch{k}", 2.4, (9.2 * math.cos(a), 9.2 * math.sin(a), z), burnt, 10, "FAULT")
cyl("Jelly_Core_Pin", 1.6, 58, (0, 0, 32), cap_m, 24, status="OK")
# top assembly
cyl("Insulator_Ring", 9.5, 1.2, (0, 0, 63.6), ins_m, 48, status="OK")
to_obj("Vent_Torn", lathe_bm([(0, 0), (8.4, 0), (8.4, 0.8), (0, 0.8)], 48), mat("VentFoil", (0.6, 0.62, 0.66), 1.0, 0.4), "FAULT").location = (0, 0, 66)
for k in range(3):
    a = 0.8 + k * 0.5
    box(f"Vent_Tear{k}", (4.5, 0.5, 1.2), (math.cos(a) * 4.5, math.sin(a) * 4.5, 66.4), tear, 0.0, "FAULT",
        rot=Matrix.Rotation(a, 3, "Z"))
cyl("Cap_Positive", 5, 3.4, (0, 0, 69.2), cap_m, 32, status="OK")
cyl("Cap_Shoulder", 8.4, 1.0, (0, 0, 67.6), cap_m, 48, status="OK")
bm = sphere_bm(1.0, 24)
bmesh.ops.scale(bm, vec=(9, 7, 0.22), verts=bm.verts[:])
to_obj("Cap_LeakPuddle", bm, fluid, "FAULT").location = (3, 5, 71.0)
for k, (x, y) in enumerate([(-6, 8), (10, -2)]):
    sphere(f"Cap_LeakDrop{k}", 1.0, (x, y, 71.3), fluid, 12, "FAULT")
cyl("Base_Negative", 9.8, 1.2, (0, 0, 0.6), can_m, 48, status="OK")
cyl("Base_Disc", 8.6, 1.0, (0, 0, 2.5), cu, 48, status="OK")

finish_product("cell", out, preview, cam=(95, -125, 85), target=(0, 0, 55), lens=36, floor_z=-4,
               rules=[("Top", sw("Cap_")), ("Vent", sw("Vent", "Insulator")), ("Jelly", sw("Jelly")),
                      ("Wrapg", sw("Wrap")), ("Can", sw("Can")), ("Baseg", sw("Base"))],
               offsets={"Baseg": (0, 0, -22), "Jelly": (0, 0, 20), "Wrapg": (40, 0, 0), "Vent": (0, 0, 48),
                        "Top": (0, 0, 70)},
               ex_target=(0, 0, 55), zoom=2.4, lift=0)
