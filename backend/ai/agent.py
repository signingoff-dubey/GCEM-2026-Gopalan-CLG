"""Analyst agent: answers questions by calling RootLens tools, then passes a grounding check."""
import json
import time
from concurrent.futures import ThreadPoolExecutor

from backend.ai import guard, llm, tools

SYSTEM = """You are RootLens, an analyst for manufacturing quality engineers.
Answer using the tools. Call several tools in one turn when they are independent.
Hard rules:
- Every number you state must appear in a tool result. Do not compute new numbers (no ratios, sums or
  conversions) unless the tool gives them. Round only by dropping decimals.
- Never mention accuracy. Model quality is PR-AUC (with its CI) on a later held-out time window.
- Never say a parameter is the root cause or that anything is proven. Say "statistically suspected,
  stability-checked". Recommendations are associations to be confirmed by a pilot.
- Parameters such as F59 and stations such as L3_S32 are anonymized. Never guess what they measure.
- Savings are always a range (low-high) and labelled "model estimate".
- If a window did not hold on the held-out test window, say so plainly.
- For savings and pilots, call the tools with their default inputs unless the user gives volumes or
  costs; then state the assumptions the tool used.
- Quote numbers as the tools give them; show rates as percentages only if the tool gives a percentage,
  otherwise quote the fraction (e.g. 0.0248). Write money without thousands separators (e.g. INR 139745).
Be concise: short paragraphs or bullets, plant-manager friendly."""

MAX_STEPS = 6


def _run_calls(calls):
    def one(c):
        t0 = time.time()
        res = tools.call(c["name"], c["args"])
        return c, res, time.time() - t0
    with ThreadPoolExecutor(max_workers=max(1, len(calls))) as ex:
        return list(ex.map(one, calls))


def ask(question: str, provider: str | None = None, history: list | None = None) -> dict:
    order = (provider,) if provider else None
    pinned = None
    messages = [{"role": "system", "content": SYSTEM}] + list(history or []) + \
               [{"role": "user", "content": question}]
    trace, evidence = [], []
    t_start = time.time()
    used = None
    reply = None
    for _ in range(MAX_STEPS):
        reply = llm.chat_with_fallback(messages, tools.schemas(), order=order, pinned=pinned)
        used = pinned = (reply.provider, reply.model)  # keep one model within a conversation
        messages.append(reply.as_message())
        if not reply.tool_calls:
            break
        for c, res, dt in _run_calls(reply.tool_calls):
            evidence.append(res)
            trace.append({"tool": c["name"], "args": c["args"], "ms": round(dt * 1000),
                          "preview": tools.dumps(res)[:300]})
            messages.append({"role": "tool", "tool_call_id": c["id"], "name": c["name"],
                             "content": tools.dumps(res)})

    answer = (reply.content or "").strip() if reply else ""
    ev = guard.evidence_numbers(question, *evidence)
    check = guard.check(answer, ev)
    revised = False
    if not check["ok"] and answer:
        messages.append({"role": "user", "content":
                         "Your answer breaks the rules. Unverified numbers: "
                         f"{check['unverified_numbers']}. Violations: {check['violations']}. "
                         "Rewrite it using only numbers from the tool results, no new calculations."})
        reply = llm.chat_with_fallback(messages, None, pinned=pinned)
        answer = reply.content.strip()
        check = guard.check(answer, ev)
        revised = True
    return {
        "answer": answer,
        "grounded": check["ok"],
        "unverified_numbers": check["unverified_numbers"],
        "violations": check["violations"],
        "revised_once": revised,
        "trace": trace,
        "provider": used[0] if used else None,
        "model": used[1] if used else None,
        "seconds": round(time.time() - t_start, 2),
        "label": "AI summary of RootLens results; numbers are checked against tool outputs.",
    }


def history_from(turns: list[dict]) -> list[dict]:
    """Prior Q/A pairs from the client, as plain user/assistant text."""
    out = []
    for t in turns[-6:]:
        if t.get("role") in ("user", "assistant") and isinstance(t.get("content"), str):
            out.append({"role": t["role"], "content": t["content"][:4000]})
    return out


def dumps(x) -> str:
    return json.dumps(x, default=str)
