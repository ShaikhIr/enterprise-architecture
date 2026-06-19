"""
User request schemas (Pydantic v2).
"""

from pydantic import BaseModel, Field


class CreateUserRequest(BaseModel):
    """Request to create a new user."""

    username: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    is_validate_ad: bool = Field(default=True, description="If true, authenticate via Darwin AD")


class UpdateUserRequest(BaseModel):
    """Request to update user properties."""

    is_active: bool | None = None
    is_blocked: bool | None = None
    is_validate_ad: bool | None = None
