"""
Authentication API endpoints.
Handles login, logout, token refresh, and Microsoft SSO operations.
Thin controller — delegates all business logic to AuthService.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_auth_manager, get_current_active_user, get_user_repository
from src.api.v1.schemas.auth_schema import (
    LoginRequest,
    RefreshRequest,
    TokenResponse,
)
from src.application.services.auth_service import AuthService
from src.common.decorators.log_execution import log_execution
from src.domain.entities.user import User
from src.domain.repositories.user_repository import IUserRepository
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.auth_manager import (
    AuthManager,
    AuthenticationError,
    InvalidCredentialsError,
    UserBlockedError,
    UserInactiveError,
)
from src.infrastructure.security.jwt_provider import JWTProvider

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ─── Dependency Factory ───


def _get_auth_service(
    session: AsyncSession = Depends(get_db_session),
    user_repo: IUserRepository = Depends(get_user_repository),
    auth_manager: AuthManager = Depends(get_auth_manager),
) -> AuthService:
    return AuthService(
        session=session,
        user_repo=user_repo,
        auth_manager=auth_manager,
        jwt_provider=JWTProvider(),
    )


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


# ─── Endpoints ───


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
    http_request: Request,
    service: AuthService = Depends(_get_auth_service),
) -> TokenResponse:
    """POST /api/v1/auth/login"""
    try:
        result = await service.login(
            username=request.username,
            password=request.password,
            ip_address=_get_client_ip(http_request),
            user_agent=http_request.headers.get("user-agent", ""),
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
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Logout user",
    description="Logs the logout event in audit trail.",
)
async def logout(
    http_request: Request,
    current_user: User = Depends(get_current_active_user),
    service: AuthService = Depends(_get_auth_service),
) -> dict:
    """POST /api/v1/auth/logout"""
    await service.logout(
        current_user=current_user,
        ip_address=_get_client_ip(http_request),
        user_agent=http_request.headers.get("user-agent", ""),
    )
    return {"detail": "Logged out successfully"}


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
    service: AuthService = Depends(_get_auth_service),
) -> TokenResponse:
    """POST /api/v1/auth/refresh"""
    try:
        result = await service.refresh(refresh_token=request.refresh_token)
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
    """GET /api/v1/auth/me"""
    return {
        "id": str(current_user.id),
        "username": current_user.username,
        "is_active": current_user.is_active,
    }


# ─── Microsoft OAuth2 / Azure AD SSO ───


@router.get(
    "/microsoft/login",
    summary="Get Microsoft SSO login URL",
    description="Returns the Azure AD authorization URL for browser redirect.",
)
async def microsoft_login(
    service: AuthService = Depends(_get_auth_service),
) -> dict:
    """GET /api/v1/auth/microsoft/login"""
    try:
        return await service.microsoft_login_url()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(e))


@router.post(
    "/microsoft/callback",
    response_model=TokenResponse,
    summary="Exchange Microsoft auth code for tokens",
    description="Exchanges Azure AD authorization code for application JWT pair.",
)
@log_execution
async def microsoft_callback(
    body: dict,
    service: AuthService = Depends(_get_auth_service),
) -> TokenResponse:
    """POST /api/v1/auth/microsoft/callback"""
    code = (body.get("code") or "").strip()

    try:
        result = await service.microsoft_callback(code)
    except ValueError as e:
        detail = str(e)
        if "not configured" in detail:
            raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=detail)
        elif "inactive" in detail or "blocked" in detail or "No account found" in detail:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
        elif "Could not reach" in detail:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    return TokenResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        token_type=result.token_type,
        expires_in=result.expires_in,
    )
