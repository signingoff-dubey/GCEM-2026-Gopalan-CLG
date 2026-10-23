"""Disc brake: cracked and scored rotor, burnt pad, torn caliper seal leaking fluid, grit where a hub bolt is gone."""
import math
import os
import sys

from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prod_common import *  # noqa: E402,F401,F403

out, preview = args()
reset()

disc = mat("CastIronDisc", (0.42, 0.43, 0.46), 0.95, 0.35)
hub_m = mat("HubSteel", (0.3, 0.31, 0.34), 0.9, 0.4)
red = mat("CaliperRed", (0.75, 0.05, 0.04), 0.3, 0.35)
pad_m = mat("PadFriction", (0.12, 0.11, 0.1), 0.0, 0.9)
burnt = mat("BurntPad", (0.03, 0.02, 0.02), 0.0, 0.95)
dark = mat("CrackDark", (0.01, 0.01, 0.01), 0.0, 1.0)
scored_m = mat("ScoreGroove", (0.15, 0.15, 0.17), 0.8, 0.5)
fluid = mat("BrakeFluid", (0.5, 0.35, 0.08), 0.0, 0.1)
bolt_m = mat("BoltSteel", (0.35, 0.35, 0.38), 1.0, 0.4)
debris_m = mat("DebrisGrit", (0.08, 0.06, 0.04), 0.2, 0.9)
soot = mat("SootBlack", (0.02, 0.02, 0.02), 0.0, 0.9)
vent_m = mat("VentHole", (0.01, 0.01, 0.01), 0.0, 1.0)

# rotor (axis Z): friction ring + hat
to_obj("Rotor_Disc", lathe_bm([(26, 0), (46, 0), (46, 5), (26, 5)], 96), disc, "OK")
to_obj("Rotor_Hat", lathe_bm([(8, 0), (26, 0), (26, 5), (24, 5), (24, 12), (8, 12)], 96), disc, "OK")
for i in range(18):
    a = i * 2 * math.pi / 18
    cyl(f"Rotor_Vent_{i}", 1.1, 5.4, (math.cos(a) * 36, math.sin(a) * 36, 2.5), vent_m, 12, status="OK")
for k, r in enumerate((29, 31.5, 38, 41)):
    to_obj(f"Rotor_ScoredGroove{k}", lathe_bm([(r, 5.0), (r + 0.5, 5.0), (r + 0.5, 5.12), (r, 5.12)], 96), scored_m, "FAULT")
for k, (a, r0, ln) in enumerate([(0.9, 27, 17), (1.0, 33, 9)]):
    box(f"Rotor_Crack{k}", (ln, 0.5, 0.4), (math.cos(a) * (r0 + ln / 2), math.sin(a) * (r0 + ln / 2), 5.1), dark, 0.0,
        "FAULT", rot=Matrix.Rotation(a, 3, "Z"))
cyl("Hub_Flange", 12, 7, (0, 0, 16), hub_m, 48, status="OK")
for i in range(5):
    a = i * 2 * math.pi / 5
    x, y = math.cos(a) * 17, math.sin(a) * 17
    if i == 2:
        for k in range(3):
            sphere(f"Hub_Debris{k}", 0.8, (x + (k - 1) * 1.4, y + k * 0.8, 6), debris_m, 8, "FAULT")
        continue
    cyl(f"Bolt_Head_{i}", 2.0, 3, (x, y, 13.5), bolt_m, 6, status="OK")
    cyl(f"Bolt_Shank_{i}", 1.0, 12, (x, y, 5), bolt_m, 10, status="OK")
# caliper straddling the disc at +X
box("Caliper_Bridge", (16, 30, 5), (52, 0, 12.5), red, 0.8, "OK")
box("Caliper_Inner", (16, 30, 8), (52, 0, -8.5), red, 0.8, "OK")
cyl("Caliper_Piston", 5, 6, (52, 0, -2), mat("PistonSteel", (0.8, 0.8, 0.84), 1.0, 0.2), 24, status="OK")
cyl("Caliper_Seal_Torn", 6, 1.2, (52, 0, -5.5), mat("TornRubber", (0.15, 0.05, 0.02), 0.0, 0.7), 24, status="FAULT")
bm = sphere_bm(1.0, 24)
bmesh.ops.scale(bm, vec=(7, 5, 0.25), verts=bm.verts[:])
to_obj("Caliper_LeakPuddle", bm, fluid, "FAULT").location = (50, -14, -13)
for k, (x, y) in enumerate([(56, -8), (46, -19)]):
    sphere(f"Caliper_LeakDrop{k}", 0.9, (x, y, -12.5), fluid, 10, "FAULT")
# pads
box("Pad_Outer", (10, 24, 3.2), (52, 0, 8.5), pad_m, 0.4, "OK")
box("Pad_Inner_Burnt", (10, 24, 3.2), (52, 0, -2), burnt, 0.4, "FAULT")
for k, (y, z) in enumerate([(-6, -0.2), (4, -0.2), (9, -0.2)]):
    sphere(f"Pad_Scorch{k}", 2.2, (52, y, z), soot, 10, "FAULT")
for k, y in enumerate((-8, 8)):
    box(f"Slider_Pin_{k}", (2, 2, 28), (52, y, 2), bolt_m, 0.1, "OK")

finish_product("brake", out, preview, cam=(120, -140, 100), target=(20, 0, 5), lens=40, floor_z=-16,
               rules=[("Bolts", sw("Bolt_", "Slider")), ("Hub", sw("Hub")), ("Rotor", sw("Rotor")),
                      ("PadOut", sw("Pad_Outer")),
                      ("PadIn", sw("Pad_Inner", "Pad_Scorch", "Caliper_Piston", "Caliper_Seal")),
                      ("CaliperTop", sw("Caliper_Bridge")), ("CaliperBot", sw("Caliper_Inner"))],
               offsets={"Hub": (0, 0, -34), "CaliperTop": (0, 0, 42), "PadOut": (0, 0, 24),
                        "PadIn": (0, 0, -20), "CaliperBot": (0, 0, -42), "Bolts": (0, 0, 60)},
               ex_target=(20, 0, 5), zoom=1.9, lift=10)
