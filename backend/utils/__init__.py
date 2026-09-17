"""Shared backend utilities."""

import re

_SECRET_VALUE = re.compile(
    r"(?i)(\b(?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|token|client[_-]?secret|password|authorization[_-]?code|code|state|cookie|session)\b\s*[:=]\s*)(?:Bearer\s+)?([^\s&,;]+)"
)
_BEARER_VALUE = re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+\-/=]+")


def redact_runtime_log_line(line: str) -> str:
    """Remove credential-shaped values before logs are exposed over HTTP."""
    line = _BEARER_VALUE.sub(r"\1[REDACTED]", line)
    return _SECRET_VALUE.sub(r"\1[REDACTED]", line)


from .runtime_logs import runtime_log_buffer  # noqa: E402,F401
