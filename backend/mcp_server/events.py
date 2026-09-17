"""In-memory pub/sub for speaking-pill SSE broadcasts.

MCP ``voicebox.speak`` calls and the REST ``POST /speak`` route publish
start/end events that DictateWindow subscribes to via /events/speak, so the
floating pill surfaces whenever an agent is speaking.
"""

import asyncio
from collections import deque
from typing import Any


# Each subscriber gets its own queue. Bounded to drop oldest if a client lags.
_subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

# Small replay buffer for transports that cannot carry SSE (for example,
# Cloudflare Quick Tunnels). Sequence numbers are process-local and monotonic.
_event_sequence = 0
_recent_events: deque[dict[str, Any]] = deque(maxlen=128)


def subscribe() -> asyncio.Queue[dict[str, Any]]:
    """Register a new subscriber; caller must call unsubscribe() when done."""
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
    _subscribers.add(queue)
    return queue


def unsubscribe(queue: asyncio.Queue[dict[str, Any]]) -> None:
    _subscribers.discard(queue)


def poll_snapshot(after: int | None) -> dict[str, Any]:
    """Return events newer than *after*, or only the current cursor for a baseline."""
    cursor = _event_sequence
    if after is None:
        return {"cursor": cursor, "events": []}
    return {
        "cursor": cursor,
        "events": [dict(event) for event in _recent_events if event["sequence"] > after],
    }


def publish(kind: str, payload: dict[str, Any]) -> None:
    """Fan out to subscribers and retain a bounded sequenced replay buffer."""
    global _event_sequence
    _event_sequence += 1
    recorded = {"sequence": _event_sequence, "kind": kind, **payload}
    _recent_events.append(recorded)

    for queue in list(_subscribers):
        event = {"kind": kind, **payload}
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            # Slow subscriber — skip rather than block publishers.
            pass
