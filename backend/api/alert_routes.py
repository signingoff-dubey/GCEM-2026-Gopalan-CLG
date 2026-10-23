"""Defect alerts (call / WhatsApp / email) and the Blender MCP link, both shown in Settings."""
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from backend.alerts import service as alerts
from backend.integrations import blender_mcp

router = APIRouter(prefix="/api", tags=["alerts"])


class TestReq(BaseModel):
    channel: str | None = None


class ToggleReq(BaseModel):
    enabled: bool


class FocusReq(BaseModel):
    name: str


@router.get("/alerts")
def alert_status():
    return alerts.status()


@router.put("/alerts/settings")
def alert_settings(patch: dict):
    return alerts.update_settings(patch)


@router.post("/alerts/test")
async def alert_test(req: TestReq):
    if req.channel not in (None, *alerts.CHANNELS):
        raise HTTPException(400, f"channel must be one of {alerts.CHANNELS}")
    return {"results": await run_in_threadpool(alerts.test_alert, req.channel)}


class CallReq(BaseModel):
    id: str


@router.post("/alerts/call")
async def alert_call(req: CallReq):
    """Phone the current inspection's report to the alert number now (Inspection page, Place call)."""
    try:
        return await run_in_threadpool(alerts.report_call, req.id)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/alerts/view-damage")
async def alert_view_damage(req: CallReq):
    """View damage pressed on a model: alert once per model with its damage and suggested fixes."""
    try:
        return await run_in_threadpool(alerts.view_damage, req.id)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/alerts/calls/{cid}")
def alert_call_status(cid: str):
    """Dialing until Sarvam reports the outcome: connected (with duration and transcript), no_answer, busy, failed."""
    row = alerts.get_call(cid)
    if row is None:
        raise HTTPException(404, "call not found")
    return row


@router.post("/alerts/call-webhook")
def alert_call_webhook(payload: dict):
    """Sarvam posts here when a call attempt ends."""
    try:
        row = alerts.call_ended(payload)
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    return {"ok": row is not None}


@router.post("/alerts/check")
async def alert_check():
    return {"sent": await run_in_threadpool(alerts.check_once)}


@router.get("/integrations/blender")
async def blender_status():
    return await run_in_threadpool(blender_mcp.status)


@router.put("/integrations/blender")
async def blender_toggle(req: ToggleReq):
    blender_mcp.set_enabled(req.enabled)
    return await run_in_threadpool(blender_mcp.status)


@router.post("/integrations/blender/focus")
async def blender_focus(req: FocusReq):
    try:
        return await run_in_threadpool(blender_mcp.focus, req.name)
    except blender_mcp.BlenderOffline as e:
        raise HTTPException(503, str(e)) from e
