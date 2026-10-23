def rd(f):
    return open(f, encoding="utf-8").read()


def rep(s, old, new, count=1):
    assert old in s, "missing: " + old[:70]
    return s.replace(old, new, count)


def wrap(s, start, end, cond):
    """Indent the block from `start` up to (not including) `end` under `if cond:`."""
    a = s.index(start)
    b = s.index(end, a)
    block = s[a:b].rstrip("\n")
    ind = "\n".join(("    " + ln if ln.strip() else ln) for ln in block.split("\n"))
    return s[:a] + f"if {cond}:\n" + ind + "\n\n" + s[b:]


def cut_labels(s, start, new):
    a = s.index(start)
    b = s.index("stage(", a)
    return s[:a] + new + "\n" + s[b:]


def tail(s, fam):
    a = s.index("os.makedirs(out")
    return s[:a] + f'''os.makedirs(out, exist_ok=True)
sc = bpy.context.scene
base = os.path.join(out, "{fam}_v%d" % VAR)
tag_rootlens("{fam}", VAR, base + ".json")
sc.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=base + ".blend")
export_glb(base + ".glb")
print("DONE")
'''


HEAD = '\nVAR = int(os.environ.get("VARIANT", "1"))\nVP = {table}[VAR]\n'


def head(s, table):
    return rep(s, "reset()\n", "reset()" + HEAD.format(table=table), 1)


# ------------------------------------------------------------------ bearing
s = rd("bearing.py")
s = head(s, """{
    1: dict(N=8, broken=3, missing=None, spall=True, spall_deg=200, crack=False, crack_deg=300),
    2: dict(N=10, broken=None, missing=2, spall=False, spall_deg=130, crack=True, crack_deg=60),
    3: dict(N=7, broken=5, missing=1, spall=True, spall_deg=290, crack=True, crack_deg=20),
}""")
s = rep(s, "N = 9\n", 'N = VP["N"]\n')
s = rep(s, "broken_i, missing_i = 7, 6", 'broken_i, missing_i = VP["broken"], VP["missing"]')
s = rep(s, "th_s = math.radians(130)", 'th_s = math.radians(VP["spall_deg"])')
s = rep(s, "th_c = math.radians(300)", 'th_c = math.radians(VP["crack_deg"])')
s = rep(s, "    if d < 1.7:", '    if VP["spall"] and d < 1.7:')
s = rep(s, "    if (f.calc_center_median() - P).length < 2.0:", '    if VP["spall"] and (f.calc_center_median() - P).length < 2.0:')
s = rep(s, 'outer = to_obj("OuterRace", bm, [steel, pitted], "FAULT", smooth_angle=30)',
        'outer = to_obj("OuterRace", bm, [steel, pitted], "FAULT" if (VP["spall"] or VP["crack"]) else "OK", smooth_angle=30)')
s = rep(s, 'poly_curve("OuterRace_Crack", pts, 0.07, crack_m, "FAULT")',
        'if VP["crack"]:\n    poly_curve("OuterRace_Crack", pts, 0.07, crack_m, "FAULT")')
s = rep(s, "for k in range(6):\n    t = math.radians(broken_i",
        "for k in range(6 if broken_i is not None else 0):\n    t = math.radians(broken_i")
s = cut_labels(s, "# ---------------- labels", "CAM = Vector((46, -64, 50))")
open("bearing_v.py", "w", encoding="utf-8").write(tail(s, "bearing"))

# ------------------------------------------------------------------ pcb
s = rd("pcb.py")
s = head(s, """{
    1: dict(bulged=True, burnt=False, lift=True, lift_side=2, lift_i=5, trace=False),
    2: dict(bulged=False, burnt=True, lift=False, lift_side=3, lift_i=2, trace=True),
    3: dict(bulged=True, burnt=True, lift=True, lift_side=0, lift_i=6, trace=True),
}""")
s = rep(s, 'elec_cap("C3_BULGED", (28, -9, 0), False)',
        'elec_cap("C3_BULGED" if VP["bulged"] else "C3_OK", (28, -9, 0), not VP["bulged"])')
s = wrap(s, "# electrolyte leak around base", "# ---------------- axial resistors", 'VP["bulged"]')
s = rep(s, 'axial("R7_BURNT", (-20, -13, 2.0), False)',
        'axial("R7_BURNT" if VP["burnt"] else "R7_OK2", (-20, -13, 2.0), not VP["burnt"])')
s = wrap(s, "bm = sphere_bm(1.0, 32)\nbmesh.ops.scale(bm, vec=(8.5", "# ---------------- connector header", 'VP["burnt"]')
s = rep(s, "lifted = (side == 3 and i == 2)", 'lifted = VP["lift"] and side == VP["lift_side"] and i == VP["lift_i"]')
s = rep(s, "GAP = 0.9", 'GAP = 0.9 if VP["trace"] else 0.0')
s = wrap(s, 'box("Trace_Break"', 'trace("Trace_Net2"', 'VP["trace"]')
s = cut_labels(s, "# ---------------- labels + stage", "CAM = Vector((56, -78, 62))")
open("pcb_v.py", "w", encoding="utf-8").write(tail(s, "pcb"))

# ------------------------------------------------------------------ gear
s = rd("gear.py")
s = head(s, """{
    1: dict(n_big=28, broken=3, pits=False, pit_at=0, scored=True, hot=False),
    2: dict(n_big=24, broken=None, pits=True, pit_at=5, scored=False, hot=True),
    3: dict(n_big=26, broken=11, pits=True, pit_at=14, scored=False, hot=True),
}""")
s = rep(s, "CD = 32.4", 'CD = 9.25 + 0.77 * VP["n_big"]')
s = rep(s, 'gear("OutputGear_BROKEN", 30, 20.9, 25.4, 4.2, W, dark, P2.x, P2.y, Z_G, broken=bro, status="FAULT")',
        'gear("OutputGear_BROKEN" if VP["broken"] is not None else "OutputGear", VP["n_big"], '
        '0.77 * VP["n_big"] - 2.2, 0.77 * VP["n_big"] + 2.3, 4.2, W, dark, P2.x, P2.y, Z_G, '
        'broken=VP["broken"], status="FAULT" if VP["broken"] is not None else "OK")')
s = rep(s, "bro = 7", 'bro = VP["pit_at"] if VP["broken"] is None else VP["broken"]')
s = rep(s, "tp = 2 * math.pi / 30", 'tp = 2 * math.pi / VP["n_big"]')
s = rep(s, "23.4 * math.cos(ab)", '(0.77 * VP["n_big"] + 0.3) * math.cos(ab)')
s = rep(s, "23.4 * math.sin(ab)", '(0.77 * VP["n_big"] + 0.3) * math.sin(ab)')
s = rep(s, "rr = 24.6 - j * 1.3", 'rr = (0.77 * VP["n_big"] + 1.6) - j * 1.3')
s = wrap(s, 'cyl("OutputGear_Stump"', "for k, off in enumerate", 'VP["broken"] is not None')
s = wrap(s, "for k, off in enumerate", "for k in range(4):   # broken chunks", 'VP["pits"]')
s = wrap(s, "for k in range(4):   # broken chunks", "# shafts", 'VP["broken"] is not None')
s = rep(s, 'sh = cyl("OutputShaft_SCORED", 4.2, 36, (P2.x, P2.y, 17), steel, 40, status="FAULT")',
        'sh = cyl("OutputShaft_SCORED" if VP["scored"] else "OutputShaft", 4.2, 36, (P2.x, P2.y, 17), steel, 40, '
        'status="FAULT" if VP["scored"] else "OK")')
s = rep(s, 'cyl("OutputShaft_ScoredBand", 4.28, 4.0, (P2.x, P2.y, 24.2), scored, 40, status="FAULT")',
        'if VP["scored"]:\n    cyl("OutputShaft_ScoredBand", 4.28, 4.0, (P2.x, P2.y, 24.2), scored, 40, status="FAULT")')
s = rep(s, 'brg("BearingLow_Out_OVERHEATED", P2, 9.0, tempered, "FAULT")',
        'brg("BearingLow_Out_OVERHEATED" if VP["hot"] else "BearingLow_Out", P2, 9.0, '
        'tempered if VP["hot"] else bearing_m, "FAULT" if VP["hot"] else "OK")')
s = cut_labels(s, "CAM = Vector((95, -125, 90))", "CAM = Vector((95, -125, 90))")
open("gear_v.py", "w", encoding="utf-8").write(tail(s, "gear"))

# ------------------------------------------------------------------ pump
s = rd("pump.py")
s = head(s, """{
    1: dict(blades=5, broken=1, torn=False, pitting=True),
    2: dict(blades=7, broken=None, torn=True, pitting=False),
    3: dict(blades=8, broken=5, torn=True, pitting=True),
}""")
s = rep(s, 'seal = to_obj("Seal_TORN", lathe_bm([(4.6, -1.5), (8.8, -1.5), (8.8, 1.5), (4.6, 1.5)], 48), torn, "FAULT")',
        'seal = to_obj("Seal_TORN" if VP["torn"] else "Seal", lathe_bm([(4.6, -1.5), (8.8, -1.5), (8.8, 1.5), '
        '(4.6, 1.5)], 48), torn if VP["torn"] else rubber, "FAULT" if VP["torn"] else "OK")')
s = wrap(s, "for k in range(3):\n    ang = 2.2", "# impeller", 'VP["torn"]')
s = rep(s, "BR = 2\nfor i in range(6):\n    a = i * math.pi / 3",
        'BR = VP["broken"]\nfor i in range(VP["blades"]):\n    a = i * 2 * math.pi / VP["blades"]')
s = rep(s, "# shaft\n", '''pit_m = mat("CavitationPits", (0.02, 0.03, 0.04), 0.5, 0.8)
if VP["pitting"]:
    for k in range(16):
        ang = random.uniform(0, 2 * math.pi)
        rad = random.uniform(27.2, 28.3)
        sphere(f"Casing_Pit{k}", 0.55, (rad * math.cos(ang), rad * math.sin(ang), random.uniform(5, 14)), pit_m, 10, "FAULT")
# shaft
''')
s = cut_labels(s, "CAM = Vector((105, -135, 85))", "CAM = Vector((105, -135, 85))")
open("pump_v.py", "w", encoding="utf-8").write(tail(s, "pump"))

# ------------------------------------------------------------------ phone
s = rd("phone_teardown.py")
s = head(s, """{
    1: dict(crack=True, imp=(-18, -30), deadline=False, swell=5.0, burnt=False),
    2: dict(crack=False, imp=(14, 24), deadline=False, swell=4.0, burnt=True),
    3: dict(crack=True, imp=(20, -10), deadline=True, swell=0.0, burnt=True),
}""")
s = rep(s, "v.co.z += 5.0 * math.exp", 'v.co.z += VP["swell"] * math.exp')
s = rep(s, 'to_obj("Battery_SWOLLEN", bm, foil, "FAULT", smooth_angle=60)',
        'SW = VP["swell"] > 0\nto_obj("Battery_SWOLLEN" if SW else "Battery", bm, foil, "FAULT" if SW else "OK", smooth_angle=60)')
s = rep(s, 'box("Battery_Label", (34, 26, 0.12), (0, -26, 10.0), label_m, 0.05, "FAULT")',
        'box("Battery_Label", (34, 26, 0.12), (0, -26, 6.3 + VP["swell"] * 0.75), label_m, 0.05, "FAULT" if SW else "OK")')
s = wrap(s, "for k in range(3):    # wrinkled", "# mainboard (upper section)", "SW")
s = rep(s, 'box("PMIC_BURNT", (6, 6, 0.9), (22, BY - 14, 4.15), char, 0.2, "FAULT")',
        'box("PMIC_BURNT" if VP["burnt"] else "PMIC", (6, 6, 0.9), (22, BY - 14, 4.15), char if VP["burnt"] else chip, '
        '0.2, "FAULT" if VP["burnt"] else "OK")')
s = wrap(s, "for k, (dx, dy, r) in enumerate([(-1.2, 1, 0.8)", "# camera module", 'VP["burnt"]')
s = rep(s, 'box("Display_CRACKED", (W - 1.6, H - 1.6, 0.8), (0, 0, 8.4), screen_m, 0.5, "FAULT")',
        'box("Display_CRACKED" if VP["crack"] or VP["deadline"] else "Display", (W - 1.6, H - 1.6, 0.8), (0, 0, 8.4), '
        'screen_m, 0.5, "FAULT" if (VP["crack"] or VP["deadline"]) else "OK")')
s = rep(s, "imp = Vector((14, 24, 0))", 'imp = Vector((*VP["imp"], 0))')
s = wrap(s, "for k in range(9):\n    a = k * 2 * math.pi / 9", 'box("Display_DeadLine"', 'VP["crack"]')
s = rep(s, 'box("Display_DeadLine", (66, 1.3, 0.05), (0, -4, 8.82), deadpx, 0, "FAULT")',
        'if VP["deadline"]:\n    box("Display_DeadLine", (66, 1.3, 0.05), (0, -4, 8.82), deadpx, 0, "FAULT")')
s = cut_labels(s, "CAM = Vector((125, -190, 140))", "CAM = Vector((125, -190, 140))")
open("phone_v.py", "w", encoding="utf-8").write(tail(s, "phone_teardown"))
print("patched")
