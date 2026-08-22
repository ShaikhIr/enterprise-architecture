"""
Global exception handler middleware.
Catches unhandled exceptions, logs them with correlation ID and stack trace,
and returns a standardized error response.
"""

import traceback

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from src.domain.exceptions.domain_exceptions import (
    BusinessRuleViolationError,
    DomainError,
    DuplicateEntityError,
    EntityNotFoundError,
)
from src.infrastructure.security.auth_manager import (
    AuthenticationError,
)
from src.observability.correlation import get_correlation_id
from src.observability.structured_logger import get_logger

logger = get_logger("exception_handler")

# Domain failures carry no HTTP status of their own — choosing one is a
# transport concern, so the mapping lives here at the API boundary.
DOMAIN_ERROR_STATUS: dict[type[DomainError], int] = {
    EntityNotFoundError: status.HTTP_404_NOT_FOUND,
    DuplicateEntityError: status.HTTP_409_CONFLICT,
    BusinessRuleViolationError: status.HTTP_409_CONFLICT,
}
DEFAULT_DOMAIN_ERROR_STATUS = status.HTTP_400_BAD_REQUEST


class ExceptionHandlerMiddleware(BaseHTTPMiddleware):
    """Catches and handles all unhandled exceptions globally."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            return await call_next(request)
        except AuthenticationError as e:
            return self._handle_auth_error(request, e)
        except DomainError as e:
            return self._handle_domain_error(request, e)
        except Exception as e:
            return self._handle_unexpected_error(request, e)

    def _handle_domain_error(self, request: Request, error: DomainError) -> JSONResponse:
        """Handle expected business rule failures (not found, conflict, invalid)."""
        correlation_id = get_correlation_id()

        logger.info(
            "Domain rule rejected request",
            correlation_id=correlation_id,
            error_type=type(error).__name__,
            message=error.message,
            path=request.url.path,
            method=request.method,
        )

        return JSONResponse(
            status_code=DOMAIN_ERROR_STATUS.get(
                type(error), DEFAULT_DOMAIN_ERROR_STATUS
            ),
            content={
                "success": False,
                "message": error.message,
                "correlation_id": correlation_id,
            },
        )

    def _handle_auth_error(
        self, request: Request, error: AuthenticationError
    ) -> JSONResponse:
        """Handle known authentication/authorization errors."""
        correlation_id = get_correlation_id()

        logger.warning(
            "Authentication error",
            correlation_id=correlation_id,
            error_type=type(error).__name__,
            message=error.message,
            path=request.url.path,
            method=request.method,
        )

        # AuthenticationError carries its own status (401 vs 403), set by the
        # auth layer that raised it.
        return JSONResponse(
            status_code=error.status_code,
            content={
                "success": False,
                "message": error.message,
                "correlation_id": correlation_id,
            },
        )

    def _handle_unexpected_error(
        self, request: Request, error: Exception
    ) -> JSONResponse:
        """Handle unexpected/unhandled exceptions."""
        correlation_id = get_correlation_id()
        stack_trace = traceback.format_exc()

        logger.error(
            "Unhandled exception",
            correlation_id=correlation_id,
            error_type=type(error).__name__,
            error_message=str(error),
            stack_trace=stack_trace,
            request_path=request.url.path,
            request_method=request.method,
        )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "message": "Internal Server Error",
                "correlation_id": correlation_id,
            },
        )
