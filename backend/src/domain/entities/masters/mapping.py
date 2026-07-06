"""
Vendor-Customer Mapping domain entity.

Represents a time-bounded association between a Vendor and a Customer. Inherits
identity and audit fields from ``BaseEntity``.
"""

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID, uuid4

from src.domain.entities.base_entity import BaseEntity
from src.domain.enums.masters import MappingStatus


@dataclass
class MappingEntity(BaseEntity):
    """
    Vendor-Customer Mapping aggregate root.

    Business Rules:
    - Vendor and Customer must both exist (enforced at the service level).
    - ``validity_from`` must be on or before ``validity_to`` (enforced at the
      service level).
    - Active mappings for the same Vendor + Customer must not have overlapping
      validity periods (enforced at the repository/service level).
    - New mappings default to ``Active``.
    - A mapping whose ``validity_to`` has passed is moved to ``Expired``.
    """

    vendor_id: UUID = field(default_factory=uuid4)
    customer_id: UUID = field(default_factory=uuid4)
    validity_from: date = field(default_factory=date.today)
    validity_to: date = field(default_factory=date.today)
    status: MappingStatus = field(default=MappingStatus.Active)

    def expire(self, modified_by: str) -> None:
        """Mark the mapping expired."""
        self.status = MappingStatus.Expired
        self.mark_modified(modified_by)

    def activate(self, modified_by: str) -> None:
        """Mark the mapping active."""
        self.status = MappingStatus.Active
        self.mark_modified(modified_by)
