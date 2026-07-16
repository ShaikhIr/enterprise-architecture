"""
Invoice Master application service.

Orchestrates the Invoice aggregate (Header + Lines): atomic creation with
reference validation, partial header update, paginated listing, cascade delete,
and the SAP-payment / final-approval status lifecycle. Persistence is delegated
to ``IInvoiceRepository``; reference-existence checks use the Vendor, Customer,
Product, and Agreement repositories.

Design notes / decoupling
--------------------------
The design's service contract is expressed in terms of API response schemas
(``InvoiceResponse``, ``PaginatedResponse``). Those schema/controller files are
owned by a sibling task (12.3), so to avoid coupling this service to schemas
that may still be in flux, the service is **Pydantic-agnostic**:

* methods accept lightweight input dataclasses defined in this module
  (:class:`InvoiceLineInput`, :class:`InvoiceCreateInput`,
  :class:`InvoiceUpdateInput`, :class:`SapPaymentInput`);
* create/read/update/lifecycle methods return the :class:`InvoiceHeaderEntity`
  domain object (with its lines populated);
* ``list_invoices`` returns an ``(items, total)`` tuple.

The controller task adapts these to the API request/response schemas.

Partial updates use a dedicated ``UNSET`` sentinel so that "field not supplied"
is distinguished from "field explicitly set to null".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Final
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.domain.entities.masters.invoice import (
    InvoiceHeaderEntity,
    InvoiceLineEntity,
)
from src.domain.entities.user import User
from src.domain.enums.masters import InvoiceStatus
from src.domain.repositories.masters.agreement_repository import (
    IAgreementRepository,
)
from src.domain.repositories.masters.customer_repository import ICustomerRepository
from src.domain.repositories.masters.invoice_repository import IInvoiceRepository
from src.domain.repositories.masters.product_repository import IProductRepository
from src.domain.repositories.masters.vendor_repository import IVendorRepository

# ─── Field length limits (per the data model) ───
_MAX_INVOICE_NUMBER_LEN: Final[int] = 50
_MAX_SAP_DOCUMENT_NO_LEN: Final[int] = 50


class _UnsetType:
    """Sentinel marking an update field that was not supplied at all.

    Distinct from ``None``, which represents an explicit request to clear a
    nullable field. Singleton: there is only ever one ``UNSET`` instance.
    """

    _instance: _UnsetType | None = None

    def __new__(cls) -> _UnsetType:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return "UNSET"

    def __bool__(self) -> bool:  # pragma: no cover - guard against truthiness use
        return False


UNSET: Final[_UnsetType] = _UnsetType()


@dataclass(frozen=True)
class InvoiceLineInput:
    """Payload for a single Invoice Line on a create request.

    ``quantity``, ``line_amount`` and ``vat_gst_amount`` are optional; when
    supplied they must be non-negative.
    """

    product_master_id: UUID
    quantity: Decimal | None = None
    line_amount: Decimal | None = None
    vat_gst_amount: Decimal | None = None


@dataclass(frozen=True)
class InvoiceCreateInput:
    """Validated-on-the-way-in payload for creating an Invoice.

    ``amount_deducted`` and ``tds_value`` default to ``None`` so the service can
    apply the ``0`` default (Req 16.5) when omitted. ``due_date`` of ``None``
    means "not supplied" — the service then computes it from an applicable
    Agreement or leaves it unset (Req 16.6–16.8).
    """

    invoice_number: str
    invoice_date: date
    vendor_id: UUID
    customer_id: UUID
    bill_amount_excl_gst: Decimal
    entity_id: UUID | None = None
    lines: list[InvoiceLineInput] = field(default_factory=list)
    bill_amount_incl_tax: Decimal | None = None
    amount_deducted: Decimal | None = None
    tds_value: Decimal | None = None
    due_date: date | None = None


@dataclass(frozen=True)
class InvoiceUpdateInput:
    """Partial-update payload for an Invoice Header's own fields.

    Each field defaults to :data:`UNSET`; only supplied fields are applied. A
    supplied ``due_date`` replaces the stored value (Req 16.7). Line membership
    is not updated here (lines are part of the create aggregate).
    """

    bill_amount_excl_gst: Decimal | _UnsetType = UNSET
    bill_amount_incl_tax: Decimal | None | _UnsetType = UNSET
    amount_deducted: Decimal | _UnsetType = UNSET
    tds_value: Decimal | _UnsetType = UNSET
    due_date: date | None | _UnsetType = UNSET


@dataclass(frozen=True)
class SapPaymentInput:
    """Payload for an SAP payment confirmation.

    The target Invoice Header may be addressed by ``invoice_id`` or
    ``invoice_number`` (at least one must be supplied). An unknown reference is
    rejected with a not-found error (Req 17.4).
    """

    payment_clearing_date: date
    sap_clearing_document_no: str
    invoice_id: UUID | None = None
    invoice_number: str | None = None


class InvoiceService:
    """Application service for Invoice Master (Header + Line) management."""

    def __init__(
        self,
        session: AsyncSession,
        invoice_repo: IInvoiceRepository,
        vendor_repo: IVendorRepository,
        customer_repo: ICustomerRepository,
        product_repo: IProductRepository,
        agreement_repo: IAgreementRepository,
    ) -> None:
        self._session = session
        self._invoice_repo = invoice_repo
        self._vendor_repo = vendor_repo
        self._customer_repo = customer_repo
        self._product_repo = product_repo
        self._agreement_repo = agreement_repo

    # ─── Create ───

    async def create_invoice(
        self, data: InvoiceCreateInput, actor: User
    ) -> InvoiceHeaderEntity:
        """Validate and atomically persist an Invoice Header with its lines.

        Validates required fields, Invoice Number uniqueness (Req 16.2), and
        Vendor/Customer/Product-Detail existence (Req 16.3, 16.4) *before* any
        write, so a rejected request persists nothing. Defaults Amount Deducted
        and TDS Value to 0 and Status to ``Open`` (Req 16.5). Resolves the Due
        Date from the supplied value, else an applicable Agreement's Credit Days
        (Req 16.6), else leaves it unset (Req 16.8).
        """
        invoice_number = self._validate_invoice_number(data.invoice_number)
        invoice_date = self._validate_invoice_date(data.invoice_date)
        bill_amount_excl_gst = self._validate_amount(
            data.bill_amount_excl_gst, "bill_amount_excl_gst", required=True
        )
        bill_amount_incl_tax = self._validate_amount(
            data.bill_amount_incl_tax, "bill_amount_incl_tax", required=False
        )
        amount_deducted = self._validate_amount(
            data.amount_deducted, "amount_deducted", required=False
        )
        tds_value = self._validate_amount(
            data.tds_value, "tds_value", required=False
        )

        if not data.lines:
            raise MasterValidationError(
                "lines", "An invoice must have at least one invoice line"
            )
        for index, line in enumerate(data.lines):
            self._validate_line_amounts(line, index)

        # Reference existence — validated before any persist (Req 16.3, 16.4).
        if await self._vendor_repo.get_by_id(data.vendor_id) is None:
            raise MasterValidationError(
                "vendor_id", f"Vendor '{data.vendor_id}' does not exist"
            )
        if await self._customer_repo.get_by_id(data.customer_id) is None:
            raise MasterValidationError(
                "customer_id", f"Customer '{data.customer_id}' does not exist"
            )
        for index, line in enumerate(data.lines):
            if (
                await self._product_repo.get_by_id(line.product_master_id)
                is None
            ):
                raise MasterValidationError(
                    f"lines[{index}].product_master_id",
                    f"Product Detail '{line.product_master_id}' does not exist",
                )

        # Uniqueness — Invoice Number conflict (Req 16.2).
        if await self._invoice_repo.exists_by_invoice_number(invoice_number):
            raise MasterConflictError(
                f"Invoice Number '{invoice_number}' is already in use"
            )

        # Due Date resolution (Req 16.6–16.8).
        due_date = await self._resolve_due_date(
            supplied_due_date=data.due_date,
            vendor_id=data.vendor_id,
            invoice_date=invoice_date,
            line_inputs=data.lines,
        )

        header_id = uuid4()
        header = InvoiceHeaderEntity(
            id=header_id,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            vendor_id=data.vendor_id,
            customer_id=data.customer_id,
            entity_id=data.entity_id,
            bill_amount_excl_gst=bill_amount_excl_gst,
            bill_amount_incl_tax=bill_amount_incl_tax,
            amount_deducted=amount_deducted
            if amount_deducted is not None
            else Decimal("0"),
            tds_value=tds_value if tds_value is not None else Decimal("0"),
            due_date=due_date,
            invoice_status=InvoiceStatus.Open,
            created_by=actor.username,
            modified_by=actor.username,
        )
        lines = [
            InvoiceLineEntity(
                id=uuid4(),
                invoice_header_id=header_id,
                product_master_id=line.product_master_id,
                quantity=line.quantity,
                line_amount=line.line_amount,
                vat_gst_amount=line.vat_gst_amount,
                created_by=actor.username,
                modified_by=actor.username,
            )
            for line in data.lines
        ]
        header.lines = lines
        return await self._invoice_repo.create(header, lines)

    # ─── Read ───

    async def get_invoice(self, invoice_id: UUID) -> InvoiceHeaderEntity:
        """Return an Invoice Header (with lines) by ID or raise not-found."""
        header = await self._invoice_repo.get_by_id(invoice_id)
        if header is None:
            raise MasterNotFoundError("Invoice Header", invoice_id)
        return header

    # ─── Update (partial header) ───

    async def update_invoice(
        self, invoice_id: UUID, patch: InvoiceUpdateInput, actor: User
    ) -> InvoiceHeaderEntity:
        """Apply a partial update to an existing Invoice Header.

        Only supplied fields change; a supplied Due Date replaces the stored
        value (Req 16.7). Unknown ID → not-found (Req 17.4).
        """
        header = await self._invoice_repo.get_by_id(invoice_id)
        if header is None:
            raise MasterNotFoundError("Invoice Header", invoice_id)

        if not isinstance(patch.bill_amount_excl_gst, _UnsetType):
            header.bill_amount_excl_gst = self._validate_amount(
                patch.bill_amount_excl_gst,
                "bill_amount_excl_gst",
                required=True,
            )

        if not isinstance(patch.bill_amount_incl_tax, _UnsetType):
            header.bill_amount_incl_tax = self._validate_amount(
                patch.bill_amount_incl_tax,
                "bill_amount_incl_tax",
                required=False,
            )

        if not isinstance(patch.amount_deducted, _UnsetType):
            validated = self._validate_amount(
                patch.amount_deducted, "amount_deducted", required=True
            )
            header.amount_deducted = validated

        if not isinstance(patch.tds_value, _UnsetType):
            validated = self._validate_amount(
                patch.tds_value, "tds_value", required=True
            )
            header.tds_value = validated

        if not isinstance(patch.due_date, _UnsetType):
            header.due_date = patch.due_date

        header.mark_modified(actor.username)
        return await self._invoice_repo.update(header)

    # ─── List (pagination) ───

    async def list_invoices(
        self,
        skip: int = 0,
        limit: int = 20,
        invoice_number: str | None = None,
        vendor_name: str | None = None,
        customer_name: str | None = None,
        invoice_status: str | None = None,
        vendor_id: str | None = None,
        entity_id: str | None = None,
    ) -> tuple[list[tuple[InvoiceHeaderEntity, str | None, str | None]], int]:
        """Return a filtered page of Invoice Headers with vendor/customer names."""
        items = await self._invoice_repo.list_with_names(
            skip=skip, limit=limit,
            invoice_number=invoice_number,
            vendor_name=vendor_name,
            customer_name=customer_name,
            invoice_status=invoice_status,
            vendor_id=vendor_id,
            entity_id=entity_id,
        )
        total = await self._invoice_repo.count_filtered(
            invoice_number=invoice_number,
            vendor_name=vendor_name,
            customer_name=customer_name,
            invoice_status=invoice_status,
            vendor_id=vendor_id,
            entity_id=entity_id,
        )
        return items, total

    # ─── Delete (cascade lines) ───

    async def delete_invoice(self, invoice_id: UUID, actor: User) -> None:
        """Delete an Invoice Header, cascading to its lines (Req 16.9).

        Unknown ID → not-found (Req 17.4). Deletion of the header removes its
        Invoice Lines via the ``ON DELETE CASCADE`` foreign key.
        """
        if not await self._invoice_repo.exists_by_id(invoice_id):
            raise MasterNotFoundError("Invoice Header", invoice_id)
        await self._invoice_repo.delete(invoice_id)

    # ─── Status lifecycle ───

    async def record_sap_payment(
        self, data: SapPaymentInput, actor: User
    ) -> InvoiceHeaderEntity:
        """Record an SAP payment confirmation against an Invoice Header.

        Sets the Payment Clearing Date and SAP Clearing Document No to the
        supplied values and the Status to ``Payment Cleared`` (Req 17.1). An
        unknown Invoice Number / Invoice Header is rejected with a not-found
        error and nothing is modified (Req 17.4).
        """
        if data.invoice_id is None and not data.invoice_number:
            raise MasterValidationError(
                "invoice_id",
                "An invoice id or invoice number is required to record payment",
            )

        sap_document_no = self._validate_sap_document_no(
            data.sap_clearing_document_no
        )
        if data.payment_clearing_date is None:
            raise MasterValidationError(
                "payment_clearing_date", "Payment Clearing Date is required"
            )

        header = await self._resolve_header(data.invoice_id, data.invoice_number)
        if header is None:
            reference = data.invoice_id or data.invoice_number
            raise MasterNotFoundError("Invoice Header", reference)

        header.payment_clearing_date = data.payment_clearing_date
        header.sap_clearing_document_no = sap_document_no
        header.invoice_status = InvoiceStatus.PaymentCleared
        header.mark_modified(actor.username)
        return await self._invoice_repo.update(header)

    async def mark_settled(
        self, invoice_id: UUID, actor: User
    ) -> InvoiceHeaderEntity:
        """Mark an Invoice Header ``Settled`` on final claim approval (Req 17.2).

        Unknown ID → not-found (Req 17.4).
        """
        header = await self._invoice_repo.get_by_id(invoice_id)
        if header is None:
            raise MasterNotFoundError("Invoice Header", invoice_id)

        header.invoice_status = InvoiceStatus.Settled
        header.mark_modified(actor.username)
        return await self._invoice_repo.update(header)

    # ─── Internal helpers ───

    async def _resolve_header(
        self, invoice_id: UUID | None, invoice_number: str | None
    ) -> InvoiceHeaderEntity | None:
        """Resolve an Invoice Header by ID (preferred) or Invoice Number."""
        if invoice_id is not None:
            return await self._invoice_repo.get_by_id(invoice_id)
        if invoice_number:
            return await self._invoice_repo.get_by_invoice_number(invoice_number)
        return None

    async def _resolve_due_date(
        self,
        supplied_due_date: date | None,
        vendor_id: UUID,
        invoice_date: date,
        line_inputs: list[InvoiceLineInput],
    ) -> date | None:
        """Resolve the Due Date per Req 16.6–16.8.

        * A supplied Due Date is used as-is (Req 16.7).
        * Otherwise, the first active Agreement for the Vendor and one of the
          invoice's Product Details whose validity period covers the Invoice
          Date yields ``Invoice Date + Credit Days`` (Req 16.6).
        * Otherwise the Due Date is left unset (Req 16.8).
        """
        if supplied_due_date is not None:
            return supplied_due_date

        seen: set[UUID] = set()
        for line in line_inputs:
            product_master_id = line.product_master_id
            if product_master_id in seen:
                continue
            seen.add(product_master_id)
            agreements = await self._agreement_repo.find_overlapping_active(
                vendor_id=vendor_id,
                product_master_id=product_master_id,
                from_date=invoice_date,
                to_date=invoice_date,
            )
            if agreements:
                credit_days = agreements[0].credit_days
                return invoice_date + timedelta(days=credit_days)

        return None

    @staticmethod
    def _validate_invoice_number(invoice_number: object) -> str:
        """Invoice Number: required, non-empty/whitespace, ≤ 50 chars (Req 16.2)."""
        if not isinstance(invoice_number, str) or invoice_number.strip() == "":
            raise MasterValidationError(
                "invoice_number",
                "Invoice Number is required and must not be empty",
            )
        if len(invoice_number) > _MAX_INVOICE_NUMBER_LEN:
            raise MasterValidationError(
                "invoice_number",
                f"Invoice Number must not exceed {_MAX_INVOICE_NUMBER_LEN} characters",
            )
        return invoice_number

    @staticmethod
    def _validate_invoice_date(invoice_date: object) -> date:
        """Invoice Date: required and a valid ``date``."""
        if not isinstance(invoice_date, date):
            raise MasterValidationError(
                "invoice_date", "Invoice Date is required"
            )
        return invoice_date

    @staticmethod
    def _validate_amount(
        amount: Decimal | None, field_name: str, *, required: bool
    ) -> Decimal | None:
        """Validate a monetary amount: present-if-required and non-negative."""
        if amount is None:
            if required:
                raise MasterValidationError(
                    field_name, f"{field_name} is required"
                )
            return None
        if not isinstance(amount, Decimal):
            raise MasterValidationError(
                field_name, f"{field_name} must be a numeric amount"
            )
        if amount < Decimal("0"):
            raise MasterValidationError(
                field_name, f"{field_name} must not be negative"
            )
        return amount

    @staticmethod
    def _validate_line_amounts(line: InvoiceLineInput, index: int) -> None:
        """Validate an invoice line's optional quantity/amounts are non-negative."""
        for attr in ("quantity", "line_amount", "vat_gst_amount"):
            value = getattr(line, attr)
            if value is None:
                continue
            if not isinstance(value, Decimal):
                raise MasterValidationError(
                    f"lines[{index}].{attr}",
                    f"{attr} must be a numeric amount",
                )
            if value < Decimal("0"):
                raise MasterValidationError(
                    f"lines[{index}].{attr}",
                    f"{attr} must not be negative",
                )

    @staticmethod
    def _validate_sap_document_no(sap_document_no: object) -> str:
        """SAP Clearing Document No: required, non-empty, ≤ 50 chars (Req 17.1)."""
        if not isinstance(sap_document_no, str) or sap_document_no.strip() == "":
            raise MasterValidationError(
                "sap_clearing_document_no",
                "SAP Clearing Document No is required and must not be empty",
            )
        if len(sap_document_no) > _MAX_SAP_DOCUMENT_NO_LEN:
            raise MasterValidationError(
                "sap_clearing_document_no",
                f"SAP Clearing Document No must not exceed "
                f"{_MAX_SAP_DOCUMENT_NO_LEN} characters",
            )
        return sap_document_no
