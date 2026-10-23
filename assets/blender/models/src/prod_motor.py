"""Electric motor (vertical): burnt stator winding, cracked end cap, scored rotor shaft, lifted terminal lead."""
import math
import os
import sys

from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prod_common import *  # noqa: E402,F401,F403

out, preview = args()
reset()

body = mat("MotorBody", (0.1, 0.25, 0.5), 0.6, 0.4)
iron = mat("LaminationIron", (0.45, 0.46, 0.5), 0.9, 0.35)
copper = mat("Copper", (0.75, 0.38, 0.15), 1.0, 0.3)
burnt = mat("BurntCopper", (0.05, 0.03, 0.02), 0.2, 0.8)
steel = mat("ShaftSteel", (0.7, 0.71, 0.75), 1.0, 0.2)
dark = mat("CrackDark", (0.01, 0.01, 0.01), 0.0, 1.0)
soot = mat("SootBlack", (0.02, 0.02, 0.02), 0.0, 0.9)
bolt_m = mat("BoltSteel", (0.35, 0.35, 0.38), 1.0, 0.4)
wire_m = mat("WireRed", (0.7, 0.05, 0.04), 0.0, 0.5)

# frame
to_obj("Housing", lathe_bm([(26, 0), (30, 0), (30, 50), (26, 50)], 64), body, "OK").location = (0, 0, 10)
for i in range(4):
    a = i * math.pi / 2 + math.pi / 4
    box(f"Housing_Foot_{i}", (14, 8, 4), (math.cos(a) * 34, math.sin(a) * 34, 12), body, 0.4, "OK",
        rot=Matrix.Rotation(a, 3, "Z"))
box("Housing_TerminalBox", (14, 16, 14), (36, 0, 38), body, 0.8, "OK")
poly_curve("Terminal_Lead_Lifted", [(36, 0, 46), (42, 4, 56), (36, 12, 62), (28, 14, 58)], 0.9, wire_m, "FAULT")
# stator: laminated ring + 12 coils (coil 3 burnt)
to_obj("Stator_Core", lathe_bm([(19, 0), (26, 0), (26, 40), (19, 40)], 64), iron, "OK").location = (0, 0, 15)
for i in range(12):
    a = i * math.pi / 6
    c = (math.cos(a) * 17.0, math.sin(a) * 17.0, 35)
    if i == 3:
        box("Winding_Burnt_3", (4, 6.5, 40), c, burnt, 0.5, "FAULT", rot=Matrix.Rotation(a, 3, "Z"))
        for k, dz in enumerate((-10, 2, 12)):
            sphere(f"Winding_Scorch{k}", 2.4, (math.cos(a) * 15.2, math.sin(a) * 15.2, 35 + dz), soot, 12, "FAULT")
    else:
        box(f"Winding_{i}", (4, 6.5, 40), c, copper, 0.5, "OK", rot=Matrix.Rotation(a, 3, "Z"))
# rotor
cyl("Rotor_Core", 12.5, 40, (0, 0, 35), iron, 48, status="OK")
cyl("Rotor_Shaft", 4, 100, (0, 0, 40), steel, 32, status="OK")
for k, z in enumerate((78, 82, 86)):
    cyl(f"Rotor_ScoredRing{k}", 4.4, 1.2, (0, 0, z), dark, 24, status="FAULT")
for i in range(6):
    a = i * math.pi / 3
    box(f"Fan_Blade_{i}", (9, 1.2, 6), (math.cos(a) * 9, math.sin(a) * 9, 12), steel, 0.2, "OK",
        rot=Matrix.Rotation(a, 3, "Z"))
cyl("Fan_Hub", 5, 4, (0, 0, 12), steel, 24, status="OK")
# end caps
to_obj("EndCap_Bottom", lathe_bm([(0, 0), (30, 0), (30, 4), (7, 4), (7, 8), (0, 8)], 64), body, "OK").location = (0, 0, 6)
to_obj("EndCap_Top", lathe_bm([(0, 0), (30, 0), (30, 4), (7, 4), (7, 8), (0, 8)], 64), body, "OK").location = (0, 0, 60)
for k, (x, y, ln, ang) in enumerate([(14, 6, 18, 0.5), (22, -4, 11, -0.8), (8, 16, 9, 1.2)]):
    box(f"EndCap_Crack{k}", (ln, 0.7, 0.5), (x, y, 64.1), dark, 0.0, "FAULT", rot=Matrix.Rotation(ang, 3, "Z"))
for i in range(4):
    a = i * math.pi / 2 + math.pi / 4
    x, y = math.cos(a) * 28, math.sin(a) * 28
    cyl(f"Bolt_Head_{i}", 2.2, 2.4, (x, y, 66), bolt_m, 6, status="OK")
    cyl(f"Bolt_Rod_{i}", 1.0, 58, (x, y, 36), bolt_m, 10, status="OK")

finish_product("motor", out, preview, cam=(120, -150, 95), target=(0, 0, 35), lens=42, floor_z=0,
               rules=[("Bolts", sw("Bolt_")), ("Top", sw("EndCap_Top")), ("Rotor", sw("Rotor", "Fan")),
                      ("Stator", sw("Winding", "Stator")), ("Bottom", sw("EndCap_Bottom"))],
               offsets={"Bottom": (0, 0, -22), "Rotor": (0, 0, 18), "Stator": (82, 0, 0), "Top": (0, 0, 52),
                        "Bolts": (0, 0, 78)},
               ex_target=(0, 0, 45), zoom=1.7, lift=20)
