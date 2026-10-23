"""Shared driver for the production-line product models (unlabelled, fault names carry the damage keywords).
Usage of each script: blender -b --python prod_<name>.py -- <out_dir> [preview]
"""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa: E402,F401,F403


def args():
    a = sys.argv[sys.argv.index("--") + 1:]
    return os.path.abspath(a[0]), len(a) > 1


def sw(*p):
    return lambda n: n.startswith(p)


def finish_product(family, out, preview, cam, target, lens, floor_z, rules, offsets, ex_target, zoom, lift,
                   exposure=0.5):
    stage(cam, target, lens, floor_z, exposure=exposure, res=(1280, 720), samples=48)
    groups = collect(rules)
    peak = explode(groups, offsets, target=ex_target, zoom=zoom, lift=lift)
    os.makedirs(out, exist_ok=True)
    sc = bpy.context.scene
    base = os.path.join(out, family + "_v1")
    if preview:
        sc.cycles.samples = 24
        sc.render.resolution_percentage = 50
        sc.frame_set(peak)
        render(os.path.join(out, family + "_preview.png"))
        return
    sc.frame_set(1)
    render(base + ".png")
    sc.frame_set(peak)
    render(base + "_exploded.png")
    tag_rootlens(family, 1, base + ".json")
    sc.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=base + ".blend")
    export_glb(base + ".glb")
    print("DONE", family)


def gear_bm(teeth, r_root, r_tip, thick, skip=None):
    """Spur gear outline extruded along Z and centred on z=0. `skip` removes one tooth."""
    bm = bmesh.new()
    step = 2 * math.pi / teeth
    vs = []
    for i in range(teeth):
        for fr, r in ((0.0, r_root), (0.22, r_tip), (0.52, r_tip), (0.74, r_root)):
            if i == skip:
                r = r_root
            a = (i + fr) * step
            vs.append(bm.verts.new((r * math.cos(a), r * math.sin(a), 0)))
    f = bm.faces.new(vs)
    geom = bmesh.ops.extrude_face_region(bm, geom=[f])["geom"]
    bmesh.ops.translate(bm, vec=(0, 0, thick), verts=[v for v in geom if isinstance(v, bmesh.types.BMVert)])
    bmesh.ops.translate(bm, vec=(0, 0, -thick / 2), verts=bm.verts[:])
    return bm


def helix(r, z0, z1, turns, n=48):
    return [(r * math.cos(2 * math.pi * turns * k / n), r * math.sin(2 * math.pi * turns * k / n),
             z0 + (z1 - z0) * k / n) for k in range(n + 1)]
