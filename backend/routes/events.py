"""Server-Sent-Event streams the frontend subscribes to.

``GET /events/speak`` — broadcasts ``speak-start`` / ``speak-end`` events
whenever an agent-initiated speak (MCP tool or POST /speak) runs. The
DictateWindow uses them to show the floating pill in a `speaking` state.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from ..mcp_server import events as mcp_events


logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/events/speak/poll")
async def poll_speak_events(after: int | None = None, timeout: float = 10.0):
    """Bounded long-poll fallback for transports that buffer SSE."""
    timeout = max(0.0, min(timeout, 12.0))
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout

    while True:
        snapshot = mcp_events.poll_snapshot(after)
        if after is None or snapshot["events"] or loop.time() >= deadline:
            return snapshot
        await asyncio.sleep(0.2)


@router.get("/events/speak")
async def speak_events(request: Request):
    """SSE stream of speak-start / speak-end events."""

    async def event_stream():
        queue = mcp_events.subscribe()
        try:
            # Immediate hello so EventSource knows the connection is live.
            yield {"event": "ready", "data": "{}"}
            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except TimeoutError:
                    # Heartbeat so proxies don't reap idle streams.
                    yield {"event": "ping", "data": "{}"}
                    continue
                kind = event.pop("kind", "message")
                yield {"event": kind, "data": json.dumps(event)}
        finally:
            mcp_events.unsubscribe(queue)

    return EventSourceResponse(event_stream())
