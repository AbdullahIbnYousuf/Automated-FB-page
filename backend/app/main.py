"""FastAPI application entry point for hosted post and dry-run workflows."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.facebook import router as facebook_router
from app.api.health import router as health_router
from app.api.media import router as media_router
from app.api.posts import router as posts_router
from app.api.system import router as system_router
from app.config import get_settings
from app.database import initialize_database
from app.logging_config import configure_logging
from app.services.errors import AppError


settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if settings.application_mode.lower() in {"production", "hosted"}:
        if not settings.auth_required or not settings.supabase_configured:
            raise RuntimeError(
                "Hosted mode requires Supabase Auth and Storage configuration."
            )
    initialize_database()
    logger.info(
        "Application started",
        extra={
            "event": "application_started",
            "application_mode": settings.application_mode,
            "publish_mode": settings.publish_mode.value,
            "automation_enabled": settings.automation_enabled,
        },
    )
    yield
    logger.info("Application stopped", extra={"event": "application_stopped"})


app = FastAPI(
    title=settings.application_name,
    version="0.5.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_frontend_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Accept", "Authorization", "Content-Type"],
)


@app.exception_handler(AppError)
async def handle_app_error(_: Request, error: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"error": {"code": error.code, "message": error.message}},
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    _: Request,
    error: RequestValidationError,
) -> JSONResponse:
    del error
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "The request contains invalid or missing fields.",
            }
        },
    )


@app.middleware("http")
async def log_request(request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
    started_at = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "Request failed",
            extra={
                "event": "http_request_failed",
                "method": request.method,
                "path": request.url.path,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            },
        )
        raise

    logger.info(
        "Request completed",
        extra={
            "event": "http_request",
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round((perf_counter() - started_at) * 1000, 2),
        },
    )
    return response


app.include_router(health_router)
app.include_router(system_router)
app.include_router(facebook_router)
app.include_router(posts_router)
app.include_router(media_router)
