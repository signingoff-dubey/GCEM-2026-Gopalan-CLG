"""What usually causes a defect type and what to change, for the Inspection page, the alert call and the AI.

Engineering reference for electronics packaging and assembly (die attach, wire bond, mould, trim and form,
reflow, battery cells). It is general knowledge about the defect type, not something learned from this
line's data: the UI labels it that way, and the line's own suspected parameters come from the SECOM analysis.
"""

SOURCE = "Engineering reference for this defect type, not derived from your line data."

# keyword in the damage type -> causes, checks, actions (what to change), process stage
TABLE = [
    (("die crack",), {
        "stage": "Die attach, moulding and singulation",
        "causes": ["Voids or an uneven bond line under the die concentrate stress",
                   "Mould transfer pressure or cure ramp too aggressive (thermo-mechanical stress)",
                   "Chipping from a worn dicing blade that grows into a crack"],
        "checks": ["Die-attach void % and bond-line thickness (X-ray)", "Mould transfer pressure and cure profile log",
                   "Dicing blade life and saw feed speed"],
        "actions": ["Quarantine the lot and scan it (C-SAM / X-ray) before shipping",
                    "Lower mould transfer pressure and slow the cure ramp, inside the qualified window",
                    "Replace the dicing blade and reduce feed speed if chipping is present"]}),
    (("burn", "scorch", "short"), {
        "stage": "Electrical test and assembly",
        "causes": ["Electrical overstress or ESD", "A short between neighbouring bonds or leads",
                   "Test current limits set too high"],
        "checks": ["ESD grounding and ioniser logs", "Curve trace of the affected pins", "Test program current limits"],
        "actions": ["Verify ESD controls on the line", "Lower test current limits", "Inspect for bridging between bonds"]}),
    (("contamination", "particle", "dust"), {
        "stage": "Clean room and bonding",
        "causes": ["Particles from tooling or the environment", "Missing plasma clean"],
        "checks": ["Particle counts", "Plasma clean step"], "actions": ["Clean the tooling", "Restore the plasma clean step"]}),
    (("void", "delamination"), {
        "stage": "Moulding and die attach",
        "causes": ["Moisture or poor adhesion between mould compound and the lead frame", "Incomplete cure"],
        "checks": ["C-SAM scan", "Cure time and temperature", "Lead-frame surface treatment"],
        "actions": ["Bake before moulding", "Extend cure within spec", "Plasma-clean the lead frame"]}),
    (("swelling", "cell"), {
        "stage": "Cell formation and pack assembly",
        "causes": ["Gas from overcharge or a cell defect", "Heat from a neighbouring fault"],
        "checks": ["Charge controller limits", "Cell temperature during formation"],
        "actions": ["Quarantine the pack", "Check charge limits and cell-level fusing"]}),
    (("crack", "fracture"), {
        "stage": "Moulding, reflow and handling",
        "causes": ["Moisture absorbed by the package flashes to steam in reflow (popcorn cracking)",
                   "Reflow peak temperature or ramp above the package rating",
                   "Mechanical shock in trim and form or in the handler"],
        "checks": ["Floor-life exposure versus the moisture sensitivity level", "Reflow profile: peak and ramp rate",
                   "Trim/form tool condition and handler pick force"],
        "actions": ["Bake parts per their moisture sensitivity level before reflow",
                    "Bring the reflow peak and ramp back inside the package rating",
                    "Inspect and re-shim the trim/form tooling; lower handler pick force"]}),
    (("chip",), {
        "stage": "Singulation, trim and form, handling",
        "causes": ["Impact from a misaligned punch or handler nozzle", "Worn singulation tool"],
        "checks": ["Punch alignment and wear", "Handler nozzle height and force"],
        "actions": ["Re-align or replace the punch", "Reduce handler force and add soft-landing"]}),
    (("bond wire", "wire"), {
        "stage": "Wire bonding and moulding",
        "causes": ["Low bond force, ultrasonic power or bond temperature (weak bond that lifts)",
                   "Contaminated bond pads", "Wire sweep from fast mould transfer", "Overcurrent fusing the wire"],
        "checks": ["Wire pull and ball shear test results", "Pad cleanliness (plasma clean log)",
                   "Mould transfer speed and loop height", "Electrical test current limits"],
        "actions": ["Raise ultrasonic power and bond force within the qualified window; re-run pull/shear tests",
                    "Plasma-clean pads before bonding",
                    "Slow the mould transfer and lower loop height to reduce wire sweep"]}),
    (("lead", "tear"), {
        "stage": "Trim and form",
        "causes": ["Worn or misaligned trim/form tool", "Over-bending of leads", "Handling damage after forming"],
        "checks": ["Lead coplanarity and length", "Form tool wear and alignment"],
        "actions": ["Replace or re-align the form tool", "Add a coplanarity check after trim/form"]}),
    (("dent", "deformation", "deformed"), {
        "stage": "Handling and forming",
        "causes": ["Impact in handling or transport", "Forming force too high"],
        "checks": ["Fixture and tray condition", "Forming force"], "actions": ["Fix the fixture or tray", "Lower forming force"]}),
    (("fragment", "loose"), {
        "stage": "Assembly and handling",
        "causes": ["A piece broke off another part"], "checks": ["Which part it came from (look for a matching gap)"],
        "actions": ["Quarantine the unit and trace the fragment to its source part"]}),
]
GENERIC = {"stage": "Unknown", "causes": ["No reference entry for this defect type"],
           "checks": ["Inspect the part and the process step that forms it"], "actions": ["Quarantine the unit and review the step"]}


def lookup(damage_type: str | None, part: str = "") -> dict:
    """First matching entry for 'part + damage type', most specific defects first (die crack before crack)."""
    text = f"{part} {damage_type or ''}".lower()
    for keys, entry in TABLE:
        if any(k in text for k in keys):
            return {**entry, "source": SOURCE}
    return {**GENERIC, "source": SOURCE}


def attach(record: dict | None) -> dict | None:
    """Give every damage entry of a model or scan its fix (records saved before fixes existed get one too)."""
    if not record:
        return record
    for holder in (record, record.get("parts") if isinstance(record.get("parts"), dict) else None):
        if not holder:
            continue
        for d in holder.get("damage") or []:
            d.setdefault("remedy", lookup(d.get("type"), d.get("display_name", "")))
        for p in holder.get("parts") or [] if isinstance(holder.get("parts"), list) else []:
            if p.get("damage"):
                p["damage"].setdefault("remedy", lookup(p["damage"].get("type"), p.get("display_name", "")))
    return record


def one_line(damage_type: str | None, part: str = "") -> str:
    r = lookup(damage_type, part)
    return r["actions"][0]
