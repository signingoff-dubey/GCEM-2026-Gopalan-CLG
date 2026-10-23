"""Minimal glTF 2.0 reader/writer: GLB container, accessors, world transforms. No dependencies
beyond numpy, so uploads can be inspected without a 3D library."""
import json
import struct

import numpy as np

GLB_MAGIC = 0x46546C67
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942
COMPONENT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


class GltfError(ValueError):
    pass


def read_glb(data: bytes) -> tuple[dict, bytes]:
    if len(data) < 20:
        raise GltfError("file too small to be a GLB")
    magic, version, length = struct.unpack_from("<III", data, 0)
    if magic != GLB_MAGIC:
        raise GltfError("not a GLB file (bad magic)")
    if version != 2:
        raise GltfError(f"glTF version {version} not supported (need 2)")
    off, doc, binary = 12, None, b""
    while off + 8 <= min(length, len(data)):
        clen, ctype = struct.unpack_from("<II", data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == CHUNK_JSON:
            doc = json.loads(chunk.decode("utf-8"))
        elif ctype == CHUNK_BIN and not binary:
            binary = bytes(chunk)
        off += 8 + clen
    if doc is None:
        raise GltfError("GLB has no JSON chunk")
    return doc, binary


def write_glb(doc: dict, binary: bytes) -> bytes:
    js = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    binary += b"\x00" * (-len(binary) % 4)
    if doc.get("buffers"):
        doc["buffers"][0]["byteLength"] = len(binary)
        js = json.dumps(doc, separators=(",", ":")).encode("utf-8")
        js += b" " * (-len(js) % 4)
    total = 12 + 8 + len(js) + (8 + len(binary) if binary else 0)
    out = struct.pack("<III", GLB_MAGIC, 2, total) + struct.pack("<II", len(js), CHUNK_JSON) + js
    if binary:
        out += struct.pack("<II", len(binary), CHUNK_BIN) + binary
    return out


def read_accessor(doc: dict, binary: bytes, idx: int) -> np.ndarray:
    """Values of an accessor stored in the GLB binary chunk (buffer 0)."""
    acc = doc["accessors"][idx]
    if "bufferView" not in acc:
        return np.zeros((acc["count"], WIDTH[acc["type"]]), np.float32)
    bv = doc["bufferViews"][acc["bufferView"]]
    if bv.get("buffer", 0) != 0:
        raise GltfError("external buffers are not supported here")
    dtype = np.dtype(COMPONENT[acc["componentType"]])
    width = WIDTH[acc["type"]]
    start = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = bv.get("byteStride") or dtype.itemsize * width
    count = acc["count"]
    raw = np.frombuffer(binary, np.uint8, count=(count - 1) * stride + dtype.itemsize * width, offset=start)
    rows = np.lib.stride_tricks.as_strided(raw, shape=(count, dtype.itemsize * width), strides=(stride, 1))
    return rows.copy().view(dtype).reshape(count, width)


def _trs_matrix(node: dict) -> np.ndarray:
    if "matrix" in node:
        return np.array(node["matrix"], float).reshape(4, 4).T
    t = np.array(node.get("translation", [0, 0, 0]), float)
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    s = np.array(node.get("scale", [1, 1, 1]), float)
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    m = np.eye(4)
    m[:3, :3] = r * s
    m[:3, 3] = t
    return m


def world_matrices(doc: dict) -> dict[int, np.ndarray]:
    out = {}
    nodes = doc.get("nodes", [])

    def walk(i, parent):
        m = parent @ _trs_matrix(nodes[i])
        out[i] = m
        for c in nodes[i].get("children", []):
            walk(c, m)

    roots = set(range(len(nodes))) - {c for n in nodes for c in n.get("children", [])}
    scene = doc.get("scenes", [{}])[doc.get("scene", 0)] if doc.get("scenes") else {"nodes": sorted(roots)}
    for r in scene.get("nodes", sorted(roots)):
        walk(r, np.eye(4))
    return out


def mesh_bounds(doc: dict, mesh_idx: int) -> tuple[np.ndarray, np.ndarray] | None:
    """Local-space AABB from POSITION accessor min/max (required by the spec)."""
    lo, hi = [], []
    for prim in doc["meshes"][mesh_idx].get("primitives", []):
        pos = prim.get("attributes", {}).get("POSITION")
        if pos is None:
            continue
        acc = doc["accessors"][pos]
        if "min" in acc and "max" in acc:
            lo.append(acc["min"])
            hi.append(acc["max"])
    if not lo:
        return None
    return np.min(lo, axis=0), np.max(hi, axis=0)


def world_bounds(local: tuple[np.ndarray, np.ndarray], m: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    lo, hi = local
    corners = np.array([[x, y, z, 1.0] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    w = (m @ corners.T).T[:, :3]
    return w.min(axis=0), w.max(axis=0)
