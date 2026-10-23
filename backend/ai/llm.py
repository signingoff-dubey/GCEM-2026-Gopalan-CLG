"""Groq, Gemini and OpenRouter chat clients (tools, JSON mode, images) behind one interface,
plus a failover chain whose provider/model order lives in config/llm_chain.yaml.

Messages use the OpenAI shape: {"role": "system"|"user"|"assistant"|"tool", ...}.
User turns may carry "images": [(mime, bytes)]. Assistant turns may carry
"tool_calls": [{"id", "name", "args"}]; tool turns carry "tool_call_id", "name", "content".
Gemini turns keep their raw parts so thought signatures are echoed back unchanged.
"""
import base64
import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field

import httpx
import yaml

from backend.config import ROOT

TIMEOUT = 90.0
PROVIDERS = ("groq", "gemini", "openrouter")
DEFAULT_MODELS = {"groq": "openai/gpt-oss-120b", "gemini": "gemini-flash-latest",
                  "openrouter": "nvidia/nemotron-3.5-super-vl:free"}
CHAIN_FILE = ROOT / "config" / "llm_chain.yaml"
OPENAI_COMPAT = {"groq": "https://api.groq.com/openai/v1/chat/completions",
                 "openrouter": "https://openrouter.ai/api/v1/chat/completions"}


def load_env(path=ROOT / ".env") -> None:
    """Read KEY=value lines into os.environ without overriding existing values."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"\''))


load_env()


class LLMError(RuntimeError):
    pass


@dataclass
class Reply:
    content: str
    tool_calls: list = field(default_factory=list)
    provider: str = ""
    model: str = ""
    latency_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    raw_parts: list | None = None   # Gemini only

    def as_message(self) -> dict:
        m = {"role": "assistant", "content": self.content, "tool_calls": self.tool_calls}
        if self.raw_parts is not None:
            m["_gemini_parts"] = self.raw_parts
        return m


# ---------------- keys ----------------

def keys_for(provider: str) -> list[str]:
    """PROVIDER_API_KEY, PROVIDER_API_KEY_2, ... in order."""
    base = f"{provider.upper()}_API_KEY"
    keys = [os.getenv(base)] + [os.getenv(f"{base}_{i}") for i in range(2, 10)]
    return [k for k in keys if k]


_key_cursor = {p: 0 for p in PROVIDERS}


def _current_key(provider: str) -> str:
    keys = keys_for(provider)
    if not keys:
        raise LLMError(f"{provider.upper()}_API_KEY not set")
    return keys[_key_cursor[provider] % len(keys)]


def _rotate(provider: str) -> None:
    _key_cursor[provider] += 1


def available() -> dict:
    return {p: bool(keys_for(p)) for p in PROVIDERS}


def model_for(provider: str) -> str:
    return os.getenv(f"{provider.upper()}_MODEL", DEFAULT_MODELS[provider])


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


# ---------------- OpenAI-compatible (Groq, OpenRouter) ----------------

def _openai_compat(provider, messages, tools, model, json_mode, temperature, max_tokens) -> Reply:
    key = _current_key(provider)
    msgs = []
    for m in messages:
        if m["role"] == "assistant":
            out = {"role": "assistant", "content": m.get("content") or ""}
            if m.get("tool_calls"):
                out["tool_calls"] = [{"id": c["id"], "type": "function",
                                      "function": {"name": c["name"], "arguments": json.dumps(c["args"])}}
                                     for c in m["tool_calls"]]
            msgs.append(out)
        elif m["role"] == "tool":
            msgs.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]})
        elif m.get("images"):
            parts = [{"type": "text", "text": m["content"]}] + [
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{_b64(data)}"}}
                for mime, data in m["images"]]
            msgs.append({"role": m["role"], "content": parts})
        else:
            msgs.append({"role": m["role"], "content": m["content"]})
    body = {"model": model, "messages": msgs, "temperature": temperature, "max_tokens": max_tokens}
    if tools:
        body["tools"] = [{"type": "function", "function": t} for t in tools]
        body["tool_choice"] = "auto"
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    t0 = time.time()
    r = httpx.post(OPENAI_COMPAT[provider], json=body, timeout=TIMEOUT,
                   headers={"Authorization": f"Bearer {key}"})
    dt = time.time() - t0
    if r.status_code != 200:
        raise LLMError(f"{provider} {r.status_code}: {r.text[:300]}")
    j = r.json()
    if "choices" not in j:
        raise LLMError(f"{provider} returned no choices: {str(j)[:200]}")
    msg = j["choices"][0]["message"]
    calls = []
    for c in msg.get("tool_calls") or []:
        try:
            args = json.loads(c["function"].get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        calls.append({"id": c["id"], "name": c["function"]["name"], "args": args})
    u = j.get("usage") or {}
    return Reply(msg.get("content") or "", calls, provider, model, dt,
                 u.get("prompt_tokens", 0), u.get("completion_tokens", 0))


# ---------------- Gemini ----------------

def _clean_schema(s):
    """Gemini accepts an OpenAPI subset; drop keys it rejects."""
    if isinstance(s, dict):
        return {k: _clean_schema(v) for k, v in s.items() if k not in ("additionalProperties", "default")}
    if isinstance(s, list):
        return [_clean_schema(v) for v in s]
    return s


def _gemini(messages, tools, model, json_mode, temperature, max_tokens) -> Reply:
    key = _current_key("gemini")
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    contents = []
    for m in messages:
        if m["role"] == "user":
            parts = [{"text": m["content"]}] + [{"inline_data": {"mime_type": mime, "data": _b64(data)}}
                                                for mime, data in m.get("images") or []]
            contents.append({"role": "user", "parts": parts})
        elif m["role"] == "assistant":
            parts = m.get("_gemini_parts")
            if parts is None:
                parts = ([{"text": m["content"]}] if m.get("content") else []) + \
                        [{"functionCall": {"name": c["name"], "args": c["args"]}} for c in m.get("tool_calls", [])]
            contents.append({"role": "model", "parts": parts})
        elif m["role"] == "tool":
            part = {"functionResponse": {"name": m["name"], "response": {"result": json.loads(m["content"])}}}
            if contents and contents[-1]["role"] == "user" and "functionResponse" in contents[-1]["parts"][0]:
                contents[-1]["parts"].append(part)
            else:
                contents.append({"role": "user", "parts": [part]})
    body = {"contents": contents,
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if tools:
        body["tools"] = [{"functionDeclarations": [_clean_schema(t) for t in tools]}]
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    t0 = time.time()
    r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                   json=body, timeout=TIMEOUT, headers={"x-goog-api-key": key})
    dt = time.time() - t0
    if r.status_code != 200:
        raise LLMError(f"gemini {r.status_code}: {r.text[:300]}")
    j = r.json()
    cands = j.get("candidates") or []
    if not cands:
        raise LLMError(f"gemini returned no candidates: {str(j)[:200]}")
    parts = cands[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    calls = [{"id": uuid.uuid4().hex[:12], "name": p["functionCall"]["name"],
              "args": p["functionCall"].get("args", {})} for p in parts if "functionCall" in p]
    u = j.get("usageMetadata", {})
    return Reply(text, calls, "gemini", model, dt, u.get("promptTokenCount", 0),
                 u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0), raw_parts=parts)


_BACKENDS = {
    "groq": lambda *a: _openai_compat("groq", *a),
    "openrouter": lambda *a: _openai_compat("openrouter", *a),
    "gemini": _gemini,
}
RETRYABLE = ("429", "500", "502", "503", "504", "no candidates", "no choices")


def _wait_hint(msg: str) -> float:
    m = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", msg)
    if m:
        return float(m.group(1) or 0) * 60 + float(m.group(2))
    m = re.search(r"retryDelay\W+(\d+)s", msg)
    return float(m.group(1)) if m else 4.0


def chat(messages, tools=None, provider="groq", model=None, json_mode=False,
         temperature=0.1, max_tokens=2048, retries=2, max_wait=20.0) -> Reply:
    """One completion. On a rate limit, switch to the next key at once; once every key has been
    tried, wait for the server's hinted delay. Overload errors are retried after a delay."""
    n_keys = max(1, len(keys_for(provider)))
    rotations, attempt = 0, 0
    while True:
        try:
            return _BACKENDS[provider](messages, tools, model or model_for(provider), json_mode,
                                       temperature, max_tokens)
        except LLMError as e:
            msg = str(e)
            if not any(code in msg for code in RETRYABLE):
                raise
            if "429" in msg and rotations < n_keys - 1:
                _rotate(provider)
                rotations += 1
                continue
            if attempt >= retries:
                raise
            attempt += 1
            rotations = 0
            time.sleep(min(_wait_hint(msg), max_wait))


# ---------------- chains ----------------

def chain(task: str) -> list[dict]:
    """Ordered [{provider, model, ...}] for a task from config/llm_chain.yaml, keyed providers only."""
    cfg = yaml.safe_load(CHAIN_FILE.read_text(encoding="utf-8")) if CHAIN_FILE.exists() else {}
    steps = cfg.get(task) or [{"provider": p, "model": model_for(p)} for p in ("groq", "gemini")]
    return [s for s in steps if available().get(s["provider"])]


def run_chain(task: str, messages, tools=None, validate=None, **kw) -> tuple[Reply, list[dict]]:
    """Try each chain entry; move on when a call fails or `validate(reply)` returns an error string.
    Returns the first good reply and a log of every attempt."""
    log = []
    max_tokens = kw.pop("max_tokens", None)
    for step in chain(task):
        t0 = time.time()
        try:
            r = chat(messages, tools, provider=step["provider"], model=step["model"],
                     retries=step.get("retries", 0), max_wait=step.get("max_wait", 5.0),
                     max_tokens=max_tokens or step.get("max_tokens", 2048), **kw)
            problem = validate(r) if validate else None
            if not problem and not (r.content or r.tool_calls):
                problem = "empty response"
            log.append({"provider": step["provider"], "model": step["model"], "ok": not problem,
                        "ms": round((time.time() - t0) * 1000), "error": problem})
            if not problem:
                return r, log
        except (LLMError, httpx.HTTPError) as e:
            log.append({"provider": step["provider"], "model": step["model"], "ok": False,
                        "ms": round((time.time() - t0) * 1000), "error": str(e)[:200]})
    raise LLMError("chain exhausted: " + "; ".join(f"{s['provider']}:{s['error']}" for s in log))


def chat_with_fallback(messages, tools=None, order=None, pinned=None, **kw) -> Reply:
    """Text/agent calls. `pinned=(provider, model)` keeps one model for a whole conversation;
    `order` restricts to providers (e.g. ('groq',)); default is the 'text' chain."""
    if pinned:
        return chat(messages, tools, provider=pinned[0], model=pinned[1], **kw)
    if order:
        steps = [s for s in chain("text") if s["provider"] in order] or                 [{"provider": p, "model": model_for(p)} for p in order if available().get(p)]
        errors = []
        for s in steps:
            try:
                return chat(messages, tools, provider=s["provider"], model=s["model"], **kw)
            except (LLMError, httpx.HTTPError) as e:
                errors.append(str(e)[:200])
        raise LLMError("all providers failed: " + " | ".join(errors))
    reply, _ = run_chain("text", messages, tools, **kw)
    return reply
