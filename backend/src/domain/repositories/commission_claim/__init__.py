"""
Commission Claim repository interfaces (Ports).

This package exposes:

- IClaimHeaderRepository  — ClaimHeader persistence + ClaimFilterParams value object
- IClaimLineRepository    — ClaimLine persistence + ClaimTotals value object
- IClaimAuditRepository   — append-only audit entry persistence

All three interfaces are abstract base classes that the infrastructure layer
implements; no concrete code lives here.
"""

from src.domain.repositories.commission_claim.claim_audit_repository import (
    IClaimAuditRepository,
)
from src.domain.repositories.commission_claim.claim_header_repository import (
    ClaimFilterParams,
    IClaimHeaderRepository,
)
from src.domain.repositories.commission_claim.claim_line_repository import (
    ClaimTotals,
    IClaimLineRepository,
)

__all__ = [
    "IClaimHeaderRepository",
    "IClaimLineRepository",
    "IClaimAuditRepository",
    "ClaimTotals",
    "ClaimFilterParams",
]
