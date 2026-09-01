"""
FastAPI application entry point.
Configures middleware, routers, CORS, and OpenAPI documentation.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from src.api.middleware.audit_context_middleware import AuditContextMiddleware
from src.api.middleware.correlation_id import CorrelationIdMiddleware
from src.api.middleware.exception_handler import ExceptionHandlerMiddleware
from src.api.middleware.request_logging import RequestLoggingMiddleware
from src.api.v1.router import api_v1_router
from src.config.dependency_injection import Container
from src.config.logging_config import configure_file_logging
from src.config.settings import settings
from src.observability.structured_logger import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    # Startup
    configure_logging()
    configure_file_logging()

    # Prove object storage is usable before traffic arrives, so a bucket typo or
    # an expired key stops deployment rather than surfacing as a 500 for whoever
    # uploads first. The probe is a cheap, read-only exists() call. The local
    # backend has nothing to reach, so it is skipped.
    if settings.STORAGE_BACKEND == "s3":
        if not settings.S3_BUCKET:
            raise RuntimeError("STORAGE_BACKEND=s3 requires S3_BUCKET to be set.")
        await Container.get_file_storage().exists("startup-probe")

    yield
    # Shutdown (cleanup resources here)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Enterprise Architecture API — enterprise-grade "
        "FastAPI with Clean Architecture"
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ─── OpenAPI Security Scheme (enables Swagger Authorize button) ───


def custom_openapi() -> dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    # Ensure the HTTPBearer scheme is defined (matches FastAPI's HTTPBearer dependency)
    if "components" not in openapi_schema:
        openapi_schema["components"] = {}
    if "securitySchemes" not in openapi_schema["components"]:
        openapi_schema["components"]["securitySchemes"] = {}
    openapi_schema["components"]["securitySchemes"]["HTTPBearer"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "Enter your JWT access token",
    }
    # Apply globally so all endpoints show the lock
    openapi_schema["security"] = [{"HTTPBearer": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema


# Overriding the bound method is the documented way to customise FastAPI's
# schema; mypy flags method assignment, so the override is narrowly silenced.
app.openapi = custom_openapi  # type: ignore[method-assign]

# ─── Middleware (order matters: outermost first) ───
app.add_middleware(ExceptionHandlerMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(AuditContextMiddleware)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ───
app.include_router(api_v1_router)


@app.get("/", tags=["Root"])
async def root() -> dict[str, Any]:
    """Root endpoint - application info."""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
    }
