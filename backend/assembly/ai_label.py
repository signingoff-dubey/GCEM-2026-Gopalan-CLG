"""Find and label damage in a GLB that carries no rootlens_* tags, so an upload does not depend on labelled data.

Two passes, both recorded on each finding as `source`:
1. geometry (deterministic): parts that repeat (96 leads, 32 bond wires) should match their siblings. A part
   whose size differs strongly from its group's median is flagged as deformed or broken; a small piece sitting
   outside the main body is flagged as a loose fragment.
2. AI: the per-part facts (name, material, colour, size, position, sibling statistics, geometry flags) go to the
   text model chain as JSON. It returns readable part names, roles and any further suspected damage with a
   reason. Its output is validated (known part names only, severity 0..1) and marked "AI-suggested".
"""
import json
import re
from collections import defaultdict

import numpy as np

from backend.assembly.infer import nice_name

MAX_PARTS_FOR_AI = 160
ROLES = {"housing", "internal", "fastener", "damage_marker", "other"}


def _size(p):
    b = p.get("bbox")
    return np.array(b["max"]) - np.array(b["min"]) if b else None


def _family(name: str) -> str:
    """Lead0_3_a -> lead_a, Wire2_7 -> wire, Mesh.012 -> mesh: parts that should look alike."""
    head = re.match(r"[A-Za-z]+", name)
    tail = re.findall(r"_([a-z])$", name)
    return ((head.group(0) if head else name) + ("_" + tail[0] if tail else "")).lower()


def _clusters(sizes: np.ndarray, tol: float = 0.12) -> list[list[int]]:
    """Greedy clustering of size vectors: members within tol (relative) of the cluster's first member."""
    clusters: list[list[int]] = []
    for i, s in enumerate(sizes):
        for c in clusters:
            ref = sizes[c[0]]
            if np.all(np.abs(s - ref) <= tol * np.maximum(ref, 1e-12)):
                c.append(i)
                break
        else:
            clusters.append([i])
    return clusters


def geometry_findings(parts: list[dict]) -> list[str]:
    """Flag parts that should match their siblings but do not, and loose fragments. Mutates parts.

    Siblings are parts with the same mesh topology (triangle count), so this works with generic names too.
    Inside a topology group, near-identical sizes form the normal shapes (3+ members); a part that fits no
    normal shape is compared with the closest one and flagged as broken (smaller) or deformed (larger).
    """
    groups = defaultdict(list)
    for p in parts:
        if _size(p) is not None and p.get("triangles"):
            groups[p["triangles"]].append(p)
    flagged = 0
    for tris, members in groups.items():
        if len(members) < 6:
            continue
        sizes = np.array([np.sort(_size(p))[::-1] for p in members])        # largest extent first
        clusters = _clusters(sizes)
        normal = [c for c in clusters if len(c) >= 3]
        if not normal or sum(len(c) for c in normal) < 0.8 * len(members):
            continue                     # no clear family of identical parts (e.g. unrelated meshes): no baseline
        centres = [np.median(sizes[c], axis=0) for c in normal]
        for c in clusters:
            if len(c) >= 3:
                continue
            for i in c:
                p = members[i]
                if p.get("damage"):
                    continue
                s = sizes[i]
                k = int(np.argmin([np.abs(np.log(np.maximum(s, 1e-12) / np.maximum(m, 1e-12))).sum() for m in centres]))
                ref = centres[k]
                dev = np.abs(s - ref) / np.maximum(ref, 1e-12)
                worst = float(dev[:2].max())
                shorter = s[0] < ref[0]
                if worst < 0.25 or (not shorter and worst > 1.0):   # over twice the size: a different part, not a deformed one
                    continue
                head = nice_name(p["name"]).split(" ")[0].lower()
                p["damage"] = {"type": f"{'broken' if shorter else 'deformed'} {head if head != 'mesh' else 'part'}",
                               "severity": round(min(0.9, 0.4 + min(worst, 1.0) / 2), 2), "internal": None,
                               "description": f"{'Smaller' if shorter else 'Larger'} than the {len(normal[k])} identical parts it "
                                              f"matches by {min(worst, 9.99):.0%} (geometry check against siblings)",
                               "source": "geometry"}
                p["display_name"] = p.get("display_name") or nice_name(p["name"])
                flagged += 1
    # loose fragments: small parts whose centre lies outside the biggest part's box
    boxes = [(p, np.array(p["bbox"]["min"]), np.array(p["bbox"]["max"])) for p in parts if p.get("bbox")]
    if boxes:
        body = max(boxes, key=lambda t: float(np.prod(np.maximum(t[2] - t[1], 1e-9))))
        bsize = body[2] - body[1]
        for p, lo, hi in boxes:
            if p is body[0] or p.get("damage"):
                continue
            c = (lo + hi) / 2
            small = float(np.max(hi - lo)) < 0.08 * float(np.max(bsize))
            outside = np.any(c < body[1] - 0.15 * bsize) or np.any(c > body[2] + 0.15 * bsize)
            if small and outside:
                p["damage"] = {"type": "loose fragment", "severity": 0.5, "internal": False,
                               "description": "Small piece lying away from the assembly (geometry check)", "source": "geometry"}
                p["display_name"] = nice_name(p["name"])
                flagged += 1
    return [f"geometry check flagged {flagged} part(s) that differ from their siblings or lie loose"] if flagged else []


def _facts(parts: list[dict], materials: dict) -> list[dict]:
    fam_count = defaultdict(int)        # same mesh topology = copies of one part (works with generic names)
    for p in parts:
        fam_count[p.get("triangles")] += 1
    out = []
    for p in parts[:MAX_PARTS_FOR_AI]:
        s = _size(p)
        out.append({"name": p["name"], "material": materials.get(p["name"]),
                    "size": None if s is None else [round(float(v), 4) for v in s],
                    "centre": None if not p.get("bbox") else
                    [round((a + b) / 2, 4) for a, b in zip(p["bbox"]["min"], p["bbox"]["max"])],
                    "identical_copies": fam_count[p.get("triangles")] - 1,
                    "flag": (p.get("damage") or {}).get("description")})
    return out


PROMPT = """You label parts of a 3D model of a manufactured product for a quality inspection tool.
You get one JSON object per part: name, material, size and centre (model units), how many other parts share
its exact mesh shape (identical_copies), and a flag from a geometry check if any. Infer what each part is from
shape, size, material, position and copies even when names are generic: e.g. dozens of thin identical parts
around a flat body are leads or pins, one large flat box is the body or housing, a small thin square in the
middle is a die, many tiny thin curves are bond wires. Give readable names like "Lead 12" or "Package body". Reply with JSON only:
{"product": "<what the product most likely is>",
 "parts": [{"name": "<exact input name>", "display_name": "<short readable name>",
            "role": "housing|internal|fastener|damage_marker|other",
            "damage": null | {"type": "<crack|chip|broken lead|lifted bond wire|burn|contamination|deformation|...>",
                              "severity": <0..1>, "reason": "<the evidence: name, material or geometry flag>"}}]}
Only report damage when the name, the material name or the geometry flag gives evidence; never guess from
size alone. Keep every name exactly as given. Include every part."""


def generic_name(text: str) -> bool:
    return bool(re.match(r"^(mesh|object|cube|node|part)", text or "", re.I))


def ai_labels(parts: list[dict], materials: dict, label: str) -> tuple[list[str], dict | None]:
    """Ask the text model chain to label parts and suggest damage. Never raises: returns notes and the reply."""
    from backend.ai import llm
    if not any(llm.available().values()):
        return ["AI labelling skipped: no model keys configured"], None
    facts = _facts(parts, materials)
    names = {p["name"] for p in parts}

    def valid(r):
        try:
            d = json.loads(re.sub(r"^```(json)?|```$", "", r.content.strip(), flags=re.M))
            return None if isinstance(d.get("parts"), list) else "no parts list"
        except (ValueError, AttributeError):
            return "not JSON"

    try:
        reply, _ = llm.run_chain("text", [{"role": "system", "content": PROMPT},
                                          {"role": "user", "content": json.dumps({"file": label, "parts": facts})}],
                                 validate=valid, json_mode=True, temperature=0.0, max_tokens=8000)
    except Exception as e:  # noqa: BLE001 - labelling is optional; the geometry and name passes still stand
        return [f"AI labelling unavailable: {str(e)[:120]}"], None
    data = json.loads(re.sub(r"^```(json)?|```$", "", reply.content.strip(), flags=re.M))
    by_name = {p["name"]: p for p in parts}
    added = 0
    for item in data.get("parts", []):
        p = by_name.get(item.get("name"))
        if p is None or item.get("name") not in names:
            continue
        generic = re.match(r"^(mesh|object|cube|node|part)", p["display_name"], re.I) or             p["display_name"] == p["name"].replace("_", " ")
        if item.get("display_name") and generic:
            p["display_name"] = str(item["display_name"])[:60]
            dmg = p.get("damage") or {}
            if dmg.get("source") == "geometry" and dmg.get("type", "").endswith(" part") and not generic_name(p["display_name"]):
                dmg["type"] = dmg["type"][: -len("part")] + p["display_name"].lower()
        if item.get("role") in ROLES and p.get("role") == "other" and not p.get("damage"):
            p["role"] = item["role"]
        d = item.get("damage")
        if isinstance(d, dict) and d.get("type") and not p.get("damage"):
            try:
                sev = min(1.0, max(0.0, float(d.get("severity", 0.5))))
            except (TypeError, ValueError):
                sev = 0.5
            p["damage"] = {"type": str(d["type"])[:40], "severity": round(sev, 2), "internal": None,
                           "description": f"AI-suggested: {str(d.get('reason', ''))[:160]}", "source": "AI"}
            added += 1
    return [f"AI ({reply.provider}/{reply.model}) labelled the parts and suggested {added} further damage finding(s); "
            f"AI findings are unverified"], {"product": data.get("product"), "provider": reply.provider, "model": reply.model}
