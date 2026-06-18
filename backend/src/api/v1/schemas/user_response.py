"""
User response schemas (Pydantic v2).
Never exposes password_hash.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class UserResponse(BaseModel):
    """User response - excludes sensitive fields."""

    id: UUID
    username: str
    is_active: bool
    is_blocked: bool
    is_validate_ad: bool
    role: str
    created_by: str
    created_date: datetime
    modified_by: str
    modified_date: datetime


class UserListResponse(BaseModel):
    """Paginated user list response."""

    users: list[UserResponse]
    total: int = Field(default=0)
    skip: int = Field(default=0)
    limit: int = Field(default=100)
