"""
Vendor-Customer Mapping request schemas (Pydantic v2).

These thin DTOs carry the raw request payload to ``MappingService``. Business
rules (Vendor/Customer existence, From ≤ To, inclusive overlap) live in the
service so they produce ``MasterValidationError`` / ``MasterConflictError``
(mapped to HTTP 422 / 409 by the controller).

Per Requirement 14.6 an update changes **only** the validity dates, so
``UpdateMappingRequest`` exposes just those two fields. It relies on Pydantic's
``model_fields_set`` so the controller can distinguish "field omitted" (leave
unchanged) from a supplied value.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domain.enums.masters import MappingStatus


class CreateMappingRequest(BaseModel):
    """Payload for creating a Vendor-Customer Mapping (Requirement 14)."""

    model_config = ConfigDict(extra="forbid")

    vendor_id: UUID = Field(..., description="Referenced Vendor ID")
    customer_id: UUID = Field(..., description="Referenced Customer ID")
    validity_from: date = Field(..., description="Validity start date (inclusive)")
    validity_to: date = Field(..., description="Validity end date (inclusive)")
    status: MappingStatus | None = Field(
        default=None, description="Defaults to Active when omitted"
    )


class UpdateMappingRequest(BaseModel):
    """Dates-only partial-update payload for a Mapping (Req 14.6).

    Only the validity dates may change; Vendor, Customer, and Status are left
    unchanged by the service. Omitted fields stay unchanged.
    """

    model_config = ConfigDict(extra="forbid")

    validity_from: date | None = Field(default=None)
    validity_to: date | None = Field(default=None)
