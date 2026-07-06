"""
Claim-validation request schema (Pydantic v2).

A claim submission asks the Claim Validation Triangle to evaluate one or more
Invoice Lines for commission-claim eligibility. The request is a thin DTO
carrying the referenced Invoice Line ids; all evaluation logic lives in
``ClaimValidationService``.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ValidateClaimRequest(BaseModel):
    """Payload for validating a set of Invoice Lines against the triangle.

    ``invoice_line_ids`` lists the Invoice Lines submitted in the claim. Order is
    preserved in the response and duplicate ids are evaluated once each (the
    service returns one result per supplied id). At least one id is required; an
    unknown id is rejected with a not-found error by the service.
    """

    model_config = ConfigDict(extra="forbid")

    invoice_line_ids: list[UUID] = Field(
        ...,
        min_length=1,
        description="Invoice Line ids to evaluate (at least one required)",
    )
