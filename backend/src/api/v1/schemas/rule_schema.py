"""
Pydantic schemas for the Rule master API.
"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class RuleCreate(BaseModel):
    """Create a new rule."""

    code: str = Field(..., min_length=2, max_length=50, examples=["IN-FACT-1948-R5"])
    name: str = Field(
        ..., min_length=1, max_length=500, examples=["Maintenance of health register"]
    )
    description: str = Field(default="")
    legislation_id: UUID = Field(..., description="Parent legislation")
    country_id: UUID = Field(..., description="Owning country")
    state_id: UUID | None = Field(
        default=None,
        description="Owning state. Leave empty for central (country-wide) rules.",
    )
    rule_number: str | None = Field(default=None, max_length=100, examples=["Rule 5(2)"])
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


class RuleUpdate(BaseModel):
    """Update an existing rule. Only supplied fields are changed."""

    code: str | None = Field(default=None, min_length=2, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None)
    legislation_id: UUID | None = Field(default=None)
    country_id: UUID | None = Field(default=None)
    state_id: UUID | None = Field(default=None)
    rule_number: str | None = Field(default=None, max_length=100)
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


class RuleResponse(BaseModel):
    """Rule read response."""

    id: UUID
    code: str
    name: str
    description: str
    legislation_id: UUID
    country_id: UUID
    state_id: UUID | None
    rule_number: str | None
    effective_date: date | None
    is_active: bool
    created_by: str
    created_date: datetime
    modified_by: str
    modified_date: datetime

    model_config = {"from_attributes": True}


class RuleListResponse(BaseModel):
    """Paginated list of rules."""

    rules: list[RuleResponse]
    total: int
    skip: int
    limit: int
