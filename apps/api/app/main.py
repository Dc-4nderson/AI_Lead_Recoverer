"""FastAPI application factory (§2).

Wires middleware, structured logging, domain-exception handling, the event-bus
subscriber registration, and the versioned API router.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import bind_log_context, configure_logging
from app.events.handlers import register_all_handlers
from app.shared.exceptions import DomainError

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    # Wire every event-bus subscriber once, at startup (§16).
    register_all_handlers()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Lead Recovery Platform API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if not settings.is_production else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        bind_log_context(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
