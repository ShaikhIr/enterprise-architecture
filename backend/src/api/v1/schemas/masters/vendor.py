"""
Vendor Master request/response schemas (Pydantic v2).

These are the API-boundary contracts for the Vendor controller. The
``VendorService`` is deliberately Pydantic-agnostic (it accepts
``VendorCreateInput`` / ``VendorUpdateInput`` dataclasses and returns
``VendorEntity``), so the controller is responsible for translating between
these schemas and the service's input/output types.

Heavy validation (required fields, email/GSTN format, uniqueness) lives in the
service and surfaces as typed master exceptions mapped to HTTP 422/409/404. The
request schemas keep only structural typing so the service remains the single
source of truth for business validation.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domain.entities.masters.vendor import VendorEntity
from src.domain.enums.masters import VendorStatus


class CreateVendorRequest(BaseModel):
    """Payload for creating a Vendor (Req 6.2–6.8)."""

    model_config = ConfigDict(str_strip_whitespace=False)

    vendor_code: str = Field(..., description="Unique business code for the vendor")
    vendor_name: str = Field(..., description="Vendor display name")
    vendor_email: str = Field(..., description="Unique vendor email address")
    vendor_contact: str | None = Field(default=None)
    vendor_address: str | None = Field(default=None)
    city: str | None = Field(default=None)
    gstn_number: str | None = Field(default=None)
    pan_number: str | None = Field(default=None)
    bank_account_no: str | None = Field(default=None)
    bank_ifsc: str | None = Field(default=None)
    bank_name: str | None = Field(default=None)


class UpdateVendorRequest(BaseModel):
    """Partial-update payload for a Vendor.

    Every field is optional; only fields explicitly supplied in the request are
    applied. A nullable field set to ``null`` explicitly clears that value,
    while an omitted field is left unchanged (the controller relies on Pydantic
    ``exclude_unset`` to make that distinction).
    """

    model_config = ConfigDict(str_strip_whitespace=False)

    vendor_code: str | None = Field(default=None)
    vendor_name: str | None = Field(default=None)
    vendor_email: str | None = Field(default=None)
    vendor_contact: str | None = Field(default=None)
    vendor_address: str | None = Field(default=None)
    city: str | None = Field(default=None)
    gstn_number: str | None = Field(default=None)
    pan_number: str | None = Field(default=None)
    bank_account_no: str | None = Field(default=None)
    bank_ifsc: str | None = Field(default=None)
    bank_name: str | None = Field(default=None)
    status: VendorStatus | None = Field(default=None, description="Active or Inactive")


class VendorResponse(BaseModel):
    """Vendor representation returned by the API."""

    id: UUID
    vendor_code: str
    vendor_name: str
    vendor_email: str
    vendor_contact: str | None = None
    vendor_address: str | None = None
    city: str | None = None
    gstn_number: str | None = None
    pan_number: str | None = None
    bank_account_no: str | None = None
    bank_ifsc: str | None = None
    bank_name: str | None = None
    portal_user_id: UUID | None = None
    status: VendorStatus
    created_by: str
    created_date: datetime
    modified_by: str
    modified_date: datetime

    @classmethod
    def from_entity(cls, vendor: VendorEntity) -> "VendorResponse":
        """Build a response DTO from a Vendor domain entity."""
        return cls(
            id=vendor.id,
            vendor_code=vendor.vendor_code,
            vendor_name=vendor.vendor_name,
            vendor_email=vendor.vendor_email,
            vendor_contact=vendor.vendor_contact,
            vendor_address=vendor.vendor_address,
            city=vendor.city,
            gstn_number=vendor.gstn_number,
            pan_number=vendor.pan_number,
            bank_account_no=vendor.bank_account_no,
            bank_ifsc=vendor.bank_ifsc,
            bank_name=vendor.bank_name,
            portal_user_id=vendor.portal_user_id,
            status=vendor.status,
            created_by=vendor.created_by,
            created_date=vendor.created_date,
            modified_by=vendor.modified_by,
            modified_date=vendor.modified_date,
        )
