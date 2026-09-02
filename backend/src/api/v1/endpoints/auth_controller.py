"""
Authentication API endpoints.
Handles login, logout, and token refresh operations.
Captures audit trail for all authentication events.
"""

from typing import Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status

from src.api.v1.dependencies import (
    get_audit_service,
    get_auth_manager,
    get_current_active_user,
    get_user_repository,
)
from src.api.v1.schemas.auth_schema import (
    LoginRequest,
    TokenResponse,
)
from src.common.decorators.log_execution import log_execution
from src.config.settings import settings
from src.domain.entities.user import User
from src.domain.repositories.user_repository import IUserRepository
from src.infrastructure.security.audit_service import AuditService
from src.infrastructure.security.auth_manager import (
    AuthenticationError,
    AuthManager,
    InvalidCredentialsError,
    UserBlockedError,
    UserInactiveError,
)
from src.observability.structured_logger import get_logger

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = get_logger(__name__)


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """
    Store the refresh token in an HttpOnly cookie.

    HttpOnly prevents JavaScript (and thus XSS) from reading the token.
    The cookie is path-scoped to the auth endpoints so it is only ever
    transmitted where it is needed (refresh / logout).
    """
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path=settings.REFRESH_COOKIE_PATH,
        domain=settings.COOKIE_DOMAIN or None,
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Remove the refresh token cookie (used on logout)."""
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        path=settings.REFRESH_COOKIE_PATH,
        domain=settings.COOKIE_DOMAIN or None,
    )


def _refresh_cookie_clear_headers() -> dict[str, str]:
    """
    Build the ``Set-Cookie`` header that clears the refresh cookie.

    Raising an ``HTTPException`` discards any mutation already made to the
    ``Response`` object injected via ``Depends()``: FastAPI's exception
    handling builds a brand-new response from ``HTTPException.headers``
    only, so a prior ``response.delete_cookie(...)`` call on the injected
    ``Response`` never reaches the client once the handler raises instead
    of returning. Attaching the header to the exception itself is the only
    way to make the deletion take effect on an error response.
    """
    scratch = Response()
    scratch.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        path=settings.REFRESH_COOKIE_PATH,
        domain=settings.COOKIE_DOMAIN or None,
    )
    return {"set-cookie": scratch.headers["set-cookie"]}


@router.post(
    "/login",
    response_model=TokenResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user",
    description="Validate credentials and set the refresh cookie; returns the access token.",
)
@log_execution
async def login(
    request: LoginRequest,
    http_request: Request,
    response: Response,
    auth_manager: AuthManager = Depends(get_auth_manager),
    user_repo: IUserRepository = Depends(get_user_repository),
    audit: AuditService = Depends(get_audit_service),
) -> TokenResponse:
    """POST /api/v1/auth/login — Authenticates and logs the event."""
    ip = _get_client_ip(http_request)
    user_agent = http_request.headers.get("user-agent", "")

    try:
        result = await auth_manager.login(
            username=request.username,
            password=request.password,
        )
    except InvalidCredentialsError as e:
        await audit.log_login(
            user_id=None, username=request.username, success=False,
            ip_address=ip, user_agent=user_agent, reason="Invalid credentials",
        )
        raise HTTPException(status_code=e.status_code, detail=e.message) from e
    except UserInactiveError as e:
        await audit.log_login(
            user_id=None, username=request.username, success=False,
            ip_address=ip, user_agent=user_agent, reason="User inactive",
        )
        raise HTTPException(status_code=e.status_code, detail=e.message) from e
    except UserBlockedError as e:
        await audit.log_login(
            user_id=None, username=request.username, success=False,
            ip_address=ip, user_agent=user_agent, reason="User blocked",
        )
        raise HTTPException(status_code=e.status_code, detail=e.message) from e

    # Log successful login
    user = await user_repo.get_by_username(request.username)
    if user:
        await audit.log_login(
            user_id=user.id, username=user.username, success=True,
            ip_address=ip, user_agent=user_agent,
        )

    # Refresh token → HttpOnly cookie (never exposed to JS). Access token → body.
    _set_refresh_cookie(response, result.refresh_token)

    return TokenResponse(
        access_token=result.access_token,
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
    response: Response,
    current_user: User = Depends(get_current_active_user),
    audit: AuditService = Depends(get_audit_service),
) -> dict[str, Any]:
    """POST /api/v1/auth/logout — Records logout in audit trail and clears the refresh cookie."""
    ip = _get_client_ip(http_request)
    user_agent = http_request.headers.get("user-agent", "")

    await audit.log(
        actor_id=current_user.id,
        actor_username=current_user.username,
        action="LOGOUT",
        resource_type="Authentication",
        resource_id=current_user.username,
        ip_address=ip,
        user_agent=user_agent,
    )

    _clear_refresh_cookie(response)

    return {"detail": "Logged out successfully"}


@router.post(
    "/refresh",
    response_model=TokenResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
    description="Exchange the refresh cookie for a new access token.",
)
@log_execution
async def refresh_token(
    refresh_token: str | None = Cookie(default=None, alias=settings.REFRESH_COOKIE_NAME),
    auth_manager: AuthManager = Depends(get_auth_manager),
) -> TokenResponse:
    """
    POST /api/v1/auth/refresh

    Reads the refresh token from the HttpOnly cookie and issues a new access
    token. Used both for silent re-auth on access-token expiry and for the
    SPA's session bootstrap on page load / new tab.

    Errors:
        401: Missing, invalid, or expired refresh token
        403: User blocked or inactive
    """
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token",
        )

    try:
        result = await auth_manager.refresh(refresh_token=refresh_token)
    except AuthenticationError as e:
        # Token is unusable — clear the stale cookie so the client stops
        # retrying with it. Attached to the exception itself (see
        # `_refresh_cookie_clear_headers`) since this response never returns
        # normally.
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
            headers=_refresh_cookie_clear_headers(),
        ) from e

    return TokenResponse(
        access_token=result.access_token,
        token_type=result.token_type,
        expires_in=result.expires_in,
    )


@router.get(
    "/me",
    summary="Get current user info",
    description="Returns the authenticated user's profile (no password hash).",
)
async def get_me(current_user: User = Depends(get_current_active_user)) -> dict[str, Any]:
    """GET /api/v1/auth/me - Returns current user info."""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "is_active": current_user.is_active,
    }


# ─── Microsoft OAuth2 / Azure AD SSO ───


@router.get(
    "/microsoft/login",
    summary="Get Microsoft SSO login URL",
    description="Returns the Azure AD authorization URL for browser redirect.",
)
async def microsoft_login() -> dict[str, Any]:
    """
    GET /api/v1/auth/microsoft/login

    Returns the Azure AD OAuth2 authorization URL.
    Frontend should redirect the browser to the returned auth_url.
    Returns 501 if Azure SSO is not configured.
    """
    from src.infrastructure.external.azure_sso import AzureSsoClient

    client = AzureSsoClient()
    if not client.is_configured:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Microsoft SSO is not configured on this server",
        )

    auth_url, redirect_uri = client.build_authorization_url()
    return {"auth_url": auth_url, "redirect_uri": redirect_uri}


@router.post(
    "/microsoft/callback",
    response_model=TokenResponse,
    response_model_exclude_none=True,
    summary="Exchange Microsoft auth code for tokens",
    description="Exchanges Azure AD authorization code for an access token + refresh cookie.",
)
@log_execution
async def microsoft_callback(
    body: dict[str, Any],
    response: Response,
    user_repo: IUserRepository = Depends(get_user_repository),
) -> TokenResponse:
    """
    POST /api/v1/auth/microsoft/callback

    Flow:
    1. Exchange code for Microsoft access_token via AzureSsoClient
    2. Fetch Graph profile (UPN, email, employeeId, name)
    3. Look up local user by username (email)
    4. If not found → auto-provision with is_active=True
    5. Issue app JWT pair
    6. Return token response

    Errors:
        400: Missing code or exchange failure
        403: User account is inactive/blocked
        501: Azure SSO not configured
    """
    import secrets

    from src.infrastructure.external.azure_sso import (
        AzureAuthError,
        AzureSsoClient,
        AzureTokenMissingError,
        AzureUnavailableError,
    )
    from src.infrastructure.security.jwt_provider import JWTProvider
    from src.infrastructure.security.password_encoder import hash_password

    client = AzureSsoClient()
    if not client.is_configured:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Microsoft SSO is not configured on this server",
        )

    code = (body.get("code") or "").strip()
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization code is required",
        )

    # Exchange code for Microsoft tokens + Graph profile
    try:
        ms_user = await client.exchange_code_for_profile(code)
    except AzureTokenMissingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to obtain access token from Microsoft",
        ) from exc
    except AzureAuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.detail) from exc
    except AzureUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach Microsoft authentication service",
        ) from exc

    # Extract user info from Graph profile
    upn = ms_user.get("userPrincipalName") or ms_user.get("mail") or ""
    email = (ms_user.get("mail") or upn or "").lower().strip()

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Microsoft account has no email — cannot map to a user",
        )

    # Find or create local user
    user = await user_repo.get_by_username(email)

    if user is None:
        # Auto-provision: create local user from Microsoft profile
        from src.domain.entities.user import User as UserEntity

        user = UserEntity(
            username=email,
            password_hash=hash_password(secrets.token_urlsafe(32)),
            is_active=True,
            is_blocked=False,
            created_by="microsoft_sso",
            modified_by="microsoft_sso",
        )
        user = await user_repo.create(user)

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )
    if user.is_blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is blocked",
        )

    # Issue application JWT pair
    jwt_provider = JWTProvider()
    access_token = jwt_provider.create_access_token(user.username, user.id)
    refresh_token = jwt_provider.create_refresh_token(user.username, user.id)

    _set_refresh_cookie(response, refresh_token)

    return TokenResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
