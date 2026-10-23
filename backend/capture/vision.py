"""Read parameter values off a photo of a run sheet. The model only transcribes digits;
it never interprets or explains a parameter."""
import hashlib
import io
import json
import re

from PIL import Image, ImageOps

from backend.ai import llm
from backend.config import CAPTURES_DIR

PROMPT = """This image is a process run sheet with a table of PARAMETER and VALUE.
Transcribe it exactly. Return JSON only, in this shape:
{"run_id": "<run id text or null>", "values": {"<PARAMETER>": <number>, ...}, "unreadable": ["<PARAMETER>", ...]}
Rules: copy digits exactly, keep signs and decimals, no units, no rounding. If a value is blank, a dash,
or you cannot read it with confidence, put that parameter in "unreadable" instead of guessing.
Expected parameter ids (use these exact keys): {fields}"""


def prepare(image_bytes: bytes, max_side=1600) -> bytes:
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _parse(text: str) -> dict | None:
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        j = json.loads(m.group())
    except json.JSONDecodeError:
        return None
    if not isinstance(j.get("values"), dict):
        return None
    vals = {}
    for k, v in j["values"].items():
        try:
            vals[str(k).strip()] = float(str(v).replace(",", "").strip())
        except (TypeError, ValueError):
            j.setdefault("unreadable", []).append(k)
    return {"run_id": j.get("run_id"), "values": vals,
            "unreadable": [str(u) for u in j.get("unreadable") or []]}


def cached(raw: bytes) -> dict | None:
    p = CAPTURES_DIR / "cache" / f"{hashlib.sha256(raw).hexdigest()}.json"
    return json.loads(p.read_text()) if p.exists() else None


def extract(raw: bytes, fields: list[str]) -> dict:
    """Run the vision chain. Returns {extracted, provider, model, chain_log}; extracted is None
    when every provider failed and nothing is cached (caller falls back to manual entry)."""
    img = prepare(raw)
    known = set(fields)
    messages = [{"role": "user", "content": PROMPT.replace("{fields}", ", ".join(fields)),
                 "images": [("image/jpeg", img)]}]

    def validate(reply):
        parsed = _parse(reply.content)
        if parsed is None:
            return "invalid JSON"
        if not set(parsed["values"]) & known:
            return "no expected parameters read"
        return None

    try:
        reply, log = llm.run_chain("vision", messages, json_mode=True, temperature=0.0)
        parsed = _parse(reply.content)
        parsed["values"] = {k: v for k, v in parsed["values"].items() if k in known}
        return {"extracted": parsed, "provider": reply.provider, "model": reply.model, "chain_log": log}
    except llm.LLMError as e:
        log = [{"provider": "chain", "model": None, "ok": False, "ms": 0, "error": str(e)[:300]}]
    hit = cached(raw)
    if hit:
        log.append({"provider": "cache", "model": None, "ok": True, "ms": 0, "error": None})
        return {"extracted": hit, "provider": "cache", "model": None, "chain_log": log}
    return {"extracted": None, "provider": None, "model": None, "chain_log": log}
