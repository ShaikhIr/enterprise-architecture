"""
Claim-validation response schemas (Pydantic v2).

Adapt the Pydantic-agnostic results returned by ``ClaimValidationService``
(:class:`~src.application.services.masters.claim_validation_service.LineValidationResult`
/ ``LineValidationError`` dataclasses) into the API representation.

Each line carries its eligibility outcome (``allowed``) plus one distinct error
per failed triangle check (Req 18.6). Valid and blocked lines coexist in a
single response without rejecting the whole claim (Req 18.5).
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from src.application.services.masters.claim_validation_service import (
    LineValidationError as LineValidationErrorDTO,
    LineValidationResult as LineValidationResultDTO,
)


class LineValidationError(BaseModel):
    """API representation of a single failed-check error for one invoice line."""

    invoice_line_id: UUID
    code: str
    message: str

    @classmethod
    def from_result(cls, error: LineValidationErrorDTO) -> "LineValidationError":
        """Build a response DTO from a service ``LineValidationError`` dataclass."""
        return cls(
            invoice_line_id=error.invoice_line_id,
            code=error.code,
            message=error.message,
        )


class LineValidationResult(BaseModel):
    """API representation of the eligibility outcome for one invoice line.

    ``allowed`` is ``True`` only when ``errors`` is empty, i.e. all three
    triangle checks passed (Req 18.4).
    """

    invoice_line_id: UUID
    allowed: bool
    errors: list[LineValidationError]

    @classmethod
    def from_result(cls, result: LineValidationResultDTO) -> "LineValidationResult":
        """Build a response DTO from a service ``LineValidationResult`` dataclass."""
        return cls(
            invoice_line_id=result.invoice_line_id,
            allowed=result.allowed,
            errors=[
                LineValidationError.from_result(error) for error in result.errors
            ],
        )
