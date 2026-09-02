"""
Pydantic schemas for the Legislation master API.
"""

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator


class LegislationCreate(BaseModel):
    """Create a new legislation."""

    code: str = Field(..., min_length=2, max_length=50, examples=["IN-FACT-1948"])
    name: str = Field(
        ..., min_length=1, max_length=500, examples=["The Factories Act, 1948"]
    )
    description: str = Field(default="")
    category_of_law_id: int = Field(..., description="Category this legislation falls under")
    country_id: int = Field(..., description="Owning country")
    state_id: int | None = Field(
        default=None,
        description="Owning state. Leave empty for central (country-wide) legislation.",
    )
    legislation_number: str | None = Field(
        default=None, max_length=100, examples=["Act No. 63 of 1948"]
    )
    effective_date: date | None = Field(default=None)
    is_active: bool = Field(default=True)

    @field_validator("code")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("name")
    @classmethod
    def _trim(cls, value: str) -> str:
        return value.strip()


class LegislationUpdate(BaseModel):
    """Update an existing legislation. Only supplied fields are changed."""

    code: str | None = Field(default=None, min_length=2, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None)
    category_of_law_id: int | None = Field(default=None)
    country_id: int | None = Field(default=None)
    state_id: int | None = Field(default=None)
    legislation_number: str | None = Field(default=None, max_length=100)
    effective_date: date | None = Field(default=None)
    is_active: bool | None = Field(default=None)

    @field_validator("code")
    @classmethod
    def _upper(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value

    @field_validator("name")
    @classmethod
    def _trim(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class LegislationResponse(BaseModel):
    """Legislation read response."""

    id: int
    code: str
    name: str
    description: str
    category_of_law_id: int
    country_id: int
    state_id: int | None
    legislation_number: str | None
    effective_date: date | None
    is_active: bool
    created_by: str
    created_date: datetime
    modified_by: str
    modified_date: datetime

    model_config = {"from_attributes": True}


class LegislationListResponse(BaseModel):
    """Paginated list of legislations."""

    legislations: list[LegislationResponse]
    total: int
    skip: int
    limit: int
