"""Grounding guard: every number an LLM states must come from tool output (or the question),
and the text must follow the honesty rules. Fails closed."""
import json
import re

NUM_RE = re.compile(
    r"(?<![A-Za-z_\d])(?:INR|Rs\.?|₹)?\s*(-?\d[\d,]*\.?\d*)\s*(%|x|×|k|K|M|lakh|lakhs|crore|crores)?(?![\d])")
ID_RE = re.compile(r"\b(?:F\d+(?:_missing)?|L\d+_S\d+(?:_[FD]\d+)?|S\d+|G\d+|v\d+(?:\.\d+)*)\b")
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?\b|\b\d{1,2}:\d{2}\b")
SCALE = {"k": 1e3, "K": 1e3, "M": 1e6, "lakh": 1e5, "lakhs": 1e5, "crore": 1e7, "crores": 1e7}

BANNED = [
    # an accuracy claim = the word next to a figure; refusing to give accuracy is fine
    (re.compile(r"\baccura(?:te|cy)\b[^.\n]{0,25}?\d|\d[\d.]*\s*%?\s*accura(?:te|cy)\b", re.I),
     "reports accuracy (use PR-AUC / MCC instead)"),
    (re.compile(r"\b(?:the\s+)?root\s+cause\s+(?:is|was|has been)\b", re.I), "claims a proven root cause"),
    (re.compile(r"(?<!not )\b(?:proves?|proven|confirms? that)\b(?! nothing)", re.I), "claims proof"),
    (re.compile(r"\bcaused by\b", re.I), "claims causation"),
    # competitor claims are phrased as what we found in the sources we checked
    (re.compile(r"\b(?:competitors?|other (?:teams|tools|solutions|projects)|others)\s+(?:all\s+)?"
                r"(?:lack|lacks|don't have|do not have|cannot|can't|fail to|miss)\b", re.I),
     "claims competitors lack something (say 'we did not find it in the sources we checked')"),
    (re.compile(r"\b(?:no one|nobody|no other (?:team|tool|solution|project))\s+(?:else\s+)?"
                r"(?:does|has|offers|builds|can)\b", re.I), "absolute uniqueness claim"),
    (re.compile(r"(?<!not )\breal[- ]time\b", re.I), "says real-time (say 'analyzed after upload')"),
]
PHYSICAL = re.compile(
    r"\bF\d+\b[^.\n]{0,40}\b(?:temperature|pressure|flow|voltage|current|humidity|thickness|chamber|"
    r"gas|power|etch|deposition|rpm|speed|torque|vacuum|plasma)\b", re.I)


def _flatten_numbers(obj, out: list) -> None:
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, str):
        for m in re.finditer(r"-?\d+(?:\.\d+)?", obj.replace(",", "")):
            out.append(float(m.group()))
    elif isinstance(obj, dict):
        for v in obj.values():
            _flatten_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _flatten_numbers(v, out)


def evidence_numbers(*sources) -> list[float]:
    nums: list[float] = []
    for s in sources:
        if isinstance(s, str):
            try:
                s = json.loads(s)
            except (json.JSONDecodeError, TypeError):
                pass
        _flatten_numbers(s, nums)
    return nums


def _decimals(token: str) -> int:
    return len(token.split(".")[1]) if "." in token else 0


def _matches(value: float, token: str, unit: str | None, evidence: list[float]) -> bool:
    """True if some evidence number rounds to what was written. Percentages may be stored as
    fractions; k / M / lakh / crore are scaled; large whole numbers may be rounded to ~1 %."""
    half = 0.5 * 10 ** (-_decimals(token)) + 1e-12
    if unit in SCALE:
        candidates = [(value * SCALE[unit], half * SCALE[unit])]
    elif unit == "%":
        candidates = [(value, half), (value / 100, half / 100)]
    else:
        candidates = [(value, half)]
    for c, tol in candidates:
        for e in evidence:
            if abs(e - c) <= max(tol, abs(e) * 0.005):
                return True
            if abs(c) >= 1000 and abs(e - c) <= abs(e) * 0.01:
                return True
    return False


GROUP_SEP = re.compile(r"(?<=\d)[\u202f\u00a0\u2009 ,](?=\d{3}(?!\d))")


def check(text: str, evidence: list[float], allow_small_ints: int = 10) -> dict:
    scrub = ID_RE.sub(" ", DATE_RE.sub(" ", text))
    for _ in range(4):  # "1 397 445" / "1,397,445" / thin spaces -> 1397445
        scrub = GROUP_SEP.sub("", scrub)
    unverified = []
    for m in NUM_RE.finditer(scrub):
        token, unit = m.group(1).replace(",", ""), m.group(2)
        if token in ("", "-", "."):
            continue
        try:
            value = float(token.rstrip("."))
        except ValueError:
            continue
        if unit is None and value.is_integer() and 0 <= value <= allow_small_ints:
            continue
        if unit in ("x", "×"):
            unit = None
        if not _matches(value, token.rstrip("."), unit, evidence):
            unverified.append(m.group(0).strip())
    violations = [msg for rx, msg in BANNED if rx.search(text)]
    if PHYSICAL.search(text):
        violations.append("attributes a physical meaning to an anonymized feature")
    return {"ok": not unverified and not violations, "unverified_numbers": sorted(set(unverified)),
            "violations": violations}
