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


TOOL_USE_FAILED = ('groq 400: {"error":{"message":"Failed to parse tool call arguments as JSON",'
                   '"type":"invalid_request_error","code":"tool_use_failed"}}')


def test_malformed_tool_call_is_sampled_again(monkeypatch):
    calls = []

    def backend(messages, tools, model, json_mode, temperature, max_tokens):
        calls.append(temperature)
        if len(calls) == 1:
            raise llm.LLMError(TOOL_USE_FAILED)
        return llm.Reply("ok", [], "groq", model)
    monkeypatch.setitem(llm._BACKENDS, "groq", backend)
    assert llm.chat([], provider="groq", model="m").content == "ok"
    assert len(calls) == 2 and calls[1] >= 0.4


def test_refused_key_rotates_to_next(monkeypatch):
    monkeypatch.setattr(llm, "keys_for", lambda p: ["k1", "k2"])
    seen = []

    def backend(*a):
        seen.append(llm._current_key("groq"))
        if len(seen) == 1:
            raise llm.LLMError("groq 401: invalid api key")
        return llm.Reply("ok", [], "groq", "m")
    monkeypatch.setitem(llm._BACKENDS, "groq", backend)
    assert llm.chat([], provider="groq", model="m").content == "ok"
    assert seen[0] != seen[1]


def test_pinned_model_failure_falls_back_to_chain(monkeypatch):
    monkeypatch.setattr(llm, "chain", lambda task: [{"provider": "gemini", "model": "b"}])

    def fake_chat(messages, tools=None, provider=None, model=None, **kw):
        if provider == "groq":
            raise llm.LLMError(TOOL_USE_FAILED)
        return llm.Reply("answer", [], provider, model)
    monkeypatch.setattr(llm, "chat", fake_chat)
    assert llm.chat_with_fallback([], pinned=("groq", "a")).provider == "gemini"


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


def test_app_keys_come_first_for_the_app_only(monkeypatch):
    for i in range(2, 10):
        monkeypatch.delenv(f"GROQ_API_KEY_{i}", raising=False)
        monkeypatch.delenv(f"GROQ_APP_API_KEY_{i}", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "shared1")
    monkeypatch.setenv("GROQ_API_KEY_2", "shared2")
    monkeypatch.setenv("GROQ_APP_API_KEY", "app1")
    assert llm.keys_for("groq") == ["shared1", "shared2"]
    token = llm.client.set("app")
    try:
        assert llm.keys_for("groq") == ["app1", "shared1", "shared2"]
    finally:
        llm.client.reset(token)


def test_conversation_is_shared_between_clients(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from backend.ai import chats
    from backend.api.main import app
    monkeypatch.setattr(chats, "DIR", tmp_path)
    seen = {}

    def fake_ask(q, provider, history, topic):
        seen["history"] = history
        seen["client"] = llm.client.get()
        return {"answer": f"re: {q}", "grounded": True, "provider": "groq", "model": "m", "sources": []}
    monkeypatch.setattr(agent, "ask", fake_ask)
    c = TestClient(app)
    c.post("/api/ai/ask", json={"question": "asked on the phone"}, headers={"X-RootLens-Client": "android"})
    assert seen["client"] == "app"
    c.post("/api/ai/ask", json={"question": "asked on the web"})
    assert seen["client"] == "web" and seen["history"][0]["content"] == "asked on the phone"
    msgs = c.get("/api/ai/chat").json()["messages"]
    assert [m["client"] for m in msgs] == ["app", "app", "web", "web"]
    assert c.delete("/api/ai/chat").json()["deleted"] == 4 and c.get("/api/ai/chat").json()["messages"] == []


def test_transcribe_endpoint_passes_language_and_client(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.api.main import app
    seen = {}

    def fake(audio, filename, language):
        seen.update(audio=audio, filename=filename, language=language, client=llm.client.get())
        return {"text": "how did this month compare", "model": "whisper", "seconds": 0.1}
    monkeypatch.setattr(llm, "transcribe", fake)
    c = TestClient(app)
    r = c.post("/api/ai/transcribe", files={"file": ("speech.webm", b"abc")}, data={"language": "kn"}, headers={"X-RootLens-Client": "android"})
    assert r.status_code == 200 and r.json()["text"].startswith("how")
    assert seen == {"audio": b"abc", "filename": "speech.webm", "language": "kn", "client": "app"}
    assert c.post("/api/ai/transcribe", files={"file": ("s.webm", b"x")}, data={"language": "fr"}).status_code == 422
