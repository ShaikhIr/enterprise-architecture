"""
Pydantic schemas for the Category of Law master API.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class CategoryOfLawCreate(BaseModel):
    """Create a new category of law."""

    code: str = Field(..., min_length=2, max_length=50, examples=["LABOUR"])
    name: str = Field(..., min_length=1, max_length=255, examples=["Labour Law"])
    description: str = Field(default="")
    state_id: UUID | None = Field(
        default=None,
        description="Owning state. Leave empty for a country-wide category.",
    )
    is_active: bool = Field(default=True)

    @field_validator("code")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("name")
    @classmethod
    def _trim(cls, value: str) -> str:
        return value.strip()


class CategoryOfLawUpdate(BaseModel):
    """Update an existing category of law. Only supplied fields are changed."""

    code: str | None = Field(default=None, min_length=2, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None)
    state_id: UUID | None = Field(default=None)
    is_active: bool | None = Field(default=None)

    @field_validator("code")
    @classmethod
    def _upper(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value

    @field_validator("name")
    @classmethod
    def _trim(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class CategoryOfLawResponse(BaseModel):
    """Category of law read response."""

    id: UUID
    code: str
    name: str
    description: str
    state_id: UUID | None
    is_active: bool
    created_by: str
    created_date: datetime
    modified_by: str
    modified_date: datetime

    model_config = {"from_attributes": True}


class CategoryOfLawListResponse(BaseModel):
    """Paginated list of categories of law."""

    categories_of_law: list[CategoryOfLawResponse]
    total: int
    skip: int
    limit: int
