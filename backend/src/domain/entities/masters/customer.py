"""
Customer (serviced/invoiced institution) domain entity.

Represents a government body, hospital, pharmacy, or institution serviced and
invoiced by a vendor. Inherits identity and audit fields from ``BaseEntity``.
"""

from dataclasses import dataclass, field

from src.domain.entities.base_entity import BaseEntity
from src.domain.enums.masters import CustomerStatus


@dataclass
class CustomerEntity(BaseEntity):
    """
    Customer Master aggregate root.

    Business Rules:
    - Customer Code and Customer Name are required (validated at service level).
    - Customer Code must be unique (enforced at repository/DB level).
    - GSTN Number, when supplied, must match the pattern ``[A-Z0-9]{15}``.
    - New customers default to ``Active`` status.
    - A Customer cannot be deleted while referenced by an active
      Vendor-Customer Mapping or any Invoice Header (enforced at service level
      using repository reference-existence checks).
    """

    customer_code: str = field(default="")
    customer_name: str = field(default="")
    address: str | None = field(default=None)
    gstn_number: str | None = field(default=None)
    contact_person: str | None = field(default=None)
    contact_number: str | None = field(default=None)
    contact_email: str | None = field(default=None)
    status: CustomerStatus = field(default=CustomerStatus.Active)
