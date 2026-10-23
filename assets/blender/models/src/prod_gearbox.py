"""Two-stage gearbox: broken gear tooth with fragment, scored output shaft, overheated bearing, leaking housing seam."""
import math
import os
import sys

from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prod_common import *  # noqa: E402,F401,F403

out, preview = args()
reset()

cast = mat("GearboxCasting", (0.15, 0.3, 0.2), 0.5, 0.55)
gear_m = mat("GearSteel", (0.55, 0.57, 0.62), 1.0, 0.3)
gear_b = mat("GearBronze", (0.72, 0.45, 0.18), 1.0, 0.3)
steel = mat("ShaftSteel", (0.7, 0.71, 0.75), 1.0, 0.2)
frac = mat("FractureFace", (0.55, 0.3, 0.12), 0.8, 0.45)
hot = mat("OverheatedBearing", (0.25, 0.1, 0.4), 1.0, 0.4)
bearing = mat("BearingSteel", (0.6, 0.62, 0.66), 1.0, 0.25)
oil = mat("GearOil", (0.25, 0.15, 0.03), 0.0, 0.1)
dark = mat("ScoreDark", (0.02, 0.02, 0.02), 0.5, 0.7)
bolt_m = mat("BoltSteel", (0.35, 0.35, 0.38), 1.0, 0.4)

# housing: open-top box (floor + 4 walls), 100 x 56 x 30
box("Housing_Floor", (100, 56, 4), (0, 0, 2), cast, 0.8, "OK")
box("Housing_WallFront", (100, 4, 28), (0, -26, 16), cast, 0.8, "OK")
box("Housing_WallBack", (100, 4, 28), (0, 26, 16), cast, 0.8, "OK")
box("Housing_WallLeft", (4, 48, 28), (-48, 0, 16), cast, 0.8, "OK")
box("Housing_WallRight", (4, 48, 28), (48, 0, 16), cast, 0.8, "OK")
box("Housing_Seam_Leak", (98, 0.6, 0.8), (0, -28.1, 29.6), oil, 0.0, "FAULT")
bm = sphere_bm(1.0, 24)
bmesh.ops.scale(bm, vec=(16, 7, 0.25), verts=bm.verts[:])
to_obj("Housing_LeakPuddle", bm, oil, "FAULT").location = (-6, -34, -0.2)
for k, (x, y) in enumerate([(14, -31), (-20, -30), (6, -36)]):
    sphere(f"Housing_LeakDrop{k}", 1.0, (x, y, 0.2), oil, 12, "FAULT")
# stage 1: input shaft + pinion, intermediate gear; stage 2: output
XI = -30
XC = XI + 31      # idler / countershaft
XO = XC + 22.5    # output shaft
cyl("Input_Shaft", 3.5, 56, (XI, 0, 28), steel, 24, status="OK")
to_obj("Input_Pinion", gear_bm(14, 8.4, 10.4, 8), gear_m, "OK").location = (XI, 0, 12)
to_obj("Idler_Gear", gear_bm(32, 19.5, 21.5, 8, skip=11), gear_b, "OK").location = (XC, 0, 12)
# broken tooth: stump + fractured face + fragment on the housing floor
a = (11 + 0.3) * 2 * math.pi / 32
bx, by = XC + 20.5 * math.cos(a), 20.5 * math.sin(a)
box("Gear_Tooth_Broken", (1.6, 2.2, 8), (bx, by, 12), gear_b, 0.1, "FAULT", rot=Matrix.Rotation(a, 3, "Z"))
box("Gear_ToothBreak", (0.4, 2.4, 8.1), (bx + 1.1 * math.cos(a), by + 1.1 * math.sin(a), 12), frac, 0.0, "FAULT",
    rot=Matrix.Rotation(a, 3, "Z"))
box("Gear_ToothFragment", (3.2, 2.0, 2.6), (6, 12, 5.8), gear_b, 0.1, "FAULT",
    rot=Matrix.Rotation(0.9, 3, "Z") @ Matrix.Rotation(0.5, 3, "X"))
cyl("Idler_Shaft", 3, 44, (XC, 0, 22), steel, 24, status="OK")
to_obj("Output_Pinion", gear_bm(11, 6.6, 8.6, 8), gear_m, "OK").location = (XC, 0, 22)
to_obj("Output_Gear", gear_bm(20, 12, 14, 8), gear_m, "OK").location = (XO, 0, 22)
cyl("Output_Shaft", 4, 62, (XO, 0, 26), steel, 24, status="OK")
for k, z in enumerate((40, 43.5, 47)):
    cyl(f"Output_ScoredRing{k}", 4.35, 1.0, (XO, 0, z), dark, 24, status="FAULT")
# bearings (one overheated)
for nm, x, y, st, m in (("Bearing_In", XI, 0, "OK", bearing), ("Bearing_Idler", XC, 0, "OK", bearing),
                        ("Bearing_Overheated_Out", XO, 0, "FAULT", hot)):
    to_obj(nm, lathe_bm([(4.2, 0), (7.6, 0), (7.6, 5), (4.2, 5)], 40), m, st).location = (x, y, 3.5)
# cover + bolts
box("Cover_Plate", (102, 58, 3), (0, 0, 31.5), cast, 0.8, "OK")
for i, (x, y) in enumerate([(-46, -24), (46, -24), (-46, 24), (46, 24), (0, -26.5), (0, 26.5)]):
    cyl(f"Bolt_Head_{i}", 2.2, 2.0, (x, y, 34), bolt_m, 6, status="OK")
    cyl(f"Bolt_Shank_{i}", 1.1, 8, (x, y, 28), bolt_m, 10, status="OK")

finish_product("gearbox", out, preview, cam=(130, -150, 120), target=(0, 0, 30), lens=34, floor_z=-1,
               rules=[("Bolts", sw("Bolt_")), ("Cover", sw("Cover")), ("Output", sw("Output")),
                      ("Idler", sw("Idler", "Gear_")), ("Input", sw("Input")), ("Bearings", sw("Bearing"))],
               offsets={"Bearings": (0, 0, 8), "Input": (0, 0, 22), "Idler": (0, 0, 40), "Output": (0, 0, 58),
                        "Cover": (0, 0, 80), "Bolts": (0, 0, 98)},
               ex_target=(0, 0, 50), zoom=1.9, lift=0)
