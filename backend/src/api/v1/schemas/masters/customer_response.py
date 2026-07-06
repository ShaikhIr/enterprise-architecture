"""
Customer Master response schemas (Pydantic v2).

Maps the :class:`CustomerEntity` domain object to the API representation,
exposing the persisted fields plus the standard audit fields.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from src.domain.entities.masters.customer import CustomerEntity


class CustomerResponse(BaseModel):
    """API representation of a Customer record."""

    id: UUID
    customer_code: str
    customer_name: str
    address: str | None = None
    gstn_number: str | None = None
    contact_person: str | None = None
    contact_number: str | None = None
    contact_email: str | None = None
    status: str
    created_by: str
    created_date: datetime
    modified_by: str
    modified_date: datetime

    @classmethod
    def from_entity(cls, entity: CustomerEntity) -> "CustomerResponse":
        """Build a response DTO from a domain entity."""
        return cls(
            id=entity.id,
            customer_code=entity.customer_code,
            customer_name=entity.customer_name,
            address=entity.address,
            gstn_number=entity.gstn_number,
            contact_person=entity.contact_person,
            contact_number=entity.contact_number,
            contact_email=entity.contact_email,
            status=entity.status.value,
            created_by=entity.created_by,
            created_date=entity.created_date,
            modified_by=entity.modified_by,
            modified_date=entity.modified_date,
        )
