"""Runtime log API tests for local and remote Voicebox monitoring."""

import logging

from backend.app import app
import backend.utils as backend_utils


def test_runtime_log_redactor_masks_credentials():
    redactor = getattr(backend_utils, "redact_runtime_log_line", None)
    assert callable(redactor)
    sanitized = redactor("Authorization: Bearer example-secret token=abc123 password=hunter2")
    assert "example-secret" not in sanitized
    assert "abc123" not in sanitized
    assert "hunter2" not in sanitized
    assert "[REDACTED]" in sanitized


def test_runtime_log_redactor_masks_oauth_query_values():
    redactor = backend_utils.redact_runtime_log_line
    sanitized = redactor("https://example.test/callback?code=oauth-code&state=oauth-state")
    assert "oauth-code" not in sanitized
    assert "oauth-state" not in sanitized


def test_runtime_log_buffer_is_cursor_based_and_sanitized():
    handler = getattr(backend_utils, "runtime_log_buffer", None)
    assert handler is not None
    before = handler.snapshot(after=None, limit=1)["cursor"]
    record = logging.LogRecord("voicebox.test", logging.INFO, __file__, 1, "token=do-not-leak hello", (), None)
    handler.emit(record)
    payload = handler.snapshot(after=before, limit=10)
    assert payload["cursor"] > before
    assert payload["entries"][-1]["line"] == "token=[REDACTED] hello"


def test_runtime_log_route_is_registered():
    assert "/health" in app.openapi()["paths"]
    assert "/logs/runtime" in app.openapi()["paths"]


def test_runtime_log_handler_is_reinstalled_during_app_startup():
    source = (__import__('pathlib').Path(__file__).parents[1] / 'backend' / 'app.py').read_text()
    startup = source.split('async def _run_startup', 1)[1].split('async def _run_shutdown', 1)[0]
    assert 'install_runtime_log_handler()' in startup
