"""
Vendor (liaisoning agent) domain entity.

Represents an external service vendor that procures orders and raises commission
claims. Inherits identity and audit fields from ``BaseEntity``.
"""

from dataclasses import dataclass, field
from uuid import UUID

from src.domain.entities.base_entity import BaseEntity
from src.domain.enums.masters import VendorStatus


@dataclass
class VendorEntity(BaseEntity):
    """
    Vendor Master aggregate root.

    Business Rules:
    - Vendor Code, Vendor Name, and Vendor Email are required (enforced at the
      service level).
    - Vendor Code and Vendor Email must each be unique across vendors (enforced
      at the repository level).
    - A portal-login user is provisioned for each vendor; ``portal_user_id``
      references that user.
    - New vendors default to ``Active``.
    """

    vendor_code: str = field(default="")
    vendor_name: str = field(default="")
    vendor_email: str = field(default="")
    vendor_contact: str | None = field(default=None)
    vendor_address: str | None = field(default=None)
    city: str | None = field(default=None)
    gstn_number: str | None = field(default=None)
    pan_number: str | None = field(default=None)
    bank_account_no: str | None = field(default=None)
    bank_ifsc: str | None = field(default=None)
    bank_name: str | None = field(default=None)
    portal_user_id: UUID | None = field(default=None)
    status: VendorStatus = field(default=VendorStatus.Active)

    def deactivate(self, modified_by: str) -> None:
        """Mark the vendor inactive."""
        self.status = VendorStatus.Inactive
        self.mark_modified(modified_by)

    def activate(self, modified_by: str) -> None:
        """Mark the vendor active."""
        self.status = VendorStatus.Active
        self.mark_modified(modified_by)
