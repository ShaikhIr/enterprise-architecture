"""
Customer Master request schemas (Pydantic v2).

These thin DTOs carry the raw request payload to ``CustomerService``. Field
*content* validation (required/format/length/enum) is intentionally delegated to
the service so that all business rules live in one place and produce
``MasterValidationError`` (mapped to HTTP 422 by the controller).

Partial-update semantics: ``UpdateCustomerRequest`` relies on Pydantic's
``model_fields_set`` so the controller can distinguish "field omitted" (leave
unchanged) from "field explicitly set to null" (clear the value).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.domain.enums.masters import CustomerStatus


class CreateCustomerRequest(BaseModel):
    """Payload for creating a Customer (Requirement 8)."""

    model_config = ConfigDict(extra="forbid")

    customer_code: str = Field(..., description="Unique business Customer Code")
    customer_name: str = Field(..., description="Customer display name")
    address: str | None = Field(default=None)
    gstn_number: str | None = Field(
        default=None, description="15-character GSTN ([A-Z0-9]{15})"
    )
    contact_person: str | None = Field(default=None)
    contact_number: str | None = Field(default=None)
    contact_email: str | None = Field(default=None)
    status: CustomerStatus | None = Field(
        default=None, description="Defaults to Active when omitted"
    )


class UpdateCustomerRequest(BaseModel):
    """Partial-update payload for a Customer.

    Every field is optional. Only fields explicitly present in the request are
    applied; omitted fields are left unchanged (Req 8 partial-update semantics).
    """

    model_config = ConfigDict(extra="forbid")

    customer_code: str | None = Field(default=None)
    customer_name: str | None = Field(default=None)
    address: str | None = Field(default=None)
    gstn_number: str | None = Field(default=None)
    contact_person: str | None = Field(default=None)
    contact_number: str | None = Field(default=None)
    contact_email: str | None = Field(default=None)
    status: CustomerStatus | None = Field(default=None)
