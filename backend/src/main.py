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
from src.observability.structured_logger import configure_logging, get_logger


def log_login_throttle_configuration() -> None:
    """
    Say at startup how login throttling is set up, and warn about the one setting that
    silently changes what it means.

    Behind a reverse proxy the API sees the proxy's address as the client, so with
    TRUSTED_PROXY_HOPS left at 0 every user shares one per-IP budget. COOKIE_SECURE is the
    existing "this is a real deployment" switch, so it is what the warning keys on.
    """
    log = get_logger("login_throttle")
    if not settings.LOGIN_THROTTLE_ENABLED:
        log.warning(
            "login_throttle_disabled",
            detail="LOGIN_THROTTLE_ENABLED is false: login is not protected against guessing",
        )
        return
    log.info(
        "login_throttle_configured",
        window_seconds=settings.LOGIN_ATTEMPT_WINDOW_SECONDS,
        max_attempts_per_account_ip=settings.LOGIN_MAX_ATTEMPTS_PER_ACCOUNT_IP,
        max_attempts_per_account=settings.LOGIN_MAX_ATTEMPTS_PER_ACCOUNT,
        max_failures_per_ip=settings.LOGIN_MAX_FAILURES_PER_IP,
        lockout_seconds=settings.LOGIN_LOCKOUT_SECONDS,
        familiar_ip_ttl_seconds=settings.LOGIN_FAMILIAR_IP_TTL_SECONDS,
        trusted_proxy_hops=settings.TRUSTED_PROXY_HOPS,
        shared_store="redis" if settings.REDIS_URL else "none (per-process counters)",
    )
    if settings.TRUSTED_PROXY_HOPS == 0 and settings.COOKIE_SECURE:
        log.warning(
            "login_throttle_proxy_hops_unset",
            detail=(
                "TRUSTED_PROXY_HOPS is 0, so X-Forwarded-For is ignored. If the API runs "
                "behind a reverse proxy, every user shares the proxy's address and the "
                "per-IP limit applies to all of them together. Set it to the number of "
                "proxies in front of the API."
            ),
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    # Startup
    configure_logging()
    configure_file_logging()
    log_login_throttle_configuration()

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
    # Not CORS-safelisted, so a cross-origin browser client cannot read it otherwise. The
    # login page uses it to say how long to wait after a 429.
    expose_headers=["Retry-After"],
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
