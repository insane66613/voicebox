"""Read-only sanitized runtime log diagnostics."""

from fastapi import APIRouter, Query

from ..utils import runtime_log_buffer

router = APIRouter()


@router.get("/logs/runtime")
async def runtime_logs(
    after: int | None = Query(default=None, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
):
    """Return sanitized log records newer than the supplied cursor."""
    return runtime_log_buffer.snapshot(after=after, limit=limit)
