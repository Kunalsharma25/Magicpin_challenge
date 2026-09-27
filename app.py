from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from models import (
    ContextPushRequest, ContextPushResponse,
    TickRequest, TickResponse,
    ReplyRequest, ReplyResponse,
    HealthzResponse, MetadataResponse
)
from store import store

app = FastAPI(title="magicpin AI Challenge Bot", version="1.0.0")

@app.get("/v1/healthz", response_model=HealthzResponse)
async def healthz():
    return HealthzResponse(status="ok")

@app.get("/v1/metadata", response_model=MetadataResponse)
async def metadata():
    return MetadataResponse(team_name="Vera-Beater", model="gpt-4o-mini")

@app.post("/v1/context", response_model=ContextPushResponse)
async def push_context(req: ContextPushRequest):
    accepted, err_msg, status_code = store.push_context(
        scope=req.scope,
        context_id=req.context_id,
        version=req.version,
        payload=req.payload
    )
    if not accepted:
        return JSONResponse(
            status_code=status_code,
            content={"accepted": False, "error": err_msg}
        )
    return ContextPushResponse(accepted=True)

from engagement.scheduler import schedule_tick

@app.post("/v1/tick", response_model=TickResponse)
async def tick(req: TickRequest):
    actions = schedule_tick(req.available_triggers, req.now)
    return TickResponse(actions=actions)

from conversation.respond import handle_reply

@app.post("/v1/reply", response_model=ReplyResponse)
async def reply(req: ReplyRequest):
    return handle_reply(req)

from engagement.suppression import suppression_manager
from engagement.cadence import cadence_manager

@app.post("/v1/teardown")
async def teardown():
    store.wipe()
    suppression_manager.clear()
    cadence_manager.reset_tick()
    return {"status": "cleared"}
