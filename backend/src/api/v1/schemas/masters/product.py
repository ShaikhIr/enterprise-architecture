"""
Pydantic v2 request/response schemas for Product Master.

The former two-level hierarchy (ProductMaster + ProductDetail) has been
collapsed into a single entity. These schemas serve the merged
``/product-masters`` endpoints.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.domain.entities.masters.product import ProductMasterEntity
from src.domain.enums.masters import ProductStatus


class ProductMasterCreateRequest(BaseModel):
    """Request body for creating a Product Master."""

    basic_material_code: str
    product_name: str
    child_code: str
    variant_description: str | None = None
    hsn_code: str | None = None
    pack_size: str | None = None
    unit_of_measure: str | None = None
    mrp: Decimal | None = None
    rate: Decimal | None = None
    gst_percent: Decimal | None = None
    status: ProductStatus | None = None


class ProductMasterUpdateRequest(BaseModel):
    """Request body for partially updating a Product Master.

    Every field is optional. Only fields present in ``model_fields_set``
    are applied; the rest are left unchanged.
    """

    basic_material_code: str | None = None
    product_name: str | None = None
    child_code: str | None = None
    variant_description: str | None = None
    hsn_code: str | None = None
    pack_size: str | None = None
    unit_of_measure: str | None = None
    mrp: Decimal | None = None
    rate: Decimal | None = None
    gst_percent: Decimal | None = None
    status: ProductStatus | None = None


class ProductMasterResponse(BaseModel):
    """Response body representing a Product Master."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    basic_material_code: str
    product_name: str
    child_code: str
    variant_description: str | None
    hsn_code: str | None
    pack_size: str | None
    unit_of_measure: str | None
    mrp: Decimal | None
    rate: Decimal | None
    gst_percent: Decimal | None
    status: ProductStatus
    created_by: str
    created_date: datetime
    modified_by: str
    modified_date: datetime

    @classmethod
    def from_entity(cls, entity: ProductMasterEntity) -> "ProductMasterResponse":
        """Build a response from a domain :class:`ProductMasterEntity`."""
        return cls.model_validate(entity)
