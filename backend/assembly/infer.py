"""Fill in damage and thermal data for a model exported without rootlens_* custom properties.

Many Blender scenes name their fault objects plainly (DieCrack, Scorch0, WireLift2_3, Shard1). When no
part carries rootlens_* extras, the object names are read instead:
- overlay objects (cracks, burn marks, chips, debris, dust) become damage markers, and the part they
  sit on (the smallest part whose box holds the marker's centre) is tagged with that damage;
- broken or lifted pieces (stub, remnant, lift, tear) are tagged as damaged parts themselves;
- the largest part is the housing;
- every part gets a simulated temperature that rises near the damage, so the thermal view works.
Everything here is labelled inferred / simulated in the manifest.
"""
import re

import numpy as np

# word in the object name -> (damage type, severity, marker overlay?, description)
RULES = [
    ("crack", ("crack", 0.9, True, "Crack line on {host}")),
    ("fracture", ("crack", 0.85, True, "Fracture on {host}")),
    ("scorch", ("burn", 0.65, True, "Burn mark on {host}")),
    ("burn", ("burn", 0.65, True, "Burn mark on {host}")),
    ("shard", ("chip", 0.75, True, "Chipped piece broken off {host}")),
    ("debristear", ("torn {head}", 0.6, False, "Torn end of a {head} that broke off")),
    ("debris", ("broken {head}", 0.6, False, "{Head} broken off the package")),
    ("stub", ("broken {head}", 0.8, False, "Broken {head}, stub left in place")),
    ("remnant", ("broken {head}", 0.8, False, "Broken {head}, remnant on the far side")),
    ("lift", ("lifted {head}", 0.7, False, "{Head} lifted off its pad")),
    ("tear", ("torn {head}", 0.6, False, "Torn {head}")),
    ("dust", ("contamination", 0.3, True, "Loose particle on {host}")),
    ("void", ("void", 0.6, True, "Void in {host}")),
    ("delam", ("delamination", 0.7, True, "Delamination on {host}")),
]
NICE = {"die": "silicon die", "body": "package body", "attach": "die attach", "paddle": "die paddle",
        "ball": "bond ball", "pad": "bond pad", "inner": "inner lead", "lead": "lead", "wire": "bond wire",
        "plate": "lead plating", "stitch": "stitch bond", "marking": "marking"}
NOT_HOST = ("marking", "label", "text")     # printed decals sit on top of the real part
T_BASE, T_PEAK = 34.0, 46.0


def _rule(name: str):
    low = name.lower().replace("_", "")
    for word, rule in RULES:
        if word in low:
            return rule
    return None


def nice_name(name: str) -> str:
    """'Lead0_2_tear' -> 'Lead 0-2 tear', 'DieCrackB1' -> 'Die crack B1'."""
    base = re.match(r"[A-Za-z]+", name)
    word = base.group(0) if base else name
    parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", word)
    head = NICE.get(parts[0].lower(), parts[0].lower()) if parts else word
    rest = " ".join(p.lower() if p.isalpha() and len(p) > 1 else p for p in parts[1:])
    idx = "-".join(re.findall(r"\d+", name[len(word):]))
    tail = re.sub(r"^[\d_]+", "", name[len(word):]).strip("_").replace("_", " ")
    text = " ".join(x for x in (head, rest, idx, tail) if x)
    return text[:1].upper() + text[1:]


def _head(name: str) -> str:
    m = re.match(r"[A-Z]?[a-z]+", name)
    return NICE.get(m.group(0).lower(), m.group(0).lower()) if m else "part"


def _cover(marker, host) -> float:
    """Share of the marker's footprint (largest two box faces) that lies inside the host's box."""
    lo, hi = np.maximum(marker[0], host[0]), np.minimum(marker[1], host[1])
    size = np.maximum(marker[1] - marker[0], 1e-6)
    inter = np.clip(hi - lo, 0, None)
    keep = np.argsort(size)[1:]                      # ignore the thinnest axis (cracks are flat)
    if np.any(inter[np.argsort(size)[0]] <= 0) and not np.all(marker[0] <= host[1] + 1e-3):
        return 0.0
    return float(np.prod(inter[keep]) / np.prod(size[keep]))


def _box(p):
    b = p.get("bbox")
    return (np.array(b["min"]), np.array(b["max"])) if b else None


def applies(parts: list[dict]) -> bool:
    return bool(parts) and not any(p.get("_has_props") for p in parts)


def infer(parts: list[dict]) -> list[str]:
    """Mutates parts in place. Returns notes for the manifest warnings."""
    boxes = {p["name"]: _box(p) for p in parts}
    vol = {n: float(np.prod(np.maximum(b[1] - b[0], 1e-9))) if b else 0.0 for n, b in boxes.items()}
    housing = max(vol, key=vol.get) if vol else None
    hb = boxes.get(housing)
    found = []
    for p in parts:
        if p["name"] == housing:
            p["role"] = "housing"
        rule = _rule(p["name"])
        if not rule:
            continue
        kind, sev, marker, desc = rule
        b = boxes[p["name"]]
        centre = (b[0] + b[1]) / 2 if b else None
        host = None
        if marker and b is not None and kind != "contamination":
            def area(q):
                s_ = np.sort(boxes[q["name"]][1] - boxes[q["name"]][0])
                return float(s_[1] * s_[2])
            hosts = [q for q in parts if q["name"] != p["name"] and not _rule(q["name"]) and boxes[q["name"]] is not None
                     and not q["name"].lower().startswith(NOT_HOST) and _cover(b, boxes[q["name"]]) >= 0.5
                     and area(q) >= 0.5 * float(np.prod(np.sort(b[1] - b[0])[1:]))]
            host = min(hosts, key=area) if hosts else None
        internal = bool(hb is not None and centre is not None and (host or p)["name"] != housing
                        and np.all(centre >= hb[0]) and np.all(centre <= hb[1]))
        host_name = nice_name(host["name"]).lower() if host else "the part"
        head = _head(p["name"])
        kind = kind.format(head=head)
        dmg = {"type": kind, "severity": sev, "internal": internal,
               "description": desc.format(host=host_name, head=head, Head=head.capitalize()),
               "inferred": True, "source": "object name"}
        p["display_name"] = nice_name(p["name"])
        p["damage"] = dmg
        if marker:
            p["role"] = "damage_marker"
            if host and (not host.get("damage") or host["damage"]["severity"] < sev):
                host["damage"] = {**dmg, "description": f"{kind.capitalize()} found on the {host_name}"}
                host["display_name"] = nice_name(host["name"])
                if host["role"] not in ("housing",):
                    host["role"] = "internal" if internal else host["role"]
        elif p["role"] != "housing":
            p["role"] = "internal" if internal else "other"
        found.append((centre, sev))

    # simulated temperatures: hotter close to the damage
    lo = np.min([b[0] for b in boxes.values() if b], axis=0) if any(boxes.values()) else np.zeros(3)
    hi = np.max([b[1] for b in boxes.values() if b], axis=0) if any(boxes.values()) else np.ones(3)
    radius = 0.18 * float(np.linalg.norm(hi - lo)) or 1.0
    for p in parts:
        b = boxes[p["name"]]
        if b is None:
            continue
        c = (b[0] + b[1]) / 2
        heat = max((s * np.exp(-np.linalg.norm(c - fc) / radius) for fc, s in found if fc is not None), default=0.0)
        p["temp_c"] = round(T_BASE + T_PEAK * float(heat), 1)
    notes = ["damage inferred from object names (no rootlens_* custom properties in the file)"] if found else []
    notes.append("temperatures simulated from distance to the damage")
    return notes
