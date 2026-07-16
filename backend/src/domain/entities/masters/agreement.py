"""
Agreement domain entity.

An Agreement defines a vendor's commission entitlement for a specific Product
Detail over a validity period. It carries the commission-slab parameters used by
the commission engine and supports renewal (an Agreement may reference a prior
Agreement it replaces). Inherits identity and audit fields from ``BaseEntity``.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from src.domain.entities.base_entity import BaseEntity
from src.domain.enums.masters import AgreementStatus, AgreementType


@dataclass
class AgreementEntity(BaseEntity):
    """
    Agreement Master aggregate root.

    Business Rules:
    - Must reference an existing Vendor and Product Detail (enforced at the
      service level).
    - From Date must be on or before To Date; Min Commission % must not exceed
      Max Commission %; Reduction/Max/Min percentages must lie within 0-100;
      Slab in Days must be greater than 0; Credit Days must be 0 or greater
      (all enforced at the service level).
    - An active Agreement's validity period must not overlap another active
      Agreement for the same Vendor and Product Detail (inclusive overlap,
      enforced via the repository overlap query and the service).
    - New agreements default to Agreement Type ``Original`` and Status
      ``Active``.
    - A renewal Agreement references the prior Agreement it replaces via
      ``prior_agreement_id``.
    """

    vendor_id: UUID | None = field(default=None)
    product_master_id: UUID | None = field(default=None)
    from_date: date | None = field(default=None)
    to_date: date | None = field(default=None)
    slab_in_days: int = field(default=0)
    reduction_percent: Decimal = field(default=Decimal("0"))
    max_commission_percent: Decimal = field(default=Decimal("0"))
    min_commission_percent: Decimal = field(default=Decimal("0"))
    credit_days: int = field(default=0)
    agreement_type: AgreementType = field(default=AgreementType.Original)
    prior_agreement_id: UUID | None = field(default=None)
    agreement_document_ref: str | None = field(default=None)
    status: AgreementStatus = field(default=AgreementStatus.Active)

    def mark_renewed(self, modified_by: str) -> None:
        """Mark this agreement as superseded by a renewal."""
        self.status = AgreementStatus.Renewed
        self.mark_modified(modified_by)

    def mark_expired(self, modified_by: str) -> None:
        """Mark this agreement as expired."""
        self.status = AgreementStatus.Expired
        self.mark_modified(modified_by)
