"""
Pydantic schemas for the Country master API.
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class CountryCreate(BaseModel):
    """Create a new country."""

    code: str = Field(..., min_length=2, max_length=10, examples=["IN"])
    name: str = Field(..., min_length=1, max_length=255, examples=["India"])
    iso3_code: str | None = Field(default=None, max_length=10, examples=["IND"])
    dial_code: str | None = Field(default=None, max_length=10, examples=["+91"])
    currency_code: str | None = Field(default=None, max_length=10, examples=["INR"])
    is_active: bool = Field(default=True)

    @field_validator("code", "iso3_code", "currency_code")
    @classmethod
    def _upper(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value

    @field_validator("name")
    @classmethod
    def _trim(cls, value: str) -> str:
        return value.strip()


class CountryUpdate(BaseModel):
    """Update an existing country. Only supplied fields are changed."""

    code: str | None = Field(default=None, min_length=2, max_length=10)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    iso3_code: str | None = Field(default=None, max_length=10)
    dial_code: str | None = Field(default=None, max_length=10)
    currency_code: str | None = Field(default=None, max_length=10)
    is_active: bool | None = Field(default=None)

    @field_validator("code", "iso3_code", "currency_code")
    @classmethod
    def _upper(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value

    @field_validator("name")
    @classmethod
    def _trim(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class CountryResponse(BaseModel):
    """Country read response."""

    id: int
    code: str
    name: str
    iso3_code: str | None
    dial_code: str | None
    currency_code: str | None
    is_active: bool
    created_by: str
    created_date: datetime
    modified_by: str
    modified_date: datetime

    model_config = {"from_attributes": True}


class CountryListResponse(BaseModel):
    """Paginated list of countries."""

    countries: list[CountryResponse]
    total: int
    skip: int
    limit: int
