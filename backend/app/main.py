"""FastAPI application factory."""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import errors, logging_setup
from app.api import admin, auth, exports, health, jobs, orgs, projects, records
from app.config import get_settings

log = logging.getLogger("webdata.http")


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.env != "test":
        logging_setup.configure()
    if settings.env == "production" and settings.secret_key.lower().startswith("change-me"):
        raise RuntimeError("Set WEBDATA_SECRET_KEY to a long random value")
    app = FastAPI(title="WebData AI", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    errors.install(app)
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                           allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                           allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key"])

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("X-Request-ID", "")[:64] or uuid.uuid4().hex
        if not rid.replace("-", "").isalnum():
            rid = uuid.uuid4().hex
        request.state.request_id = rid
        token = logging_setup.request_id.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            logging_setup.request_id.reset(token)
        response.headers["X-Request-ID"] = rid
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        # Path only: query strings can carry download tokens.
        log.info("%s %s %s %.0fms", request.method, request.url.path, response.status_code,
                 (time.perf_counter() - start) * 1000)
        return response

    app.include_router(health.router)
    for module in (auth, orgs, projects, jobs, records, exports, admin):
        app.include_router(module.router, prefix="/api/v1")
    return app


app = create_app()
