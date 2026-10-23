"""Pin-tumbler padlock: cracked shackle, broken key pin with fragment, broken spring, pitted (corroded) body."""
import math
import os
import random
import sys

from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prod_common import *  # noqa: E402,F401,F403

out, preview = args()
random.seed(5)
reset()

body_m = mat("LockBrass", (0.78, 0.58, 0.18), 1.0, 0.3)
steel = mat("HardenedSteel", (0.72, 0.73, 0.77), 1.0, 0.2)
plug_m = mat("PlugBrass", (0.85, 0.7, 0.3), 1.0, 0.25)
pin_m = mat("PinNickel", (0.8, 0.8, 0.84), 1.0, 0.2)
frac = mat("FractureFace", (0.55, 0.3, 0.12), 0.8, 0.45)
spring_m = mat("SpringSteel", (0.5, 0.5, 0.55), 1.0, 0.3)
dark = mat("CrackDark", (0.01, 0.01, 0.01), 0.0, 1.0)
pit_m = mat("CorrosionPits", (0.1, 0.12, 0.08), 0.3, 0.9)
bolt_m = mat("BoltSteel", (0.35, 0.35, 0.38), 1.0, 0.4)

# body: laminated block with lock cylinder bore at the front (-Y)
box("Body_Lower", (50, 22, 24), (0, 0, 12), body_m, 1.2, "OK")
box("Body_Upper", (50, 22, 12), (0, 0, 30), body_m, 1.2, "OK")
for k in range(8):
    x, z = random.uniform(-20, 20), random.uniform(4, 34)
    sphere(f"Body_Pit{k}", 0.8, (x, -11.0, z), pit_m, 10, "FAULT")
# shackle: U-shape with a long and a short leg
sh = [(-16, 0, 36), (-16, 0, 66), (-12, 0, 76), (0, 0, 80), (12, 0, 76), (16, 0, 66), (16, 0, 36)]
poly_curve("Shackle_Cracked", sh, 3.4, steel, "FAULT")
for k, (x, z, ang) in enumerate([(-16.5, 60, 0.0), (13.5, 74, 0.7)]):
    box(f"Shackle_Crack{k}", (0.6, 0.6, 7), (x, -2.2 if k == 0 else -1.6, z), dark, 0.0, "FAULT",
        rot=Matrix.Rotation(ang, 3, "Y"))
cyl("Shackle_Bushing_L", 5, 4, (-16, 0, 38), steel, 24, status="OK")
cyl("Shackle_Bushing_R", 5, 4, (16, 0, 38), steel, 24, status="OK")
# lock cylinder (plug) + keyway
cyl("Plug_Cylinder", 8, 22, (0, -4, 14), plug_m, 40, axis="Y", status="OK")
cyl("Plug_Face", 8.6, 2, (0, -15, 14), plug_m, 40, axis="Y", status="OK")
box("Plug_Keyway", (1.6, 2.2, 8), (0, -15.8, 14), dark, 0.0, "OK")
# pin stack: 5 key pins + driver pins + springs above the plug
for i in range(5):
    x = -8 + i * 4
    if i == 2:
        box("Pin_Broken_2", (2.4, 2.4, 3.2), (x, 0, 25.5), pin_m, 0.1, "FAULT")
        box("Pin_BrokenFace_2", (2.4, 2.4, 0.4), (x, 0, 27.3), frac, 0.0, "FAULT")
        box("Pin_Fragment_2", (2.2, 2.2, 4.6), (10, 6, 3.5), pin_m, 0.1, "FAULT",
            rot=Matrix.Rotation(0.7, 3, "X") @ Matrix.Rotation(0.4, 3, "Y"))
        sp = poly_curve("Spring_Broken_2", helix(1.3, 29, 33, 2.0, 20), 0.25, spring_m, "FAULT")
        sp.location = (x, 0, 0)
    else:
        box(f"Pin_Key_{i}", (2.4, 2.4, 5 + 0.6 * (i % 3)), (x, 0, 24.6 + 0.3 * (i % 3)), pin_m, 0.1, "OK")
        box(f"Pin_Driver_{i}", (2.4, 2.4, 4), (x, 0, 30.5), pin_m, 0.1, "OK")
        sp = poly_curve(f"Spring_{i}", helix(1.3, 33, 40, 4.0, 40), 0.25, spring_m, "OK")
        sp.location = (x, 0, 0)
# retaining parts
box("Cover_Plate", (46, 18, 3), (0, 0, 43), body_m, 0.8, "OK")
for i, (x, y) in enumerate([(-21, -7), (21, -7), (-21, 7), (21, 7)]):
    cyl(f"Bolt_Head_{i}", 1.8, 1.6, (x, y, 45), bolt_m, 6, status="OK")
    cyl(f"Bolt_Shank_{i}", 0.9, 16, (x, y, 36), bolt_m, 10, status="OK")

finish_product("padlock", out, preview, cam=(120, -160, 105), target=(0, 0, 40), lens=38, floor_z=-1,
               rules=[("Bolts", sw("Bolt_")), ("Shackle", sw("Shackle")), ("Cover", sw("Cover")),
                      ("Springs", sw("Spring")), ("Pins", sw("Pin_")), ("Plug", sw("Plug"))],
               offsets={"Plug": (0, -42, 0), "Pins": (0, 0, 26), "Springs": (0, 0, 46), "Cover": (0, 0, 68),
                        "Shackle": (0, 0, 40), "Bolts": (0, 0, 92)},
               ex_target=(0, 0, 55), zoom=1.8, lift=0)
