"""
Atlas v0.19 — Async Agent Service API
======================================
Chapter 19: FastAPI wrapper for the Atlas agent with sync, streaming,
and async (Celery) endpoints.

Usage:
    uvicorn api:app --host 0.0.0.0 --port 8000 --reload

Endpoints:
    POST /agent/run      — Synchronous (waits for result)
    POST /agent/stream   — Server-Sent Events stream
    POST /agent/async    — Enqueues task, returns task_id
    GET  /agent/status/{task_id} — Check async task status

Requires: pip install fastapi uvicorn anthropic celery redis
"""

import json
import uuid

import anthropic
from celery import Celery
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.config import ANTHROPIC_MODEL  # also loads .env


# ── App and clients ───────────────────────────────────────────────────

app    = FastAPI(title="Atlas Agent API", version="0.19")
client = anthropic.Anthropic()

celery_app = Celery(
    "atlas",
    broker="redis://redis:6379/0",
    backend="redis://redis:6379/1",
)

# ── Request/response models ───────────────────────────────────────────

class AgentRequest(BaseModel):
    message:     str
    session_id:  str  = "default"
    webhook_url: str | None = None

class AgentResponse(BaseModel):
    answer:       str
    tools_used:   list[str]
    input_tokens:  int
    output_tokens: int

class AsyncTaskResponse(BaseModel):
    task_id: str
    status:  str

# ── Core agent logic ──────────────────────────────────────────────────

ATLAS_SYSTEM = (
    "You are Atlas, a research assistant. Answer concisely and accurately. "
    "When you cite sources, include the URL."
)

def _run_atlas(message: str) -> dict:
    """Run Atlas synchronously. Returns result dict."""
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        system=ATLAS_SYSTEM,
        messages=[{"role": "user", "content": message}],
        max_tokens=1024,
    )
    return {
        "answer":        response.content[0].text,
        "tools_used":    [],  # Extend with tool_use blocks when tools are added
        "input_tokens":  response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }


# ── Endpoints ─────────────────────────────────────────────────────────

@app.post("/agent/run", response_model=AgentResponse)
async def run_agent(request: AgentRequest):
    """Synchronous: waits for the full response before returning."""
    try:
        result = _run_atlas(request.message)
        return AgentResponse(**result)
    except anthropic.APIError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/agent/stream")
async def stream_agent(request: AgentRequest):
    """Server-Sent Events: streams tokens as they are generated."""
    async def event_stream():
        with client.messages.stream(
            model=ANTHROPIC_MODEL,
            system=ATLAS_SYSTEM,
            messages=[{"role": "user", "content": request.message}],
            max_tokens=1024,
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'type': 'delta', 'text': text})}\n\n"

            final = stream.get_final_message()
            yield f"data: {json.dumps({'type': 'done', 'usage': {'input': final.usage.input_tokens, 'output': final.usage.output_tokens}})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/agent/async", response_model=AsyncTaskResponse)
async def async_agent(request: AgentRequest):
    """Enqueue a long-running task. Returns task_id for polling."""
    task = process_agent_task.delay({
        "message":     request.message,
        "session_id":  request.session_id,
        "task_id":     str(uuid.uuid4()),
        "webhook_url": request.webhook_url,
    })
    return AsyncTaskResponse(task_id=task.id, status="queued")


@app.get("/agent/status/{task_id}")
async def get_task_status(task_id: str):
    """Poll for async task result."""
    task = process_agent_task.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status":  task.status,
        "result":  task.result if task.ready() else None,
    }


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.19"}


# ── Celery task ───────────────────────────────────────────────────────

@celery_app.task(bind=True, max_retries=3)
def process_agent_task(self, task_data: dict):
    """Async agent task with exponential backoff retry."""
    import requests
    try:
        result = _run_atlas(task_data["message"])

        if task_data.get("webhook_url"):
            requests.post(task_data["webhook_url"], json=result, timeout=10)

        return result

    except Exception as e:
        raise self.retry(exc=e, countdown=2 ** self.request.retries)
