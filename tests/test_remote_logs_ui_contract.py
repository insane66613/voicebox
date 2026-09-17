"""Contract checks for remote runtime logs in the existing Logs tab."""

from pathlib import Path


def test_api_client_exposes_cursor_based_runtime_logs():
    text = Path("app/src/lib/api/client.ts").read_text(encoding="utf-8")
    assert "getRuntimeLogs" in text
    assert "/logs/runtime" in text


def test_logs_page_polls_remote_logs_without_sse():
    text = Path("app/src/components/ServerTab/LogsPage.tsx").read_text(encoding="utf-8")
    assert "getRuntimeLogs" in text
    assert "useServerStore" in text
    assert "mode !== 'remote'" in text
    assert "remoteLogCursor" in text
    assert "EventSource" not in text
