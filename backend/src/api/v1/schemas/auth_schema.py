"""
Authentication request and response schemas (Pydantic v2).
"""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Login request payload."""

    username: str = Field(..., min_length=3, max_length=255, description="Username")
    password: str = Field(..., min_length=1, description="Password")


class MicrosoftCallbackRequest(BaseModel):
    """What the SPA forwards from Microsoft's redirect back to the app."""

    code: str = Field(..., min_length=1, max_length=4096, description="Authorization code")
    state: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description="The `state` Microsoft returned; must equal the one issued at sign-in start",
    )


class TokenResponse(BaseModel):
    """
    Authentication token response.

    The refresh token is delivered via an HttpOnly cookie (not in the body),
    so it is never exposed to client-side JavaScript. The field is kept
    optional for backward compatibility but is not populated by default.
    """

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str | None = Field(
        default=None,
        description="Deprecated: refresh token is now set as an HttpOnly cookie",
    )
    token_type: str = Field(default="Bearer", description="Token type")
    expires_in: int = Field(..., description="Access token expiry in seconds")


class ErrorResponse(BaseModel):
    """Standard error response (`detail` is the canonical field; `message` mirrors it)."""

    detail: str = Field(..., description="Error message")
    success: bool = Field(default=False)
    message: str = Field(..., description="Same text as `detail`, kept for older clients")
    correlation_id: str = Field(default="", description="Request correlation ID")
