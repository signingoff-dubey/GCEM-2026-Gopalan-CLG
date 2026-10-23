"""AI endpoints: grounded Q&A agent and one-click investigation."""
from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from backend.ai import agent, llm, orchestrator

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/topics")
def topics():
    """What the assistant can be pointed at: the line analysis and each saved model or multi-part scan."""
    from backend.ai import topic
    return {"topics": topic.topics()}


@router.get("/status")
def status():
    return {"providers": llm.available(), "models": {p: llm.model_for(p) for p in llm.PROVIDERS},
            "chains": {t: llm.chain(t) for t in ("text", "vision")},
            "keys": {p: len(llm.keys_for(p)) for p in llm.PROVIDERS}}


class AskRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=2000)
    provider: str | None = Field(None, pattern="^(groq|gemini|openrouter)$")
    history: list[dict] = Field(default_factory=list, description="prior turns: {role, content}")
    topic: str | None = Field(None, max_length=40, description="a saved model or scan id the conversation is about")


@router.post("/ask")
async def ask(req: AskRequest):
    try:
        return await run_in_threadpool(agent.ask, req.question, req.provider, agent.history_from(req.history), req.topic)
    except llm.LLMError as e:
        raise HTTPException(502, str(e))


class InvestigateRequest(BaseModel):
    provider: str | None = Field(None, pattern="^(groq|gemini|openrouter)$")
    volume_per_day: float = Field(1000, gt=0)
    scrap_cost_per_part: float = Field(500, gt=0)


@router.post("/investigate")
async def investigate(req: InvestigateRequest):
    try:
        return await run_in_threadpool(orchestrator.investigate, req.provider, req.volume_per_day,
                                       req.scrap_cost_per_part)
    except llm.LLMError as e:
        raise HTTPException(502, str(e))


class VoiceRequest(BaseModel):
    question: str | None = Field(None, max_length=1000)
    caller: str | None = None


@router.post("/voice")
async def voice(req: VoiceRequest | None = None, question: str | None = Query(None, max_length=1000)):
    """HTTP tool for the Sarvam phone agent: a spoken answer about any date, month or the analysis.
    Read-only like /api/ai/ask (same public analysis data), so the phone agent needs no secret."""
    from backend.ai import voice as v
    q = (question or (req.question if req else None) or "").strip()   # Sarvam may send it as a query param or JSON body
    if not q:
        raise HTTPException(422, "question is required")
    return await run_in_threadpool(v.answer, q)
