"""Spark plug (vertical): cracked ceramic insulator, overheated electrode, sooted shell, burnt terminal."""
import math
import os
import sys

from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prod_common import *  # noqa: E402,F401,F403

out, preview = args()
reset()

ceramic = mat("Ceramic", (0.95, 0.94, 0.9), 0.0, 0.25)
steel = mat("ShellZinc", (0.6, 0.62, 0.66), 1.0, 0.35)
nickel = mat("Nickel", (0.75, 0.75, 0.78), 1.0, 0.25)
hot = mat("OverheatedMetal", (0.28, 0.12, 0.35), 1.0, 0.4)
soot = mat("SootBlack", (0.02, 0.02, 0.02), 0.0, 0.9)
dark = mat("CrackDark", (0.01, 0.01, 0.01), 0.0, 1.0)
copper = mat("CopperCore", (0.75, 0.38, 0.15), 1.0, 0.3)
burnt = mat("BurntTerminal", (0.08, 0.04, 0.02), 0.3, 0.7)

# insulator: stepped ceramic with ribs
ins = [(0, 0), (4.2, 0), (4.2, 28), (6.4, 30), (6.4, 54), (5.2, 56), (5.2, 58), (6.4, 60), (6.4, 66), (0, 66)]
to_obj("Insulator", lathe_bm(ins, 64), ceramic, "OK").location = (0, 0, 22)
for k, (a, z, ln) in enumerate([(0.4, 56, 12), (-0.3, 64, 9), (1.1, 48, 8)]):
    box(f"Insulator_Crack{k}", (0.45, 0.5, ln), (6.55 * math.cos(a), 6.55 * math.sin(a), z), dark, 0.0, "FAULT",
        rot=Matrix.Rotation(a, 3, "Z"))
# shell: hex + threaded body
to_obj("Shell_Thread", lathe_bm([(5.0, 0), (7.4, 0), (7.4, 20), (5.0, 20)], 48), steel, "OK").location = (0, 0, 2)
bmh = bmesh.new()
bmesh.ops.create_cone(bmh, cap_ends=True, segments=6, radius1=10.5, radius2=10.5, depth=9)
bmesh.ops.translate(bmh, vec=(0, 0, 26.5), verts=bmh.verts[:])
to_obj("Shell_Hex", bmh, steel, "OK")
for k in range(10):
    cyl(f"Shell_Rib_{k}", 7.7, 0.5, (0, 0, 4 + k * 1.8), steel, 24, status="OK")
for k, (a, z, r) in enumerate([(0.7, 6, 2.0), (2.4, 12, 2.4), (4.0, 17, 1.8), (5.4, 9, 2.2)]):
    sphere(f"Shell_Soot{k}", r, (8.0 * math.cos(a), 8.0 * math.sin(a), z), soot, 10, "FAULT")
cyl("Gasket_Washer", 9.2, 1.4, (0, 0, 22.4), nickel, 40, status="OK")
# centre electrode + ground electrode
cyl("Electrode_Centre", 1.1, 10, (0, 0, 1), nickel, 16, status="OK")
cyl("Electrode_Tip", 1.4, 1.6, (0, 0, -3.6), nickel, 16, status="OK")
poly_curve("Electrode_Overheated_Ground", [(7.0, 0, 2), (7.0, 0, -4.4), (3.0, 0, -4.8), (0.9, 0, -4.8)], 1.1, hot, "FAULT")
sphere("Electrode_OverheatedTipBlob", 1.5, (0, 0, -5.0), hot, 12, "FAULT")
# terminal stack
cyl("Terminal_Rod", 2.0, 20, (0, 0, 100), nickel, 16, status="OK")
cyl("Terminal_Nut_Burnt", 4.2, 6, (0, 0, 111), burnt, 6, status="FAULT")
for k, dz in enumerate((-2, 2, 6)):
    sphere(f"Terminal_Scorch{k}", 1.7, (3.5 * math.cos(k * 2.1), 3.5 * math.sin(k * 2.1), 111 + dz), soot, 10, "FAULT")
cyl("Core_Resistor", 2.6, 12, (0, 0, 92), copper, 16, status="OK")

finish_product("sparkplug", out, preview, cam=(110, -150, 95), target=(0, 0, 70), lens=36, floor_z=-8,
               rules=[("Terminal", sw("Terminal")), ("Core", sw("Core")), ("Ins", sw("Insulator")),
                      ("Washer", sw("Gasket")), ("Shell", sw("Shell")), ("Elec", sw("Electrode"))],
               offsets={"Elec": (0, 0, -26), "Shell": (0, 0, -10), "Washer": (0, 0, 14), "Ins": (0, 0, 34),
                        "Core": (0, 0, 58), "Terminal": (0, 0, 80)},
               ex_target=(0, 0, 70), zoom=2.2, lift=0)
