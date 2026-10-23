"""Topics: a saved 3D model or multi-part scan the user picks in the assistant, so the AI keeps that part in
context for the whole conversation (its parts, damage, severity, simulated heat and the fix for each defect)."""
from backend.assembly import service as asm
from backend.inspection import service as insp

LINE = {"id": "line", "label": "Line analysis (SECOM)", "kind": "line"}


def topics() -> list[dict]:
    """The line analysis, every saved model (one per label) and multi-part scans, then samples not loaded yet."""
    out, labels = [LINE], set()
    for a in asm.listing():
        if a["label"] in labels:
            continue
        labels.add(a["label"])
        out.append({"id": a["id"], "label": a["label"], "kind": "model",
                    "damaged": (a.get("counts") or {}).get("damaged_parts", 0)})
    for i in insp.listing():
        if i.get("part_damage"):
            out.append({"id": i["id"], "label": f"Scan: {(i.get('inputs') or {}).get('mesh')}", "kind": "scan",
                        "damaged": len(i["part_damage"])})
    for f in asm.samples()["files"]:
        if f["label"] not in labels and f["kind"] in ("glb", "builtin"):
            out.append({"id": None, "sample": f["name"], "label": f["label"], "kind": "sample"})
    return out


def context(topic_id: str | None) -> tuple[dict | None, dict | None]:
    """A system message describing the chosen model, and a short summary for the UI."""
    if not topic_id or topic_id == "line":
        return None, LINE
    if topic_id.startswith("i_"):
        r = insp.get(topic_id) or {}
        label = (r.get("inputs") or {}).get("mesh")
        m = r.get("parts") or {}
    else:
        m = asm.get(topic_id) or {}
        label = m.get("label")
    if not label:
        return None, None
    dmg = sorted(m.get("damage", []), key=lambda d: -(d.get("severity") or 0))
    lines = []
    for d in dmg[:12]:
        r = d.get("remedy") or {}
        lines.append(f"- {d.get('display_name')}: {d.get('type')}, severity {d.get('severity')}"
                     f"{', internal' if d.get('internal') else ''}; {d.get('description') or ''} "
                     f"(found by {d.get('source') or 'tags'}); stage: {r.get('stage')}; "
                     f"fix: {'; '.join(r.get('actions', [])[:2])}")
    counts = m.get("counts") or {}
    th = m.get("thermal") or {}
    body = (f'The user is asking about the saved 3D model "{label}" (id {topic_id}). Keep it in mind for every answer '
            f"in this conversation. It has {counts.get('parts')} parts, {counts.get('damaged_parts')} damaged parts and "
            f"{counts.get('damage_markers')} damage marks; simulated temperatures {th.get('min_c')} to {th.get('max_c')} C "
            f"(hottest: {th.get('hottest_part')}). Damaged parts, worst first:\n" + "\n".join(lines) +
            "\nThe fixes are engineering reference for the defect type, not learned from the line data. "
            "Temperatures are simulated. Use get_latest_inspection or get_solutions for more.")
    info = {"id": topic_id, "label": label, "kind": "scan" if topic_id.startswith("i_") else "model",
            "damaged": counts.get("damaged_parts"), "parts": counts.get("parts")}
    return {"role": "system", "content": body}, info
