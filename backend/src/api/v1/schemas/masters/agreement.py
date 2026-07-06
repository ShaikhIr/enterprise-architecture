"""
Pydantic v2 request/response schemas for the Agreement Master.

These schemas form the API boundary for Agreement CRUD and renewal. They are
intentionally thin data carriers: the authoritative business validation
(reference existence, From ≤ To, Min ≤ Max, percentage ranges, Slab/Credit
bounds, document type/size, overlap rejection, status/type defaulting) lives in
:class:`AgreementService`. The controller adapts these schemas to the service's
primitive input dataclasses and back to :class:`AgreementResponse`.

Multipart upload
----------------
An Agreement may carry an Agreement Document (PDF/JPEG/PNG, ≤ 10 MB — Req 11.9).
Because the create/update/renew endpoints accept that file alongside the
structured fields, the request bodies are submitted as ``multipart/form-data``.
Each request schema therefore exposes an :meth:`as_form` classmethod that FastAPI
uses as a dependency to bind the individual form fields; the uploaded file is
bound separately as an ``UploadFile`` parameter on the route.

Partial-update semantics: every field on :class:`AgreementUpdateRequest` is
optional. A field omitted from the form arrives as ``None`` and is treated by
the controller as "not supplied" (mapped to the service ``UNSET`` sentinel), so
unsupplied fields are left unchanged. None of the Agreement scalar fields are
nullable, so there is no "explicit null" case to distinguish.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import Form
from pydantic import BaseModel, ConfigDict

from src.domain.entities.masters.agreement import AgreementEntity
from src.domain.enums.masters import AgreementStatus, AgreementType


class AgreementCreateRequest(BaseModel):
    """Request body for creating an Agreement (``multipart/form-data``).

    ``slab_in_days``, the percentages, and ``credit_days`` are optional; when
    omitted the service applies its defaults before field validation (Req 11.8).
    The Agreement Document file is bound separately on the route.
    """

    vendor_id: UUID
    product_detail_id: UUID
    from_date: date
    to_date: date
    slab_in_days: int | None = None
    reduction_percent: Decimal | None = None
    max_commission_percent: Decimal | None = None
    min_commission_percent: Decimal | None = None
    credit_days: int | None = None

    @classmethod
    def as_form(
        cls,
        vendor_id: UUID = Form(...),
        product_detail_id: UUID = Form(...),
        from_date: date = Form(...),
        to_date: date = Form(...),
        slab_in_days: int | None = Form(default=None),
        reduction_percent: Decimal | None = Form(default=None),
        max_commission_percent: Decimal | None = Form(default=None),
        min_commission_percent: Decimal | None = Form(default=None),
        credit_days: int | None = Form(default=None),
    ) -> "AgreementCreateRequest":
        """Bind ``multipart/form-data`` fields into an create request."""
        return cls(
            vendor_id=vendor_id,
            product_detail_id=product_detail_id,
            from_date=from_date,
            to_date=to_date,
            slab_in_days=slab_in_days,
            reduction_percent=reduction_percent,
            max_commission_percent=max_commission_percent,
            min_commission_percent=min_commission_percent,
            credit_days=credit_days,
        )


class AgreementUpdateRequest(BaseModel):
    """Request body for partially updating an Agreement (``multipart/form-data``).

    Every field is optional. Fields omitted from the form arrive as ``None`` and
    are treated by the controller as "not supplied" (left unchanged). A newly
    uploaded document replaces the stored reference; omitting the file leaves the
    existing document untouched.
    """

    vendor_id: UUID | None = None
    product_detail_id: UUID | None = None
    from_date: date | None = None
    to_date: date | None = None
    slab_in_days: int | None = None
    reduction_percent: Decimal | None = None
    max_commission_percent: Decimal | None = None
    min_commission_percent: Decimal | None = None
    credit_days: int | None = None

    @classmethod
    def as_form(
        cls,
        vendor_id: UUID | None = Form(default=None),
        product_detail_id: UUID | None = Form(default=None),
        from_date: date | None = Form(default=None),
        to_date: date | None = Form(default=None),
        slab_in_days: int | None = Form(default=None),
        reduction_percent: Decimal | None = Form(default=None),
        max_commission_percent: Decimal | None = Form(default=None),
        min_commission_percent: Decimal | None = Form(default=None),
        credit_days: int | None = Form(default=None),
    ) -> "AgreementUpdateRequest":
        """Bind ``multipart/form-data`` fields into an update request."""
        return cls(
            vendor_id=vendor_id,
            product_detail_id=product_detail_id,
            from_date=from_date,
            to_date=to_date,
            slab_in_days=slab_in_days,
            reduction_percent=reduction_percent,
            max_commission_percent=max_commission_percent,
            min_commission_percent=min_commission_percent,
            credit_days=credit_days,
        )


class AgreementRenewRequest(BaseModel):
    """Request body for renewing an Agreement (``multipart/form-data``).

    ``vendor_id`` / ``product_detail_id`` are optional; when omitted the service
    inherits them from the prior Agreement. The renewal period (From/To) is
    required and the renewal record is validated like a create.
    """

    from_date: date
    to_date: date
    vendor_id: UUID | None = None
    product_detail_id: UUID | None = None
    slab_in_days: int | None = None
    reduction_percent: Decimal | None = None
    max_commission_percent: Decimal | None = None
    min_commission_percent: Decimal | None = None
    credit_days: int | None = None

    @classmethod
    def as_form(
        cls,
        from_date: date = Form(...),
        to_date: date = Form(...),
        vendor_id: UUID | None = Form(default=None),
        product_detail_id: UUID | None = Form(default=None),
        slab_in_days: int | None = Form(default=None),
        reduction_percent: Decimal | None = Form(default=None),
        max_commission_percent: Decimal | None = Form(default=None),
        min_commission_percent: Decimal | None = Form(default=None),
        credit_days: int | None = Form(default=None),
    ) -> "AgreementRenewRequest":
        """Bind ``multipart/form-data`` fields into a renewal request."""
        return cls(
            from_date=from_date,
            to_date=to_date,
            vendor_id=vendor_id,
            product_detail_id=product_detail_id,
            slab_in_days=slab_in_days,
            reduction_percent=reduction_percent,
            max_commission_percent=max_commission_percent,
            min_commission_percent=min_commission_percent,
            credit_days=credit_days,
        )


class AgreementResponse(BaseModel):
    """Response body representing an Agreement."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vendor_id: UUID | None
    vendor_name: str | None = None
    product_detail_id: UUID | None
    product_detail_child_code: str | None = None
    product_detail_name: str | None = None
    from_date: date | None
    to_date: date | None
    slab_in_days: int
    reduction_percent: Decimal
    max_commission_percent: Decimal
    min_commission_percent: Decimal
    credit_days: int
    agreement_type: AgreementType
    prior_agreement_id: UUID | None
    agreement_document_ref: str | None
    status: AgreementStatus
    created_by: str
    created_date: datetime
    modified_by: str
    modified_date: datetime

    @classmethod
    def from_entity(
        cls,
        entity: AgreementEntity,
        vendor_name: str | None = None,
        product_detail_child_code: str | None = None,
        product_detail_name: str | None = None,
    ) -> "AgreementResponse":
        """Build a response from a domain :class:`AgreementEntity`."""
        obj = cls.model_validate(entity)
        obj.vendor_name = vendor_name
        obj.product_detail_child_code = product_detail_child_code
        obj.product_detail_name = product_detail_name
        return obj
