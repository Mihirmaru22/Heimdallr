"""Liveness and readiness probes."""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import get_settings
from app.db import engine
from app.deps import current_user
from app.models import User
from app.version import report

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz() -> JSONResponse:
    checks: dict[str, str] = {}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {type(exc).__name__}"
    try:
        import redis

        redis.Redis.from_url(get_settings().redis_url, socket_timeout=2).ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {type(exc).__name__}"
    ok = all(v == "ok" for v in checks.values())
    return JSONResponse({"status": "ok" if ok else "degraded", "checks": checks}, status_code=200 if ok else 503)


@router.get("/api/v1/version")
def version(frontend: str | None = Query(None, max_length=64, pattern=r"^[0-9a-zA-Z._-]*$"),
            _user: User = Depends(current_user)) -> dict:
    """Which commit the API, workers and this page run, compared with the code checked out on disk."""
    return report(frontend)


@router.get("/api/v1/llm/status")
async def llm_status(_user: User = Depends(current_user)) -> dict:
    """The free-model allowance: key configured, requests used today, the free models available."""
    from app.llm.openrouter import OpenRouter

    router_ = OpenRouter()
    try:
        return await router_.status()
    finally:
        await router_.aclose()
