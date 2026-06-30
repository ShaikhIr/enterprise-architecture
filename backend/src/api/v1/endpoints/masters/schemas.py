"""Pydantic schemas for Master Data endpoints."""

from uuid import UUID
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================
# PRODUCT TYPE MASTER
# ============================================================

class ProductTypeCreateRequest(BaseModel):
    product_type_name: str = Field(..., min_length=1, max_length=100)


class ProductTypeUpdateRequest(BaseModel):
    product_type_name: Optional[str] = Field(None, min_length=1, max_length=100)
    is_active: Optional[bool] = None


class ProductTypeResponse(BaseModel):
    id: UUID
    product_type_name: str
    is_active: bool

    model_config = {"from_attributes": True}


# ============================================================
# PACK STYLE MASTER
# ============================================================

class PackStyleCreateRequest(BaseModel):
    pack_style: str = Field(..., min_length=1, max_length=100)


class PackStyleUpdateRequest(BaseModel):
    pack_style: Optional[str] = Field(None, min_length=1, max_length=100)
    is_active: Optional[bool] = None


class PackStyleResponse(BaseModel):
    id: UUID
    pack_style: str
    is_active: bool

    model_config = {"from_attributes": True}


# ============================================================
# TYPE OF PALLET MASTER
# ============================================================

class PalletCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    length: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    gross_weight_per_pack_type: Optional[int] = None
    volumetric_weight: Optional[int] = None


class PalletUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    length: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    gross_weight_per_pack_type: Optional[int] = None
    volumetric_weight: Optional[int] = None
    is_active: Optional[bool] = None


class PalletResponse(BaseModel):
    id: UUID
    name: str
    length: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    gross_weight_per_pack_type: Optional[int] = None
    volumetric_weight: Optional[int] = None
    is_active: bool

    model_config = {"from_attributes": True}


# ============================================================
# BRAND MASTER
# ============================================================

class BrandCreateRequest(BaseModel):
    brand_name: str = Field(..., min_length=1, max_length=100)


class BrandUpdateRequest(BaseModel):
    brand_name: Optional[str] = Field(None, min_length=1, max_length=100)
    is_active: Optional[bool] = None


class BrandResponse(BaseModel):
    id: UUID
    brand_name: str
    is_active: bool

    model_config = {"from_attributes": True}


# ============================================================
# DOSAGE MASTER
# ============================================================

class DosageCreateRequest(BaseModel):
    dosage: str = Field(..., min_length=1, max_length=100)


class DosageUpdateRequest(BaseModel):
    dosage: Optional[str] = Field(None, min_length=1, max_length=100)
    is_active: Optional[bool] = None


class DosageResponse(BaseModel):
    id: UUID
    dosage: str
    is_active: bool

    model_config = {"from_attributes": True}


# ============================================================
# MODE OF SHIPMENT MASTER
# ============================================================

class ModeOfShipmentCreateRequest(BaseModel):
    mode_name: str = Field(..., min_length=1, max_length=100)


class ModeOfShipmentUpdateRequest(BaseModel):
    mode_name: Optional[str] = Field(None, min_length=1, max_length=100)
    is_active: Optional[bool] = None


class ModeOfShipmentResponse(BaseModel):
    id: UUID
    mode_name: str
    is_active: bool

    model_config = {"from_attributes": True}


# ============================================================
# THERAPEUTIC CATEGORY MASTER
# ============================================================

class TherapeuticCategoryCreateRequest(BaseModel):
    therapeutic_category_name: str = Field(..., min_length=1, max_length=100)


class TherapeuticCategoryUpdateRequest(BaseModel):
    therapeutic_category_name: Optional[str] = Field(None, min_length=1, max_length=100)
    is_active: Optional[bool] = None


class TherapeuticCategoryResponse(BaseModel):
    id: UUID
    therapeutic_category_name: str
    is_active: bool

    model_config = {"from_attributes": True}
