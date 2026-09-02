"""
Pydantic schemas for the State master API.
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class StateCreate(BaseModel):
    """Create a new state."""

    code: str = Field(..., min_length=2, max_length=20, examples=["IN-MH"])
    name: str = Field(..., min_length=1, max_length=255, examples=["Maharashtra"])
    country_id: int = Field(..., description="Owning country")
    is_union_territory: bool = Field(default=False)
    is_active: bool = Field(default=True)

    @field_validator("code")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("name")
    @classmethod
    def _trim(cls, value: str) -> str:
        return value.strip()


class StateUpdate(BaseModel):
    """Update an existing state. Only supplied fields are changed."""

    code: str | None = Field(default=None, min_length=2, max_length=20)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    country_id: int | None = Field(default=None)
    is_union_territory: bool | None = Field(default=None)
    is_active: bool | None = Field(default=None)

    @field_validator("code")
    @classmethod
    def _upper(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value

    @field_validator("name")
    @classmethod
    def _trim(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class StateResponse(BaseModel):
    """State read response."""

    id: int
    code: str
    name: str
    country_id: int
    is_union_territory: bool
    is_active: bool
    created_by: str
    created_date: datetime
    modified_by: str
    modified_date: datetime

    model_config = {"from_attributes": True}


class StateListResponse(BaseModel):
    """Paginated list of states."""

    states: list[StateResponse]
    total: int
    skip: int
    limit: int
