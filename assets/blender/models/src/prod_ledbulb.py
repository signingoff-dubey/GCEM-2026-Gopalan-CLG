"""LED bulb (vertical): burnt LED chip, cracked diffuser dome, bulged driver capacitor, scorched driver board."""
import math
import os
import sys

from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prod_common import *  # noqa: E402,F401,F403

out, preview = args()
reset()

glass = mat("DiffuserGlass", (0.92, 0.93, 0.95), 0.0, 0.2, alpha=0.55)
alu = mat("HeatsinkAluminium", (0.8, 0.82, 0.86), 1.0, 0.3)
brass = mat("BaseBrass", (0.78, 0.58, 0.18), 1.0, 0.3)
white = mat("PlasticWhite", (0.93, 0.93, 0.9), 0.0, 0.5)
led_m = mat("LEDPhosphor", (1.0, 0.85, 0.3), 0.0, 0.3, emit=(1.0, 0.8, 0.25), estr=2.0)
led_burnt = mat("BurntLED", (0.03, 0.02, 0.01), 0.0, 0.9)
pcb_m = mat("DriverBoard", (0.05, 0.35, 0.18), 0.0, 0.5)
cap_m = mat("CapacitorBlue", (0.05, 0.1, 0.5), 0.2, 0.4)
cap_top = mat("CapacitorTop", (0.7, 0.7, 0.72), 1.0, 0.3)
dark = mat("CrackDark", (0.01, 0.01, 0.01), 0.0, 1.0)
soot = mat("SootBlack", (0.02, 0.02, 0.02), 0.0, 0.9)
insul = mat("InsulatorBlack", (0.03, 0.03, 0.03), 0.0, 0.6)

# E27-style base (bottom) with thread rings
to_obj("Base_Shell", lathe_bm([(8.5, 0), (13.5, 0), (13.5, 24), (8.5, 24)], 48), brass, "OK").location = (0, 0, 0)
for k in range(6):
    cyl(f"Base_Thread_{k}", 14.1, 1.2, (0, 0, 3 + k * 3.4), brass, 48, status="OK")
cyl("Base_Contact", 4.5, 2, (0, 0, -1), brass, 24, status="OK")
cyl("Base_Insulator", 7.5, 2, (0, 0, 1), insul, 32, status="OK")
# driver board + components
cyl("Driver_Board", 10, 1.6, (0, 0, 32), pcb_m, 48, status="OK")
for k, (x, y, h, r) in enumerate([(-4, 0, 7, 2.6), (3, 4, 6, 2.2), (4, -4, 5, 2.0)]):
    if k == 0:
        cyl("Capacitor_Bulged_0", r * 1.0, h * 1.35, (x, y, 32.8 + h * 0.675), cap_m, 24, status="FAULT")
        cyl("Capacitor_BulgedTop_0", r * 1.15, 0.8, (x, y, 32.8 + h * 1.35), cap_top, 24, status="FAULT")
    else:
        cyl(f"Capacitor_{k}", r, h, (x, y, 32.8 + h / 2), cap_m, 24, status="OK")
for k, (x, y) in enumerate([(5, 1), (6.5, 3), (-1, -6)]):
    sphere(f"Driver_Scorch{k}", 1.4, (x, y, 33.0), soot, 10, "FAULT")
box("Driver_Chip", (4, 4, 1.4), (-2, 5, 33.4), insul, 0.2, "OK")
# heatsink: collar + fins
to_obj("Heatsink_Collar", lathe_bm([(9, 0), (15, 0), (19, 10), (15, 10), (9, 10)], 64), alu, "OK").location = (0, 0, 24)
for i in range(16):
    a = i * 2 * math.pi / 16
    box(f"Heatsink_Fin_{i}", (4.5, 0.8, 9), (math.cos(a) * 16.5, math.sin(a) * 16.5, 29), alu, 0.1, "OK",
        rot=Matrix.Rotation(a, 3, "Z"))
# LED board
cyl("Board_Disc", 18, 1.6, (0, 0, 42), white, 64, status="OK")
for i in range(12):
    a = i * 2 * math.pi / 12
    x, y = math.cos(a) * 11, math.sin(a) * 11
    if i == 4:
        box("LED_Burnt_4", (3.4, 3.4, 1.6), (x, y, 43.4), led_burnt, 0.2, "FAULT")
        sphere("LED_Scorch4", 2.0, (x, y, 44.4), soot, 10, "FAULT")
    else:
        box(f"LED_{i}", (3.4, 3.4, 1.6), (x, y, 43.4), led_m, 0.2, "OK")
for i in range(6):
    a = i * 2 * math.pi / 6 + math.pi / 6
    box(f"LED_Inner_{i}", (3.4, 3.4, 1.6), (math.cos(a) * 5, math.sin(a) * 5, 43.4), led_m, 0.2, "OK")
# diffuser dome (hollow) with cracks
dome = [(0, 0), (18, 0), (19, 4), (20.5, 14), (20, 26), (15, 36), (8, 42), (0, 44), (0, 43), (7, 41), (14, 35), (19, 25),
        (19.5, 14), (18, 4), (17.4, 1), (0, 1)]
to_obj("Dome_Diffuser", lathe_bm(dome, 64), glass, "OK").location = (0, 0, 45)
for k, (a, z, ln, tilt) in enumerate([(0.4, 62, 14, 0.4), (0.7, 70, 9, -0.5), (-0.2, 58, 8, 0.8)]):
    r = 20.4 - (z - 59) * 0.18
    box(f"Dome_Crack{k}", (0.5, 0.5, ln), (r * math.cos(a), r * math.sin(a), z), dark, 0.0, "FAULT",
        rot=Matrix.Rotation(a, 3, "Z") @ Matrix.Rotation(tilt, 3, "Y"))

finish_product("ledbulb", out, preview, cam=(115, -150, 100), target=(0, 0, 40), lens=36, floor_z=-4,
               rules=[("Dome", sw("Dome")), ("LEDs", sw("LED", "Board")), ("Sink", sw("Heatsink")),
                      ("Driver", sw("Driver", "Capacitor")), ("Basegrp", sw("Base"))],
               offsets={"Basegrp": (0, 0, -18), "Driver": (0, 0, 6), "Sink": (46, 0, 18), "LEDs": (0, 0, 30),
                        "Dome": (0, 0, 56)},
               ex_target=(0, 0, 45), zoom=2.3, lift=0)
