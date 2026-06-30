"""Pydantic schemas for Freight Master endpoints."""

from uuid import UUID
from typing import Optional

from pydantic import BaseModel, Field, model_validator


# ============================================================
# SHARED — Rate response
# ============================================================

class RateResponse(BaseModel):
    """Common rate response for Air, Sea, and Local masters."""

    id: UUID
    rate: float
    valid_from: Optional[str] = None
    valid_till: Optional[str] = None
    is_active: bool

    model_config = {"from_attributes": True}


class RateCreateRequest(BaseModel):
    """Common rate creation request."""

    rate: float = Field(..., gt=0, description="Rate amount")
    valid_from: str = Field(..., description="ISO date string for validity start")
    valid_till: str = Field(..., description="ISO date string for validity end")


# ============================================================
# COUNTRY MASTER
# ============================================================

class CountryCreateRequest(BaseModel):
    country_name: str = Field(..., min_length=1, max_length=200)
    country_code: str = Field(..., min_length=1, max_length=10)


class CountryUpdateRequest(BaseModel):
    country_name: Optional[str] = Field(None, min_length=1, max_length=200)
    country_code: Optional[str] = Field(None, min_length=1, max_length=10)
    is_active: Optional[bool] = None


class CountryResponse(BaseModel):
    id: UUID
    country_name: str
    country_code: str
    is_active: bool

    model_config = {"from_attributes": True}


# ============================================================
# CITY MASTER
# ============================================================

class CityCreateRequest(BaseModel):
    city_name: str = Field(..., min_length=1, max_length=200)
    country_id: Optional[UUID] = None


class CityUpdateRequest(BaseModel):
    city_name: Optional[str] = Field(None, min_length=1, max_length=200)
    country_id: Optional[UUID] = None
    is_active: Optional[bool] = None


class CityResponse(BaseModel):
    id: UUID
    city_name: str
    country_id: Optional[UUID] = None
    is_active: bool

    model_config = {"from_attributes": True}


# ============================================================
# AIR MASTER (Freight Slab)
# ============================================================

class AirMasterCreateRequest(BaseModel):
    to_country_id: UUID
    product_type: Optional[str] = Field(None, max_length=100)
    min_slab: int = Field(..., ge=0)
    max_slab: int = Field(..., ge=0)


class AirMasterUpdateRequest(BaseModel):
    to_country_id: Optional[UUID] = None
    product_type: Optional[str] = Field(None, max_length=100)
    min_slab: Optional[int] = Field(None, ge=0)
    max_slab: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None

    @model_validator(mode="before")
    @classmethod
    def clean_empty(cls, data):
        if isinstance(data, dict):
            return {k: (None if v == "" or v == "null" else v) for k, v in data.items()}
        return data


class AirMasterResponse(BaseModel):
    id: UUID
    to_country_id: UUID
    country_code: Optional[str] = None
    country_name: Optional[str] = None
    product_type: Optional[str] = None
    min_slab: int
    max_slab: int
    slab_name: Optional[str] = None
    rates: list[RateResponse] = []
    is_active: bool

    model_config = {"from_attributes": True}


# ============================================================
# SEA MASTER
# ============================================================

class SeaMasterCreateRequest(BaseModel):
    to_country_id: UUID
    product_type: Optional[str] = Field(None, max_length=100)
    slab_name: Optional[str] = Field(None, max_length=100)
    currency: Optional[str] = Field(None, max_length=10)


class SeaMasterUpdateRequest(BaseModel):
    to_country_id: Optional[UUID] = None
    product_type: Optional[str] = Field(None, max_length=100)
    slab_name: Optional[str] = Field(None, max_length=100)
    currency: Optional[str] = Field(None, max_length=10)
    is_active: Optional[bool] = None

    @model_validator(mode="before")
    @classmethod
    def clean_empty(cls, data):
        if isinstance(data, dict):
            return {k: (None if v == "" or v == "null" else v) for k, v in data.items()}
        return data


class SeaMasterResponse(BaseModel):
    id: UUID
    to_country_id: UUID
    country_code: Optional[str] = None
    country_name: Optional[str] = None
    product_type: Optional[str] = None
    slab_name: Optional[str] = None
    currency: Optional[str] = None
    rates: list[RateResponse] = []
    is_active: bool

    model_config = {"from_attributes": True}


# ============================================================
# SEA CBM MASTER
# ============================================================

class SeaCbmCreateRequest(BaseModel):
    slab_name: Optional[str] = Field(None, max_length=100)
    from_cbm: int = Field(..., ge=0)
    to_cbm: int = Field(..., ge=0)
    type: Optional[str] = Field(None, max_length=100)
    total_count: Optional[int] = Field(None, ge=0)


class SeaCbmUpdateRequest(BaseModel):
    slab_name: Optional[str] = Field(None, max_length=100)
    from_cbm: Optional[int] = Field(None, ge=0)
    to_cbm: Optional[int] = Field(None, ge=0)
    type: Optional[str] = Field(None, max_length=100)
    total_count: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None

    @model_validator(mode="before")
    @classmethod
    def clean_empty(cls, data):
        if isinstance(data, dict):
            return {k: (None if v == "" or v == "null" else v) for k, v in data.items()}
        return data


class SeaCbmResponse(BaseModel):
    id: UUID
    slab_name: Optional[str] = None
    from_cbm: int
    to_cbm: int
    type: Optional[str] = None
    total_count: Optional[int] = None
    is_active: bool

    model_config = {"from_attributes": True}


# ============================================================
# VEHICLE TYPE MASTER
# ============================================================

class VehicleTypeCreateRequest(BaseModel):
    from_no_of_pallet_or_box: int = Field(..., ge=0)
    to_no_of_pallet_or_box: int = Field(..., ge=0)
    vehicle_type: str = Field(..., min_length=1, max_length=100)


class VehicleTypeUpdateRequest(BaseModel):
    from_no_of_pallet_or_box: Optional[int] = Field(None, ge=0)
    to_no_of_pallet_or_box: Optional[int] = Field(None, ge=0)
    vehicle_type: Optional[str] = Field(None, min_length=1, max_length=100)
    is_active: Optional[bool] = None

    @model_validator(mode="before")
    @classmethod
    def clean_empty(cls, data):
        if isinstance(data, dict):
            return {k: (None if v == "" or v == "null" else v) for k, v in data.items()}
        return data


class VehicleTypeResponse(BaseModel):
    id: UUID
    from_no_of_pallet_or_box: int
    to_no_of_pallet_or_box: int
    vehicle_type: str
    is_active: bool

    model_config = {"from_attributes": True}


# ============================================================
# LOCAL MASTER
# ============================================================

class LocalMasterCreateRequest(BaseModel):
    from_city_id: UUID
    to_city_id: UUID
    product_type: Optional[str] = Field(None, max_length=100)
    vehicle_type_id: Optional[UUID] = None
    min_slab: Optional[str] = Field(None, max_length=50)
    max_slab: Optional[str] = Field(None, max_length=50)


class LocalMasterUpdateRequest(BaseModel):
    from_city_id: Optional[UUID] = None
    to_city_id: Optional[UUID] = None
    product_type: Optional[str] = Field(None, max_length=100)
    vehicle_type_id: Optional[UUID] = None
    min_slab: Optional[str] = Field(None, max_length=50)
    max_slab: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None

    @model_validator(mode="before")
    @classmethod
    def clean_empty(cls, data):
        if isinstance(data, dict):
            return {k: (None if v == "" or v == "null" else v) for k, v in data.items()}
        return data


class LocalMasterResponse(BaseModel):
    id: UUID
    from_city_id: UUID
    from_city_name: Optional[str] = None
    to_city_id: UUID
    to_city_name: Optional[str] = None
    product_type: Optional[str] = None
    vehicle_type_id: Optional[UUID] = None
    vehicle_type_name: Optional[str] = None
    min_slab: Optional[str] = None
    max_slab: Optional[str] = None
    rates: list[RateResponse] = []
    is_active: bool

    model_config = {"from_attributes": True}
