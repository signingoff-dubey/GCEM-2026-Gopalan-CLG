"""Answers for the phone agent (Sarvam calls this as an HTTP tool during a call, with a ~10 s budget).

Questions about dates, weeks and months ("what happened on 12 September", "compare this month with last month",
"anything last year") are answered straight from the replayed history in well under a second, as two or three
spoken sentences. Anything else goes to the grounded AI agent with a spoken-style instruction.
"""
import re
from datetime import date

from backend.api.state import state

MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}
PHRASES = ["today", "yesterday", "this week", "last week", "previous week", "this month", "current month",
           "last month", "previous month", "last year", "previous year"]


def _pct(x):
    return f"{x * 100:.1f} percent"


def periods(question: str, year: int = 2026) -> list[str]:
    """Dates (12 September / September 12th), months (October) and phrases, in the order they appear."""
    q = question.lower()
    found = []
    for m in re.finditer(r"(\d{1,2})(?:st|nd|rd|th)?(?: of)? (" + "|".join(MONTHS) + r")|(" + "|".join(MONTHS) +
                         r") (\d{1,2})(?:st|nd|rd|th)?\b|\b(" + "|".join(MONTHS) + r")\b|(" + "|".join(PHRASES) + r")", q):
        if m.group(1):
            found.append((m.start(), date(year, MONTHS[m.group(2)], int(m.group(1))).isoformat()))
        elif m.group(3):
            found.append((m.start(), date(year, MONTHS[m.group(3)], int(m.group(4))).isoformat()))
        elif m.group(5):
            found.append((m.start(), f"{year}-{MONTHS[m.group(5)]:02d}"))
        else:
            found.append((m.start(), m.group(6)))
    for m in re.finditer(r"\b(20\d\d)-(\d\d)(?:-(\d\d))?\b", q):
        found.append((m.start(), m.group(0)))
    seen, out = set(), []
    for _, p in sorted(found):
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def spoken(key: str) -> str:
    """2026-09-12 -> '12 September 2026', 2026-10 -> 'October 2026', phrases unchanged."""
    m = re.fullmatch(r"(\d{4})-(\d\d)(?:-(\d\d))?", key)
    if not m:
        return key
    month = [k for k, v in MONTHS.items() if v == int(m.group(2))][0].capitalize()
    return f"{int(m.group(3))} {month} {m.group(1)}" if m.group(3) else f"{month} {m.group(1)}"


def _say(p: dict, name: str) -> str:
    name = spoken(name)
    if not p.get("runs"):
        return f"There is no production data for {name}; the history covers the first of September to the twenty-third of October 2026."
    s = (f"For {name}, {p['runs']} runs were made: {p['passes']} passed and {p['fails']} failed, a fail rate of {_pct(p['fail_rate'])}. "
         f"{p['high_risk_runs']} runs were flagged high risk by the model.")
    w = p.get("F33_window")
    if w and w.get("fail_rate_inside") is not None:
        s += (f" Runs with F33 inside its recommended window failed {_pct(w['fail_rate_inside'])} of the time, "
              f"against {_pct(w['fail_rate_outside'] or 0)} outside.")
    return s


def fix_answer() -> str:
    from backend.api.solutions import solutions
    sol = solutions()
    do = [x for x in sol["line"] if x["do"]]
    dont = [x for x in sol["line"] if not x["do"]][:2]
    s = " ".join(f"{x['action']}. Inside that range the failure rate was {_pct(x['evidence']['fail_rate_inside'])} "
                 f"against {_pct(x['evidence']['fail_rate_outside'])} outside, and it held on later data." for x in do)
    if dont:
        s += " " + " ".join(f"{x['parameter']} is also suspected, but do not change it yet: {x['reason_not']}." for x in dont)
    return (s + " Run a short pilot to confirm before changing the line.").strip()


def fast_answer(question: str) -> str | None:
    from backend.ml import replay
    q0 = question.lower()
    if re.search(r"\b(fix|change|adjust|recommend|should we|what to do|first)\b", q0) and \
            not re.search(r"part|model|crack|die|wire|lead|chip|scan", q0) and not periods(question):
        return fix_answer()
    ps = periods(question)
    if not ps:
        return None
    r = state.json("replay.json")
    q = question.lower()
    if len(ps) >= 2 and re.search(r"compar|versus|\bvs\b|than|differ|better|worse", q):
        a, b = (replay.resolve(r, x) for x in ps[:2])
        pa, pb = replay.period(r, *a), replay.period(r, *b)
        if not (pa.get("runs") and pb.get("runs")):
            return " ".join(_say(p, n) for p, n in ((pa, ps[0]), (pb, ps[1])))
        n0, n1 = spoken(ps[0]), spoken(ps[1])
        d = pa["fail_rate"] - pb["fail_rate"]
        trend = "lower than" if d < 0 else "higher than" if d > 0 else "the same as"
        cap = lambda t: t[:1].upper() + t[1:]
        return (f"{cap(n0)} had {pa['runs']} runs and {pa['fails']} failures, a fail rate of {_pct(pa['fail_rate'])}. "
                f"{cap(n1)} had {pb['runs']} runs and {pb['fails']} failures, {_pct(pb['fail_rate'])}. "
                f"So {n0}'s fail rate is {trend} {n1}'s" + (f", by {abs(d) * 100:.1f} points." if d else ".") +
                " These are replayed SECOM runs.")
    s, e = replay.resolve(r, ps[0])
    return _say(replay.period(r, s, e), ps[0]) + " These are replayed SECOM runs."


SPOKEN = ("You are answering on a phone call. Reply in two to four short spoken sentences: no markdown, no lists, "
          "no tables, no source tags, round numbers sensibly. Still use only numbers from the tools.")


def answer(question: str) -> dict:
    fast = fast_answer(question)
    if fast:
        return {"result": fast, "via": "history"}
    from backend.ai import agent
    r = agent.ask(question, history=[{"role": "system", "content": SPOKEN}])
    text = re.sub(r"\[S\d+\]|【[^】]*】|[*#`|]", "", r["answer"])
    text = re.sub(r"\s+", " ", text).strip()
    return {"result": text or "I could not find that in the RootLens analysis.", "via": r.get("provider")}
