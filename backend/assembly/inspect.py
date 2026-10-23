"""Summarise an assembly: parts, damage annotations, simulated thermal data, animations,
and a "view damage" plan the viewer can follow."""
import numpy as np

from backend.assembly import SIMULATED_NOTE, infer
from backend.assembly.gltf import mesh_bounds, read_accessor, world_bounds, world_matrices

PREFIX = "rootlens_"
ROLES = {"housing", "internal", "fastener", "damage_marker", "other"}


def _props(node: dict, mesh: dict | None) -> dict:
    """Custom properties: Blender writes them to node extras (and sometimes mesh extras)."""
    extras = {}
    for src in (mesh or {}).get("extras", {}), node.get("extras", {}):
        if isinstance(src, dict):
            extras.update(src)
    return {k[len(PREFIX):]: v for k, v in extras.items() if isinstance(k, str) and k.startswith(PREFIX)}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _bool(v):
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes")
    return bool(v) if v is not None else None


def _thermal_attr(mesh: dict) -> str | None:
    for prim in mesh.get("primitives", []):
        attrs = prim.get("attributes", {})
        for name in attrs:
            if "THERMAL" in name.upper():
                return name
        if "COLOR_0" in attrs:
            return "COLOR_0"
    return None


def _animations(doc: dict, binary: bytes) -> list[dict]:
    out = []
    for i, anim in enumerate(doc.get("animations", [])):
        duration = 0.0
        for s in anim.get("samplers", []):
            acc = doc["accessors"][s["input"]]
            if "max" in acc:
                duration = max(duration, float(acc["max"][0]))
            elif binary:
                duration = max(duration, float(read_accessor(doc, binary, s["input"]).max()))
        targets = {c.get("target", {}).get("node") for c in anim.get("channels", [])}
        out.append({"index": i, "name": anim.get("name") or f"animation_{i}",
                    "duration_s": round(duration, 3), "channels": len(anim.get("channels", [])),
                    "nodes_animated": len(targets - {None})})
    return out


def summarize(doc: dict, binary: bytes = b"") -> dict:
    nodes = doc.get("nodes", [])
    meshes = doc.get("meshes", [])
    mats = world_matrices(doc)
    parts, warnings = [], []
    lo_all, hi_all = [], []
    for i, node in enumerate(nodes):
        if "mesh" not in node:
            continue
        mesh = meshes[node["mesh"]]
        p = _props(node, mesh)
        bounds = mesh_bounds(doc, node["mesh"])
        wb = world_bounds(bounds, mats.get(i, np.eye(4))) if bounds else None
        if wb:
            lo_all.append(wb[0])
            hi_all.append(wb[1])
        name = node.get("name") or mesh.get("name") or f"part_{i}"
        role = str(p.get("role", "")).lower() or ("damage_marker" if name.lower().startswith("damage_") else "other")
        damage = None
        if p.get("damage_type") or role == "damage_marker":
            damage = {"type": p.get("damage_type") or "marker",
                      "severity": _num(p.get("severity")),
                      "internal": _bool(p.get("internal")),
                      "description": p.get("description")}
        parts.append({
            "node": i, "name": name, "display_name": p.get("part") or name.replace("_", " "),
            "role": role if role in ROLES else "other",
            "order": int(p["order"]) if _num(p.get("order")) is not None else None,
            "temp_c": _num(p.get("temp_c")),
            "station": p.get("station"),
            "damage": damage,
            "bbox": None if wb is None else {"min": [round(float(v), 5) for v in wb[0]],
                                            "max": [round(float(v), 5) for v in wb[1]]},
            "triangles": sum(_tri_count(doc, pr) for pr in mesh.get("primitives", [])),
            "thermal_attribute": _thermal_attr(mesh),
            "_has_props": bool(p),
        })
    if infer.applies(parts):
        warnings += infer.infer(parts)
    for part in parts:
        part.pop("_has_props", None)

    anims = _animations(doc, binary)
    damaged = sorted([p for p in parts if p["damage"] and p["role"] != "damage_marker"],
                     key=lambda p: -(p["damage"]["severity"] or 0))
    markers = [p for p in parts if p["role"] == "damage_marker"]
    temps = [p["temp_c"] for p in parts if p["temp_c"] is not None]
    thermal_parts = [p for p in parts if p["thermal_attribute"]]

    if len(parts) < 2:
        warnings.append("single mesh: no separate parts, so explode and disassembly are unavailable")
    if not anims:
        warnings.append("no animations: the viewer will use a computed exploded view instead")
    if not damaged and not markers:
        warnings.append("no damage annotations (rootlens_damage_type or damage_* objects)")
    if not thermal_parts and not temps:
        warnings.append("no thermal data (COLOR_0 attribute or rootlens_temp_c)")
    unnamed = [p["name"] for p in parts if p["name"].startswith(("part_", "Mesh", "mesh"))]
    if unnamed:
        warnings.append(f"{len(unnamed)} parts have generic names")

    center = (np.mean([np.min(lo_all, axis=0), np.max(hi_all, axis=0)], axis=0) if lo_all else np.zeros(3))
    focus = damaged[0] if damaged else (markers[0] if markers else None)
    disassembly = next((a for a in anims if "disassembl" in a["name"].lower() or "explod" in a["name"].lower()),
                       anims[0] if anims else None)
    return {
        "counts": {"parts": len(parts), "triangles": sum(p["triangles"] for p in parts),
                   "animations": len(anims), "damaged_parts": len(damaged), "damage_markers": len(markers)},
        "bounds": None if not lo_all else {"min": np.min(lo_all, axis=0).round(5).tolist(),
                                           "max": np.max(hi_all, axis=0).round(5).tolist(),
                                           "center": np.round(center, 5).tolist()},
        "parts": parts,
        "animations": anims,
        "damage": [{"part": p["name"], "display_name": p["display_name"], **p["damage"],
                    "temp_c": p["temp_c"], "bbox": p["bbox"]} for p in damaged],
        "thermal": {"available": bool(thermal_parts or temps),
                    "attribute": thermal_parts[0]["thermal_attribute"] if thermal_parts else None,
                    "min_c": min(temps) if temps else None, "max_c": max(temps) if temps else None,
                    "hottest_part": max((p for p in parts if p["temp_c"] is not None),
                                        key=lambda p: p["temp_c"])["name"] if temps else None},
        "view_damage": None if focus is None else {
            "focus_part": focus["name"],
            "focus_bbox": focus["bbox"],
            "animation": disassembly["name"] if disassembly else None,
            "fallback": None if disassembly else "computed explode",
            "isolate": [focus["name"]] + [m["name"] for m in markers],
            "thermal": bool(thermal_parts or temps),
            "steps": ["play disassembly" if disassembly else "explode parts", "isolate damaged part",
                      "switch to thermal view", "show damage card"],
        },
        "warnings": warnings,
        "note": SIMULATED_NOTE,
    }


def _tri_count(doc, prim) -> int:
    if "indices" in prim:
        return doc["accessors"][prim["indices"]]["count"] // 3
    pos = prim.get("attributes", {}).get("POSITION")
    return doc["accessors"][pos]["count"] // 3 if pos is not None else 0
