"""
User request schemas (Pydantic v2).
"""

from pydantic import BaseModel, Field


class CreateUserRequest(BaseModel):
    """Request to create a new user."""

    username: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(default="USER", pattern="^(ADMIN|MANAGER|USER)$")


class UpdateUserRequest(BaseModel):
    """Request to update user properties."""

    is_active: bool | None = None
    is_blocked: bool | None = None
    role: str | None = Field(default=None, pattern="^(ADMIN|MANAGER|USER)$")
