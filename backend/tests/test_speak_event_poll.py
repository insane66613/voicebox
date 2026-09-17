"""Tests for the HTTP-poll fallback used when SSE is transport-buffered."""

from backend.mcp_server import events


def _reset_bus(monkeypatch):
    monkeypatch.setattr(events, "_event_sequence", 0, raising=False)
    if hasattr(events, "_recent_events"):
        events._recent_events.clear()


def test_poll_snapshot_baselines_without_replaying_old_events(monkeypatch):
    assert hasattr(events, "poll_snapshot")
    _reset_bus(monkeypatch)
    events.publish("speak-start", {"text": "old"})

    snapshot = events.poll_snapshot(None)

    assert snapshot == {"cursor": 1, "events": []}


def test_poll_snapshot_returns_only_events_after_cursor(monkeypatch):
    assert hasattr(events, "poll_snapshot")
    _reset_bus(monkeypatch)
    events.publish("speak-start", {"text": "one"})
    events.publish("speak-end", {"text": "two"})

    snapshot = events.poll_snapshot(1)

    assert snapshot["cursor"] == 2
    assert snapshot["events"] == [{"sequence": 2, "kind": "speak-end", "text": "two"}]
