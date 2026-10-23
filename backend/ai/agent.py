"""Analyst agent: answers questions by calling RootLens tools, then passes a grounding check."""
import json
import time
from concurrent.futures import ThreadPoolExecutor

from backend.ai import guard, llm, rag, tools, topic

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
- For "what should we fix or change", use get_solutions: only windows marked recommended are actions; a
  top-ranked parameter whose window is not recommended (e.g. it did not hold on later data) must not be changed yet.
- End every answer about a problem with a short "What to do" list: concrete actions from get_solutions
  (corrective windows marked recommended, stations to start with) or, for a damaged part, the fixes from
  get_latest_inspection. Say which actions are not recommended yet and why.
Be concise: short paragraphs or bullets, plant-manager friendly."""

MAX_STEPS = 6


def _run_calls(calls):
    def one(c):
        t0 = time.time()
        res = tools.call(c["name"], c["args"])
        return c, res, time.time() - t0
    with ThreadPoolExecutor(max_workers=max(1, len(calls))) as ex:
        return list(ex.map(one, calls))


def ask(question: str, provider: str | None = None, history: list | None = None, topic_id: str | None = None) -> dict:
    order = (provider,) if provider else None
    pinned = None
    try:   # retrieval-augmented context: the most relevant RootLens passages, cited as [S1] ...
        ctx, sources = rag.context_message(question)
    except Exception:  # noqa: BLE001 - the tools alone still answer if retrieval fails
        ctx, sources = None, []
    topic_msg, topic_info = topic.context(topic_id)
    from datetime import date
    today_msg = {"role": "system", "content": f"Today is {date.today().isoformat()}. Production history in RootLens is SECOM 2008 runs replayed onto 1 Sep - 23 Oct 2026 (say 'replayed SECOM runs' when you quote it). Use get_period and compare_periods for any question about a date, a week or a month, this month versus last month, or last year (which has no data)."}
    messages = [{"role": "system", "content": SYSTEM}, today_msg] + ([topic_msg] if topic_msg else []) + ([ctx] if ctx else []) + \
               list(history or []) + \
               [{"role": "user", "content": question}]
    trace, evidence = [], ([{"retrieved": [h["text"] for h in sources]}] if sources else [])
    if topic_msg:
        evidence.append({"topic": topic_msg["content"]})
    usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
    t_start = time.time()
    used = None
    reply = None
    for _ in range(MAX_STEPS):
        reply = llm.chat_with_fallback(messages, tools.schemas(), order=order, pinned=pinned)
        usage['calls'] += 1
        usage['input_tokens'] += reply.input_tokens or 0
        usage['output_tokens'] += reply.output_tokens or 0
        used = pinned = (reply.provider, reply.model)  # keep one model within a conversation
        messages.append(reply.as_message())
        if not reply.tool_calls:
            break
        for c, res, dt in _run_calls(reply.tool_calls):
            evidence.append(res)
            trace.append({"tool": c["name"], "args": c["args"], "ms": round(dt * 1000),
                          "preview": tools.dumps(res)[:300]})
            messages.append({"role": "tool", "tool_call_id": c["id"], "name": c["name"],
                             "content": _for_model(tools.dumps(res))})

    answer = (reply.content or "").strip() if reply else ""
    if not answer and evidence:   # some models stop after the tool call with no text: ask once for the answer
        messages.append({"role": "user", "content": "Now write the answer from the tool results and the retrieved context."})
        answer = _final_text(messages, pinned) or answer
    ev = guard.evidence_numbers(question, *evidence)
    check = guard.check(answer, ev)
    revised = False
    if not check["ok"] and answer:
        messages.append({"role": "user", "content":
                         "Your answer breaks the rules. Unverified numbers: "
                         f"{check['unverified_numbers']}. Violations: {check['violations']}. "
                         "Rewrite it using only numbers from the tool results, no new calculations."})
        answer = _final_text(messages, pinned) or answer
        check = guard.check(answer, ev)
        revised = True
    return {
        "answer": answer,
        "grounded": check["ok"],
        "unverified_numbers": check["unverified_numbers"],
        "violations": check["violations"],
        "revised_once": revised,
        "trace": trace,
        "sources": [{k: h[k] for k in ("id", "source", "text", "score")} for h in sources],
        "topic": topic_info,
        "context": {"system_chars": len(SYSTEM), "topic_chars": len(topic_msg["content"]) if topic_msg else 0,
                    "retrieved": len(sources), "retrieved_chars": len(ctx["content"]) if ctx else 0,
                    "history_turns": len(history or []), "tools_used": len(trace), **usage},
        "provider": used[0] if used else None,
        "model": used[1] if used else None,
        "seconds": round(time.time() - t_start, 2),
        "label": "AI summary of RootLens results; numbers are checked against tool outputs.",
    }


# Tool results are resent on every step of an answer and Groq allows 8k tokens a minute per key, so each result is
# capped for the model. The guard still checks the answer's numbers against the full results.
TOOL_CHARS = 4000


def _for_model(text: str) -> str:
    return text if len(text) <= TOOL_CHARS else text[:TOOL_CHARS] + ' ..."(trimmed; ask a narrower question for the rest)"'


def _final_text(messages, pinned) -> str:
    """One text-only follow-up call. Some models still try a tool here; then keep the earlier answer."""
    try:
        return (llm.chat_with_fallback(messages, None, pinned=pinned).content or "").strip()
    except llm.LLMError:
        return ""


def history_from(turns: list[dict]) -> list[dict]:
    """Prior Q/A pairs from the client, as plain user/assistant text."""
    out = []
    for t in turns[-6:]:
        if t.get("role") in ("user", "assistant") and isinstance(t.get("content"), str):
            out.append({"role": t["role"], "content": t["content"][:4000]})
    return out


def dumps(x) -> str:
    return json.dumps(x, default=str)
