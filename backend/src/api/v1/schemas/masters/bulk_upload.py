"""
Bulk-upload API response schemas.

Pydantic v2 envelopes that adapt the Pydantic-agnostic
:class:`~src.application.services.masters.bulk_upload_service.BulkUploadReport`
(and its :class:`BulkRowError` rows) to the HTTP boundary. The service returns
plain dataclasses; the controller converts them with
:meth:`BulkUploadReportResponse.from_report` so the accounting invariant
``received == stored + skipped`` and the positional row errors (Req 19.6) are
surfaced verbatim in the response.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.application.services.masters.bulk_upload_service import (
    BulkRowError,
    BulkUploadReport,
)


class BulkRowErrorResponse(BaseModel):
    """A single skipped-row error, naming the 1-based row position and reason."""

    row_number: int = Field(
        ..., description="1-based position of the skipped data row in the file."
    )
    reason: str = Field(..., description="Why the row was skipped.")

    @classmethod
    def from_error(cls, error: BulkRowError) -> "BulkRowErrorResponse":
        """Adapt a service :class:`BulkRowError` to the response schema."""
        return cls(row_number=error.row_number, reason=error.reason)


class BulkUploadReportResponse(BaseModel):
    """Per-row accounting for a bulk-upload request (Req 19.6).

    ``received == stored + skipped`` always holds, and there is exactly one
    :class:`BulkRowErrorResponse` per skipped row.
    """

    received: int = Field(..., description="Total data rows read from the file.")
    stored: int = Field(..., description="Rows successfully stored.")
    skipped: int = Field(..., description="Rows skipped due to a row-level error.")
    errors: list[BulkRowErrorResponse] = Field(
        default_factory=list,
        description="One entry per skipped row, in file order.",
    )

    @classmethod
    def from_report(cls, report: BulkUploadReport) -> "BulkUploadReportResponse":
        """Adapt a service :class:`BulkUploadReport` to the response schema."""
        return cls(
            received=report.received,
            stored=report.stored,
            skipped=report.skipped,
            errors=[
                BulkRowErrorResponse.from_error(error) for error in report.errors
            ],
        )
