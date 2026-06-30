"""Pydantic schemas for Freight Master data endpoints."""

from datetime import datetime
from uuid import UUID
from typing import Optional

from pydantic import BaseModel, Field, model_validator


# ─── Currency Conversion ───

class CurrencyConversionCreate(BaseModel):
    exrt: Optional[str] = None
    from_currency: str = Field(..., min_length=1, max_length=10)
    to_currency: str = Field(..., min_length=1, max_length=10)
    valid_from: Optional[str] = None
    exchange_rate: Optional[float] = None
    ratio_from: Optional[int] = None
    ratio_to: Optional[int] = None


class CurrencyConversionUpdate(BaseModel):
    exrt: Optional[str] = None
    from_currency: Optional[str] = None
    to_currency: Optional[str] = None
    valid_from: Optional[str] = None
    exchange_rate: Optional[float] = None
    ratio_from: Optional[int] = None
    ratio_to: Optional[int] = None
    is_active: Optional[bool] = None

    @model_validator(mode="before")
    @classmethod
    def clean_empty(cls, data: dict) -> dict:
        if isinstance(data, dict):
            return {k: (None if v == "" or v == "null" else v) for k, v in data.items()}
        return data


class CurrencyConversionResponse(BaseModel):
    id: UUID
    exrt: Optional[str] = None
    from_currency: str
    to_currency: str
    valid_from: Optional[str] = None
    exchange_rate: Optional[float] = None
    ratio_from: Optional[int] = None
    ratio_to: Optional[int] = None
    is_active: bool

    model_config = {"from_attributes": True}


# ─── Container Master ───

class ContainerCreate(BaseModel):
    container_type: str = Field(..., min_length=1, max_length=100)


class ContainerUpdate(BaseModel):
    container_type: Optional[str] = Field(default=None, max_length=100)
    is_active: Optional[bool] = None


class ContainerResponse(BaseModel):
    id: UUID
    container_type: str
    is_active: bool

    model_config = {"from_attributes": True}


# ─── Transit Day Master ───

class TransitDayCreate(BaseModel):
    country_name: str = Field(..., min_length=1, max_length=100)
    country_code: Optional[str] = Field(default=None, max_length=10)
    customer_clearance: Optional[int] = None
    transit_days_for_air: Optional[int] = None
    container_load_for_sea: Optional[int] = None
    test_days: Optional[int] = None


class TransitDayUpdate(BaseModel):
    country_name: Optional[str] = Field(default=None, max_length=100)
    country_code: Optional[str] = Field(default=None, max_length=10)
    customer_clearance: Optional[int] = None
    transit_days_for_air: Optional[int] = None
    container_load_for_sea: Optional[int] = None
    test_days: Optional[int] = None
    is_active: Optional[bool] = None

    @model_validator(mode="before")
    @classmethod
    def clean_empty(cls, data: dict) -> dict:
        if isinstance(data, dict):
            return {k: (None if v == "" or v == "null" else v) for k, v in data.items()}
        return data


class TransitDayResponse(BaseModel):
    id: UUID
    country_name: str
    country_code: Optional[str] = None
    customer_clearance: Optional[int] = None
    transit_days_for_air: Optional[int] = None
    container_load_for_sea: Optional[int] = None
    test_days: Optional[int] = None
    is_active: bool

    model_config = {"from_attributes": True}


# ─── Fixed Charges Master ───

class FixedChargesCreate(BaseModel):
    mode_of_shipment: Optional[str] = None
    pallet_name: Optional[str] = None
    document_charges: Optional[float] = None
    shrink_wrap_charges: Optional[float] = None
    unloading_charges: Optional[float] = None
    pallet_charges: Optional[float] = None
    data_logger_charges: Optional[float] = None
    blanket_charges: Optional[float] = None


class FixedChargesUpdate(BaseModel):
    mode_of_shipment: Optional[str] = None
    pallet_name: Optional[str] = None
    document_charges: Optional[float] = None
    shrink_wrap_charges: Optional[float] = None
    unloading_charges: Optional[float] = None
    pallet_charges: Optional[float] = None
    data_logger_charges: Optional[float] = None
    blanket_charges: Optional[float] = None
    is_active: Optional[bool] = None

    @model_validator(mode="before")
    @classmethod
    def clean_empty(cls, data: dict) -> dict:
        if isinstance(data, dict):
            return {k: (None if v == "" or v == "null" else v) for k, v in data.items()}
        return data


class FixedChargesResponse(BaseModel):
    id: UUID
    mode_of_shipment: Optional[str] = None
    pallet_name: Optional[str] = None
    document_charges: Optional[float] = None
    shrink_wrap_charges: Optional[float] = None
    unloading_charges: Optional[float] = None
    pallet_charges: Optional[float] = None
    data_logger_charges: Optional[float] = None
    blanket_charges: Optional[float] = None
    is_active: bool

    model_config = {"from_attributes": True}
