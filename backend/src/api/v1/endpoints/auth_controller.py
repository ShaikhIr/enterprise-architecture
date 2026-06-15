"""
Authentication API endpoints.
Handles login and token refresh operations.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.v1.dependencies import get_auth_manager, get_current_active_user
from src.api.v1.schemas.auth_schema import (
    LoginRequest,
    RefreshRequest,
    TokenResponse,
)
from src.common.decorators.log_execution import log_execution
from src.domain.entities.user import User
from src.infrastructure.security.auth_manager import (
    AuthManager,
    AuthenticationError,
    InvalidCredentialsError,
    UserBlockedError,
    UserInactiveError,
)
from src.observability.structured_logger import get_logger

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = get_logger(__name__)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user",
    description="Validate credentials and return JWT token pair.",
)
@log_execution
async def login(
    request: LoginRequest,
    auth_manager: AuthManager = Depends(get_auth_manager),
) -> TokenResponse:
    """
    POST /api/v1/auth/login

    Authenticates a user and returns access + refresh tokens.

    Errors:
        401: Invalid credentials
        403: User blocked or inactive
    """
    try:
        result = await auth_manager.login(
            username=request.username,
            password=request.password,
        )
    except InvalidCredentialsError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except UserInactiveError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except UserBlockedError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    return TokenResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        token_type=result.token_type,
        expires_in=result.expires_in,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
    description="Exchange a valid refresh token for a new access token.",
)
@log_execution
async def refresh_token(
    request: RefreshRequest,
    auth_manager: AuthManager = Depends(get_auth_manager),
) -> TokenResponse:
    """
    POST /api/v1/auth/refresh

    Validates refresh token and issues a new access token.

    Errors:
        401: Invalid or expired refresh token
        403: User blocked or inactive
    """
    try:
        result = await auth_manager.refresh(refresh_token=request.refresh_token)
    except AuthenticationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    return TokenResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        token_type=result.token_type,
        expires_in=result.expires_in,
    )


@router.get(
    "/me",
    summary="Get current user info",
    description="Returns the authenticated user's profile (no password hash).",
)
async def get_me(current_user: User = Depends(get_current_active_user)) -> dict:
    """GET /api/v1/auth/me - Returns current user info."""
    return {
        "id": str(current_user.id),
        "username": current_user.username,
        "role": current_user.role,
        "is_active": current_user.is_active,
    }
