"""AI layer tests with a scripted fake LLM: no network, deterministic."""
import json

import pytest

from backend.ai import agent, guard, llm, tools


# ---- guard ----

@pytest.mark.parametrize("text,ok", [
    ("F33 window fail rate 0.0248, savings INR 238533 to 779525 (model estimate)", True),
    ("Fail rate drops to 1.2%", False),                             # invented number
    ("Accuracy is 94%", False),
    ("We do not report accuracy because failures are rare", True),
    ("The root cause is F59", False),
    ("F59 is the chamber pressure", False),
    ("Competitors lack stability checks", False),
    ("We did not find this in the 7 projects we checked", True),
    ("Scans are processed in real-time", False),
    ("Savings INR 238 533 per month", True),
])
def test_guard(text, ok):
    ev = guard.evidence_numbers({"rate": 0.02479, "low": 238533, "high": 779525, "checked": 7})
    assert guard.check(text, ev)["ok"] is ok


def test_tidy_rounds_for_quoting():
    assert tools.tidy({"a": 0.024793388429752067, "b": 238532.60011, "c": [1.0, None, True]}) == \
        {"a": 0.02479, "b": 238533, "c": [1.0, None, True]}


# ---- agent loop with a fake model ----

class FakeLLM:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def __call__(self, messages, tools=None, order=None, pinned=None, **kw):
        self.calls.append(messages)
        return self.script.pop(0)


def test_agent_calls_tools_and_passes_guard(monkeypatch):
    monkeypatch.setattr(tools, "call", lambda name, args: {"feature": "F33", "rate_in": 0.0248})
    fake = FakeLLM([
        llm.Reply("", [{"id": "1", "name": "get_safe_windows", "args": {}}], "groq", "m"),
        llm.Reply("F33 has a fail rate of 0.0248 inside its window.", [], "groq", "m"),
    ])
    monkeypatch.setattr(llm, "chat_with_fallback", fake)
    out = agent.ask("what to fix?")
    assert out["grounded"] and out["trace"][0]["tool"] == "get_safe_windows"
    tool_msg = [m for m in fake.calls[1] if m["role"] == "tool"][0]
    assert json.loads(tool_msg["content"])["rate_in"] == 0.0248


def test_agent_revises_once_then_reports_unverified(monkeypatch):
    monkeypatch.setattr(agent.rag, "context_message", lambda q: (None, []))   # only the tool result as evidence
    monkeypatch.setattr(tools, "call", lambda name, args: {"rate_in": 0.0248})
    fake = FakeLLM([
        llm.Reply("", [{"id": "1", "name": "get_safe_windows", "args": {}}], "groq", "m"),
        llm.Reply("Fail rate falls to 0.9%.", [], "groq", "m"),
        llm.Reply("Fail rate falls to 0.9%, trust me.", [], "groq", "m"),
    ])
    monkeypatch.setattr(llm, "chat_with_fallback", fake)
    out = agent.ask("what to fix?")
    assert out["revised_once"] and not out["grounded"] and out["unverified_numbers"]


def test_chain_skips_failures_and_logs(monkeypatch):
    monkeypatch.setattr(llm, "chain", lambda task: [{"provider": "groq", "model": "a"},
                                                   {"provider": "gemini", "model": "b"}])

    def fake_chat(messages, tools=None, provider=None, model=None, **kw):
        if provider == "groq":
            raise llm.LLMError("groq 503: busy")
        return llm.Reply('{"ok": 1}', [], provider, model)
    monkeypatch.setattr(llm, "chat", fake_chat)
    reply, log = llm.run_chain("vision", [{"role": "user", "content": "x"}])
    assert reply.provider == "gemini" and [s["ok"] for s in log] == [False, True]


def test_chain_validation_moves_on(monkeypatch):
    monkeypatch.setattr(llm, "chain", lambda task: [{"provider": "groq", "model": "a"},
                                                   {"provider": "openrouter", "model": "b"}])
    monkeypatch.setattr(llm, "chat", lambda m, t=None, provider=None, model=None, **kw:
                        llm.Reply("not json" if provider == "groq" else '{"values": {}}', [], provider, model))
    reply, log = llm.run_chain("vision", [], validate=lambda r: None if r.content.startswith("{") else "invalid JSON")
    assert reply.provider == "openrouter" and log[0]["error"] == "invalid JSON"


def test_rag_retrieves_the_right_passages():
    from backend.ai import rag
    assert rag.retrieve("how were missing values handled")[0]["source"] == "data cleaning"
    assert rag.retrieve("is the data drifting")[0]["source"] == "drift"
    assert rag.retrieve("what should we change on the line")[0]["source"].startswith("corrective window")
    msg, hits = rag.context_message("why does a die crack")
    assert "[S1]" in msg["content"] and any("die crack" in h["source"] for h in hits)
