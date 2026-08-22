"""
Application settings using Pydantic BaseSettings.
Loads configuration from environment variables and .env files.
"""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Enterprise Architecture application configuration."""

    # Application
    APP_NAME: str = Field(
        default="Enterprise Architecture", description="Application name"
    )
    APP_VERSION: str = Field(default="1.0.0", description="Application version")
    DEBUG: bool = Field(default=False, description="Debug mode")

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/base-app-setup",
        description="Async database connection string",
    )
    DB_POOL_SIZE: int = Field(default=20, description="Database connection pool size")
    DB_MAX_OVERFLOW: int = Field(default=10, description="Max overflow connections")
    TEST_DATABASE_URL: str = Field(
        default="",
        description=(
            "Async connection string for the integration test database. "
            "When empty, tests derive it from DATABASE_URL by appending '_test' "
            "to the database name. The name must end with '_test' as a safety guard."
        ),
    )

    # JWT Authentication
    JWT_SECRET_KEY: str = Field(
        default="change-me-in-production-use-strong-secret",
        description="JWT signing secret key",
    )
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT algorithm")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30, description="Access token expiry in minutes"
    )
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(
        default=7, description="Refresh token expiry in days"
    )

    # File storage
    UPLOAD_DIR: str = Field(
        default="storage",
        description=(
            "Base directory for everything the application writes to disk. "
            "Relative LOG_FILE_PATH values are resolved beneath it (see the "
            "`log_file` property), and file uploads should be rooted here too "
            "once that feature exists. A relative value is taken from the "
            "process working directory."
        ),
    )

    # Logging
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    LOG_FILE_PATH: str = Field(
        default="logs/application.log",
        description=(
            "Log file path. Relative values are resolved beneath UPLOAD_DIR; "
            "an absolute value is used verbatim. Read it through the `log_file` "
            "property rather than directly."
        ),
    )
    LOG_MAX_BYTES: int = Field(
        default=10 * 1024 * 1024, description="Max log file size (10MB)"
    )
    LOG_BACKUP_COUNT: int = Field(default=10, description="Number of log backups")

    # Redis (Optional Cache)
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0", description="Redis connection URL"
    )

    # Celery
    CELERY_BROKER_URL: str = Field(
        default="redis://localhost:6379/1", description="Celery broker URL"
    )

    # OpenTelemetry
    OTEL_EXPORTER_ENDPOINT: str = Field(
        default="http://localhost:4317", description="OpenTelemetry exporter endpoint"
    )
    OTEL_SERVICE_NAME: str = Field(
        default="compliance-api", description="OpenTelemetry service name"
    )

    # Azure AD / Microsoft SSO
    AZURE_CLIENT_ID: str = Field(default="", description="Azure App Registration client ID")
    AZURE_CLIENT_SECRET: str = Field(default="", description="Azure App Registration client secret")
    AZURE_TENANT_ID: str = Field(default="", description="Azure AD tenant ID")
    AZURE_REDIRECT_URI: str = Field(
        default="http://localhost:6769/auth/microsoft/callback",
        description="OAuth2 redirect URI (must match Azure App Registration)",
    )

    # Employee AD (Darwin) Service
    EMPLOYEE_AD_BASE_URL: str = Field(
        default="https://ad-prod-darwinsvc-prod.apps.emart.oneemcure.local/adintegratorservices/rest/v1",
        description="Base URL for the Darwin AD integrator service",
    )



    # CORS
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:6769"], description="Allowed CORS origins"
    )

    # ─── Auth Cookies (refresh token) ───
    REFRESH_COOKIE_NAME: str = Field(
        default="refresh_token", description="Name of the HttpOnly refresh token cookie"
    )
    REFRESH_COOKIE_PATH: str = Field(
        default="/api/v1/auth",
        description="Path scope for the refresh cookie (only sent to auth endpoints)",
    )
    COOKIE_SECURE: bool = Field(
        default=False,
        description="Send cookies only over HTTPS. Set True in production.",
    )
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = Field(
        default="lax",
        description=(
            "SameSite policy for auth cookies. Typed as a literal so an invalid "
            "value in .env fails at startup instead of silently producing a "
            "malformed Set-Cookie header."
        ),
    )
    COOKIE_DOMAIN: str = Field(
        default="",
        description="Cookie domain. Empty means host-only (recommended for same-origin).",
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }

    # ─── Derived paths ───
    #
    # Exposed as properties rather than fields so there is a single place that
    # decides how UPLOAD_DIR and LOG_FILE_PATH combine. Callers should use these
    # instead of joining the raw strings themselves.

    @property
    def storage_root(self) -> Path:
        """UPLOAD_DIR as an absolute path. Not created here — writers do that."""
        return Path(self.UPLOAD_DIR).expanduser().resolve()

    @property
    def log_file(self) -> Path:
        """
        Absolute path of the application log file.

        A relative LOG_FILE_PATH lands beneath UPLOAD_DIR, so everything the app
        writes shares one configured root. An absolute LOG_FILE_PATH wins, which
        keeps container deployments that mount a dedicated log volume working
        without also having to move UPLOAD_DIR.
        """
        configured = Path(self.LOG_FILE_PATH).expanduser()
        if configured.is_absolute():
            return configured
        return self.storage_root / configured


# Singleton settings instance
settings = Settings()
