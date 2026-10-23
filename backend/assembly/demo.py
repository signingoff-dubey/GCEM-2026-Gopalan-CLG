"""Built-in sample: a simple power bank with a simulated internal crack in one cell.

Written as plain glTF (no Blender needed) so the "View damage" flow works before a Blender
asset exists. Follows the same contract as Blender exports: rootlens_* extras on nodes, a
COLOR_0 thermal layer, and `disassembly` / `damage_reveal` animations.
"""
import numpy as np
import trimesh

from backend.assembly.gltf import write_glb

HOTSPOT = np.array([0.0, 0.004, 0.012])     # crack location on cell 2 (assembled pose, metres)
T_RANGE = (25.0, 85.0)


def ironbow(t_c: np.ndarray) -> np.ndarray:
    """Thermal-camera style palette: blue -> purple -> orange -> yellow-white."""
    x = np.clip((t_c - T_RANGE[0]) / (T_RANGE[1] - T_RANGE[0]), 0, 1)
    stops = np.array([[0.05, 0.05, 0.35], [0.45, 0.05, 0.55], [0.85, 0.25, 0.10],
                      [1.00, 0.65, 0.05], [1.00, 0.97, 0.80]])
    pos = x * (len(stops) - 1)
    i = np.clip(pos.astype(int), 0, len(stops) - 2)
    f = (pos - i)[:, None]
    return stops[i] * (1 - f) + stops[i + 1] * f


# name, display, role, shape, size, position, colour, base temp, order, explode offset, extras
PARTS = [
    ("shell_bottom", "Bottom shell", "housing", "box", (0.150, 0.006, 0.075), (0, -0.0105, 0), (0.18, 0.2, 0.24), 31, 9, (0, -0.02, 0)),
    ("shell_top", "Top shell", "housing", "box", (0.150, 0.006, 0.075), (0, 0.0105, 0), (0.18, 0.2, 0.24), 33, 2, (0, 0.07, 0)),
    ("end_cap_left", "Left end cap", "housing", "box", (0.006, 0.027, 0.075), (-0.078, 0, 0), (0.12, 0.13, 0.15), 31, 3, (-0.06, 0, 0)),
    ("end_cap_right", "Right end cap (ports)", "housing", "box", (0.006, 0.027, 0.075), (0.078, 0, 0), (0.12, 0.13, 0.15), 34, 3, (0.06, 0, 0)),
    ("screw_1", "Screw 1", "fastener", "cyl", (0.002, 0.008), (-0.065, 0.016, -0.03), (0.75, 0.75, 0.78), 32, 1, (0, 0.10, 0)),
    ("screw_2", "Screw 2", "fastener", "cyl", (0.002, 0.008), (0.065, 0.016, -0.03), (0.75, 0.75, 0.78), 32, 1, (0, 0.10, 0)),
    ("screw_3", "Screw 3", "fastener", "cyl", (0.002, 0.008), (-0.065, 0.016, 0.03), (0.75, 0.75, 0.78), 32, 1, (0, 0.10, 0)),
    ("screw_4", "Screw 4", "fastener", "cyl", (0.002, 0.008), (0.065, 0.016, 0.03), (0.75, 0.75, 0.78), 32, 1, (0, 0.10, 0)),
    ("pcb_main", "Charge controller PCB", "internal", "box", (0.030, 0.0016, 0.060), (0.055, -0.004, 0), (0.05, 0.35, 0.15), 41, 4, (0.05, 0.03, 0)),
    ("battery_cell_1", "Battery cell 1", "internal", "cell", (0.0095, 0.065), (-0.03, 0, 0), (0.15, 0.35, 0.75), 36, 5, (-0.03, 0.03, -0.06)),
    ("battery_cell_2", "Battery cell 2", "internal", "cell", (0.0095, 0.065), (0.0, 0, 0), (0.15, 0.35, 0.75), 52, 5, (0.0, 0.05, 0.08)),
]
DAMAGE = {
    "battery_cell_2": {"rootlens_damage_type": "crack", "rootlens_severity": 0.85, "rootlens_internal": True,
                       "rootlens_description": "Simulated hairline crack across the cell casing near the positive tab",
                       "rootlens_station": "L3_S32"},
}


def _dense(m: trimesh.Trimesh, max_edge=0.004) -> trimesh.Trimesh:
    """Subdivide so the per-vertex thermal gradient has enough vertices to show."""
    v, f = trimesh.remesh.subdivide_to_size(m.vertices, m.faces, max_edge=max_edge, max_iter=8)
    return trimesh.Trimesh(v, f, process=True)


def _geometry(shape, size):
    if shape == "box":
        m = trimesh.creation.box(extents=size)
    elif shape == "cyl":   # screw, axis +Y
        m = trimesh.creation.cylinder(radius=size[0], height=size[1], sections=16)
        m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    else:                  # battery cell, axis +Z
        m = trimesh.creation.cylinder(radius=size[0], height=size[1], sections=40)
    return _dense(m)


def _crack_marker():
    """Thin jagged sliver on the cell surface, child of battery_cell_2 (local coordinates)."""
    pts = np.array([[-0.004, 0.0094, -0.010], [-0.001, 0.0096, -0.004], [-0.003, 0.0096, 0.002],
                    [0.001, 0.0096, 0.008], [-0.001, 0.0096, 0.014], [0.002, 0.0094, 0.020]])
    segs = []
    for a, b in zip(pts[:-1], pts[1:]):
        seg = trimesh.creation.box(extents=(0.0012, 0.0006, np.linalg.norm(b - a) + 0.0008))
        d = (b - a) / np.linalg.norm(b - a)
        rot = trimesh.geometry.align_vectors([0, 0, 1], d)
        rot[:3, 3] = (a + b) / 2
        seg.apply_transform(rot)
        segs.append(seg)
    return trimesh.util.concatenate(segs)


class _Builder:
    def __init__(self):
        self.bin = bytearray()
        self.doc = {"asset": {"version": "2.0", "generator": "RootLens demo builder"},
                    "buffers": [{"byteLength": 0}], "bufferViews": [], "accessors": [],
                    "meshes": [], "materials": [], "nodes": [], "animations": [],
                    "scenes": [{"nodes": [0]}], "scene": 0}

    def accessor(self, arr, gtype, target=None, minmax=False):
        arr = np.ascontiguousarray(arr)
        comp = 5125 if arr.dtype == np.uint32 else 5126
        self.bin += b"\x00" * (-len(self.bin) % 4)
        view = {"buffer": 0, "byteOffset": len(self.bin), "byteLength": arr.nbytes}
        if target:
            view["target"] = target
        self.bin += arr.tobytes()
        self.doc["bufferViews"].append(view)
        acc = {"bufferView": len(self.doc["bufferViews"]) - 1, "componentType": comp,
               "count": int(arr.shape[0]), "type": gtype}
        if minmax:
            acc["min"] = arr.min(axis=0).tolist() if arr.ndim > 1 else [float(arr.min())]
            acc["max"] = arr.max(axis=0).tolist() if arr.ndim > 1 else [float(arr.max())]
        self.doc["accessors"].append(acc)
        return len(self.doc["accessors"]) - 1

    def mesh(self, name, m: trimesh.Trimesh, rgb, colors, emissive=None):
        mat = {"name": f"{name}_mat", "pbrMetallicRoughness": {"baseColorFactor": [*rgb, 1.0],
                                                              "metallicFactor": 0.2, "roughnessFactor": 0.6}}
        if emissive:
            mat["emissiveFactor"] = emissive
        self.doc["materials"].append(mat)
        prim = {"attributes": {
            "POSITION": self.accessor(m.vertices.astype(np.float32), "VEC3", 34962, minmax=True),
            "NORMAL": self.accessor(m.vertex_normals.astype(np.float32), "VEC3", 34962),
            "COLOR_0": self.accessor(colors.astype(np.float32), "VEC3", 34962)},
            "indices": self.accessor(m.faces.astype(np.uint32).ravel(), "SCALAR", 34963),
            "material": len(self.doc["materials"]) - 1}
        self.doc["meshes"].append({"name": name, "primitives": [prim]})
        return len(self.doc["meshes"]) - 1

    def animation(self, name, tracks):
        """tracks: [(node, path, times, values)]"""
        anim = {"name": name, "samplers": [], "channels": []}
        for node, path, times, values in tracks:
            width = "VEC4" if path == "rotation" else "VEC3"
            anim["samplers"].append({"input": self.accessor(np.asarray(times, np.float32), "SCALAR", minmax=True),
                                     "output": self.accessor(np.asarray(values, np.float32), width),
                                     "interpolation": "LINEAR"})
            anim["channels"].append({"sampler": len(anim["samplers"]) - 1,
                                     "target": {"node": node, "path": path}})
        self.doc["animations"].append(anim)


def build() -> bytes:
    b = _Builder()
    root = {"name": "power_bank", "children": [],
            "extras": {"rootlens_part": "Power bank (sample)", "rootlens_note": "simulated damage and thermal data"}}
    b.doc["nodes"].append(root)
    disassembly, node_of = [], {}
    order_start = {1: 0.0, 2: 1.0, 3: 2.3, 4: 3.4, 5: 4.4, 9: 6.0}
    for name, display, role, shape, size, pos, rgb, temp, order, offset in PARTS:
        m = _geometry(shape, size)
        world = m.vertices + np.array(pos)
        d = np.linalg.norm(world - HOTSPOT, axis=1)
        t_field = temp + (80.0 - temp) * np.exp(-(d ** 2) / (2 * 0.012 ** 2)) * (1.0 if name == "battery_cell_2" else 0.55)
        extras = {"rootlens_part": display, "rootlens_role": role, "rootlens_order": order,
                  "rootlens_temp_c": round(float(t_field.max()), 1), **DAMAGE.get(name, {})}
        mi = b.mesh(name, m, rgb, ironbow(t_field))
        b.doc["nodes"].append({"name": name, "mesh": mi, "translation": list(map(float, pos)), "extras": extras})
        idx = len(b.doc["nodes"]) - 1
        root["children"].append(idx)
        node_of[name] = idx
        t0 = order_start[order]
        start = np.array(pos, float)
        end = start + np.array(offset, float)
        disassembly.append((idx, "translation", [0.0, t0, t0 + 1.0, 7.0], [start, start, end, end]))

    marker = _crack_marker()
    t_marker = np.full(len(marker.vertices), 80.0)
    mi = b.mesh("damage_battery_cell_2", marker, (0.9, 0.1, 0.05), ironbow(t_marker), emissive=[1.0, 0.15, 0.05])
    b.doc["nodes"].append({"name": "damage_battery_cell_2", "mesh": mi, "extras": {
        "rootlens_part": "Crack marker (cell 2)", "rootlens_role": "damage_marker", "rootlens_order": 5,
        "rootlens_temp_c": 80.0, "rootlens_damage_type": "crack", "rootlens_severity": 0.85,
        "rootlens_internal": True, "rootlens_description": "Marker around the simulated crack"}})
    b.doc["nodes"][node_of["battery_cell_2"]]["children"] = [len(b.doc["nodes"]) - 1]

    b.animation("disassembly", disassembly)
    cell2 = node_of["battery_cell_2"]
    angles = np.linspace(0, 2 * np.pi, 9)
    quats = [[0.0, np.sin(a / 2), 0.0, np.cos(a / 2)] for a in angles]
    b.animation("damage_reveal", [(cell2, "rotation", np.linspace(0, 3.0, 9), quats)])
    return write_glb(b.doc, bytes(b.bin))
