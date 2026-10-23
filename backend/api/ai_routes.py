"""AI endpoints: grounded Q&A agent and one-click investigation."""
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from backend.ai import agent, llm, orchestrator

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/status")
def status():
    return {"providers": llm.available(),
            "chains": {t: llm.chain(t) for t in ("text", "vision")},
            "keys": {p: len(llm.keys_for(p)) for p in llm.PROVIDERS}}


class AskRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=2000)
    provider: str | None = Field(None, pattern="^(groq|gemini|openrouter)$")
    history: list[dict] = Field(default_factory=list, description="prior turns: {role, content}")


@router.post("/ask")
async def ask(req: AskRequest):
    try:
        return await run_in_threadpool(agent.ask, req.question, req.provider, agent.history_from(req.history))
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
