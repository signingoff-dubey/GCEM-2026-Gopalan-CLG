"""Ball valve: pitted ball, leaking stem packing, cracked handle, torn seat seal."""
import math
import os
import sys

from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prod_common import *  # noqa: E402,F401,F403

out, preview = args()
reset()

brass = mat("Brass", (0.8, 0.6, 0.2), 1.0, 0.3)
chrome = mat("ChromeBall", (0.85, 0.86, 0.9), 1.0, 0.12)
red = mat("HandleRed", (0.7, 0.05, 0.04), 0.0, 0.5)
ptfe = mat("PTFE", (0.9, 0.9, 0.88), 0.0, 0.6)
torn = mat("TornPTFE", (0.35, 0.3, 0.2), 0.0, 0.8)
pit_m = mat("PitDark", (0.03, 0.03, 0.03), 0.4, 0.8)
fluid = mat("LeakFluid", (0.15, 0.3, 0.4), 0.0, 0.1)
dark = mat("CrackDark", (0.01, 0.01, 0.01), 0.0, 1.0)
bolt_m = mat("BoltSteel", (0.35, 0.35, 0.38), 1.0, 0.4)

# body (flow along X): centre sphere + two threaded ends
bodyb = sphere_bm(26, 48)
to_obj("Body_Centre", bodyb, brass, "OK")
cyl("Body_InletPipe", 15, 40, (-38, 0, 0), brass, 40, axis="X", status="OK")
cyl("Body_InletNut", 20, 8, (-52, 0, 0), brass, 6, axis="X", status="OK")
cyl("Body_OutletPipe", 15, 40, (38, 0, 0), brass, 40, axis="X", status="OK")
cyl("Body_OutletNut", 20, 8, (52, 0, 0), brass, 6, axis="X", status="OK")
cyl("Body_NeckBoss", 11, 16, (0, 0, 30), brass, 32, status="OK")
# ball with bore, pitted
ball = sphere_bm(20, 48)
to_obj("Ball", ball, chrome, "OK")
cyl("Ball_Bore", 9, 41, (0, 0, 0), mat("Bore", (0.02, 0.02, 0.025), 0.5, 0.5), 32, axis="X", status="OK")
for k in range(9):
    lon = -math.pi / 2 + (k % 3 - 1) * 0.32
    lat = (k // 3 - 1) * 0.3
    r = 20.15
    sphere(f"Ball_Pit{k}", 0.9, (r * math.cos(lat) * math.cos(lon), r * math.cos(lat) * math.sin(lon), r * math.sin(lat)),
           pit_m, 10, "FAULT")
# seats
for s in (-1, 1):
    if s == 1:
        to_obj("Seat_TornSeal", lathe_bm([(14, -2), (19, -2), (19, 2), (14, 2)], 48), torn, "FAULT").rotation_euler = (0, math.pi / 2, 0)
        bpy.data.objects["Seat_TornSeal"].location = (s * 21, 0, 0)
        for k in range(3):
            ang = 0.4 + k * 0.15
            box(f"Seat_Tear{k}", (0.6, 3.5, 3.0), (s * 21, math.cos(ang) * 16.5, math.sin(ang) * 16.5), mat("TearGap", (0, 0, 0), 0, 1),
                0.0, "FAULT")
    else:
        t = to_obj("Seat_In", lathe_bm([(14, -2), (19, -2), (19, 2), (14, 2)], 48), ptfe, "OK")
        t.rotation_euler = (0, math.pi / 2, 0)
        t.location = (s * 21, 0, 0)
# stem + packing + gland + handle
cyl("Stem", 4, 46, (0, 0, 26), chrome, 24, status="OK")
cyl("Packing_Ring", 6.2, 4, (0, 0, 40), ptfe, 24, status="OK")
cyl("Gland_Nut", 9.5, 6, (0, 0, 46), brass, 6, status="OK")
bm = sphere_bm(1.0, 24)
bmesh.ops.scale(bm, vec=(9, 7, 0.3), verts=bm.verts[:])
to_obj("Neck_LeakPuddle", bm, fluid, "FAULT").location = (0, 5, 38.2)
for k, (x, y) in enumerate([(5, 10), (-4, 12)]):
    sphere(f"Neck_LeakDrop{k}", 1.1, (x, y, 38.6), fluid, 12, "FAULT")
box("Handle_Lever", (50, 8, 4), (24, 0, 56), red, 0.8, "OK")
cyl("Handle_Hub", 8, 6, (0, 0, 56), red, 24, status="OK")
for k, (x, ang) in enumerate([(14, 0.9), (22, -0.7)]):
    box(f"Handle_Crack{k}", (7, 0.5, 0.5), (x, 1.5 * (-1) ** k, 58.1), dark, 0.0, "FAULT", rot=Matrix.Rotation(ang, 3, "Z"))
cyl("Handle_Nut", 3.2, 4, (0, 0, 60), bolt_m, 6, status="OK")
# flange bolts on the inlet/outlet nuts
for i, x in enumerate((-52, 52)):
    for j in range(4):
        a = j * math.pi / 2 + math.pi / 4
        cyl(f"Bolt_{i}_{j}", 1.4, 9, (x, math.cos(a) * 16.5, math.sin(a) * 16.5), bolt_m, 8, axis="X", status="OK")

finish_product("valve", out, preview, cam=(110, -150, 90), target=(0, 0, 18), lens=40, floor_z=-28,
               rules=[("Bolts", sw("Bolt_")), ("Handle", sw("Handle")), ("Gland", sw("Gland", "Packing")),
                      ("Stem", sw("Stem")), ("BallGroup", sw("Ball")), ("SeatOut", sw("Seat_Torn")),
                      ("SeatIn", sw("Seat_In"))],
               offsets={"SeatIn": (-26, 0, 0), "SeatOut": (26, 0, 0), "BallGroup": (0, -40, 0), "Stem": (0, 0, 14),
                        "Gland": (0, 0, 30), "Handle": (0, 0, 48), "Bolts": (0, 34, 0)},
               ex_target=(0, 0, 25), zoom=1.8, lift=20)
