"""Sanitized bounded runtime log buffer for the diagnostics API."""

from collections import deque
import logging
import threading

from . import redact_runtime_log_line


class RuntimeLogBuffer(logging.Handler):
    def __init__(self, capacity: int = 2000):
        super().__init__(level=logging.INFO)
        self._entries = deque(maxlen=capacity)
        self._cursor = 0
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = redact_runtime_log_line(record.getMessage())
        except Exception:
            return
        if "/logs/runtime" in line:
            return
        entry = {
            "timestamp": int(record.created * 1000),
            "stream": "stderr" if record.levelno >= logging.WARNING else "stdout",
            "line": line,
        }
        with self._lock:
            self._cursor += 1
            entry["cursor"] = self._cursor
            self._entries.append(entry)

    def snapshot(self, after: int | None = None, limit: int = 200) -> dict:
        limit = max(1, min(limit, 500))
        with self._lock:
            cursor = self._cursor
            entries = list(self._entries)
        if after is not None:
            entries = [entry for entry in entries if entry["cursor"] > after]
        return {"cursor": cursor, "entries": entries[-limit:]}


runtime_log_buffer = RuntimeLogBuffer()


def install_runtime_log_handler() -> None:
    """Attach once to application and Uvicorn logging trees."""
    targets = [logging.getLogger(), logging.getLogger("uvicorn.error"), logging.getLogger("uvicorn.access")]
    for target in targets:
        if runtime_log_buffer not in target.handlers:
            target.addHandler(runtime_log_buffer)


install_runtime_log_handler()
