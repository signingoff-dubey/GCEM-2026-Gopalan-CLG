"""Shared helpers for the fault-annotated demo models. 1 Blender unit = 1 mm."""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

RED = (1.0, 0.05, 0.03)
GREEN = (0.08, 0.9, 0.25)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def mat(name, col, metal=0.0, rough=0.5, emit=None, estr=1.0, alpha=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*col, 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = estr
    if alpha is not None:
        b.inputs["Alpha"].default_value = alpha
    return m


def finish(bm, angle=35):
    """Sharp edges above `angle`, smooth elsewhere."""
    a = math.radians(angle)
    for e in bm.edges:
        if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > a:
            e.smooth = False
    for f in bm.faces:
        f.smooth = True
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])


def to_obj(name, bm, mats, status=None, smooth_angle=35):
    finish(bm, smooth_angle)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats if isinstance(mats, (list, tuple)) else [mats]:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    if status:
        ob["status"] = status
    return ob


def box(name, size, loc, m, bevel=0.0, status=None, rot=None):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts[:])
    if bevel:
        bmesh.ops.bevel(bm, geom=bm.edges[:] + bm.verts[:], offset=bevel, segments=2, affect="EDGES")
    if rot is not None:
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=rot, verts=bm.verts[:])
    bmesh.ops.translate(bm, vec=Vector(loc), verts=bm.verts[:])
    return to_obj(name, bm, m, status)


def cyl(name, r, h, loc, m, seg=32, axis="Z", r2=None, status=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r,
                          radius2=r if r2 is None else r2, depth=h)
    if axis == "X":
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, "Y"), verts=bm.verts[:])
    elif axis == "Y":
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, "X"), verts=bm.verts[:])
    bmesh.ops.translate(bm, vec=Vector(loc), verts=bm.verts[:])
    return to_obj(name, bm, m, status)


def sphere_bm(r, seg=48):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2, radius=r)
    return bm


def sphere(name, r, loc, m, seg=48, status=None):
    bm = sphere_bm(r, seg)
    bmesh.ops.translate(bm, vec=Vector(loc), verts=bm.verts[:])
    return to_obj(name, bm, m, status)


def lathe_bm(prof, seg=96):
    """Revolve a closed (r, z) profile around Z."""
    bm = bmesh.new()
    vs = [bm.verts.new((r, 0, z)) for r, z in prof]
    es = [bm.edges.new((vs[i], vs[(i + 1) % len(vs)])) for i in range(len(vs))]
    bmesh.ops.spin(bm, geom=vs + es, cent=(0, 0, 0), axis=(0, 0, 1), angle=2 * math.pi, steps=seg)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-4)
    return bm


def poly_curve(name, pts, radius, m, status=None):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = 2
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for p, c in zip(sp.points, pts):
        p.co = (*c, 1.0)
    cu.materials.append(m)
    ob = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(ob)
    if status:
        ob["status"] = status
    return ob


def label(text, anchor, offset, kind, cam, size=3.2, name=None):
    """Floating label + leader line + dot, facing the camera. kind: 'FAULT' or 'OK'."""
    col = RED if kind == "FAULT" else GREEN
    m = mat(f"Label_{kind}", (0.02, 0.02, 0.02), emit=col, estr=4.0)
    anchor = Vector(anchor)
    pos = anchor + Vector(offset)
    cu = bpy.data.curves.new("T_" + text, "FONT")
    cu.body = text
    cu.size = size
    cu.align_x = "CENTER"
    cu.extrude = size * 0.04
    cu.materials.append(m)
    ob = bpy.data.objects.new(name or ("Label_" + text.replace(" ", "_")), cu)
    ob.location = pos
    ob.rotation_euler = (Vector(cam) - pos).to_track_quat("Z", "Y").to_euler()
    ob["status"] = kind
    bpy.context.scene.collection.objects.link(ob)
    # leader line from anchor to just under the text
    a, b = anchor, pos - Vector((0, 0, size * 0.35))
    d = b - a
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=size * 0.035, radius2=size * 0.035,
                          depth=d.length)
    bmesh.ops.translate(bm, vec=(0, 0, d.length / 2), verts=bm.verts[:])
    st = to_obj("Leader_" + text.replace(" ", "_"), bm, m, kind)
    st.location = a
    st.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    sphere("Dot_" + text.replace(" ", "_"), size * 0.11, anchor, m, seg=16, status=kind)
    return ob


def stage(cam_loc, target, lens, floor_z, floor_size=600, exposure=-1.2, res=(1920, 1080), samples=64):
    sc = bpy.context.scene
    fm = mat("Floor", (0.07, 0.075, 0.09), 0.0, 0.35)
    bpy.ops.mesh.primitive_plane_add(size=floor_size, location=(0, 0, floor_z))
    fl = bpy.context.object
    fl.name = "Stage_Floor"
    fl.data.materials.append(fm)
    for n, loc, e, s in (("Key", (60, -50, 80), 9000, 60), ("Rim", (-70, 60, 50), 5000, 50),
                         ("Fill", (-50, -70, 40), 2500, 60), ("Top", (0, 0, 120), 4000, 90)):
        L = bpy.data.lights.new("Stage_" + n, "AREA")
        L.energy, L.size = e, s
        o = bpy.data.objects.new("Stage_" + n, L)
        o.location = loc
        o.rotation_euler = (-Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        sc.collection.objects.link(o)
    w = bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.12, 0.13, 0.16, 1)
    bg.inputs["Strength"].default_value = 0.8
    cd = bpy.data.cameras.new("Stage_Cam")
    cd.lens = lens
    cd.clip_start, cd.clip_end = 1, 5000
    co = bpy.data.objects.new("Stage_Cam", cd)
    co.location = cam_loc
    co.rotation_euler = (Vector(target) - Vector(cam_loc)).to_track_quat("-Z", "Y").to_euler()
    sc.collection.objects.link(co)
    sc.camera = co
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.exposure = exposure
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.image_settings.file_format = "PNG"
    return sc


def render(path):
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def export_glb(path):
    """Strip stage objects, bake text/curves to mesh, scale mm -> m, export GLB."""
    sc = bpy.context.scene
    ctx = bpy.context
    for ob in list(sc.objects):
        if ob.name.startswith("Stage_"):
            bpy.data.objects.remove(ob, do_unlink=True)
    for ob in list(sc.objects):
        if ob.type in ("FONT", "CURVE"):
            for x in ctx.view_layer.objects:
                x.select_set(False)
            ctx.view_layer.objects.active = ob
            ob.select_set(True)
            bpy.ops.object.convert(target="MESH")
    root = bpy.data.objects.new("Model", None)
    sc.collection.objects.link(root)
    root.scale = (0.001, 0.001, 0.001)
    for ob in list(sc.objects):
        if ob is not root and ob.parent is None:
            ob.parent = root
    for ob in sc.objects:
        ob.select_set(True)
    kw = dict(filepath=path, export_format="GLB", use_selection=True, export_apply=True,
              export_extras=True, export_yup=True, export_animations=True)
    for extra in ({"export_animation_mode": "ACTIVE_ACTIONS"}, {}):
        try:
            bpy.ops.export_scene.gltf(**kw, **extra)
            break
        except TypeError as e:
            print("retry export:", e)
    print("EXPORTED", path)


# ------------------------------------------------------------------ exploded-view animation
def collect(rules, lbl_map=None):
    """rules: ordered [(group, predicate(name))]; first match wins. Labels/leaders/dots follow lbl_map
    (label text with underscores -> group). Returns {group: [objects]}."""
    groups = {}
    for ob in bpy.context.scene.objects:
        n = ob.name
        if n.startswith("Stage_") or ob.type in ("EMPTY", "LIGHT", "CAMERA"):
            continue
        g = None
        if lbl_map and n.split("_", 1)[0] in ("Label", "Leader", "Dot"):
            g = lbl_map.get(n.split("_", 1)[1])
        else:
            for name, pred in rules:
                if pred(n):
                    g = name
                    break
        if g:
            groups.setdefault(g, []).append(ob)
    return groups


def explode(groups, offsets, target=(0, 0, 0), zoom=1.45, lift=0.0, t_in=54, hold=45, stag=5, lead=24, fps=30):
    """Group empties parented over the parts; staggered open, hold, close; camera dolly. offsets: ordered
    {group: (dx, dy, dz)}."""
    sc = bpy.context.scene
    last_open = last_close = 0
    close_first = None
    idx = 0
    for g, off in offsets.items():
        obs = groups.get(g)
        if not obs:
            continue
        e = bpy.data.objects.new("Explode_" + g, None)
        sc.collection.objects.link(e)
        for ob in obs:
            ob.parent = e
            ob["rootlens_order"] = idx + 1
        t0 = lead + idx * stag
        t1, t2 = t0 + t_in, t0 + t_in + hold
        t3 = t2 + t_in
        for f, v in ((1, (0, 0, 0)), (t0, (0, 0, 0)), (t1, off), (t2, off), (t3, (0, 0, 0))):
            e.location = v
            e.keyframe_insert("location", frame=f)
        last_open = max(last_open, t1)
        close_first = t2 if close_first is None else min(close_first, t2)
        last_close = max(last_close, t3)
        idx += 1
    sc.frame_start, sc.frame_end = 1, last_close + 15
    sc.render.fps = fps
    cam = sc.camera
    if cam:
        tg, near = Vector(target), cam.location.copy()
        far = tg + (near - tg) * zoom
        far.z += lift
        for f, v in ((1, near), (lead, near), (last_open, far), (close_first, far), (last_close, near)):
            cam.location = v
            cam.keyframe_insert("location", frame=f)
    sc.frame_set(1)
    return last_open


# ------------------------------------------------------------------ rootlens_* tags + ground truth
import json as _json

_DAMAGE = [  # (substring of lower-case name, damage type, severity)
    ("missing", "missing part", 0.9), ("crack", "crack", 0.9), ("half", "fracture", 0.9),
    ("stump", "fracture", 0.8), ("break", "fracture", 0.8), ("fragment", "fracture", 0.7),
    ("broken", "fracture", 0.8), ("burnt", "burn", 0.7), ("blister", "burn", 0.7), ("scorch", "burn", 0.65),
    ("soot", "burn", 0.5), ("charred", "burn", 0.7), ("leak", "leak", 0.6), ("residue", "leak", 0.5),
    ("lifted", "lifted lead", 0.7), ("swollen", "swelling", 0.85), ("bulged", "swelling", 0.85),
    ("battery", "swelling", 0.85), ("flap", "swelling", 0.7), ("tear", "tear", 0.6), ("torn", "tear", 0.6),
    ("pit", "pitting", 0.5), ("scored", "scoring", 0.6), ("overheated", "overheating", 0.7),
    ("debris", "debris", 0.4), ("whisker", "open circuit", 0.9), ("trace_break", "open circuit", 0.9),
    ("deadline", "dead pixels", 0.6), ("outerrace", "spall", 0.8), ("pmic", "burn", 0.7),
]
_OVERLAY = ("Crack", "Pit", "Leak", "Soot", "Scorch", "Blister", "Residue", "Whisker", "DeadLine", "Debris",
            "Seam", "Tear", "Trace_Break", "BladeBreak", "Stump", "Fragment", "Drop", "Puddle")
_HOUSING = ("Board", "Housing_Base", "Cover_Plate", "Casing", "BackGlass", "Frame_", "Bracket", "OuterRace",
            "Cover")


def tag_rootlens(family, variant, json_path):
    """Write rootlens_* custom properties (read by backend/assembly) and a ground-truth JSON."""
    truth = []
    for ob in bpy.context.scene.objects:
        st = ob.get("status")
        if ob.type != "MESH" and ob.type not in ("CURVE", "FONT") or st not in ("OK", "FAULT"):
            continue
        n = ob.name
        ob["rootlens_part"] = n.replace("_", " ")
        if st == "FAULT":
            low = n.lower()
            typ, sev = next(((t, v) for k, t, v in _DAMAGE if k in low), ("damage", 0.5))
            overlay = any(k in n for k in _OVERLAY)
            ob["rootlens_role"] = "damage_marker" if overlay else "internal"
            ob["rootlens_damage_type"] = typ
            ob["rootlens_severity"] = sev
            ob["rootlens_internal"] = family in ("bearing", "gear", "pump") and "Crack" not in n
            ob["rootlens_description"] = f"{typ} on {n.replace('_', ' ')}"
            truth.append({"object": n, "damage_type": typ, "severity": sev, "marker": overlay})
        else:
            ob["rootlens_role"] = ("fastener" if n.startswith(("Bolt", "Key")) else
                                   "housing" if n.startswith(_HOUSING) else "internal")
    types = sorted({t["damage_type"] for t in truth})
    with open(json_path, "w", encoding="utf-8") as f:
        _json.dump({"family": family, "variant": variant, "fault_types": types, "n_fault_objects": len(truth),
                    "faults": truth}, f, indent=1)
    return truth
