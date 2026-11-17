"""
Authentication API endpoints.
Handles login, logout, and token refresh operations.
Captures audit trail for all authentication events.
"""

from typing import Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from src.api.v1.dependencies import (
    get_audit_service,
    get_azure_sso_client,
    get_client_ip,
    get_current_active_user,
    get_login_service,
    get_session_authenticator,
)
from src.api.v1.schemas.auth_schema import (
    LoginRequest,
    MicrosoftCallbackRequest,
    TokenResponse,
)
from src.application.exceptions.auth_exceptions import AuthenticationError
from src.application.ports.session_authenticator import AuthTokenResponse, ISessionAuthenticator
from src.application.ports.sso_client import ISsoClient
from src.application.services.login_service import (
    LoginRejected,
    LoginService,
    LoginThrottled,
)
from src.common.decorators.log_execution import log_execution
from src.config.settings import settings
from src.domain.entities.user import User
from src.infrastructure.external.azure_sso import (
    AzureAuthError,
    AzureTokenMissingError,
    AzureUnavailableError,
    SsoTransaction,
)
from src.infrastructure.security.audit_service import AuditService
from src.observability.structured_logger import get_logger

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = get_logger(__name__)

# One message for every throttled attempt, whichever limit refused it and whether or not the
# account exists, so the response reveals nothing about either.
THROTTLED_DETAIL = "Too many login attempts. Please try again later."

SSO_NOT_CONFIGURED_DETAIL = "Microsoft SSO is not configured on this server"
SSO_SESSION_INVALID_DETAIL = (
    "Microsoft sign-in session is invalid or has expired. Please try again."
)


def _refused(
    status_code: int, detail: str, *, retry_after: int | None = None
) -> JSONResponse:
    """
    An error response for the auth endpoints, returned rather than raised.

    Raising HTTPException makes `get_db_session` roll the request back, which would discard
    whatever was written a moment earlier: the audit row of a failed login, or the revocation
    of a session whose refresh token was replayed. Returning the response lets the session
    commit. The body and status are what HTTPException produced, so clients see no difference.
    """
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
    return JSONResponse(status_code=status_code, content={"detail": detail}, headers=headers)


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


def _clear_cookie(response: Response, name: str) -> None:
    """Remove a cookie set by the auth endpoints."""
    response.delete_cookie(
        key=name,
        path=settings.REFRESH_COOKIE_PATH,
        domain=settings.COOKIE_DOMAIN or None,
    )


def _clear_cookie_headers(name: str) -> dict[str, str]:
    """
    Build the ``Set-Cookie`` header that clears a cookie, for attaching to an exception.

    Raising an ``HTTPException`` discards any mutation already made to the ``Response``
    object injected via ``Depends()``: FastAPI builds a brand-new response from
    ``HTTPException.headers`` only, so a prior ``response.delete_cookie(...)`` never reaches
    the client once the handler raises instead of returning.
    """
    scratch = Response()
    _clear_cookie(scratch, name)
    return {"set-cookie": scratch.headers["set-cookie"]}


def _session_response(response: Response, tokens: AuthTokenResponse) -> TokenResponse:
    """
    The success body, with the refresh token delivered as an HttpOnly cookie.

    `tokens.refresh_token` is None when the caller's token was spent a moment ago by another
    tab; that tab's response already carries the successor cookie, so none is set here.
    """
    if tokens.refresh_token is not None:
        _set_refresh_cookie(response, tokens.refresh_token)
    return TokenResponse(
        access_token=tokens.access_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
    )


def _session_ended(status_code: int, detail: str) -> JSONResponse:
    """An error response that also tells the browser to drop its refresh cookie."""
    refused = _refused(status_code, detail)
    _clear_cookie(refused, settings.REFRESH_COOKIE_NAME)
    return refused


@router.post(
    "/login",
    response_model=TokenResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user",
    description=(
        "Validate credentials and set the refresh cookie; returns the access token. "
        "Repeated failures are throttled per account and per client IP: once a limit is "
        "reached the endpoint answers 429 without checking the password, and `Retry-After` "
        "says how many seconds to wait."
    ),
    responses={
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Too many attempts. Wait `Retry-After` seconds before retrying.",
            "headers": {
                "Retry-After": {
                    "description": "Seconds until another attempt is accepted.",
                    "schema": {"type": "integer"},
                }
            },
        }
    },
)
@log_execution
async def login(
    request: LoginRequest,
    http_request: Request,
    response: Response,
    service: LoginService = Depends(get_login_service),
    client_ip: str = Depends(get_client_ip),
) -> TokenResponse | JSONResponse:
    """POST /api/v1/auth/login — Throttles, authenticates and logs the event."""
    result = await service.login(
        request.username,
        request.password,
        client_ip=client_ip,
        user_agent=http_request.headers.get("user-agent", ""),
    )
    if isinstance(result, LoginThrottled):
        return _refused(
            status.HTTP_429_TOO_MANY_REQUESTS,
            THROTTLED_DETAIL,
            retry_after=result.retry_after_seconds,
        )
    if isinstance(result, LoginRejected):
        return _refused(result.status_code, result.message)
    return _session_response(response, result.tokens)


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Logout user",
    description=(
        "Ends the session (revokes its refresh token) and logs the event in the audit trail."
    ),
)
async def logout(
    http_request: Request,
    response: Response,
    client_ip: str = Depends(get_client_ip),
    refresh_token: str | None = Cookie(default=None, alias=settings.REFRESH_COOKIE_NAME),
    current_user: User = Depends(get_current_active_user),
    authenticator: ISessionAuthenticator = Depends(get_session_authenticator),
    audit: AuditService = Depends(get_audit_service),
) -> dict[str, Any]:
    """POST /api/v1/auth/logout — Revokes the session, records it and clears the cookie."""
    if refresh_token:
        await authenticator.revoke_session(refresh_token)

    await audit.log(
        actor_id=current_user.id,
        actor_username=current_user.username,
        action="LOGOUT",
        resource_type="Authentication",
        resource_id=current_user.username,
        ip_address=client_ip,
        user_agent=http_request.headers.get("user-agent", ""),
    )

    _clear_cookie(response, settings.REFRESH_COOKIE_NAME)

    return {"detail": "Logged out successfully"}


@router.post(
    "/refresh",
    response_model=TokenResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
    description=(
        "Exchange the refresh cookie for a new access token. The refresh token is single-use: "
        "the response sets a new cookie, and presenting a spent one ends the session."
    ),
)
@log_execution
async def refresh_token(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=settings.REFRESH_COOKIE_NAME),
    authenticator: ISessionAuthenticator = Depends(get_session_authenticator),
) -> TokenResponse | JSONResponse:
    """
    POST /api/v1/auth/refresh

    Reads the refresh token from the HttpOnly cookie, spends it, and issues a new access token
    and a new refresh cookie. Used both for silent re-auth on access-token expiry and for the
    SPA's session bootstrap on page load / new tab.

    Errors (the unusable cookie is cleared so the client stops retrying with it):
        401: Missing, invalid, expired, revoked or already-spent refresh token
        403: User blocked or inactive

    Failures are returned, not raised: revoking a session whose token was replayed must be
    committed, and raising would roll it back.
    """
    if not refresh_token:
        return _session_ended(status.HTTP_401_UNAUTHORIZED, "Missing refresh token")

    try:
        tokens = await authenticator.refresh(refresh_token)
    except AuthenticationError as e:
        return _session_ended(e.status_code, e.message)

    return _session_response(response, tokens)


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
    description=(
        "Returns the Azure AD authorization URL for browser redirect, and binds the sign-in "
        "to this browser with a short-lived HttpOnly cookie (OAuth `state` and PKCE verifier)."
    ),
)
async def microsoft_login(
    response: Response,
    client: ISsoClient = Depends(get_azure_sso_client),
) -> dict[str, Any]:
    """
    GET /api/v1/auth/microsoft/login

    Returns the Azure AD OAuth2 authorization URL.
    Frontend should redirect the browser to the returned auth_url.
    Returns 501 if Azure SSO is not configured.
    """
    if not client.is_configured:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=SSO_NOT_CONFIGURED_DETAIL,
        )

    transaction = SsoTransaction.start()
    auth_url, redirect_uri = client.build_authorization_url(
        state=transaction.state, code_challenge=transaction.code_challenge
    )
    response.set_cookie(
        key=settings.SSO_TXN_COOKIE_NAME,
        value=transaction.to_cookie_value(),
        max_age=settings.SSO_TXN_TTL_SECONDS,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path=settings.REFRESH_COOKIE_PATH,
        domain=settings.COOKIE_DOMAIN or None,
    )
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
    body: MicrosoftCallbackRequest,
    response: Response,
    sso_txn: str | None = Cookie(default=None, alias=settings.SSO_TXN_COOKIE_NAME),
    authenticator: ISessionAuthenticator = Depends(get_session_authenticator),
    client: ISsoClient = Depends(get_azure_sso_client),
) -> TokenResponse:
    """
    POST /api/v1/auth/microsoft/callback

    Flow:
    1. Check `state` against the one issued when this browser started the sign-in
    2. Exchange code (with the PKCE verifier) for a Microsoft access_token via AzureSsoClient
    3. Fetch Graph profile (UPN, email)
    4. Delegate to the authenticator's microsoft_login — verifies the Microsoft email
       against the employee profile imported from AD and issues the JWT pair
    5. Set the refresh cookie and return the access token

    Errors:
        400: State missing or mismatched, exchange failure, or Microsoft account has no email
        403: User account is inactive/blocked, or not imported from AD
        501: Azure SSO not configured
        502: Microsoft authentication service unreachable
    """
    if not client.is_configured:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=SSO_NOT_CONFIGURED_DETAIL,
        )

    # A callback that this browser did not start (no cookie, or a different state) is a forged
    # or replayed redirect. Nothing is exchanged and no Microsoft call is made.
    transaction = SsoTransaction.from_cookie_value(sso_txn)
    if transaction is None or not transaction.matches_state(body.state):
        logger.warning("microsoft_callback_state_mismatch", has_cookie=sso_txn is not None)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=SSO_SESSION_INVALID_DETAIL,
            headers=_clear_cookie_headers(settings.SSO_TXN_COOKIE_NAME),
        )

    # Exchange code for Microsoft tokens + Graph profile
    try:
        ms_user = await client.exchange_code_for_profile(body.code, transaction.code_verifier)
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

    # Verify the Microsoft email against an AD-imported profile and issue tokens
    try:
        tokens = await authenticator.microsoft_login(ms_user)
    except AuthenticationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    _clear_cookie(response, settings.SSO_TXN_COOKIE_NAME)
    return _session_response(response, tokens)
