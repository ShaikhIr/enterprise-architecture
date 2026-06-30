"""Pydantic schemas for Master data endpoints."""

from uuid import UUID
from typing import Optional

from pydantic import BaseModel, Field, model_validator


# ─── Brand Master ───

class BrandCreate(BaseModel):
    brand_name: str = Field(..., min_length=1, max_length=100)

    @model_validator(mode="before")
    @classmethod
    def clean_empty(cls, data: dict) -> dict:
        if isinstance(data, dict):
            name = data.get("brand_name")
            if name is not None and isinstance(name, str):
                name = name.strip()
                if not name:
                    raise ValueError("brand_name must not be empty or whitespace-only")
                if len(name) > 100:
                    raise ValueError("brand_name must not exceed 100 characters")
                data["brand_name"] = name
        return data


class BrandUpdate(BaseModel):
    brand_name: Optional[str] = Field(default=None, max_length=100)
    is_active: Optional[bool] = None

    @model_validator(mode="before")
    @classmethod
    def clean_empty(cls, data: dict) -> dict:
        if isinstance(data, dict):
            name = data.get("brand_name")
            if name is not None and isinstance(name, str):
                stripped = name.strip()
                if not stripped:
                    raise ValueError("brand_name must not be empty or whitespace-only")
                if len(stripped) > 100:
                    raise ValueError("brand_name must not exceed 100 characters")
                data["brand_name"] = stripped
        return data


class BrandResponse(BaseModel):
    id: UUID
    brand_name: str
    is_active: bool

    model_config = {"from_attributes": True}


# ─── Dosage Master ───

class DosageCreate(BaseModel):
    dosage: str = Field(..., min_length=1, max_length=100)


class DosageUpdate(BaseModel):
    dosage: Optional[str] = Field(default=None, max_length=100)
    is_active: Optional[bool] = None


class DosageResponse(BaseModel):
    id: UUID
    dosage: str
    is_active: bool

    model_config = {"from_attributes": True}


# ─── Mode of Shipment Master ───

class ModeOfShipmentCreate(BaseModel):
    mode_name: str = Field(..., min_length=1, max_length=100)


class ModeOfShipmentUpdate(BaseModel):
    mode_name: Optional[str] = Field(default=None, max_length=100)
    is_active: Optional[bool] = None


class ModeOfShipmentResponse(BaseModel):
    id: UUID
    mode_name: str
    is_active: bool

    model_config = {"from_attributes": True}


# ─── Therapeutic Category Master ───

class TherapeuticCategoryCreate(BaseModel):
    therapeutic_category_name: str = Field(..., min_length=1, max_length=100)


class TherapeuticCategoryUpdate(BaseModel):
    therapeutic_category_name: Optional[str] = Field(default=None, max_length=100)
    is_active: Optional[bool] = None


class TherapeuticCategoryResponse(BaseModel):
    id: UUID
    therapeutic_category_name: str
    is_active: bool

    model_config = {"from_attributes": True}
