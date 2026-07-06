"""
Vendor-Customer Mapping response schemas (Pydantic v2).

Maps the :class:`MappingEntity` domain object to the API representation,
exposing the persisted fields plus the standard audit fields.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

from src.domain.entities.masters.mapping import MappingEntity


class MappingResponse(BaseModel):
    """API representation of a Vendor-Customer Mapping record."""

    id: UUID
    vendor_id: UUID
    vendor_name: str | None = None
    customer_id: UUID
    customer_name: str | None = None
    validity_from: date
    validity_to: date
    status: str
    created_by: str
    created_date: datetime
    modified_by: str
    modified_date: datetime

    @classmethod
    def from_entity(
        cls,
        entity: MappingEntity,
        vendor_name: str | None = None,
        customer_name: str | None = None,
    ) -> "MappingResponse":
        """Build a response DTO from a domain entity."""
        return cls(
            id=entity.id,
            vendor_id=entity.vendor_id,
            vendor_name=vendor_name,
            customer_id=entity.customer_id,
            customer_name=customer_name,
            validity_from=entity.validity_from,
            validity_to=entity.validity_to,
            status=entity.status.value,
            created_by=entity.created_by,
            created_date=entity.created_date,
            modified_by=entity.modified_by,
            modified_date=entity.modified_date,
        )
